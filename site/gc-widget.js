// @ts-nocheck PROTOTYPE (guide fit)
// <gc-widget>: one embedding of the simulator on a page. It reads its request
// from the JSON script inside it, asks the page's worker for both runs once a
// reader comes near it, and draws them as they stream in, as ADR 0008 lays them
// out: a row of figures, then a
// column per collector, each with the heap by space, work in bins and the work
// budget, on y-scales the two columns share. Above the figures it shows the
// controls its `controls` attribute names, and releasing one asks for both runs
// again. It groups them: the workload's, then the collector settings', with the
// collector constants behind a toggle under them. Beside them it draws a sample of the request's object graph, each
// structure under sys or its frame, with a legend under the controls. With an
// `editor` attribute, as on the playground, the legend edits the request, and
// each change asks for both runs again (ADR 0013). A switch then shows the
// request as Python source beside the rest, which runs with a button (ADR 0015),
// and the widget carries a `source` attribute meanwhile, so a page can widen it.
//
// The JSON can list entries in place of one request, each with a name, a title,
// its own request and its own controls. The widget then shows a select of their
// titles and runs one entry at a time, and the URL fragment names the entry each
// widget shows, as widget-id=entry-name pairs. An editing widget with an id also
// writes the request of its last runs there, as a widget-id.request pair, which
// makes the address a link that opens the same runs (ADR 0016). The widget keeps
// the runs of its last requests while the page stays open, so picking an entry
// again, or moving a control back, draws them at once (#135).
//
// A `compact` widget, as the guide's, leaves out the object graph, its legend
// and the select, since the page around it picks the entry (ADR 0020). An entry
// can mark the panels and figures its page talks about, each outlined with a
// badge that numbers it. A widget with a `changes` attribute notes under each
// figure what it read before the last runs it asked for, where the two differ.
//
// Each panel reads its values under the pointer, and from the keys once it has
// focus: the arrows step from one collection or bin to the next. A screen reader
// takes each panel for a slider along the allocation clock, and hears the
// tooltip's readout at each step.

// @ts-expect-error: an editor cannot fetch Plot's types from jsDelivr.
import * as Plot from "https://cdn.jsdelivr.net/npm/@observablehq/plot@0.6.17/+esm";
import {
  forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY,
  // @ts-expect-error: an editor cannot fetch d3's types from jsDelivr.
} from "https://cdn.jsdelivr.net/npm/d3-force@3.0.0/+esm";
import { Editor, EDITOR_STYLE } from "./editor.js";
import { Source, SOURCE_STYLE } from "./source.js";
import { FOREIGN, decode, encode, holdsCode, LINK_STYLE } from "./link.js";
import { describe, describeChurn, describeYoung, fit, network } from "./graph.js";
import {
  CLOCK, FADED, FULL, KEYS, KIND, LANES, PARTS, SPACES, WORK_TO_DO,
  budgetAt, ceiling, collections, cuts, heap, heapAt, spoken, step, work, workAt, workEnd,
} from "./panels.js";
import { dropRuns, requestRuns, stopRuns } from "./runs.js";
import { Kept } from "./kept.js";

/** @typedef {import("./runs.js").Record} Record */
/** @typedef {import("./runs.js").Figures} Figures */
/** @typedef {import("./runs.js").Control} Control */
/** @typedef {import("./runs.js").Listener} Listener */
/** @typedef {import("./kept.js").Runs} Runs */
/** @typedef {import("./panels.js").Collector} Collector */
/** @typedef {import("./panels.js").Readout} Readout */
/** @typedef {import("./graph.js").Graph} Graph */
/**
 * What a redraw laid out, in MB and px: the clock's length, the charts' width,
 * the run's length and a bin's in kB, and the work panel's y-scale end.
 * @typedef {{ xMax: number, width: number, runLength: number, binKb: number, workMax: number }} Layout
 */
/**
 * A workload a widget offers: its name in the URL fragment, its title in the
 * select, its request as the controls have set it, the paths of its controls,
 * and the parts it marks, as collector.panel or figure.name.
 * @typedef {{ name: string, title: string, request: any, controls: string[], marks: string[] }} Entry
 */

/** @type {Collector[]} */
const COLLECTORS = ["legacy", "incremental"];
const TITLES = { legacy: "Legacy collector", incremental: "Incremental collector" };
// How far below the top lane's baseline, in px, a tick at each gc.collect()
// reaches: into the margin, clear of the heap.
const TICK = 6;

// About this many bins of work a run, each a whole number of collection intervals.
const BINS = 40;
// PROTOTYPE (guide fit): the page may change these, through protoHeights.
const HEIGHTS = { work: 160, budget: 130 };
const MARGINS = { marginLeft: 48, marginRight: 72, marginTop: 16, marginBottom: 32 };
// A lane of the heap panel: its plot, without its margins, and the margin above
// and below it that neither axis's labels take.
let LANE_HEIGHT = 64;
const LANE_MARGIN = 12;
// About how many ticks a lane's y-axis takes.
let LANE_TICKS = 3;
// The heap panel's height: the whole heap's lane over the spaces', the margin
// between each two, and the axes' margins above the first and below the last.
let HEAP_HEIGHT = (LANES.legacy.length + 1) * (LANE_HEIGHT + 2 * LANE_MARGIN) - 2 * LANE_MARGIN
  + MARGINS.marginTop + MARGINS.marginBottom;
// The widest a bar of work grows, in px. A wider bin pads its bar on both sides.
const BAR = 24;
// How far, in px, a tooltip stands off the crosshair or bar it reads, and how far
// past a chart's plot the pointer still reads it.
const GAP = 12;
const SLACK = 4;
// How long, in ms, the pointer rests before a tooltip shows, so that a pointer
// crossing a panel leaves its plot in view, and how far, in px, the pointer can
// drift then before the tooltip goes.
const DWELL = 350;
const DRIFT = 3;
// The object graph's frame, in px, the margin its layout keeps inside it, and the
// most the layout grows to fill it, so that a small sample keeps small dots.
const GRAPH = { width: 520, height: 250, margin: 18, most: 1.3 };
const SVG = "http://www.w3.org/2000/svg";
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
// Its name is how an entry marks it.
/**
 * @type {{
 *   name: string,
 *   label: string,
 *   read: (figures: Figures, collector: Collector) => number | undefined,
 *   show: (value: number, values: number[]) => string,
 * }[]}
 */
const FIGURES = [
  { name: "peak_work", label: "Peak work (automatic)", read: (figures) => figures[0], show: count },
  { name: "peak_uncollected_garbage", label: "Peak uncollected garbage (MB)", read: (figures) => figures[1] / 1000, show: tenths },
  { name: "work_per_mb", label: "Work per MB", read: (figures) => figures[2], show: count },
  { name: "yield", label: "Yield", read: (figures) => figures[3], show: percent },
  { name: "collections", label: "Collections", read: (figures) => figures[4], show: count },
  { name: "gen2_collections_sweeps", label: "Gen 2 collections / sweeps", read: (figures, collector) => figures[collector === "legacy" ? 6 : 5], show: count },
];
// The parts an entry can mark: each collector's panels, and the figures.
const MARKS = [
  ...["legacy", "incremental"].flatMap((collector) => ["heap", "work", "budget"].map((panel) => `${collector}.${panel}`)),
  ...FIGURES.map(({ name }) => `figure.${name}`),
];

