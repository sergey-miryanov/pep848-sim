// @ts-check
// The page's one worker, made as soon as a page imports this module, so Pyodide
// starts before the reader reaches a widget (ADR 0009). Every widget on the page
// asks it for runs through `requestRuns`.

/**
 * One collection, as pep848_sim.collectors.collector.Record holds it: clock,
 * kind, marked, survived, freed, work_to_do, sweep, spaces_before,
 * spaces_after, reachable_before, reachable_after.
 * @typedef {[number, string, number, number, number, number, number, number[], number[], number, number]} Record
 */

/**
 * A run's figures so far, as pep848_sim.widget.figures.Figures.row holds them:
 * peak work, peak uncollected garbage, work per MB, yield (undefined until the
 * run has examined an object), collections, sweeps and gen 2 collections.
 * @typedef {[number, number, number, number | undefined, number, number, number]} Figures
 */

/**
 * One control, as pep848_sim.widget.controls.Control holds it: its path into the
 * request, label, unit ("kB", "share" in thousandths, or "count"), value, min,
 * max and step.
 * @typedef {[string, string, "kB" | "share" | "count", number, number, number, number]} Control
 */

/** @typedef {import("./graph.js").Graph} Graph */

/**
 * What a widget hears about its runs: the controls it asked for, with the ranges
 * the request allows, the request with any preset it names spelled out and a
 * sample of its object graph, then each part of a run, with its figures so far.
 * @typedef {{
 *   controls?: (controls: Control[], request: any, graph: Graph) => void,
 *   records: (collector: "legacy" | "incremental", records: Record[], figures: Figures) => void,
 *   done: () => void,
 *   error: (message: string) => void,
 * }} Listener
 */

/** The listener of each request still wanted, by the request's id. */
/** @type {Map<number, Listener>} */
const listeners = new Map();
/** Each widget's latest request id. The page drops the parts of older requests. */
/** @type {Map<string, number>} */
const latest = new Map();
let nextId = 0;

function startWorker() {
  const started = new Worker(new URL("worker.js", import.meta.url), { type: "module" });
  started.onmessage = (/** @type {MessageEvent} */ { data }) => {
    const listener = listeners.get(data.id);
    if (!listener) return;
    if (data.kind === "controls") listener.controls?.(data.controls, JSON.parse(data.request), JSON.parse(data.graph));
    else if (data.kind === "records") listener.records(data.collector, data.records, data.figures);
    else {
      listeners.delete(data.id);
      if (data.kind === "done") listener.done();
      else listener.error(data.message);
    }
  };
  return started;
}

let worker = startWorker();

/**
 * End every run the page asked for by ending the worker, and start another, the
 * one way to end Python that never returns, as a reader's own shape can loop
 * forever (ADR 0009). Each request still wanted hears that its runs stopped.
 */
export function stopRuns() {
  worker.terminate();
  worker = startWorker();
  const stopped = [...listeners.values()];
  listeners.clear();
  for (const listener of stopped) listener.error("The runs stopped.");
}

/**
 * Stop hearing about the runs a widget asked for last. The worker finishes them
 * unheard.
 * @param {string} widget names the widget, unique on the page
 */
export function dropRuns(widget) {
  const before = latest.get(widget);
  if (before !== undefined) listeners.delete(before);
}

/**
 * Ask for a widget's two runs, legacy and incremental, in place of any it asked
 * for before.
 * @param {string} widget names the widget, unique on the page
 * @param {object} request what pep848_sim.widget.request.runs reads
 * @param {Listener} listener
 * @param {string[]} controls the paths into the request of the controls the
 *   widget shows
 */
export function requestRuns(widget, request, listener, controls = []) {
  dropRuns(widget);
  const id = nextId++;
  latest.set(widget, id);
  listeners.set(id, listener);
  worker.postMessage({ id, widget, request: JSON.stringify(request), controls });
}
