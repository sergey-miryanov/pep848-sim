// @ts-check
// <gc-widget>: one embedding of the simulator on a page. It reads its request
// from the JSON script inside it, asks the page's worker for both runs, and draws
// them as they stream in, as ADR 0008 lays them out: a row of figures, then a
// column per collector, each with the heap by space, work in bins and the work
// budget, on y-scales the two columns share. Above the figures it shows the
// controls its `controls` attribute names, and releasing one asks for both runs
// again.
//
// The JSON can list entries in place of one request, each with a name, a title,
// its own request and its own controls. The widget then shows a select of their
// titles and runs one entry at a time, and the URL fragment names the entry each
// widget shows, as widget-id=entry-name pairs.

// @ts-expect-error: an editor cannot fetch Plot's types from jsDelivr.
import * as Plot from "https://cdn.jsdelivr.net/npm/@observablehq/plot@0.6.17/+esm";
import {
  CLOCK, FADED, FULL, KIND, LANES, PARTS, SPACES, WORK_TO_DO, budgetAt, ceiling, collections, heap, heapAt, work, workAt,
} from "./panels.js";
import { requestRuns } from "./runs.js";

/** @typedef {import("./runs.js").Record} Record */
/** @typedef {import("./runs.js").Figures} Figures */
/** @typedef {import("./runs.js").Control} Control */
/** @typedef {import("./panels.js").Collector} Collector */
/**
 * What a redraw laid out, in MB and px: the clock's length, the charts' width,
 * the run's length and a bin's in kB, and the work panel's y-scale end.
 * @typedef {{ xMax: number, width: number, runLength: number, binKb: number, workMax: number }} Layout
 */
/**
 * A workload a widget offers: its name in the URL fragment, its title in the
 * select, its request as the controls have set it, and the paths of its controls.
 * @typedef {{ name: string, title: string, request: any, controls: string[] }} Entry
 */

/** @type {Collector[]} */
const COLLECTORS = ["legacy", "incremental"];
const TITLES = { legacy: "Legacy collector", incremental: "Incremental collector" };
// How far below the top lane's baseline, in px, a tick at each gc.collect()
// reaches: into the margin, clear of the heap.
const TICK = 6;

// About this many bins of work a run, each a whole number of collection intervals.
const BINS = 40;
const HEIGHTS = { work: 160, budget: 130 };
const MARGINS = { marginLeft: 48, marginRight: 72, marginTop: 16, marginBottom: 32 };
// A lane of the heap panel: its plot, without its margins, and the margin above
// and below it that neither axis's labels take.
const LANE_HEIGHT = 64;
const LANE_MARGIN = 12;
// About how many ticks a lane's y-axis takes.
const LANE_TICKS = 3;
// The widest a bar of work grows, in px. A wider bin pads its bar on both sides.
const BAR = 24;
// How far, in px, a tooltip stands off the crosshair or bar it reads, and how far
// past a chart's plot the pointer still reads it.
const GAP = 12;
const SLACK = 4;
// How long, in ms, the pointer rests before a tooltip shows, so that a sweep
// across a panel leaves its plot in view, and how far, in px, the pointer can
// drift then before the tooltip goes.
const DWELL = 350;
const DRIFT = 3;
// Counts of objects on an axis: 0, 500, 1K, 20K.
const compact = new Intl.NumberFormat("en", { notation: "compact" }).format;

