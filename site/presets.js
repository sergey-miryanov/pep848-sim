// @ts-check
// The presets page: each preset's collections under a collector over its
// benchmark's workers', from the plot.json `just site` writes beside this
// script (ADR 0021). A panel per generation and kind of collection, as
// compare_presets.py files them, and the MB its worker had allocated before a
// collection along the x-axis, or its number in the worker where a trace has no
// allocation clock. Counts are real objects.
// @ts-expect-error: an editor cannot fetch Plot's types from jsDelivr.
import * as Plot from "https://cdn.jsdelivr.net/npm/@observablehq/plot@0.6.17/+esm";

/**
 * A collection: its number in its worker, its panel, the kB allocated before it,
 * and the series it has a value for.
 * @typedef {{ n: number, panel: string, kb?: number, examined?: number, freed?: number, yield?: number, work?: number, budget?: number }} Point
 */
/** @typedef {"examined" | "freed" | "yield" | "work" | "budget"} Series */
/** @typedef {{ preset: string, collector: string, workers: Point[][], run: Point[] }} Plotted */
/**
 * A worker's collections as plot.json holds them, a column to a series: each
 * panel by its place in the file's panels, and null where a collection has no
 * value. A series no collection has a value for has no column.
 * @typedef {{ n: number[], panel: number[], kb?: (number | null)[] } & { [key in Series]?: (number | null)[] }} Columns
 */
/**
 * The real objects one simulated object stands for travel as `object`.
 * @typedef {{ panels: string[], object: number, plots: { preset: string, collector: string, workers: Columns[], run: Columns }[] }} File
 */

/** @type {{ key: Series, label: string }[]} */
const SERIES = [
  { key: "examined", label: "examined" },
  { key: "freed", label: "freed" },
  { key: "yield", label: "running yield" },
  // Only old collections carry it.
  { key: "work", label: "work" },
];
const HEIGHT = 180;
// Past this many collections a worker on average, a panel draws lines alone.
const DOTS = 50;
// A chart's scale spans at least this many simulated objects, so that a gap of
// a few real objects looks as small as it is.
const FLOOR = 10;

const presetSelect = /** @type {HTMLSelectElement} */ (document.getElementById("preset"));
const collectorSelect = /** @type {HTMLSelectElement} */ (document.getElementById("collector"));
const panels = /** @type {HTMLElement} */ (document.getElementById("panels"));

/** @type {File} */
const file = await (await fetch(new URL("plot.json", import.meta.url))).json();
/** @type {Series[]} */
const KEYS = ["examined", "freed", "yield", "work", "budget"];
/**
 * A worker's collections, out of their columns.
 * @param {Columns} columns
 * @returns {Point[]}
 */
const points = (columns) => columns.n.map((n, i) => {
  /** @type {Point} */
  const point = { n, panel: file.panels[columns.panel[i]] };
  const kb = columns.kb?.[i];
  if (kb !== undefined && kb !== null) point.kb = kb;
  for (const key of KEYS) {
    const value = columns[key]?.[i];
    if (value !== undefined && value !== null) point[key] = value;
  }
  return point;
});
/** @type {Plotted[]} */
const plotted = file.plots.map(({ preset, collector, workers, run }) => ({
  preset, collector, workers: workers.map(points), run: points(run),
}));

/** @param {string[]} names */
const unique = (names) => [...new Set(names)];
for (const [select, names] of /** @type {const} */ ([
  [presetSelect, unique(plotted.map((p) => p.preset))],
  [collectorSelect, unique(plotted.map((p) => p.collector))],
])) {
  select.replaceChildren(...names.map((name) => new Option(name, name)));
}
// The hash keeps the choice across reloads: #preset/collector.
const [presetHash, collectorHash] = decodeURIComponent(location.hash.slice(1)).split("/");
if (presetHash) presetSelect.value = presetHash;
if (collectorHash) collectorSelect.value = collectorHash;

