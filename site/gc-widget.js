// @ts-check
// <gc-widget>: one embedding of the simulator on a page. It reads its request
// from the JSON script inside it, asks the page's worker for both runs, and draws
// them as they stream in, as ADR 0008 lays them out: a row of figures, then a
// column per collector, each with the heap by space, work in bins and the work
// budget, on y-scales the two columns share. Above the figures it shows the
// controls its `controls` attribute names, and releasing one asks for both runs
// again.

// @ts-expect-error: an editor cannot fetch Plot's types from jsDelivr.
import * as Plot from "https://cdn.jsdelivr.net/npm/@observablehq/plot@0.6.17/+esm";
import { requestRuns } from "./runs.js";

/** @typedef {import("./runs.js").Record} Record */
/** @typedef {import("./runs.js").Figures} Figures */
/** @typedef {import("./runs.js").Control} Control */
/** @typedef {"legacy" | "incremental"} Collector */

/** @type {Collector[]} */
const COLLECTORS = ["legacy", "incremental"];
const TITLES = { legacy: "Legacy collector", incremental: "Incremental collector" };
// Each collector's spaces in the order its records hold them, and the order the
// heap panel stacks them in, the old generation at the bottom.
const SPACES = {
  legacy: ["nursery", "aging", "old"],
  incremental: ["nursery", "aging", "pending", "visited"],
};
const STACKED = {
  legacy: ["old", "aging", "nursery"],
  incremental: ["visited", "pending", "aging", "nursery"],
};
const PARTS = ["marked", "survived", "freed"];
// The fields of a record, by position.
const CLOCK = 0, MARKED = 2, WORK_TO_DO = 5;
const SPACES_BEFORE = 7, SPACES_AFTER = 8, REACHABLE_BEFORE = 9, REACHABLE_AFTER = 10;

// About this many bins of work a run, each a whole number of collection intervals.
const BINS = 40;
// Each y-scale grows to the next of these times a power of ten (ADR 0008).
const STEPS = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];
const HEIGHTS = { heap: 220, work: 160, budget: 130 };
const MARGINS = { marginLeft: 48, marginRight: 72, marginTop: 16, marginBottom: 32 };
// The tallest a bar of work grows, and the least a band of the heap needs for a label.
const BAR = 24, LABEL = 14;
// Counts of objects on an axis: 0, 500, 1K, 20K.
const compact = new Intl.NumberFormat("en", { notation: "compact" }).format;

// A figure's values. One with a fraction keeps one decimal, a 0 included, so
// that 6.0% stands beside 5.3%.
const whole = new Intl.NumberFormat("en", { maximumFractionDigits: 0 }).format;
const tenths = new Intl.NumberFormat("en", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format;
const percent = new Intl.NumberFormat("en", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 }).format;
/**
 * A count, whole below 10,000 and in thousands above, as 1,284 and 12.9K. Both
 * runs' counts take the form the larger needs, so that 16.1K stands beside 4.0K
 * rather than 4,000.
 * @param {number} value
 * @param {number[]} values
 */
const count = (value, values) => (values.some((n) => n >= 10_000) ? `${tenths(value / 1000)}K` : whole(value));

// The row of figures (ADR 0008): how each reads a run's figures so far, and how
// it shows a value beside the other run's.
/**
 * @type {{
 *   label: string,
 *   read: (figures: Figures, collector: Collector) => number | undefined,
 *   show: (value: number, values: number[]) => string,
 * }[]}
 */
const FIGURES = [
  { label: "Peak work", read: (figures) => figures[0], show: count },
  { label: "Peak uncollected garbage (MB)", read: (figures) => figures[1] / 1000, show: tenths },
  { label: "Work per MB", read: (figures) => figures[2], show: count },
  { label: "Yield", read: (figures) => figures[3], show: percent },
  { label: "Collections", read: (figures) => figures[4], show: count },
  { label: "Gen 2 collections / sweeps", read: (figures, collector) => figures[collector === "legacy" ? 6 : 5], show: count },
];