/** A control's value as the reader sees it: kB, a share as a percentage, or a count. */
const reading = (/** @type {Control[2]} */ unit, /** @type {number} */ value) => {
  if (unit === "share") return percent(value / 1000);
  return unit === "count" ? whole(value) : `${whole(value)} kB`;
};

/** A control's value as the request holds it: kB or a count, or a share as a fraction. */
const held = (/** @type {Control[2]} */ unit, /** @type {number} */ value) =>
  unit === "share" ? `${value}/1000` : value;

// The controls that say what they make of the young generation.
const YOUNG = ["settings.threshold0", "settings.threshold1"];

/** Put a value into the request at a path of keys and indices joined by dots. */
function assign(/** @type {any} */ request, /** @type {string} */ path, /** @type {unknown} */ value) {
  const keys = path.split(".");
  const last = /** @type {string} */ (keys.pop());
  keys.reduce((object, key) => object[key], request)[last] = value;
}

/**
 * The entries a widget's JSON offers: the ones it lists, each with its own
 * controls and those the JSON lists for every entry, or else the one request it
 * holds, with the controls the widget's `controls` attribute names.
 * @param {any} json
 * @param {string | null} controls
 * @returns {Entry[]}
 */
function entriesOf(json, controls) {
  if (!("entries" in json)) {
    return [{ name: "", title: "", request: json, controls: (controls ?? "").split(/\s+/).filter(Boolean), marks: [] }];
  }
  /** @type {Entry[]} */
  const entries = json.entries;
  if (!entries.length) throw new Error("The widget lists no entries.");
  const names = entries.map((entry) => entry.name);
  if (new Set(names).size < names.length) throw new Error("The widget lists two entries under one name.");
  /** @type {string[]} */
  const shared = json.controls ?? [];
  for (const { name, marks = [] } of entries) {
    const unknown = marks.find((mark) => !MARKS.includes(mark));
    if (unknown) throw new Error(`The widget's entry ${name} marks ${unknown}, which it has no part by.`);
  }
  return entries.map(({ name, title, request, controls = [], marks = [] }) => ({
    name, title, request, controls: [...controls, ...shared.filter((path) => !controls.includes(path))], marks,
  }));
}

/**
 * The URL fragment's pairs of a widget's id and the name of the entry it shows,
 * and of an editing widget's id and its link's request.
 */
const fragment = () => new URLSearchParams(location.hash.slice(1));
/** The key of a widget's link's request in the URL fragment. */
const linkKey = (/** @type {string} */ id) => `${id}.request`;
// What the workload source says while a link's code waits for Run.
const HELD = "This link carries Python, which runs in your browser once you press Run. Read it first.";