const draw = () => {
  location.hash = `${presetSelect.value}/${collectorSelect.value}`;
  const chosen = plotted.find((p) => p.preset === presetSelect.value && p.collector === collectorSelect.value);
  if (!chosen) return;
  const { workers, run } = chosen;
  /** @type {HTMLElement} */ (document.getElementById("workers")).textContent =
    `the benchmark's ${workers.length} workers`;
  const style = getComputedStyle(document.documentElement);
  const token = (/** @type {string} */ name) => style.getPropertyValue(`--${name}`).trim();
  // MB allocated, where every collection carries it, else the collection's number.
  const clocked = [run, ...workers].every((points) => points.every((p) => p.kb !== undefined));
  const at = (/** @type {Point} */ p) => (clocked ? /** @type {number} */ (p.kb) / 1000 : p.n);
  // Every panel shares the worker's length, so a collection lines up across them.
  const xMax = Math.max(...[run, ...workers].flatMap((points) => points.map(at)));
  const names = unique([run, ...workers].flatMap((points) => points.map((p) => p.panel))).sort();

  /**
   * @param {HTMLElement} row
   * @param {string} caption
   * @param {Series} key
   * @param {(p: Point) => boolean} keep
   * @returns {(() => void) | null} what draws the chart once every row is laid
   *   out, so that it takes its figure's width; null without a value to draw,
   *   where an empty figure keeps the series' column
   */
  const chart = (row, caption, key, keep) => {
    const has = (/** @type {Point} */ p) => keep(p) && p[key] !== undefined;
    const theirs = workers.flatMap((points, worker) => points.filter(has).map((p) => ({ ...p, worker })));
    const ours = run.filter(has);
    const figure = document.createElement("figure");
    row.append(figure);
    if (!theirs.length && !ours.length) return null;
    figure.append(Object.assign(document.createElement("figcaption"), { textContent: caption }));
    const dots = theirs.length / workers.length <= DOTS;
    const share = key === "yield";
    const y = { x: at, y: key };
    // The run moves a simulated object at a time (ADR 0002): a band that wide
    // either side of its line. Its running yield moves by one over all the panel
    // has examined so far. Only the budget runs below zero.
    let examined = 0;
    const band = ours.map((p) => {
      examined += p.examined ?? 0;
      const step = share ? (examined ? file.object / examined : 0) : file.object;
      const value = /** @type {number} */ (p[key]);
      return { ...p, low: key === "budget" ? value - step : Math.max(0, value - step), high: value + step, step };
    });
    const values = [...theirs, ...ours].map((p) => /** @type {number} */ (p[key]));
    const floor = FLOOR * Math.max(0, ...band.map((p) => p.step));
    const domain = [Math.min(0, ...values), Math.max(floor, ...values, ...band.map((p) => p.high))];
    return () => figure.append(Plot.plot({
      width: figure.clientWidth, height: HEIGHT, marginLeft: 48,
      style: { background: "transparent", color: token("text-muted"), fontFamily: "inherit", fontSize: "11px" },
      x: { domain: [0, xMax], label: clocked ? "MB allocated in the worker" : "collection in the worker" },
      y: { domain, nice: true, label: null, tickFormat: share ? ".2~p" : "~s" },
      ariaLabel: caption,
      marks: [
        Plot.gridY({ stroke: token("grid"), strokeOpacity: 1 }),
        Plot.areaY(band, { x: at, y1: "low", y2: "high", fill: token("run"), fillOpacity: 0.2 }),
        Plot.lineY(theirs, { ...y, z: "worker", stroke: token("workers"), strokeOpacity: 0.35, strokeWidth: 1 }),
        dots ? Plot.dot(theirs, { ...y, r: 2, fill: token("workers"), fillOpacity: 0.35 }) : null,
        Plot.lineY(ours, { ...y, stroke: token("run"), strokeWidth: 2.5 }),
        dots ? Plot.dot(ours, { ...y, r: 4, fill: token("run"), stroke: token("surface"), strokeWidth: 2 }) : null,
        Plot.ruleY([0], { stroke: token("baseline") }),
        Plot.tip(ours, Plot.pointerX({
          ...y, fill: token("surface"), stroke: token("baseline"),
          title: (/** @type {Point} */ p) =>
            `collection ${p.n}${clocked ? ` at ${at(p).toFixed(1)} MB` : ""}\n${caption}: ${format(share, p[key])}`,
        })),
      ],
    }));
  };

  panels.replaceChildren();
  const charts = [];
  for (const name of names) {
    const row = document.createElement("div");
    row.className = "row";
    panels.append(Object.assign(document.createElement("h2"), { textContent: name }), row);
    for (const { key, label } of SERIES) charts.push(chart(row, label, key, (p) => p.panel === name));
  }
  if (chosen.collector === "incremental") {
    const row = document.createElement("div");
    row.className = "row";
    panels.append(
      Object.assign(document.createElement("h2"), { textContent: "work budget at each collection's start" }),
      Object.assign(document.createElement("p"), {
        className: "note",
        textContent: "The branch's old_work and the simulator's budget differ by design (ADR 0003): the branch"
          + " settles the budget once per old collection, the PEP's pseudocode after each increment.",
      }),
      row,
    );
    row.classList.add("whole");
    charts.push(chart(row, "work budget", "budget", () => true));
  }
  for (const paint of charts) paint?.();
};

/**
 * A value as the tooltip reads it: a share, or a count of real objects.
 * @param {boolean} share
 * @param {number | undefined} value
 */
const format = (share, value) =>
  value === undefined ? "-" : share ? `${(value * 100).toFixed(1)}%` : Math.round(value).toLocaleString("en");

presetSelect.addEventListener("change", draw);
collectorSelect.addEventListener("change", draw);
// The charts take their width from the page and their colors from the theme.
let frame = 0;
const redraw = () => {
  cancelAnimationFrame(frame);
  frame = requestAnimationFrame(draw);
};
addEventListener("resize", redraw);
new MutationObserver(redraw).observe(document.documentElement, { attributeFilter: ["data-theme"] });
draw();
