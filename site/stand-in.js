// @ts-check
// The stand-in page's own two runs, of the workload tests/test_run.py pins,
// asked for outside any widget. It counts their records as they stream and
// digests them when the runs end, to hold against the pinned digests.

import { requestRuns } from "./runs.js";

/** tests/test_run.py's FIXED workload and settings, as tests/test_request.py sends them. */
const REQUEST = {
  workload: {
    churn: {
      cycle_share: "1/4", cycle_size: 3, lifetime_mean: 200,
      long_share: "1/20", long_lifetimes: [100, 1000],
    },
    structures: [
      {
        shape: { chains: 16 }, size: 1000, root: "module",
        lifetime: null, rebuild_interval: null, build_churn: 0,
      },
      {
        shape: "tree", size: 100, root: "frame",
        lifetime: 400, rebuild_interval: 1000, build_churn: 1,
      },
    ],
    seed: 848,
  },
  settings: { threshold0: 20, threshold1: 10, threshold2: 10 },
  run_length: 20000,
  every: 50,
};

/** The first 16 hex digits of the SHA-256 of the records as JSON, as the tests take it. */
async function digest(/** @type {unknown} */ records) {
  const bytes = new TextEncoder().encode(JSON.stringify(records));
  const hash = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return [...hash].map((byte) => byte.toString(16).padStart(2, "0")).join("").slice(0, 16);
}

const status = /** @type {HTMLElement} */ (document.getElementById("status"));

/** @param {"legacy" | "incremental"} collector @param {number} column */
const cell = (collector, column) =>
  /** @type {HTMLElement} */ (document.querySelector(`#${collector} td:nth-of-type(${column})`));

/** The records of the runs last asked for. */
let current = {};

function start() {
  const began = performance.now();
  /** @type {{ legacy: import("./runs.js").Record[], incremental: import("./runs.js").Record[] }} */
  const runs = { legacy: [], incremental: [] };
  current = runs;
  for (const collector of /** @type {const} */ (["legacy", "incremental"])) {
    for (const column of [1, 2, 3]) cell(collector, column).textContent = "";
  }
  status.textContent = "Running";
  requestRuns("stand-in", REQUEST, {
    records(collector, records) {
      runs[collector].push(...records);
      cell(collector, 1).textContent = String(runs[collector].length);
      cell(collector, 2).textContent = String(records.at(-1)?.[0]);
    },
    async done() {
      const ms = performance.now() - began;
      const digests = [await digest(runs.legacy), await digest(runs.incremental)];
      // A click while the page took the digests asked for new runs.
      if (current !== runs) return;
      [cell("legacy", 3).textContent, cell("incremental", 3).textContent] = digests;
      const perKb = (ms * 1000) / (2 * REQUEST.run_length);
      status.textContent = `Done: ${Math.round(ms)} ms from the request, ${perKb.toFixed(2)} µs per kB of either run.`;
    },
    error(message) {
      status.textContent = message;
    },
  });
}

start();
/** @type {HTMLElement} */ (document.getElementById("again")).addEventListener("click", start);
