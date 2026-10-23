// @ts-check
// The data the widget's panels draw, under Node's test runner: `just test-js`.

// @ts-expect-error: tsc has no types for Node's modules, and the project takes
// no package for them.
import { test } from "node:test";
// @ts-expect-error: as above.
import assert from "node:assert/strict";
import { FADED, ceiling, heap, work } from "../site/panels.js";

/**
 * A record with the fields a test names, and the rest empty.
 * @param {{
 *   clock?: number, kind?: string, marked?: number, survived?: number, freed?: number,
 *   before?: number[], after?: number[], reachableBefore?: number, reachableAfter?: number,
 * }} fields
 * @returns {import("../site/runs.js").Record}
 */
function record({
  clock = 0, kind = "young", marked = 0, survived = 0, freed = 0,
  before = [0, 0, 0], after = [0, 0, 0], reachableBefore = 0, reachableAfter = 0,
} = {}) {
  return [clock, kind, marked, survived, freed, 0, 0, before, after, reachableBefore, reachableAfter];
}

test("the heap starts empty at clock 0", () => {
  const { whole, lanes } = heap("legacy", []);

  assert.deepEqual(whole, [{ mb: 0, heap: 0, reachable: 0 }]);
  assert.deepEqual(lanes, [
    [{ mb: 0, space: "nursery", y1: 0, y2: 0 }],
    [{ mb: 0, space: "aging", y1: 0, y2: 0 }],
    [{ mb: 0, space: "old", y1: 0, y2: 0 }],
  ]);
});

test("a record gives the heap before its collection and after it, at its clock", () => {
  const records = [record({ clock: 2000, before: [1500, 300, 4000], after: [0, 1200, 4000], reachableBefore: 3000, reachableAfter: 2800 })];

  assert.deepEqual(heap("legacy", records).whole, [
    { mb: 0, heap: 0, reachable: 0 },
    { mb: 2, heap: 5.8, reachable: 3 },
    { mb: 2, heap: 5.2, reachable: 2.8 },
  ]);
});

// #110: the nursery's lane once traced the whole heap.
test("each lane holds its own spaces alone", () => {
  const records = [record({ clock: 2000, before: [1500, 300, 4000], after: [0, 1200, 4000] })];

  const [nursery, aging, old] = heap("legacy", records).lanes;

  assert.deepEqual(nursery.map((band) => band.y2), [0, 1.5, 0]);
  assert.deepEqual(aging.map((band) => band.y2), [0, 0.3, 1.2]);
  assert.deepEqual(old.map((band) => band.y2), [0, 4, 4]);
  for (const band of [...nursery, ...aging, ...old]) assert.equal(band.y1, 0);
});

test("the incremental collector's old generation stacks visited on pending", () => {
  const records = [record({ clock: 2000, before: [100, 200, 3000, 500], after: [0, 300, 2000, 1500] })];

  const [, , old] = heap("incremental", records).lanes;

  assert.deepEqual(old, [
    { mb: 0, space: "pending", y1: 0, y2: 0 },
    { mb: 0, space: "visited", y1: 0, y2: 0 },
    { mb: 2, space: "pending", y1: 0, y2: 3 },
    { mb: 2, space: "visited", y1: 3, y2: 3.5 },
    { mb: 2, space: "pending", y1: 0, y2: 2 },
    { mb: 2, space: "visited", y1: 2, y2: 3.5 },
  ]);
});

test("a collection falls in the bin of the kB it ran after", () => {
  // A gc.collect() before the first allocation, at clock 0, falls in the first bin.
  const bins = (/** @type {number} */ clock) => work([record({ clock, marked: 1 })], 4000).map(({ x1, x2 }) => [x1, x2]);

  assert.deepEqual(bins(0), [[0, 4]]);
  assert.deepEqual(bins(1), [[0, 4]]);
  assert.deepEqual(bins(4000), [[0, 4]]);
  assert.deepEqual(bins(4001), [[4, 8]]);
});

test("a bin stacks marked, survived and freed, and rounds the top one", () => {
  const records = [
    record({ clock: 2000, marked: 10, survived: 5 }),
    record({ clock: 4000, marked: 2 }),
  ];

  assert.deepEqual(work(records, 4000), [
    { x1: 0, x2: 4, y1: 0, y2: 12, part: "marked", opacity: 1, top: false },
    { x1: 0, x2: 4, y1: 12, y2: 17, part: "survived", opacity: 1, top: true },
  ]);
});

test("a bin stacks its full collections' work faded above the runtime's own", () => {
  const records = [
    record({ clock: 1000, kind: "full", marked: 100, freed: 20 }),
    record({ clock: 2000, kind: "young", marked: 10 }),
    record({ clock: 3000, kind: "shutdown", freed: 30 }),
  ];

  assert.deepEqual(work(records, 4000), [
    { x1: 0, x2: 4, y1: 0, y2: 10, part: "marked", opacity: 1, top: false },
    { x1: 0, x2: 4, y1: 10, y2: 110, part: "marked", opacity: FADED, top: false },
    { x1: 0, x2: 4, y1: 110, y2: 160, part: "freed", opacity: FADED, top: true },
  ]);
});

test("a y-scale ends at the next step above its data, with room to spare", () => {
  assert.equal(ceiling(0), 1);
  assert.equal(ceiling(95), 100);
  assert.equal(ceiling(100), 120);
  assert.equal(ceiling(1000), 1200);
  assert.equal(ceiling(9.6), 12);
  for (let value = 0.01; value < 1e7; value *= 1.37) {
    assert.ok(ceiling(value) >= value * 1.05, `${ceiling(value)} leaves ${value} no room`);
  }
});