// The colors come from the page's theme.css, through the custom properties the
// shadow root inherits (ADR 0018).
const TEMPLATE = `
<style>
  :host {
    display: block;
    padding: 16px;
    background: var(--surface);
    color: var(--text-primary);
    font: 14px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  /* The parts below lay out by the width they have, which the playground's
     source shares on a wide screen (#171). */
  .content { container: widget / inline-size; }
  .picks { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 24px; margin: 0 0 16px; font-size: 13px; color: var(--text-secondary); }
  .entries { display: flex; align-items: center; gap: 8px; }
  .entries select { font: inherit; color: var(--text-primary); background: var(--surface); }
  .controls { display: grid; gap: 16px; margin: 0 0 24px; }
  .controls .group { display: flex; flex-wrap: wrap; gap: 12px 32px; align-items: start; }
  .controls h3 { flex-basis: 100%; margin: 0; font-size: 13px; font-weight: 600; color: var(--text-primary); }
  .controls details { flex-basis: 100%; font-size: 13px; color: var(--text-secondary); }
  .controls summary { width: max-content; cursor: pointer; }
  .controls details > .group { margin-top: 12px; }
  /* Their display would otherwise outrank the hidden attribute's. */
  .picks[hidden], .entries[hidden], .controls[hidden], .graph[hidden], .key-list[hidden] { display: none; }
  /* The select, the controls and the object graph's legend, beside the graph. */
  .top { display: grid; grid-template-columns: minmax(0, 1fr) minmax(320px, 520px); gap: 24px; margin: 0 0 24px; align-items: start; }
  .top > div:first-child > :last-child { margin-bottom: 0; }
  .key-list h3 { margin: 0 0 4px; font-size: 13px; font-weight: 600; }
  .key-list p { margin: 0 0 8px; font-size: 12px; color: var(--text-secondary); }
  .key-list ol { list-style: none; margin: 0 0 4px; padding: 0; display: grid; gap: 4px; font-size: 12px; color: var(--text-secondary); }
  .key-list li { display: flex; gap: 6px; align-items: baseline; }
  .badge {
    flex: none; display: inline-grid; place-items: center; width: 15px; height: 15px; border-radius: 50%;
    border: 1.5px solid var(--text-secondary); font-size: 10px; font-weight: 600; color: var(--text-primary);
  }
  .graph svg { display: block; width: 100%; height: auto; overflow: visible; }
  .graph .link { stroke: var(--text-muted); stroke-width: 1; fill: none; }
  .graph .cycle { stroke: var(--freed); stroke-width: 1.5; fill: none; }
  .graph .held { stroke: var(--text-secondary); stroke-width: 1.2; stroke-dasharray: 3 2; }
  .graph .object { fill: var(--text-secondary); }
  .graph .first circle, .graph .root rect { fill: var(--surface); stroke: var(--text-secondary); stroke-width: 1.5; }
  .graph text { fill: var(--text-primary); font-size: 10px; font-weight: 600; text-anchor: middle; dominant-baseline: central; }
  .control { display: grid; gap: 4px; width: 200px; font-size: 13px; color: var(--text-secondary); }
  .control .name { display: flex; justify-content: space-between; gap: 8px; }
  .control output { color: var(--text-primary); font-weight: 600; font-variant-numeric: tabular-nums; }
  .control input { margin: 0; accent-color: var(--text-secondary); }
  .control .note { font-size: 12px; }
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
  /* Each chart keeps the height it draws at from the start, so a widget that
     has not asked for its runs yet takes its full room on the page. */
  [data-panel="heap"] .chart { min-height: var(--proto-heap, ${HEAP_HEIGHT}px); }
  [data-panel="work"] .chart { min-height: var(--proto-work, ${HEIGHTS.work}px); }
  [data-panel="budget"] .chart { min-height: var(--proto-budget, ${HEIGHTS.budget}px); }
  .plot:focus-visible { outline: 2px solid var(--text-primary); outline-offset: 2px; border-radius: 4px; }
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
  /* A part the entry marks: outlined, with a badge that numbers it, and a
     figure's numbers tinted. */
  [data-mark] { position: relative; outline: 2px solid var(--text-primary); outline-offset: 6px; border-radius: 2px; }
  [data-mark]::after {
    content: attr(data-mark); position: absolute; top: -16px; right: -16px; z-index: 2;
    display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%;
    font-size: 12px; font-weight: 600; background: var(--text-primary); color: var(--surface);
  }
  .figure[data-mark] .value { background: color-mix(in srgb, var(--aging) 35%, transparent); border-radius: 3px; padding: 0 3px; }
  /* What a figure read before, on its own line, which keeps its height while
     empty so the charts below stay put. */
  .was { display: none; }
  :host([changes]) .was { display: block; height: 16px; font-size: 11px; line-height: 16px; color: var(--text-muted); }
  :host([compact]) .graph, :host([compact]) .key-list, :host([compact]) .picks { display: none; }
  :host([compact]) .top, :host([compact]) .controls, :host([compact]) .figures { margin-bottom: 12px; }
  /* Too narrow for three controls beside the graph: the select and the
     controls, then the graph, then its legend. */
  @container widget (width < 780px) {
    .top { grid-template-columns: minmax(0, 1fr); gap: 0; }
    .top > div:first-child { display: contents; }
    .graph { max-width: 520px; margin: 0 0 16px; }
    .key-list { order: 1; }
  }
  /* Six figures in a row, then three, then two, each legacy beside incremental:
     a figure takes up to about 120 px. */
  @container widget (width < 840px) {
    .figures { grid-template-columns: repeat(3, 1fr); }
  }
  @container widget (width < 420px) {
    .figures { grid-template-columns: repeat(2, 1fr); }
  }
  /* Too narrow for two charts that each keep about 220 px of plot: the
     incremental column under the legacy one. */
  @container widget (width < 700px) {
    .columns { grid-template-columns: minmax(0, 1fr); }
  }
  /* A compact widget keeps its columns side by side, so that a step's text
     stays near both. */
  @container widget (width < 700px) {
    :host([compact]) .columns { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; }
    :host([compact]) .figure .value { font-size: 17px; }
  }
</style>
<div class="frame"><div class="content">
<p class="error" hidden></p>
<div class="top">
  <div>
    <div class="picks" hidden><label class="entries" hidden>Workload <select></select></label></div>
    <div class="controls" hidden></div>
    <div class="key-list" hidden>
      <div class="plain">
        <h3>Object graph</h3>
        <p>A few objects of each structure, as its shape links them. One dot is one
        simulated object, 16 real ones. A red link lies on a cycle, so dropping its
        structure leaves cyclic garbage.</p>
        <ol></ol>
        <p class="churn"></p>
      </div>
    </div>
  </div>
  <div class="graph" hidden></div>
</div>
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
</div>
</div></div>`;

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
  /** Where each figure shows what each run's value was, on a widget with the `changes` attribute. */
  /** @type {{ legacy: HTMLElement, incremental: HTMLElement }[]} */
  #was = [];
  /** The figures of the last runs that finished, while the charts show them. */
  /** @type {{ legacy: Figures, incremental: Figures } | null} */
  #finished = null;
  /** The figures of the runs the charts showed before the runs asked for last, if those finished. */
  /** @type {{ legacy: Figures, incremental: Figures } | null} */
  #before = null;
  /** The workloads the widget offers, each with its request as the controls have set it. */
  /** @type {Entry[]} */
  #entries = [];
  /** The entry the widget shows. */
  /** @type {Entry | null} */
  #entry = null;
  /** The request whose records the charts show, until a newer one's first records arrive. */
  /** @type {any} */
  #drawn = null;
  /** The runs of the widget's last requests that finished, which draw at once when asked for again. */
  #kept = new Kept();
  #name = "";
  /**
   * Each control's slider, by path, what it says it makes, if anything, and
   * whether the reader is moving it.
   * @type {Map<string, { input: HTMLInputElement, note: HTMLElement | null, read: (value: number) => void, moving: boolean }>}
   */
  #sliders = new Map();
  /**
   * Whether the collector constants' controls show, kept from one entry to the
   * next. They start open only on a widget that offers no collector settings.
   */
  // PROTOTYPE (guide fit): null until the reader opens or closes the toggle.
  #constantsOpen = null;
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
  /**
   * The panel the keys read, while it has focus, and whether Escape has hidden
   * its tooltip since the last key.
   * @type {{ panel: string, plot: HTMLElement, hidden: boolean } | null}
   */
  #keys = null;
  /** The clock, in kB, the keys read, or where the pointer last rested; null until either reads one. */
  /** @type {number | null} */
  #clock = null;
  /** The legend's editor, on a widget with the `editor` attribute. */
  /** @type {Editor | null} */
  #editor = null;
  /** The request as Python source, beside the rest, on a widget with the `editor` attribute. */
  /** @type {Source | null} */
  #source = null;
  /** Which editor shows: the legend's or the source. */
  /** @type {"legend" | "source"} */
  #mode = "legend";
  /** The link's request the widget last wrote into the URL fragment or opened from it. */
  #linked = "";
  /** Links written so far, so that a slow one gives way to the next. */
  #shares = 0;
  /** Entries whose request a link with code brought, until the reader runs it. */
  /** @type {WeakSet<Entry>} */
  #held = new WeakSet();
  /** The button that copies the link, on a widget with the `editor` attribute. */
  #copy = document.createElement("button");

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
    const values = FIGURES.map(({ name, label }) => {
      const figure = document.createElement("div");
      figure.className = "figure";
      figure.dataset.figure = name;
      const term = document.createElement("dt");
      term.textContent = label;
      figure.append(term);
      // Legacy beside incremental, as the columns below stand.
      const value = (/** @type {Collector} */ collector) => {
        const description = document.createElement("dd");
        const number = document.createElement("span");
        number.className = "value";
        number.textContent = "–";
        const was = document.createElement("span");
        was.className = "was";
        description.append(number, collector, was);
        figure.append(description);
        return { number, was };
      };
      row.append(figure);
      return { legacy: value("legacy"), incremental: value("incremental") };
    });
    this.#values = values.map(({ legacy, incremental }) => ({ legacy: legacy.number, incremental: incremental.number }));
    this.#was = values.map(({ legacy, incremental }) => ({ legacy: legacy.was, incremental: incremental.was }));
    for (const collector of COLLECTORS) {
      const column = this.#column(collector);
      /** @type {HTMLElement} */ (column.querySelector("h2")).id = collector;
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
      for (const element of column.querySelectorAll(".plot")) {
        const plot = /** @type {HTMLElement} */ (element);
        const figure = /** @type {HTMLElement} */ (plot.closest("figure"));
        const panel = /** @type {string} */ (figure.dataset.panel);
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
              // The keys start where the pointer last rested.
              this.#clock = this.#kbAt(x) ?? this.#clock;
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
        // The keys read a panel too, once it has focus (#141). A screen reader
        // takes it for a slider along the allocation clock, named by its column's
        // heading and its caption, and hears its tooltip's readout as its value.
        const caption = /** @type {HTMLElement} */ (figure.querySelector("figcaption"));
        caption.id = `${collector}-${panel}`;
        plot.tabIndex = 0;
        plot.setAttribute("role", "slider");
        plot.setAttribute("aria-labelledby", `${collector} ${caption.id}`);
        plot.setAttribute("aria-valuemin", "0");
        plot.setAttribute("aria-valuemax", "0");
        plot.setAttribute("aria-valuenow", "0");
        plot.setAttribute("aria-valuetext", "no collections yet");
        plot.addEventListener("focus", () => {
          // A click focuses a panel too, but the pointer reads it then.
          if (plot.matches(":focus-visible")) this.#press(collector, panel, plot, null);
        });
        plot.addEventListener("blur", () => {
          if (this.#keys?.plot !== plot) return;
          this.#keys = null;
          this.#hover();
        });
        plot.addEventListener("keydown", (event) => {
          const { key, altKey, ctrlKey, metaKey } = /** @type {KeyboardEvent} */ (event);
          // Alt with an arrow goes back a page.
          if (altKey || ctrlKey || metaKey) return;
          // Escape hides the tooltip until the next key.
          if (key === "Escape" && this.#keys?.plot === plot && !this.#keys.hidden) {
            this.#keys.hidden = true;
            this.#hover();
          }
          if (!KEYS.includes(key)) return;
          // Home and End would scroll the page, and the arrows too.
          event.preventDefault();
          this.#press(collector, panel, plot, key);
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
    const picks = /** @type {HTMLElement} */ (root.querySelector(".picks"));
    if (this.hasAttribute("editor")) {
      const style = document.createElement("style");
      style.textContent = EDITOR_STYLE + SOURCE_STYLE + LINK_STYLE;
      root.append(style);
      // The legend's editor takes the place of the plain legend, which comes
      // back beside the workload source.
      const editing = document.createElement("div");
      editing.className = "editing";
      /** @type {HTMLElement} */ (root.querySelector(".key-list")).append(editing);
      /** @type {HTMLElement} */ (root.querySelector(".plain")).hidden = true;
      this.#editor = new Editor(editing, { change: () => this.#start(), stop: stopRuns });
      const panel = document.createElement("div");
      panel.className = "source";
      panel.hidden = true;
      /** @type {HTMLElement} */ (root.querySelector(".frame")).prepend(panel);
      this.#source = new Source(panel, { run: () => this.#runSource(false), stop: stopRuns });
      picks.append(this.#switcher());
      if (this.id) picks.append(this.#sharer());
      picks.hidden = false;
    }
    if (this.#entries.length > 1) {
      const label = /** @type {HTMLElement} */ (root.querySelector(".entries"));
      const select = /** @type {HTMLSelectElement} */ (label.querySelector("select"));
      select.append(...this.#entries.map(({ name, title }) => new Option(title, name)));
      label.hidden = picks.hidden = false;
      select.addEventListener("change", () => this.#choose(select.value, true));
    }
    if (this.#entries.length > 1 || this.#editor) addEventListener("hashchange", () => this.#follow());
    new ResizeObserver(() => this.#schedule()).observe(this);
    // Plot bakes each color into a chart, so the widget draws them again when the theme changes.
    new MutationObserver(() => this.#schedule()).observe(document.documentElement, { attributeFilter: ["data-theme"] });
    // The widget asks the page's one worker for its runs once a reader comes
    // within about a screen of it, or at once if the URL fragment names it
    // (ADR 0009).
    const named = fragment();
    if (this.id && (named.has(this.id) || named.has(linkKey(this.id)))) this.#follow();
    else {
      const near = new IntersectionObserver((seen) => {
        if (!seen.some((entry) => entry.isIntersecting)) return;
        near.disconnect();
        this.#follow();
      }, { rootMargin: "100% 0px" });
      near.observe(this);
    }
  }

  /**
   * Show what the URL fragment names: a link of the widget's own that it did
   * not write, or else the entry of the widget's id.
   */
  #follow() {
    const link = this.#editor && this.id ? fragment().get(linkKey(this.id)) : null;
    if (link && link !== this.#linked) this.#open(link);
    else this.#choose(fragment().get(this.id) ?? "", false);
  }

  /**
   * Open a link: the entry it names, with the request it holds, run at once
   * unless the request holds code, which waits in the workload source for Run.
   * When the widget cannot read a link, it shows the entry as the page gives
   * it, with the reason.
   * @param {string} link the link's request, as the URL fragment holds it
   */
  async #open(link) {
    this.#linked = link;
    const name = fragment().get(this.id) ?? "";
    let request;
    try {
      request = await decode(link);
    } catch (error) {
      this.#choose(name, false);
      this.#fail(error instanceof Error ? error.message : String(error));
      return;
    }
    // A later link came while this one opened.
    if (link !== this.#linked) return;
    const entry = this.#entries.find((offered) => offered.name === name) ?? this.#entries[0];
    entry.request = request;
    if (holdsCode(request)) this.#held.add(entry);
    else this.#held.delete(entry);
    this.#copy.disabled = false;
    this.#enter(entry);
  }

  /**
   * Show the entry of that name, or the first if the widget offers none by it, and
   * start its runs.
   * @param {string} name
   * @param {boolean} picked whether the reader picked it, which the URL fragment
   *   then records
   */
  #choose(name, picked) {
    const entry = this.#entries.find((offered) => offered.name === name) ?? this.#entries[0];
    if (entry === this.#entry) return;
    if (picked && this.id) {
      const pairs = fragment();
      pairs.set(this.id, entry.name);
      // The link held the last entry's request, and the new entry's runs write their own.
      pairs.delete(linkKey(this.id));
      history.replaceState(null, "", `#${pairs}`);
    }
    this.#enter(entry);
  }

  /**
   * Show the entry and start its runs, or, if a link with code brought its
   * request, show its workload source and wait for the reader to press Run,
   * with the switch to the legend shut until then. The last entry's controls,
   * figures and charts go at once, and its request keeps the values its
   * controls set, for when it is shown again.
   * @param {Entry} entry
   */
  #enter(entry) {
    this.#entry = entry;
    const root = /** @type {ShadowRoot} */ (this.shadowRoot);
    /** @type {HTMLSelectElement} */ (root.querySelector(".entries select")).value = entry.name;
    const row = /** @type {HTMLElement} */ (this.#row());
    row.replaceChildren();
    row.hidden = true;
    this.#sliders.clear();
    for (const part of root.querySelectorAll(".graph, .key-list")) /** @type {HTMLElement} */ (part).hidden = true;
    for (const chart of root.querySelectorAll(".chart")) chart.replaceChildren();
    this.#records = { legacy: [], incremental: [] };
    this.#figures = {};
    this.#drawn = entry.request;
    for (const part of root.querySelectorAll("[data-mark]")) delete /** @type {HTMLElement} */ (part).dataset.mark;
    entry.marks.forEach((mark, i) => {
      const [kind, name] = mark.split(".");
      const part = kind === "figure"
        ? root.querySelector(`[data-figure="${name}"]`)
        : root.querySelector(`[data-collector="${kind}"] [data-panel="${name}"]`);
      /** @type {HTMLElement} */ (part).dataset.mark = String(i + 1);
    });
    if (this.#held.has(entry)) {
      const source = /** @type {Source} */ (this.#source);
      try {
        source.show(entry);
      } catch {
        this.#fail(FOREIGN);
        return;
      }
      for (const input of root.querySelectorAll(".modes input")) /** @type {HTMLInputElement} */ (input).disabled = true;
      // The last entry's runs would draw over the empty charts.
      dropRuns(this.#name);
      this.#view("source");
      source.note(HELD);
      // The address holds the link again, if a pick of another entry took it.
      this.#share(entry, entry.request);
      return;
    }
    if (this.#mode === "source") this.#source?.show(entry);
    this.#schedule();
    this.#start();
  }

  /**
   * Ask for both runs of the request as the controls have set it, or of another
   * request for the entry, in place of any runs asked for before. The charts keep
   * the old runs until the new runs' first records arrive. If the widget kept the
   * request's runs, they draw at once, and the worker hears nothing.
   * @param {any} sent the request, the entry's own unless another is given
   * @param {() => void} made what follows once the worker spells the request out
   */
  #start(sent = /** @type {Entry} */ (this.#entry).request, made = () => {}) {
    const entry = /** @type {Entry} */ (this.#entry);
    let request = structuredClone(sent);
    let fresh = true;
    // The figures the notes compare against: the runs the charts showed, once they finished.
    this.#before = this.#finished;
    this.#finished = null;
    const root = /** @type {ShadowRoot} */ (this.shadowRoot);
    /** @type {HTMLElement} */ (root.querySelector(".error")).hidden = true;
    // What the worker sends for the request, which the widget keeps once both
    // runs finish.
    /** @type {Omit<Runs, "records" | "figures"> | null} */
    let spelled = null;
    /** @type {{ legacy: Record[], incremental: Record[] }} */
    const records = { legacy: [], incremental: [] };
    /** @type {{ legacy?: Figures, incremental?: Figures }} */
    const figures = {};
    /** @type {Required<Listener>} */
    const listener = {
      controls: (controls, expanded, graph) => {
        spelled = { controls, request: expanded, graph };
        // A request that names a preset, carries a workload source or leaves
        // out the constants comes back spelled out: its workload, run length and
        // constants, which the controls and the editors edit from then on.
        const preset = "preset" in request;
        if (preset || "source" in request || !("constants" in request)) {
          request = expanded;
          entry.request = structuredClone(expanded);
          if ("preset" in this.#drawn) this.#drawn = request;
        }
        this.#editor?.edit(entry.request);
        if (preset && this.#mode === "source") this.#source?.show(entry);
        // Either editor can show the request once the worker has spelled it out.
        for (const input of root.querySelectorAll(".modes input")) /** @type {HTMLInputElement} */ (input).disabled = false;
        this.#held.delete(entry);
        made();
        this.#share(entry, request);
        this.#show(controls);
        this.#graph(graph);
      },
      records: (collector, part, last) => {
        if (fresh) {
          fresh = false;
          this.#drawn = request;
          this.#records = records;
          this.#figures = figures;
        }
        records[collector].push(...part);
        figures[collector] = last;
        this.#schedule();
      },
      done: () => {
        const { legacy, incremental } = figures;
        if (!legacy || !incremental) return;
        if (this.#figures === figures) this.#finished = { legacy, incremental };
        if (spelled) this.#kept.keep(request, entry.controls, { ...spelled, records, figures: { legacy, incremental } });
      },
      // The legend's editor shows a refusal beside the field the reader changed,
      // and the source under its box, setting back a switch that waited on it.
      error: (message) => {
        if (this.#mode === "legend") return this.#editor?.fail(message) || this.#fail(message);
        this.#view("source");
        return this.#source?.fail(message) || this.#fail(message);
      },
    };
    const kept = this.#kept.find(sent, entry.controls);
    if (!kept) {
      requestRuns(this.#name, request, listener, entry.controls);
      return;
    }
    // Runs the widget kept go through the same steps as the worker's, at once,
    // and the runs asked for last would draw over them.
    dropRuns(this.#name);
    listener.controls(kept.controls, structuredClone(kept.request), kept.graph);
    for (const collector of COLLECTORS) listener.records(collector, kept.records[collector], kept.figures[collector]);
    listener.done();
  }

  /**
   * Write the request the worker took for the entry into the URL fragment, as
   * the link that opens its runs, unless a later run's link gets there first.
   * @param {Entry} entry
   * @param {any} request
   */
  async #share(entry, request) {
    if (!this.#editor || !this.id) return;
    const turn = ++this.#shares;
    const link = await encode(request);
    if (turn !== this.#shares) return;
    const pairs = fragment();
    pairs.set(this.id, entry.name);
    pairs.set(linkKey(this.id), link);
    this.#linked = link;
    history.replaceState(null, "", `#${pairs}`);
    this.#copy.disabled = false;
  }

  /** The button that copies the link, which waits for the first one. */
  #sharer() {
    const share = document.createElement("span");
    share.className = "share";
    const said = document.createElement("span");
    said.setAttribute("role", "status");
    /** @type {ReturnType<typeof setTimeout> | undefined} */
    let clear;
    Object.assign(this.#copy, { type: "button", textContent: "Copy link", disabled: true });
    this.#copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(location.href);
        said.textContent = "Copied";
      } catch {
        said.textContent = "Copy it from the address bar";
      }
      clearTimeout(clear);
      clear = setTimeout(() => { said.textContent = ""; }, 3000);
    });
    share.append(this.#copy, said);
    return share;
  }

  /** The switch between the legend's editor and the source, which waits for the worker's first request. */
  #switcher() {
    const group = document.createElement("div");
    group.className = "modes";
    group.setAttribute("role", "radiogroup");
    group.setAttribute("aria-label", "Edit the workload");
    group.append("Edit");
    for (const [mode, text] of /** @type {const} */ ([["legend", "in the legend"], ["source", "as Python"]])) {
      const label = document.createElement("label");
      const input = document.createElement("input");
      Object.assign(input, { type: "radio", name: "mode", value: mode, checked: mode === "legend", disabled: true });
      input.addEventListener("change", () => this.#switch(mode));
      label.append(input, text);
      group.append(label);
    }
    return group;
  }

  /**
   * Switch to the legend's editor or to the source. The source shows the reader's
   * text while the legend has changed nothing, and the request written afresh
   * once it has. Text that has not run runs first, and the legend shows the
   * workload it makes, unless it fails, when the source keeps it and its error.
   * @param {"legend" | "source"} mode
   */
  #switch(mode) {
    const source = /** @type {Source} */ (this.#source);
    if (mode === "source") source.show(/** @type {Entry} */ (this.#entry));
    // The source stays while its text runs, and a failure puts the switch back.
    if (mode === "legend" && source.changed) this.#runSource(true);
    else this.#view(mode);
  }

  /** Show one editor and hide the other. */
  #view(/** @type {"legend" | "source"} */ mode) {
    this.#mode = mode;
    const root = /** @type {ShadowRoot} */ (this.shadowRoot);
    for (const input of root.querySelectorAll(".modes input")) {
      /** @type {HTMLInputElement} */ (input).checked = /** @type {HTMLInputElement} */ (input).value === mode;
    }
    const legend = mode === "legend";
    /** @type {HTMLElement} */ (root.querySelector(".plain")).hidden = legend;
    /** @type {HTMLElement} */ (root.querySelector(".editing")).hidden = !legend;
    /** @type {HTMLElement} */ (root.querySelector(".source")).hidden = legend;
    this.toggleAttribute("source", !legend);
    // The panels' width changes with the source beside them.
    this.#schedule();
  }

  /**
   * Run the source's text for the entry, and once the worker sends back the
   * request it makes, switch to the legend, if `legend`.
   * @param {boolean} legend
   */
  #runSource(legend) {
    const entry = /** @type {Entry} */ (this.#entry);
    const source = /** @type {Source} */ (this.#source);
    const text = source.text;
    this.#start({ source: text, every: entry.request.every }, () => {
      source.ran(entry, text);
      // Unless the reader picked the source again while the text ran.
      const picked = /** @type {ShadowRoot} */ (this.shadowRoot).querySelector(".modes input:checked");
      if (legend && /** @type {HTMLInputElement | null} */ (picked)?.value === "legend") this.#view("legend");
    });
  }

  /**
   * Show each control with the range its request allows, in its group: the
   * workload's, the collector settings', or the collector constants' under them.
   */
  #show(/** @type {Control[]} */ controls) {
    const row = /** @type {HTMLElement} */ (this.#row());
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
        const note = YOUNG.includes(path) ? document.createElement("span") : null;
        if (note) {
          note.className = "note";
          control.append(note);
        }
        const group = this.#group(path);
        // The constants' toggle stays last in the collector settings' group.
        group.insertBefore(control, group.querySelector(":scope > details"));
        const made = {
          input,
          note,
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
          this.#young();
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
    this.#young();
  }

  /**
   * The group a control's path puts it in, made for the first control that
   * needs it: the workload's, the collector settings', or the collector
   * constants', which a toggle opens under the settings.
   * @param {string} path
   * @returns {HTMLElement}
   */
  #group(path) {
    const row = /** @type {HTMLElement} */ (this.#row());
    const [first] = path.split(".");
    const kind = first === "settings" || first === "constants" ? first : "workload";
    const found = /** @type {HTMLElement | null} */ (row.querySelector(`[data-group="${kind}"]`));
    if (found) return found;
    const group = document.createElement("div");
    group.className = "group";
    group.dataset.group = kind;
    group.setAttribute("role", "group");
    if (kind === "constants") {
      group.setAttribute("aria-label", "Collector constants");
      const toggle = document.createElement("details");
      // Under the collector settings, closed unless the reader opened it, or
      // open in their place where the entry shows none (ADR 0017).
      const settings = /** @type {Entry} */ (this.#entry).controls.some((control) => control.startsWith("settings."));
      toggle.open = this.#constantsOpen ?? !settings;
      const summary = document.createElement("summary");
      // PROTOTYPE (guide fit): the reader's choice holds for every entry after.
      summary.addEventListener("click", () => {
        this.#constantsOpen = !toggle.open;
      });
      summary.textContent = "Collector constants, which no Python API changes";
      toggle.append(summary, group);
      (settings ? this.#group("settings") : row).append(toggle);
      return group;
    }
    const heading = document.createElement("h3");
    heading.textContent = kind === "settings" ? "Collector settings" : "Workload";
    group.setAttribute("aria-label", heading.textContent);
    group.append(heading);
    // The workload's group comes first.
    if (kind === "workload") row.prepend(group);
    else row.append(group);
    return group;
  }

  /**
   * Say what threshold0 and threshold1 make of the incremental collector's
   * young generation, as their sliders stand.
   */
  #young() {
    const [zero, one] = YOUNG.map((path) => this.#sliders.get(path));
    if (!zero && !one) return;
    const { settings } = /** @type {Entry} */ (this.#entry).request;
    const words = describeYoung(
      zero ? Number(zero.input.value) : settings.threshold0,
      one ? Number(one.input.value) : settings.threshold1,
    );
    if (zero?.note) zero.note.textContent = words.nursery;
    if (one?.note) one.note.textContent = words.aging;
  }

  /**
   * Draw the request's object graph: each structure's sample under sys or its
   * frame, placed by a force layout that pulls the roots to the top, and number
   * each structure's first object as the legend under the controls lists it.
   * @param {Graph} graph
   */
  #graph(graph) {
    const root = /** @type {ShadowRoot} */ (this.shadowRoot);
    const frame = /** @type {HTMLElement} */ (root.querySelector(".graph"));
    const keys = /** @type {HTMLElement} */ (root.querySelector(".key-list"));
    const { nodes, links } = network(graph);
    frame.hidden = !nodes.length;
    // The editor stays, so that a workload without structures can gain one.
    keys.hidden = !nodes.length && !this.#editor;
    // The plain legend, which comes back beside the workload source on the
    // playground.
    const list = /** @type {HTMLElement} */ (keys.querySelector(".plain ol"));
    list.replaceChildren(...graph.structures.map((structure, i) => {
      const item = document.createElement("li");
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = String(i + 1);
      item.append(badge, describe(structure));
      return item;
    }));
    /** @type {HTMLElement} */ (keys.querySelector(".plain .churn")).textContent = describeChurn(graph.churn);
    this.#editor?.describe(graph);
    if (!nodes.length) return;
    // The layout's own copies, which the simulation moves and links in place. The
    // roots keep to a line along the top, and what they hold hangs below them.
    /** @type {(import("./graph.js").Node & { x?: number, y?: number, fy?: number })[]} */
    const placed = nodes.map((node) => (node.root ? { ...node, fy: -GRAPH.height / 2 } : { ...node }));
    const byKey = (/** @type {{ key: string }} */ node) => node.key;
    forceSimulation(placed)
      .force("link", forceLink(links.map((link) => ({ ...link }))).id(byKey)
        .distance((/** @type {{ kind: string }} */ link) => (link.kind === "held" ? 36 : 16)).strength(0.9))
      .force("charge", forceManyBody().strength(-22))
      // A root's box is 34 px wide, so roots keep apart further than dots do.
      .force("collide", forceCollide((/** @type {{ root?: string }} */ node) => (node.root ? 20 : 5)))
      .force("x", forceX(0).strength(0.04))
      .force("y", forceY(GRAPH.height / 4).strength(0.1))
      .stop()
      .tick(400);
    const laid = placed.map(({ key, x = 0, y = 0 }) => ({ key, x, y }));
    const places = fit(laid, GRAPH.width, GRAPH.height, GRAPH.margin, GRAPH.most);
    const at = (/** @type {string} */ key) => /** @type {[number, number]} */ (places.get(key));
    /**
     * @param {string} name
     * @param {{ [attribute: string]: string | number }} attributes
     * @param {Element} parent
     */
    const make = (name, attributes, parent) => {
      const element = document.createElementNS(SVG, name);
      for (const [attribute, value] of Object.entries(attributes)) element.setAttribute(attribute, String(value));
      parent.append(element);
      return element;
    };
    const svg = document.createElementNS(SVG, "svg");
    svg.setAttribute("viewBox", `0 0 ${GRAPH.width} ${GRAPH.height}`);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "A sample of the object graph, which the legend describes");
    const both = new Set(links.map(({ source, target }) => `${source} ${target}`));
    for (const { source, target, kind } of links) {
      const [x1, y1] = at(source), [x2, y2] = at(target);
      if (source === target) {
        make("circle", { cx: x1, cy: y1 - 6, r: 5, class: kind }, svg);
      } else if (kind !== "held" && both.has(`${target} ${source}`)) {
        // A pair of links both ways bends apart, so both show.
        const bend = (source < target ? 5 : -5) / (Math.hypot(x2 - x1, y2 - y1) || 1);
        const mx = (x1 + x2) / 2 - (y2 - y1) * bend, my = (y1 + y2) / 2 + (x2 - x1) * bend;
        make("path", { d: `M${x1},${y1} Q${mx},${my} ${x2},${y2}`, class: kind }, svg);
      } else {
        make("line", { x1, y1, x2, y2, class: kind }, svg);
      }
    }
    for (const node of nodes) {
      const [x, y] = at(node.key);
      if (node.root) {
        const group = make("g", { class: "root" }, svg);
        make("rect", { x: x - 17, y: y - 8, width: 34, height: 16, rx: 3 }, group);
        make("text", { x, y }, group).textContent = node.root;
      } else if (node.first) {
        const group = make("g", { class: "first" }, svg);
        make("circle", { cx: x, cy: y, r: 7 }, group);
        make("text", { x, y }, group).textContent = String(Number(node.structure) + 1);
      } else {
        make("circle", { cx: x, cy: y, r: 3, class: "object" }, svg);
      }
    }
    frame.replaceChildren(svg);
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

  /** PROTOTYPE (guide fit): a row of controls the page put elsewhere, or the widget's own. */
  #row() {
    return this.protoControls ?? /** @type {ShadowRoot} */ (this.shadowRoot).querySelector(".controls");
  }

  /** PROTOTYPE (guide fit): redraw with a lane, work and budget height of the page's. */
  protoHeights({ lane, work, budget }) {
    LANE_HEIGHT = lane;
    LANE_TICKS = lane < 30 ? 1 : lane < 40 ? 2 : 3;
    HEIGHTS.work = work;
    HEIGHTS.budget = budget;
    HEAP_HEIGHT = (LANES.legacy.length + 1) * (LANE_HEIGHT + 2 * LANE_MARGIN) - 2 * LANE_MARGIN + MARGINS.marginTop + MARGINS.marginBottom;
    this.style.setProperty("--proto-heap", `${HEAP_HEIGHT}px`);
    this.style.setProperty("--proto-work", `${work}px`);
    this.style.setProperty("--proto-budget", `${budget}px`);
    this.#schedule();
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
      const before = this.#before;
      const was = before && COLLECTORS.map((collector) => read(before[collector], collector));
      const wasKnown = (was ?? []).filter((value) => value !== undefined);
      COLLECTORS.forEach((collector, j) => {
        const value = values[j];
        const text = value === undefined ? "–" : show(value, known);
        this.#values[i][collector].textContent = text;
        const earlier = was?.[j];
        const then = earlier === undefined ? text : show(earlier, wasKnown);
        this.#was[i][collector].textContent = value === undefined || then === text ? "" : `was ${then}`;
      });
    });

    // A request that names a preset has no run length until the worker spells it
    // out, and the charts' clock needs one. Nor has a link still opening.
    if (!this.#drawn || "preset" in this.#drawn) {
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
    const workMax = workEnd(COLLECTORS.map((c) => this.#records[c]), binKb);
    const works = { legacy: work(this.#records.legacy, binKb, workMax), incremental: work(this.#records.incremental, binKb, workMax) };
    // The legend names the full collections' marks only for runs that make some.
    const fulls = COLLECTORS.some((c) => this.#records[c].some((record) => FULL.includes(record[KIND])));
    for (const entry of /** @type {ShadowRoot} */ (this.shadowRoot).querySelectorAll(".legend [data-full]")) {
      /** @type {HTMLElement} */ (entry).hidden = !fulls;
    }
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
      // A bin cut at the scale's end, as shutdown's can be: two slanted gaps
      // across its bar below the end, and its whole work above it.
      const cut = cuts(records, binKb, workMax);
      const objectsPerPx = workMax / (HEIGHTS.work - MARGINS.marginTop - MARGINS.marginBottom);
      const gaps = cut.flatMap(({ x1, x2 }) => [7, 12].map((below) => ({
        x1: x1 + inset / pxPerMb, x2: x2 - inset / pxPerMb,
        y1: workMax - (below + 2) * objectsPerPx, y2: workMax - (below - 2) * objectsPerPx,
      })));
      chart(column, "work", Plot.plot({
        ...frame(HEIGHTS.work),
        ariaLabel: `${TITLES[collector]}: work per bin, as marked, survived and freed, full collections' faded above`
          + (cut.length ? ", a bin past the scale cut at its end" : ""),
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
          Plot.link(gaps, { x1: "x1", y1: "y1", x2: "x2", y2: "y2", stroke: token("surface"), strokeWidth: 2 }),
          Plot.text(cut, {
            x: (/** @type {{ x1: number, x2: number }} */ d) => (d.x1 + d.x2) / 2, y: workMax,
            text: (/** @type {{ work: number }} */ d) => compact(d.work), dy: -4, lineAnchor: "bottom", fill: token("text-secondary"),
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
   * Read a panel from the keys: move the clock the pointer or the keys last read,
   * as `key` says, or keep it on focus; with no clock yet, start at the panel's
   * first collection or bin. The marks follow the keys until the pointer moves,
   * and the panel tells a screen reader its tooltip's readout. Only a key or
   * focus changes what it says, never a redraw while runs stream.
   * @param {Collector} collector
   * @param {string} panel
   * @param {HTMLElement} plot
   * @param {string | null} key null on focus
   */
  #press(collector, panel, plot, key) {
    const layout = this.#layout;
    if (!layout) return;
    const { binKb, runLength, xMax } = layout;
    let kb = this.#clock;
    if (kb === null) kb = step("Home", 0, panel, this.#records[collector], binKb, runLength);
    else if (key) kb = step(key, kb, panel, this.#records[collector], binKb, runLength);
    if (kb === null) return;
    this.#clock = kb;
    this.#keys = { panel, plot, hidden: false };
    this.#pointer = this.#rest = null;
    clearTimeout(this.#dwell);
    const readout = this.#hover();
    plot.setAttribute("aria-valuemax", String(xMax));
    plot.setAttribute("aria-valuenow", String(Math.min(kb, runLength) / 1000));
    if (readout) plot.setAttribute("aria-valuetext", spoken(...readout()));
  }

  /** The clock, in kB, `x` px across a panel reads, or null past its plot. */
  #kbAt(/** @type {number} */ x) {
    const layout = this.#layout;
    if (!layout) return null;
    const { width, runLength } = layout;
    const { marginLeft, marginRight } = MARGINS;
    if (x < marginLeft - SLACK || x > width - marginRight + SLACK) return null;
    return Math.min(Math.max(0, ((x - marginLeft) / (width - marginLeft - marginRight)) * runLength), runLength);
  }

  /**
   * Where the marks read: the panel under the pointer, or else the one the keys
   * read, the clock, in kB, and the height of the panel's tooltips, in px, or
   * null while they hide. Null when nothing reads.
   * @returns {{ panel: string, kb: number, y: number | null } | null}
   */
  #where() {
    const layout = this.#layout, pointer = this.#pointer, keys = this.#keys, clock = this.#clock;
    if (!layout) return null;
    if (pointer) {
      const kb = this.#kbAt(pointer.x);
      if (kb === null) return null;
      return { panel: pointer.panel, kb, y: this.#rest && !this.#rest.hidden ? pointer.y : null };
    }
    if (!keys || clock === null) return null;
    // A clock from a longer run reads this run's end.
    return { panel: keys.panel, kb: Math.min(clock, layout.runLength), y: keys.hidden ? null : keys.plot.clientHeight / 2 };
  }

  /**
   * Mark the clock the pointer or the keys read in every panel of both columns,
   * from the records drawn so far: both runs share the clock. The panel they
   * read shows its tooltip in both columns, once the pointer rests or at once
   * for the keys, and until Escape. A redraw leaves the marks alone and calls
   * this again, so they hold while runs stream. Returns the readout of the
   * panel the keys read, if it has one.
   * @returns {(() => Readout) | null}
   */
  #hover() {
    const root = /** @type {ShadowRoot} */ (this.shadowRoot);
    for (const mark of root.querySelectorAll(".crosshair, .outline, .tip")) /** @type {HTMLElement} */ (mark).hidden = true;
    const where = this.#where();
    if (!where) return null;
    const { panel: read, kb, y } = where;
    /** @type {(() => Readout) | null} */
    let keyed = null;
    for (const collector of COLLECTORS) {
      for (const element of this.#column(collector).querySelectorAll(".plot")) {
        const plot = /** @type {HTMLElement} */ (element);
        const panel = /** @type {string} */ (/** @type {HTMLElement} */ (plot.closest("figure")).dataset.panel);
        const readout = this.#mark(collector, panel, plot, kb, panel === read ? y : null);
        if (plot === this.#keys?.plot) keyed = readout;
      }
    }
    return keyed;
  }

  /**
   * Mark what one panel reads at clock `kb`, in kB: the heap or the budget at the
   * nearest collection, with a crosshair, or the work of the bin that holds it,
   * with an outline round its bar. Given a height `y`, in px, show its tooltip
   * there too. Returns what the tooltip reads out, or null before the panel has
   * a collection to read.
   * @param {Collector} collector
   * @param {string} panel
   * @param {HTMLElement} plot
   * @param {number} kb
   * @param {number | null} y
   * @returns {(() => Readout) | null}
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
    // What the tooltip reads out, built only when it shows or a screen reader hears it.
    /** @type {() => Readout} */
    let content;
    if (panel === "work") {
      const at = workAt(records, binKb, kb);
      const total = [...at.automatic, ...at.full].reduce((sum, part) => sum + part, 0);
      const inset = Math.max(1, (px(at.x2) - px(at.x1) - BAR) / 2);
      [left, right] = [px(at.x1) + inset - 2, px(at.x2) - inset + 2];
      // A bar cut at the scale's end stops there, and so does its outline.
      const top = marginTop + (1 - Math.min(total, workMax) / workMax) * (HEIGHTS.work - marginTop - marginBottom) - 2;
      Object.assign(mark.style, { left: `${left}px`, width: `${right - left}px`, top: `${top}px`, height: `${HEIGHTS.work - marginBottom - top}px` });
      mark.hidden = !total;
      const fulls = at.full.some(Boolean);
      content = () => [
        `${megabytes(at.x1)}–${megabytes(at.x2)} MB allocated`,
        fulls ? ["objects", "automatic", "full"] : ["objects"],
        PARTS.map((part, i) => [part, `var(--${part})`, (fulls ? [at.automatic[i], at.full[i]] : [at.automatic[i]]).map(whole)]),
      ];
    } else {
      const at = panel === "heap" ? heapAt(records, kb) : budgetAt(records, kb);
      if (!at) return null;
      left = right = px(at.clock / 1000);
      Object.assign(mark.style, { left: `${left}px`, top: `${marginTop}px`, height: `${plot.clientHeight - marginTop - marginBottom}px` });
      mark.hidden = false;
      const where = `${collections(at.kinds)} at ${megabytes(at.clock / 1000)} MB`;
      if ("budget" in at) {
        content = () => [where, ["objects"], [["work budget", "var(--text-primary)", [whole(at.budget)]]]];
      } else {
        const { before, after } = at;
        /** @returns {[string, string, string[]]} */
        const row = (/** @type {string} */ name, /** @type {string} */ color, /** @type {(read: typeof before) => number} */ value) =>
          [name, color, [hundredths(value(before)), hundredths(value(after))]];
        content = () => [where, ["MB", "before", "after"], [
          row("heap", "var(--text-muted)", (read) => read.heap),
          row("reachable", "var(--text-primary)", (read) => read.reachable),
          row("uncollected garbage", "transparent", (read) => read.garbage),
          ...SPACES[collector].map((space, i) => row(space, `var(--${space})`, (read) => read.spaces[i])),
        ]];
      }
    }
    if (y === null) return content;
    tip.replaceChildren(...readout(...content()));
    tip.hidden = false;
    // Right of the mark, or left of it where the chart ends, or over the mark
    // where neither side has room; level with the pointer, inside the panel.
    const toRight = right + GAP + tip.offsetWidth <= width;
    tip.style.left = `${toRight ? right + GAP : Math.max(0, left - GAP - tip.offsetWidth)}px`;
    tip.style.top = `${Math.min(Math.max(0, y - tip.offsetHeight / 2), plot.clientHeight - tip.offsetHeight)}px`;
    return content;
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

/** Put the charts a redraw made in their panel, in place of the ones before. */
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
