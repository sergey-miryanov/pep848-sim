// @ts-check
// The runs a widget keeps, under Node's test runner: `just test-js`.

// @ts-expect-error: tsc has no types for Node's modules, and the project takes
// no package for them.
import { test } from "node:test";
// @ts-expect-error: as above.
import assert from "node:assert/strict";
import { Kept, MOST, key } from "../site/kept.js";

/** @typedef {import("../site/kept.js").Runs} Runs */

const CHURN = { cycle_share: "1/50", cycle_size: 2, lifetime_mean: 4, long_share: "0", long_lifetimes: /** @type {[number, number]} */ ([1, 1]) };

/**
 * A request at this threshold0 and long-lived ratio, as the worker spells one out.
 * @param {number} threshold0
 * @param {string} ratio
 */
const request = (threshold0, ratio = "1/4") => ({
  workload: { churn: CHURN },
  settings: { threshold0, threshold1: 10, threshold2: 10 },
  run_length: 150_000,
  constants: { long_lived_ratio: ratio },
});

const CONTROLS = ["settings.threshold0"];

/**
 * Runs whose one record carries this clock, so a test can tell them apart.
 * @param {number} clock
 * @returns {Runs}
 */
const runs = (clock) => ({
  controls: [],
  request: request(2000),
  graph: { structures: [], churn: CHURN },
  records: { legacy: [[clock, "gen0", 0, 0, 0, 0, 0, [], [], 0, 0]], incremental: [] },
  figures: { legacy: [0, 0, 0, undefined, 1, 0, 0], incremental: [0, 0, 0, undefined, 0, 0, 0] },
});

test("a request finds the runs kept for it, and no other's", () => {
  const kept = new Kept();
  kept.keep(request(2000), CONTROLS, runs(1));
  kept.keep(request(1000), CONTROLS, runs(2));

  assert.equal(kept.find(request(2000), CONTROLS)?.records.legacy[0][0], 1);
  assert.equal(kept.find(request(1000), CONTROLS)?.records.legacy[0][0], 2);
  assert.equal(kept.find(request(500), CONTROLS), undefined);
});

test("the same request with other controls finds nothing, as their ranges differ", () => {
  const kept = new Kept();
  kept.keep(request(2000), CONTROLS, runs(1));

  assert.equal(kept.find(request(2000), [...CONTROLS, "settings.threshold1"]), undefined);
});

test("a share in thousandths finds the runs of the share in lowest terms", () => {
  const kept = new Kept();
  kept.keep(request(2000, "1/4"), CONTROLS, runs(1));

  assert.equal(kept.find(request(2000, "250/1000"), CONTROLS)?.records.legacy[0][0], 1);
  assert.equal(key(request(2000, "0/1000"), CONTROLS), key(request(2000, "0"), CONTROLS));
  assert.equal(key(request(2000, "1000/1000"), CONTROLS), key(request(2000, "1"), CONTROLS));
  assert.notEqual(key(request(2000, "251/1000"), CONTROLS), key(request(2000, "1/4"), CONTROLS));
});

test("keeping a request's runs again replaces the runs kept for it", () => {
  const kept = new Kept();
  kept.keep(request(2000), CONTROLS, runs(1));
  kept.keep(request(2000), CONTROLS, runs(2));

  assert.equal(kept.find(request(2000), CONTROLS)?.records.legacy[0][0], 2);
});

test("past the most it keeps, the runs found or kept longest ago go first", () => {
  const kept = new Kept(3);
  kept.keep(request(1000), CONTROLS, runs(1));
  kept.keep(request(2000), CONTROLS, runs(2));
  kept.keep(request(3000), CONTROLS, runs(3));
  // Found again, 1,000 goes last, and 2,000 is the oldest.
  kept.find(request(1000), CONTROLS);
  kept.keep(request(4000), CONTROLS, runs(4));

  assert.equal(kept.find(request(2000), CONTROLS), undefined);
  assert.deepEqual([1000, 3000, 4000].map((t) => kept.find(request(t), CONTROLS)?.records.legacy[0][0]), [1, 3, 4]);
});

test("a widget keeps 16 requests' runs unless told otherwise", () => {
  const kept = new Kept();
  for (let t = 1; t <= MOST + 1; t++) kept.keep(request(t), CONTROLS, runs(t));

  assert.equal(MOST, 16);
  assert.equal(kept.find(request(1), CONTROLS), undefined);
  assert.equal(kept.find(request(2), CONTROLS)?.records.legacy[0][0], 2);
  assert.equal(kept.find(request(MOST + 1), CONTROLS)?.records.legacy[0][0], MOST + 1);
});