// A figure's values. One with a fraction keeps one decimal, a 0 included, so
// that 6.0% stands beside 5.3%.
const whole = new Intl.NumberFormat("en", { maximumFractionDigits: 0 }).format;
const tenths = new Intl.NumberFormat("en", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format;
const percent = new Intl.NumberFormat("en", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 }).format;
// A tooltip's values: MB to two decimals, so that 0.13 MB of nursery shows, and
// clocks to at most two.
const hundredths = new Intl.NumberFormat("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format;
const megabytes = new Intl.NumberFormat("en", { maximumFractionDigits: 2 }).format;
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
  { label: "Peak work (automatic)", read: (figures) => figures[0], show: count },
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

/**
 * The entries a widget's JSON offers: the ones it lists, or else the one request
 * it holds, with the controls the widget's `controls` attribute names.
 * @param {any} json
 * @param {string | null} controls
 * @returns {Entry[]}
 */
function entriesOf(json, controls) {
  if (!("entries" in json)) {
    return [{ name: "", title: "", request: json, controls: (controls ?? "").split(/\s+/).filter(Boolean) }];
  }
  /** @type {Entry[]} */
  const entries = json.entries;
  if (!entries.length) throw new Error("The widget lists no entries.");
  const names = entries.map((entry) => entry.name);
  if (new Set(names).size < names.length) throw new Error("The widget lists two entries under one name.");
  return entries.map(({ name, title, request, controls = [] }) => ({ name, title, request, controls }));
}

/** The URL fragment's pairs of a widget's id and the name of the entry it shows. */
const fragment = () => new URLSearchParams(location.hash.slice(1));

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
  .entries { display: flex; align-items: center; gap: 8px; margin: 0 0 16px; font-size: 13px; color: var(--text-secondary); }
  .entries select { font: inherit; color: var(--text-primary); background: var(--surface); }
  .controls { display: flex; flex-wrap: wrap; gap: 12px 32px; margin: 0 0 24px; }
  /* Their display would otherwise outrank the hidden attribute's. */
  .entries[hidden], .controls[hidden] { display: none; }
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
  .plot { position: relative; }
  .crosshair, .outline, .tip { position: absolute; pointer-events: none; }
  .crosshair { width: 1px; background: var(--text-secondary); }
  .outline { box-sizing: border-box; border: 1.5px solid var(--text-secondary); border-radius: 5px 5px 0 0; border-bottom: 0; }
  .tip {
    z-index: 1; padding: 6px 8px; white-space: nowrap; font-size: 12px;
    background: var(--surface); border: 1px solid var(--grid); border-radius: 4px;
    box-shadow: 0 2px 8px color-mix(in srgb, var(--text-primary) 12%, transparent);
  }
  .tip p { margin: 0 0 4px; color: var(--text-secondary); }
  .tip table { border-collapse: collapse; }
  .tip th { padding: 0; font-weight: 400; text-align: left; color: var(--text-secondary); }
  .tip thead th:not(:first-child) { text-align: right; padding-left: 12px; }
  .tip td { padding: 0 0 0 12px; text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; color: var(--text-primary); }
  .error { color: var(--text-primary); }
</style>
<p class="error" hidden></p>
<label class="entries" hidden>Workload <select></select></label>
<div class="controls" hidden></div>
<dl class="figures"></dl>
<div class="columns">
  <section data-collector="legacy">
    <h2>Legacy collector</h2>
    <figure data-panel="heap"><figcaption>Heap by space</figcaption><div class="legend"></div><div class="plot"><div class="chart"></div></div></figure>
    <figure data-panel="work"><figcaption></figcaption><div class="legend"></div><div class="plot"><div class="chart"></div></div></figure>
    <figure data-panel="budget"><figcaption>Work budget</figcaption>
      <p class="none">The legacy collector keeps no work budget. A gen 2 collection takes the whole heap in one go.</p></figure>
  </section>
  <section data-collector="incremental">
    <h2>Incremental collector</h2>
    <figure data-panel="heap"><figcaption>Heap by space</figcaption><div class="legend"></div><div class="plot"><div class="chart"></div></div></figure>
    <figure data-panel="work"><figcaption></figcaption><div class="legend"></div><div class="plot"><div class="chart"></div></div></figure>
    <figure data-panel="budget"><figcaption>Work budget</figcaption><div class="plot"><div class="chart"></div></div></figure>
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
  /** The workloads the widget offers, each with its request as the controls have set it. */
  /** @type {Entry[]} */
  #entries = [];
  /** The entry the widget shows. */
  /** @type {Entry | null} */
  #entry = null;
  /** The request whose records the charts show, until a newer one's first records arrive. */
  /** @type {any} */
  #drawn = null;
  #name = "";
  /** Each control's slider, by path, and whether the reader is moving it. */
  /** @type {Map<string, { input: HTMLInputElement, read: (value: number) => void, moving: boolean }>} */
  #sliders = new Map();
  #frame = 0;
  /** What the last redraw laid out, which the pointer's marks follow; null before the clock has a length. */
  /** @type {Layout | null} */
  #layout = null;
  /** The panel under the pointer, and where in it the pointer rests, in px. */
  /** @type {{ panel: string, x: number, y: number } | null} */
  #pointer = null;
  /**
   * Where the pointer came to rest, once it has rested DWELL ms, and whether
   * Escape has hidden the tooltip since; null while the pointer moves.
   */
  /** @type {{ x: number, y: number, hidden: boolean } | null} */
  #rest = null;
  /** @type {ReturnType<typeof setTimeout> | undefined} */
  #dwell = undefined;

  connectedCallback() {
    if (this.shadowRoot) return;
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = TEMPLATE;
    let json;
    try {
      json = JSON.parse(this.querySelector('script[type="application/json"]')?.textContent ?? "");
    } catch (error) {
      this.#fail(`The widget's request is not JSON: ${error}`);
      return;
    }
    try {
      this.#entries = entriesOf(json, this.getAttribute("controls"));
    } catch (error) {
      this.#fail(String(error instanceof Error ? error.message : error));
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
      // In the lanes' order, top to bottom.
      /** @type {HTMLElement} */ (column.querySelector('[data-panel="heap"] .legend')).append(
        key("heap", "var(--text-muted)", true),
        key("reachable", "var(--text-primary)", true),
        key("uncollected garbage", "color-mix(in srgb, var(--text-muted) 18%, transparent)"),
        ...SPACES[collector].map((space) => key(space, `var(--${space})`)),
      );
      /** @type {HTMLElement} */ (column.querySelector('[data-panel="work"] .legend')).append(
        ...PARTS.map((part) => key(part, `var(--${part})`)),
        full(key("full collections, faded", `color-mix(in srgb, var(--text-secondary) ${FADED * 100}%, transparent)`)),
      );
      // Each panel reads its values under the pointer: a crosshair on the heap and
      // the budget, an outline round a bar of work, and, once the pointer rests,
      // a tooltip beside either.
      for (const plot of column.querySelectorAll(".plot")) {
        const panel = /** @type {string} */ (/** @type {HTMLElement} */ (plot.closest("figure")).dataset.panel);
        const mark = document.createElement("div");
        mark.className = panel === "work" ? "outline" : "crosshair";
        const tip = document.createElement("div");
        tip.className = "tip";
        mark.hidden = tip.hidden = true;
        plot.append(mark, tip);
        plot.addEventListener("pointermove", (event) => {
          const box = plot.getBoundingClientRect();
          const { clientX, clientY } = /** @type {PointerEvent} */ (event);
          const x = clientX - box.left, y = clientY - box.top;
          this.#pointer = { panel, x, y };
          // A move past DRIFT hides the tooltip until the pointer rests again.
          const rest = this.#rest;
          if (!rest || Math.hypot(x - rest.x, y - rest.y) > DRIFT) {
            this.#rest = null;
            clearTimeout(this.#dwell);
            this.#dwell = setTimeout(() => {
              this.#rest = { x, y, hidden: false };
              this.#hover();
            }, DWELL);
          }
          this.#hover();
        });
        plot.addEventListener("pointerleave", () => {
          this.#pointer = this.#rest = null;
          clearTimeout(this.#dwell);
          this.#hover();
        });
      }
    }
    // Escape hides the tooltip until the pointer moves on.
    addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || !this.#rest || this.#rest.hidden) return;
      this.#rest.hidden = true;
      this.#hover();
    });
    this.#name = this.id || `gc-widget-${widgets++}`;
    if (this.#entries.length > 1) {
      const label = /** @type {HTMLElement} */ (root.querySelector(".entries"));
      const select = /** @type {HTMLSelectElement} */ (label.querySelector("select"));
      select.append(...this.#entries.map(({ name, title }) => new Option(title, name)));
      label.hidden = false;
      select.addEventListener("change", () => this.#choose(select.value, true));
      addEventListener("hashchange", () => this.#choose(fragment().get(this.id) ?? "", false));
    }
    new ResizeObserver(() => this.#schedule()).observe(this);
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => this.#schedule());
    this.#choose(fragment().get(this.id) ?? "", false);
  }

  /**
   * Show the entry of that name, or the first if the widget offers none by it, and
   * start its runs. The last entry's controls, figures and charts go at once, and
   * its request keeps the values its controls set, for when it is shown again.
   * @param {string} name
   * @param {boolean} picked whether the reader picked it, which the URL fragment
   *   then records
   */
  #choose(name, picked) {
    const entry = this.#entries.find((offered) => offered.name === name) ?? this.#entries[0];
    if (entry === this.#entry) return;
    this.#entry = entry;
    const root = /** @type {ShadowRoot} */ (this.shadowRoot);
    /** @type {HTMLSelectElement} */ (root.querySelector(".entries select")).value = entry.name;
    if (picked && this.id) {
      const pairs = fragment();
      pairs.set(this.id, entry.name);
      history.replaceState(null, "", `#${pairs}`);
    }
    const row = /** @type {HTMLElement} */ (root.querySelector(".controls"));
    row.replaceChildren();
    row.hidden = true;
    this.#sliders.clear();
    for (const chart of root.querySelectorAll(".chart")) chart.replaceChildren();
    this.#records = { legacy: [], incremental: [] };
    this.#figures = {};
    this.#drawn = entry.request;
    this.#schedule();
    this.#start();
  }

  /**
   * Ask for both runs of the request as the controls have set it, in place of any
   * runs asked for before. The charts keep the old runs until the new runs' first
   * records arrive.
   */
  #start() {
    const entry = /** @type {Entry} */ (this.#entry);
    let request = structuredClone(entry.request);
    let fresh = true;
    /** @type {HTMLElement} */ (/** @type {ShadowRoot} */ (this.shadowRoot).querySelector(".error")).hidden = true;
    requestRuns(this.#name, request, {
      controls: (controls, expanded) => {
        // A request that names a preset comes back spelled out: the preset's
        // workload and run length, which the controls edit from then on.
        if ("preset" in request) {
          request = expanded;
          entry.request = structuredClone(expanded);
          if ("preset" in this.#drawn) this.#drawn = request;
        }
        this.#show(controls);
      },
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
    }, entry.controls);
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
          assign(/** @type {Entry} */ (this.#entry).request, path, held(unit, Number(input.value)));
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

    // A request that names a preset has no run length until the worker spells it
    // out, and the charts' clock needs one.
    if ("preset" in this.#drawn) {
      this.#layout = null;
      this.#hover();
      return;
    }
    const { run_length: runLength, settings: { threshold0 } } = this.#drawn;
    const style = getComputedStyle(this);
    const token = (/** @type {string} */ name) => style.getPropertyValue(`--${name}`).trim();
    const xMax = runLength / 1000;
    const width = this.#column("legacy").clientWidth;

    const heaps = { legacy: heap("legacy", this.#records.legacy), incremental: heap("incremental", this.#records.incremental) };
    // One y-scale for every lane in both columns, so that a height reads as the
    // same MB in any lane.
    const heapMax = ceiling(Math.max(...COLLECTORS.flatMap((c) => heaps[c].whole.map((point) => point.heap))));
    const binKb = Math.ceil(runLength / BINS / threshold0) * threshold0;
    const works = { legacy: work(this.#records.legacy, binKb), incremental: work(this.#records.incremental, binKb) };
    // The legend names the full collections' marks only for runs that make some.
    const fulls = COLLECTORS.some((c) => this.#records[c].some((record) => FULL.includes(record[KIND])));
    for (const entry of /** @type {ShadowRoot} */ (this.shadowRoot).querySelectorAll(".legend [data-full]")) {
      /** @type {HTMLElement} */ (entry).hidden = !fulls;
    }
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
    // A lane is too short for the ticks Plot picks, so its grid takes its axis's.
    const laneGridY = Plot.gridY({ stroke: token("grid"), strokeOpacity: 1, ticks: LANE_TICKS });

    for (const collector of COLLECTORS) {
      const column = this.#column(collector);
      /** @type {HTMLElement} */ (column.querySelector('[data-panel="work"] figcaption')).textContent =
        `Work per ${binKb / 1000} MB allocated`;
      const { whole, lanes } = heaps[collector];
      const colors = { domain: SPACES[collector], range: SPACES[collector].map((space) => token(space)) };
      // Both runs call gc.collect() and shut down at the same clocks. A tick below
      // the top lane marks each call, one to a pixel at most, and a dashed rule
      // across every panel marks shutdown. Each says what it marks in the chart,
      // so the legends keep their length.
      const records = this.#records[collector];
      const pxPerMb = (width - MARGINS.marginLeft - MARGINS.marginRight) / xMax;
      const calls = [...new Set(records.filter((record) => record[KIND] === "full")
        .map((record) => Math.round((record[CLOCK] / 1000) * pxPerMb)))].map((px) => px / pxPerMb);
      const shutdown = records.filter((record) => record[KIND] === "shutdown").slice(0, 1).map((record) => record[CLOCK] / 1000);
      const ending = [Plot.ruleX(shutdown, { stroke: token("text-secondary"), strokeDasharray: "3,3" })];
      // The lanes share the clock, whose axis only the bottom one draws, and the
      // y-scale, whose unit only the top one names. Each lane's colors name what
      // it shows.
      const lane = (/** @type {number} */ i, /** @type {string} */ shows, /** @type {unknown[]} */ marks) => {
        const top = i === 0, bottom = i === LANES[collector].length;
        const margins = { marginTop: top ? MARGINS.marginTop : LANE_MARGIN, marginBottom: bottom ? MARGINS.marginBottom : LANE_MARGIN };
        return Plot.plot({
          ...frame(LANE_HEIGHT + margins.marginTop + margins.marginBottom),
          ...margins,
          x: { domain: [0, xMax], label: "allocation clock (MB)", axis: bottom ? "bottom" : null },
          ariaLabel: `${TITLES[collector]}: ${shows}`,
          y: { domain: [0, heapMax], label: top ? "heap (MB)" : null, ticks: LANE_TICKS },
          color: colors,
          marks: [laneGridY, ...marks, ...ending, Plot.ruleY([0], { stroke: token("baseline") })],
        });
      };
      chart(column, "heap",
        lane(0, "heap, its reachable part and the uncollected garbage between them", [
          Plot.areaY(whole, { x: "mb", y1: "reachable", y2: "heap", fill: token("text-muted"), fillOpacity: 0.18 }),
          Plot.lineY(whole, { x: "mb", y: "heap", stroke: token("text-muted"), strokeWidth: 2 }),
          Plot.lineY(whole, { x: "mb", y: "reachable", stroke: token("text-primary"), strokeWidth: 2 }),
          Plot.ruleX(calls, { y1: 0, y2: (-heapMax * TICK) / LANE_HEIGHT, stroke: token("text-secondary") }),
          Plot.text(calls.slice(0, 1), {
            x: (/** @type {number} */ mb) => mb, y: 0, text: () => "gc.collect()",
            textAnchor: "start", lineAnchor: "bottom", dx: 2, dy: -2, fill: token("text-secondary"),
          }),
          Plot.text(shutdown, {
            x: (/** @type {number} */ mb) => mb, frameAnchor: "top", text: () => "shutdown",
            textAnchor: "end", dx: -4, fill: token("text-secondary"),
          }),
        ]),
        ...lanes.map((bands, i) => lane(i + 1, LANES[collector][i].join(" and "), LANES[collector][i].length > 1
          // Spaces that share a lane stack as fills alone: a line along a band's
          // top would trace the spaces below it too.
          ? [Plot.areaY(bands, { x: "mb", y1: "y1", y2: "y2", z: "space", fill: "space", fillOpacity: 0.55, stroke: token("surface"), strokeWidth: 1 })]
          : [
            Plot.areaY(bands, { x: "mb", y1: "y1", y2: "y2", fill: "space", fillOpacity: 0.1 }),
            Plot.lineY(bands, { x: "mb", y: "y2", stroke: "space", strokeWidth: 2 }),
          ])),
      );

      const segments = works[collector];
      const binPx = ((width - MARGINS.marginLeft - MARGINS.marginRight) * binKb) / runLength;
      const inset = Math.max(1, (binPx - BAR) / 2);
      chart(column, "work", Plot.plot({
        ...frame(HEIGHTS.work),
        ariaLabel: `${TITLES[collector]}: work per bin, as marked, survived and freed, full collections' faded above`,
        y: { domain: [0, workMax], label: "work (objects)", tickFormat: compact },
        color: { domain: PARTS, range: PARTS.map((part) => token(part)) },
        marks: [
          gridY,
          // A 2 px gap between segments and between bars, and rounded ends on top.
          Plot.rect(segments.filter((s) => !s.top), {
            x1: "x1", x2: "x2", y1: "y1", y2: "y2", fill: "part", fillOpacity: "opacity",
            insetLeft: inset, insetRight: inset, insetTop: 1, insetBottom: 1,
          }),
          Plot.rect(segments.filter((s) => s.top), {
            x1: "x1", x2: "x2", y1: "y1", y2: "y2", fill: "part", fillOpacity: "opacity",
            insetLeft: inset, insetRight: inset, insetTop: 1, insetBottom: 1, ry2: 4,
          }),
          ...ending,
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
            ...ending,
          ],
        }));
      }
    }
    this.#layout = { xMax, width, runLength, binKb, workMax };
    this.#hover();
  }

  /**
   * Mark the clock under the pointer in every panel of both columns, from the
   * records drawn so far: both runs share the clock. The panel the pointer is in
   * shows its tooltip in both columns, once the pointer rests and until Escape. A
   * redraw leaves the marks alone and calls this again, so they hold while runs
   * stream.
   */
  #hover() {
    const root = /** @type {ShadowRoot} */ (this.shadowRoot);
    for (const mark of root.querySelectorAll(".crosshair, .outline, .tip")) /** @type {HTMLElement} */ (mark).hidden = true;
    const pointer = this.#pointer, layout = this.#layout;
    if (!pointer || !layout) return;
    const { panel: hovered, x, y } = pointer;
    const { width, runLength } = layout;
    const { marginLeft, marginRight } = MARGINS;
    if (x < marginLeft - SLACK || x > width - marginRight + SLACK) return;
    const kb = Math.min(Math.max(0, ((x - marginLeft) / (width - marginLeft - marginRight)) * runLength), runLength - 1);
    const resting = this.#rest !== null && !this.#rest.hidden;
    for (const collector of COLLECTORS) {
      for (const plot of this.#column(collector).querySelectorAll(".plot")) {
        const panel = /** @type {string} */ (/** @type {HTMLElement} */ (plot.closest("figure")).dataset.panel);
        this.#mark(collector, panel, /** @type {HTMLElement} */ (plot), kb, resting && panel === hovered ? y : null);
      }
    }
  }

  /**
   * Mark what one panel reads at clock `kb`, in kB: the heap or the budget at the
   * nearest collection, with a crosshair, or the work of the bin that holds it,
   * with an outline round its bar. Given a height `y`, in px, show its tooltip
   * there too.
   * @param {Collector} collector
   * @param {string} panel
   * @param {HTMLElement} plot
   * @param {number} kb
   * @param {number | null} y
   */
  #mark(collector, panel, plot, kb, y) {
    const { xMax, width, binKb, workMax } = /** @type {Layout} */ (this.#layout);
    const { marginLeft, marginRight, marginTop, marginBottom } = MARGINS;
    const inner = width - marginLeft - marginRight;
    const px = (/** @type {number} */ mb) => marginLeft + (mb / xMax) * inner;
    const mark = /** @type {HTMLElement} */ (plot.querySelector(".crosshair, .outline"));
    const tip = /** @type {HTMLElement} */ (plot.querySelector(".tip"));
    const records = this.#records[collector];
    // The span the tooltip stands beside: a crosshair's x, or a bar's two edges.
    let left, right;
    // What the tooltip reads, built only when it shows.
    /** @type {() => Node[]} */
    let content;
    if (panel === "work") {
      const at = workAt(records, binKb, kb);
      const total = [...at.automatic, ...at.full].reduce((sum, part) => sum + part, 0);
      const inset = Math.max(1, (px(at.x2) - px(at.x1) - BAR) / 2);
      [left, right] = [px(at.x1) + inset - 2, px(at.x2) - inset + 2];
      const top = marginTop + (1 - total / workMax) * (HEIGHTS.work - marginTop - marginBottom) - 2;
      Object.assign(mark.style, { left: `${left}px`, width: `${right - left}px`, top: `${top}px`, height: `${HEIGHTS.work - marginBottom - top}px` });
      mark.hidden = !total;
      const fulls = at.full.some(Boolean);
      content = () => readout(
        `${megabytes(at.x1)}–${megabytes(at.x2)} MB allocated`,
        fulls ? ["objects", "automatic", "full"] : ["objects"],
        PARTS.map((part, i) => [part, `var(--${part})`, (fulls ? [at.automatic[i], at.full[i]] : [at.automatic[i]]).map(whole)]),
      );
    } else {
      const at = panel === "heap" ? heapAt(records, kb) : budgetAt(records, kb);
      if (!at) return;
      left = right = px(at.clock / 1000);
      Object.assign(mark.style, { left: `${left}px`, top: `${marginTop}px`, height: `${plot.clientHeight - marginTop - marginBottom}px` });
      mark.hidden = false;
      const where = `${collections(at.kinds)} at ${megabytes(at.clock / 1000)} MB`;
      if ("budget" in at) {
        content = () => readout(where, ["objects"], [["work budget", "var(--text-primary)", [whole(at.budget)]]]);
      } else {
        const { before, after } = at;
        /** @returns {[string, string, string[]]} */
        const row = (/** @type {string} */ name, /** @type {string} */ color, /** @type {(read: typeof before) => number} */ value) =>
          [name, color, [hundredths(value(before)), hundredths(value(after))]];
        content = () => readout(where, ["MB", "before", "after"], [
          row("heap", "var(--text-muted)", (read) => read.heap),
          row("reachable", "var(--text-primary)", (read) => read.reachable),
          row("uncollected garbage", "transparent", (read) => read.garbage),
          ...SPACES[collector].map((space, i) => row(space, `var(--${space})`, (read) => read.spaces[i])),
        ]);
      }
    }
    if (y === null) return;
    tip.replaceChildren(...content());
    tip.hidden = false;
    // Right of the mark, or left of it where the chart ends; level with the
    // pointer, inside the panel.
    const toRight = right + GAP + tip.offsetWidth <= width;
    tip.style.left = `${toRight ? right + GAP : left - GAP - tip.offsetWidth}px`;
    tip.style.top = `${Math.min(Math.max(0, y - tip.offsetHeight / 2), plot.clientHeight - tip.offsetHeight)}px`;
  }
}

/**
 * A tooltip's readout: where it reads, then a table with a row a quantity, keyed
 * with its mark's color, and a value under each column.
 * @param {string} where
 * @param {string[]} columns the unit, over the quantities, then each column's head
 * @param {[string, string, string[]][]} rows each quantity's name, color and values
 */
function readout(where, columns, rows) {
  const caption = document.createElement("p");
  caption.textContent = where;
  const table = document.createElement("table");
  const head = table.createTHead().insertRow();
  for (const column of columns) {
    const cell = document.createElement("th");
    cell.textContent = column;
    head.append(cell);
  }
  const body = table.createTBody();
  for (const [name, color, values] of rows) {
    const row = body.insertRow();
    const label = document.createElement("th");
    label.scope = "row";
    label.append(key(name, color, true));
    row.append(label);
    for (const value of values) row.insertCell().textContent = value;
  }
  return [caption, table];
}

/** Put freshly drawn charts in their panel, in place of the ones before. */
function chart(/** @type {HTMLElement} */ column, /** @type {string} */ panel, /** @type {Element[]} */ ...svgs) {
  /** @type {HTMLElement} */ (column.querySelector(`[data-panel="${panel}"] .chart`)).replaceChildren(...svgs);
}

/** Mark a legend entry as one for full collections, hidden until a run makes some. */
function full(/** @type {HTMLElement} */ entry) {
  entry.dataset.full = "";
  entry.hidden = true;
  return entry;
}

customElements.define("gc-widget", GcWidget);