/** A control's value as the reader sees it: kB, or a share as a percentage. */
const reading = (/** @type {Control[2]} */ unit, /** @type {number} */ value) =>
  unit === "share" ? percent(value / 1000) : `${whole(value)} kB`;

/** A control's value as the request holds it: kB, or a share as a fraction. */
const held = (/** @type {Control[2]} */ unit, /** @type {number} */ value) =>
  unit === "share" ? `${value}/1000` : value;

/** Put a value into the request at a path of keys and indices joined by dots. */
function assign(/** @type {any} */ request, /** @type {string} */ path, /** @type {unknown} */ value) {
  const keys = path.split(".");
  const last = /** @type {string} */ (keys.pop());
  keys.reduce((object, key) => object[key], request)[last] = value;
}

/** The y-scale's end for data that reaches `value`, with room above it. */
function ceiling(/** @type {number} */ value) {
  const room = value * 1.05;
  if (room <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(room));
  return STEPS.map((step) => step * power).find((end) => end >= room) ?? 10 * power;
}

// The colors come from the dataviz skill's reference palette, assigned so that
// neighbors in each stack pass its validator in both modes.
const TEMPLATE = `
<style>
  :host {
    display: block;
    color-scheme: light;
    --surface: #fcfcfb;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --text-muted: #898781;
    --grid: #e1e0d9;
    --baseline: #c3c2b7;
    --nursery: #2a78d6;
    --aging: #eda100;
    --pending: #1baf7a;
    --visited: #eb6834;
    --old: #e87ba4;
    --marked: #008300;
    --survived: #6250d6;
    --freed: #e34948;
    padding: 16px;
    background: var(--surface);
    color: var(--text-primary);
    font: 14px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    :host {
      color-scheme: dark;
      --surface: #1a1a19;
      --text-primary: #f0efec;
      --text-secondary: #c3c2b7;
      --grid: #2c2c2a;
      --baseline: #383835;
      --nursery: #3987e5;
      --aging: #c98500;
      --pending: #199e70;
      --visited: #d95926;
      --old: #d55181;
      --survived: #9085e9;
      --freed: #e66767;
    }
  }
  .controls { display: flex; flex-wrap: wrap; gap: 12px 32px; margin: 0 0 24px; }
  .control { display: grid; gap: 4px; width: 200px; font-size: 13px; color: var(--text-secondary); }
  .control .name { display: flex; justify-content: space-between; gap: 8px; }
  .control output { color: var(--text-primary); font-weight: 600; font-variant-numeric: tabular-nums; }
  .control input { margin: 0; accent-color: var(--text-secondary); }
  .figures { display: grid; grid-template-columns: repeat(6, 1fr); gap: 4px 16px; margin: 0 0 24px; }
  .figure { display: grid; grid-row: span 2; grid-template-rows: subgrid; grid-template-columns: 1fr 1fr; column-gap: 8px; }
  .figure dt { grid-column: 1 / -1; align-self: end; font-size: 13px; color: var(--text-secondary); }
  .figure dd { margin: 0; display: flex; flex-direction: column; font-size: 12px; color: var(--text-secondary); }
  .figure .value { font-size: 22px; font-weight: 600; line-height: 1.25; color: var(--text-primary); }
  .columns { display: grid; grid-template-columns: 1fr 1fr; gap: 32px; }
  h2 { margin: 0 0 12px; font-size: 16px; font-weight: 600; }
  figure { margin: 0 0 16px; }
  figcaption { font-weight: 600; font-size: 13px; }
  .legend { display: flex; flex-wrap: wrap; gap: 2px 12px; margin: 4px 0; font-size: 12px; color: var(--text-secondary); }
  .key { display: inline-block; width: 10px; height: 10px; margin-right: 4px; border-radius: 2px; vertical-align: -1px; }
  .key.line { height: 2px; width: 14px; border-radius: 1px; vertical-align: 3px; }
  .none { margin: 8px 0 0; color: var(--text-secondary); font-size: 13px; }
  .error { color: var(--text-primary); }
</style>
<p class="error" hidden></p>
<div class="controls" hidden></div>
<dl class="figures"></dl>
<div class="columns">
  <section data-collector="legacy">
    <h2>Legacy collector</h2>
    <figure data-panel="heap"><figcaption>Heap by space</figcaption><div class="legend"></div><div class="chart"></div></figure>
    <figure data-panel="work"><figcaption></figcaption><div class="legend"></div><div class="chart"></div></figure>
    <figure data-panel="budget"><figcaption>Work budget</figcaption>
      <p class="none">The legacy collector keeps no work budget. A gen 2 collection takes the whole heap in one go.</p></figure>
  </section>
  <section data-collector="incremental">
    <h2>Incremental collector</h2>
    <figure data-panel="heap"><figcaption>Heap by space</figcaption><div class="legend"></div><div class="chart"></div></figure>
    <figure data-panel="work"><figcaption></figcaption><div class="legend"></div><div class="chart"></div></figure>
    <figure data-panel="budget"><figcaption>Work budget</figcaption><div class="chart"></div></figure>
  </section>
</div>`;

