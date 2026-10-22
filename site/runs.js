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
 * What a widget hears about its runs: each part of one, with its figures so far.
 * @typedef {{
 *   records: (collector: "legacy" | "incremental", records: Record[], figures: Figures) => void,
 *   done: () => void,
 *   error: (message: string) => void,
 * }} Listener
 */

const worker = new Worker(new URL("worker.js", import.meta.url), { type: "module" });

/** Each widget's latest request, by its id. Parts of older requests are dropped. */
/** @type {Map<number, Listener>} */
const listeners = new Map();
/** @type {Map<string, number>} */
const latest = new Map();
let nextId = 0;

worker.onmessage = (/** @type {MessageEvent} */ { data }) => {
  const listener = listeners.get(data.id);
  if (!listener) return;
  if (data.kind === "records") listener.records(data.collector, data.records, data.figures);
  else {
    listeners.delete(data.id);
    if (data.kind === "done") listener.done();
    else listener.error(data.message);
  }
};

/**
 * Ask for a widget's two runs, legacy and incremental, in place of any it asked
 * for before.
 * @param {string} widget names the widget, unique on the page
 * @param {object} request what pep848_sim.widget.request.runs reads
 * @param {Listener} listener
 */
export function requestRuns(widget, request, listener) {
  const before = latest.get(widget);
  if (before !== undefined) listeners.delete(before);
  const id = nextId++;
  latest.set(widget, id);
  listeners.set(id, listener);
  worker.postMessage({ id, widget, request: JSON.stringify(request) });
}