/** A legend entry: a swatch for a fill, a short stroke for a line. */
function key(/** @type {string} */ name, /** @type {string} */ color, line = false) {
  const entry = document.createElement("span");
  const swatch = document.createElement("span");
  swatch.className = line ? "key line" : "key";
  swatch.style.background = color;
  entry.append(swatch, name);
  return entry;
}

let widgets = 0;

class GcWidget extends HTMLElement {
  /** @type {{ legacy: Record[], incremental: Record[] }} */
  #records = { legacy: [], incremental: [] };
  /** @type {{ legacy?: Figures, incremental?: Figures }} */
  #figures = {};
  /** Where each figure shows each run's value. */
  /** @type {{ legacy: HTMLElement, incremental: HTMLElement }[]} */
  #values = [];
  /** The request as the controls have set it. */
  /** @type {any} */
  #request = null;
  /** The request whose records the charts show, until a newer one's first records arrive. */
  /** @type {any} */
  #drawn = null;
  #name = "";
  /** The paths into the request of the controls the page names. */
  /** @type {string[]} */
  #paths = [];
  /** Each control's slider, by path, and whether the reader is moving it. */
  /** @type {Map<string, { input: HTMLInputElement, read: (value: number) => void, moving: boolean }>} */
  #sliders = new Map();
  #frame = 0;

  connectedCallback() {
    if (this.shadowRoot) return;
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = TEMPLATE;
    try {
      this.#request = JSON.parse(this.querySelector('script[type="application/json"]')?.textContent ?? "");
    } catch (error) {
      this.#fail(`The widget's request is not JSON: ${error}`);
      return;
    }
    const row = /** @type {HTMLElement} */ (root.querySelector(".figures"));
    this.#values = FIGURES.map(({ label }) => {
      const figure = document.createElement("div");
      figure.className = "figure";
      const term = document.createElement("dt");
      term.textContent = label;
      figure.append(term);
      // Legacy beside incremental, as the columns below stand.
      const value = (/** @type {Collector} */ collector) => {
        const description = document.createElement("dd");
        const number = document.createElement("span");
        number.className = "value";
        number.textContent = "–";
        description.append(number, collector);
        figure.append(description);
        return number;
      };
      row.append(figure);
      return { legacy: value("legacy"), incremental: value("incremental") };
    });
    for (const collector of COLLECTORS) {
      const column = this.#column(collector);
      /** @type {HTMLElement} */ (column.querySelector('[data-panel="heap"] .legend')).append(
        ...SPACES[collector].map((space) => key(space, `var(--${space})`)),
        key("reachable", "var(--text-primary)", true),
      );
      /** @type {HTMLElement} */ (column.querySelector('[data-panel="work"] .legend')).append(
        ...PARTS.map((part) => key(part, `var(--${part})`)),
      );
    }
    this.#drawn = this.#request;
    this.#name = this.id || `gc-widget-${widgets++}`;
    this.#paths = (this.getAttribute("controls") ?? "").split(/\s+/).filter(Boolean);
    new ResizeObserver(() => this.#schedule()).observe(this);
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => this.#schedule());
    this.#start();
  }

  /**
   * Ask for both runs of the request as the controls have set it, in place of any
   * runs asked for before. The charts keep the old runs until the new runs' first
   * records arrive.
   */
  #start() {
    const request = structuredClone(this.#request);
    let fresh = true;
    /** @type {HTMLElement} */ (/** @type {ShadowRoot} */ (this.shadowRoot).querySelector(".error")).hidden = true;
    requestRuns(this.#name, request, {
      controls: (controls) => this.#show(controls),
      records: (collector, records, figures) => {
        if (fresh) {
          fresh = false;
          this.#drawn = request;
          this.#records = { legacy: [], incremental: [] };
          this.#figures = {};
        }
        this.#records[collector].push(...records);
        this.#figures[collector] = figures;
        this.#schedule();
      },
      done: () => {},
      error: (message) => this.#fail(message),
    }, this.#paths);
  }

  /** Show each control with the range its request allows. */
  #show(/** @type {Control[]} */ controls) {
    const row = /** @type {HTMLElement} */ (/** @type {ShadowRoot} */ (this.shadowRoot).querySelector(".controls"));
    row.hidden = !controls.length;
    for (const [path, label, unit, value, min, max, step] of controls) {
      let slider = this.#sliders.get(path);
      if (!slider) {
        const control = document.createElement("label");
        control.className = "control";
        const name = document.createElement("span");
        name.className = "name";
        const output = document.createElement("output");
        name.append(label, output);
        const input = document.createElement("input");
        input.type = "range";
        input.name = path;
        control.append(name, input);
        row.append(control);
        const made = {
          input,
          moving: false,
          read: (/** @type {number} */ value) => {
            output.textContent = reading(unit, value);
            input.setAttribute("aria-valuetext", output.textContent);
          },
        };
        // Moving a slider changes only the value it shows; releasing it asks for
        // both runs again.
        input.addEventListener("input", () => {
          made.moving = true;
          made.read(Number(input.value));
        });
        input.addEventListener("change", () => {
          made.moving = false;
          assign(this.#request, path, held(unit, Number(input.value)));
          this.#start();
        });
        slider = made;
        this.#sliders.set(path, slider);
      }
      // A release of another control can move this one's range. The value follows
      // the request, unless the reader is holding this slider.
      Object.assign(slider.input, { min: String(min), max: String(max), step: String(step) });
      if (!slider.moving) {
        slider.input.value = String(value);
        slider.read(value);
      }
    }
  }

  /** @param {Collector} collector */
  #column(collector) {
    return /** @type {HTMLElement} */ (
      /** @type {ShadowRoot} */ (this.shadowRoot).querySelector(`[data-collector="${collector}"]`)
    );
  }

  /** @param {string} message */
  #fail(message) {
    const error = /** @type {HTMLElement} */ (/** @type {ShadowRoot} */ (this.shadowRoot).querySelector(".error"));
    error.textContent = message;
    error.hidden = false;
  }

  // At most one redraw an animation frame, of whatever records have arrived.
  #schedule() {
    if (this.#frame) return;
    this.#frame = requestAnimationFrame(() => {
      this.#frame = 0;
      this.#draw();
    });
  }

  #draw() {
    FIGURES.forEach(({ read, show }, i) => {
      const values = COLLECTORS.map((collector) => {
        const figures = this.#figures[collector];
        return figures && read(figures, collector);
      });
      const known = values.filter((value) => value !== undefined);
      COLLECTORS.forEach((collector, j) => {
        const value = values[j];
        this.#values[i][collector].textContent = value === undefined ? "–" : show(value, known);
      });
    });

    const { run_length: runLength, settings: { threshold0 } } = this.#drawn;
    const style = getComputedStyle(this);
    const token = (/** @type {string} */ name) => style.getPropertyValue(`--${name}`).trim();
    const xMax = runLength / 1000;
    const width = this.#column("legacy").clientWidth;

    const heaps = { legacy: heap("legacy", this.#records.legacy), incremental: heap("incremental", this.#records.incremental) };
    const heapMax = ceiling(Math.max(...COLLECTORS.flatMap((c) => heaps[c].bands.map((band) => band.y2))));
    const binKb = Math.ceil(runLength / BINS / threshold0) * threshold0;
    const works = { legacy: work(this.#records.legacy, threshold0, binKb), incremental: work(this.#records.incremental, threshold0, binKb) };
    const workMax = ceiling(Math.max(0, ...COLLECTORS.flatMap((c) => works[c].map((segment) => segment.y2))));
    const budgets = this.#records.incremental.map((record) => ({ mb: record[CLOCK] / 1000, budget: record[WORK_TO_DO] }));
    const lowest = Math.min(0, ...budgets.map((d) => d.budget));
    const budgetDomain = [lowest < 0 ? -ceiling(-lowest) : 0, ceiling(Math.max(0, ...budgets.map((d) => d.budget)))];

    const frame = (/** @type {number} */ height) => ({
      width, height, ...MARGINS,
      style: { background: "transparent", color: token("text-muted"), fontFamily: "inherit", fontSize: "11px" },
      x: { domain: [0, xMax], label: "allocation clock (MB)" },
    });
    const gridY = Plot.gridY({ stroke: token("grid"), strokeOpacity: 1 });
    const inner = (/** @type {number} */ height) => height - MARGINS.marginTop - MARGINS.marginBottom;

    for (const collector of COLLECTORS) {
      const column = this.#column(collector);
      /** @type {HTMLElement} */ (column.querySelector('[data-panel="work"] figcaption')).textContent =
        `Work per ${binKb / 1000} MB allocated`;
      const { bands, points } = heaps[collector];
      const colors = { domain: STACKED[collector], range: STACKED[collector].map((space) => token(space)) };
      // Name each band at the run's edge where it is tall enough to hold its name.
      const last = bands.slice(-STACKED[collector].length);
      const labels = last.filter((band) => ((band.y2 - band.y1) / heapMax) * inner(HEIGHTS.heap) >= LABEL);
      chart(column, "heap", Plot.plot({
        ...frame(HEIGHTS.heap),
        ariaLabel: `${TITLES[collector]}: heap by space`,
        y: { domain: [0, heapMax], label: "heap (MB)" },
        color: colors,
        marks: [
          gridY,
          Plot.areaY(bands, { x: "mb", y1: "y1", y2: "y2", z: "space", fill: "space", fillOpacity: 0.1 }),
          Plot.lineY(bands, { x: "mb", y: "y2", z: "space", stroke: "space", strokeWidth: 2 }),
          Plot.lineY(points, { x: "mb", y: "reachable", stroke: token("text-primary"), strokeWidth: 2 }),
          Plot.text(labels, {
            x: "mb", y: (/** @type {{ y1: number, y2: number }} */ band) => (band.y1 + band.y2) / 2, text: "space",
            textAnchor: "start", dx: 6, fill: token("text-secondary"),
          }),
          Plot.ruleY([0], { stroke: token("baseline") }),
        ],
      }));

      const segments = works[collector];
      const binPx = ((width - MARGINS.marginLeft - MARGINS.marginRight) * binKb) / runLength;
      const inset = Math.max(1, (binPx - BAR) / 2);
      chart(column, "work", Plot.plot({
        ...frame(HEIGHTS.work),
        ariaLabel: `${TITLES[collector]}: work per bin, as marked, survived and freed`,
        y: { domain: [0, workMax], label: "work (objects)", tickFormat: compact },
        color: { domain: PARTS, range: PARTS.map((part) => token(part)) },
        marks: [
          gridY,
          // A 2 px gap between segments and between bars, and rounded ends on top.
          Plot.rect(segments.filter((s) => !s.top), {
            x1: "x1", x2: "x2", y1: "y1", y2: "y2", fill: "part",
            insetLeft: inset, insetRight: inset, insetTop: 1, insetBottom: 1,
          }),
          Plot.rect(segments.filter((s) => s.top), {
            x1: "x1", x2: "x2", y1: "y1", y2: "y2", fill: "part",
            insetLeft: inset, insetRight: inset, insetTop: 1, insetBottom: 1, ry2: 4,
          }),
          Plot.ruleY([0], { stroke: token("baseline") }),
        ],
      }));

      if (collector === "incremental") {
        chart(column, "budget", Plot.plot({
          ...frame(HEIGHTS.budget),
          ariaLabel: `${TITLES[collector]}: work budget`,
          y: { domain: budgetDomain, label: "work budget (objects)", tickFormat: compact },
          marks: [
            gridY,
            Plot.areaY(budgets, {
              x: "mb", y1: 0, y2: (/** @type {{ budget: number }} */ d) => Math.min(0, d.budget), curve: "step-after",
              fill: token("text-muted"), fillOpacity: 0.18,
            }),
            Plot.ruleY([0], { stroke: token("text-secondary"), strokeWidth: 2 }),
            Plot.lineY(budgets, { x: "mb", y: "budget", curve: "step-after", stroke: token("text-primary"), strokeWidth: 2 }),
          ],
        }));
      }
    }
  }
}

/** Put a freshly drawn chart in its panel, in place of the one before. */
function chart(/** @type {HTMLElement} */ column, /** @type {string} */ panel, /** @type {Element} */ svg) {
  /** @type {HTMLElement} */ (column.querySelector(`[data-panel="${panel}"] .chart`)).replaceChildren(svg);
}

/**
 * The heap panel's data: each record reads the heap before its collection and
 * after it, at the same clock (ADR 0010), so the stack rises between collections
 * and drops at each. The run starts from an empty heap.
 * @param {Collector} collector
 * @param {Record[]} records
 */
function heap(collector, records) {
  const names = SPACES[collector];
  const points = [{ mb: 0, sizes: names.map(() => 0), reachable: 0 }];
  for (const record of records) {
    const mb = record[CLOCK] / 1000;
    points.push(
      { mb, sizes: record[SPACES_BEFORE], reachable: record[REACHABLE_BEFORE] / 1000 },
      { mb, sizes: record[SPACES_AFTER], reachable: record[REACHABLE_AFTER] / 1000 },
    );
  }
  const bands = points.flatMap((point) => {
    let y = 0;
    return STACKED[collector].map((space) => {
      const y1 = y;
      y += point.sizes[names.indexOf(space)] / 1000;
      return { mb: point.mb, space, y1, y2: y };
    });
  });
  return { bands, points };
}

/**
 * The work panel's data: each bin's work, stacked as marked, survived and freed.
 * A collection at clock c covers the threshold0 kB before it, so it falls in the
 * bin that holds clock c - threshold0.
 * @param {Record[]} records
 * @param {number} threshold0
 * @param {number} binKb
 */
function work(records, threshold0, binKb) {
  /** @type {Map<number, number[]>} */
  const bins = new Map();
  for (const record of records) {
    const bin = Math.floor((record[CLOCK] - threshold0) / binKb);
    const sums = bins.get(bin) ?? [0, 0, 0];
    for (let part = 0; part < PARTS.length; part++) sums[part] += /** @type {number} */ (record[MARKED + part]);
    bins.set(bin, sums);
  }
  return [...bins].flatMap(([bin, sums]) => {
    const top = sums.findLastIndex((sum) => sum > 0);
    let y = 0;
    return sums.flatMap((sum, part) => {
      if (!sum) return [];
      const y1 = y;
      y += sum;
      return [{ x1: (bin * binKb) / 1000, x2: ((bin + 1) * binKb) / 1000, y1, y2: y, part: PARTS[part], top: part === top }];
    });
  });
}

customElements.define("gc-widget", GcWidget);
