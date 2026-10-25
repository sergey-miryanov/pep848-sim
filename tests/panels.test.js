// @ts-check
// The data the widget's panels draw, under Node's test runner: `just test-js`.

// @ts-expect-error: tsc has no types for Node's modules, and the project takes
// no package for them.
import { test } from "node:test";
// @ts-expect-error: as above.
import assert from "node:assert/strict";
import { FADED, budgetAt, ceiling, collections, heap, heapAt, spoken, step, work, workAt } from "../site/panels.js";

/**
 * A record with the fields a test names, and the rest empty.
 * @param {{
 *   clock?: number, kind?: string, marked?: number, survived?: number, freed?: number, workToDo?: number,
 *   before?: number[], after?: number[], reachableBefore?: number, reachableAfter?: number,
 * }} fields
 * @returns {import("../site/runs.js").Record}
 */
function record({
  clock = 0, kind = "young", marked = 0, survived = 0, freed = 0, workToDo = 0,
  before = [0, 0, 0], after = [0, 0, 0], reachableBefore = 0, reachableAfter = 0,
} = {}) {
  return [clock, kind, marked, survived, freed, workToDo, 0, before, after, reachableBefore, reachableAfter];
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

test("the pointer reads the heap at the nearest collection, before it and after it", () => {
  const records = [
    record({ clock: 2000, before: [1500, 300, 4000], after: [0, 1200, 4000], reachableBefore: 3000, reachableAfter: 2800 }),
    record({ clock: 4000, before: [2000, 1200, 4000], after: [0, 0, 6500], reachableBefore: 5000, reachableAfter: 5000 }),
  ];

  assert.equal(heapAt([], 2000), null);
  assert.deepEqual(heapAt(records, 2900), {
    clock: 2000,
    kinds: ["young"],
    before: { heap: 5.8, reachable: 3, garbage: 2.8, spaces: [1.5, 0.3, 4] },
    after: { heap: 5.2, reachable: 2.8, garbage: 2.4, spaces: [0, 1.2, 4] },
  });
  // Halfway between two collections, the earlier.
  assert.equal(heapAt(records, 3000)?.clock, 2000);
  assert.equal(heapAt(records, 3001)?.clock, 4000);
  assert.equal(heapAt(records, 90_000)?.clock, 4000);
});

test("the pointer reads the heap before the first collection at a clock and after the last", () => {
  const records = [
    record({ clock: 9000, kind: "shutdown", before: [0, 0, 7000], after: [0, 0, 3000], reachableBefore: 3000, reachableAfter: 3000 }),
    record({ clock: 9000, kind: "shutdown", before: [0, 0, 3000], after: [0, 0, 1000], reachableBefore: 1000, reachableAfter: 1000 }),
  ];

  const at = heapAt(records, 9000);

  assert.deepEqual(at?.kinds, ["shutdown", "shutdown"]);
  assert.equal(at?.before.heap, 7);
  assert.equal(at?.after.heap, 1);
});

test("the pointer reads the budget the nearest collections left", () => {
  const records = [
    record({ clock: 2000, workToDo: 500 }),
    record({ clock: 4000, kind: "old", workToDo: -200 }),
    record({ clock: 4000, kind: "young", workToDo: 300 }),
  ];

  assert.equal(budgetAt([], 2000), null);
  assert.deepEqual(budgetAt(records, 2500), { clock: 2000, kinds: ["young"], budget: 500 });
  assert.deepEqual(budgetAt(records, 3500), { clock: 4000, kinds: ["old", "young"], budget: 300 });
});

test("the pointer reads the work of the bin under it, the full collections' apart", () => {
  const records = [
    record({ clock: 2000, marked: 10, survived: 5 }),
    record({ clock: 3000, kind: "full", marked: 100, freed: 20 }),
    record({ clock: 4001, marked: 7 }),
  ];

  assert.deepEqual(workAt(records, 4000, 3999), { x1: 0, x2: 4, automatic: [10, 5, 0], full: [100, 0, 20] });
  // A collection at a bin's end did the bin's work, so its clock reads that bin.
  assert.deepEqual(workAt(records, 4000, 4000), { x1: 0, x2: 4, automatic: [10, 5, 0], full: [100, 0, 20] });
  assert.deepEqual(workAt(records, 4000, 4001), { x1: 4, x2: 8, automatic: [7, 0, 0], full: [0, 0, 0] });
  assert.deepEqual(workAt(records, 4000, 9000), { x1: 8, x2: 12, automatic: [0, 0, 0], full: [0, 0, 0] });
  assert.deepEqual(workAt(records, 4000, -5), { x1: 0, x2: 4, automatic: [10, 5, 0], full: [100, 0, 20] });
});

test("a key steps the heap and the budget from one collection's clock to the next", () => {
  const records = [
    record({ clock: 0, kind: "full" }),
    record({ clock: 2000 }),
    record({ clock: 4000, kind: "old" }),
    record({ clock: 4000 }),
  ];
  const press = (/** @type {string} */ key, /** @type {number} */ kb, panel = "heap") => step(key, kb, panel, records, 4000, 10_000);

  assert.equal(step("Home", 0, "heap", [], 4000, 10_000), null);
  assert.equal(press("ArrowRight", 0), 2000);
  // From the nearest collection, the earlier of two as near.
  assert.equal(press("ArrowRight", 2900), 4000);
  assert.equal(press("ArrowLeft", 3000), 0);
  // Collections that share a clock make one step, and the ends hold.
  assert.equal(press("ArrowRight", 4000), 4000);
  assert.equal(press("ArrowLeft", 0), 0);
  assert.equal(press("Home", 3500, "budget"), 0);
  assert.equal(press("End", 0, "budget"), 4000);
  assert.equal(press("ArrowUp", 2000), 4000);
  assert.equal(press("ArrowDown", 2000), 0);
  assert.equal(press("PageDown", 2000), null);
});

test("a key steps the work panel from one bin to the next, at the clock that ends each", () => {
  const records = [record({ clock: 4000, marked: 10 }), record({ clock: 8000, marked: 7 })];
  // Bins of 4 MB on a 10 MB run: the last ends with the run.
  const press = (/** @type {string} */ key, /** @type {number} */ kb) => step(key, kb, "work", [], 4000, 10_000);

  assert.equal(press("Home", 7000), 4000);
  assert.equal(press("ArrowRight", 4000), 8000);
  assert.equal(press("ArrowRight", 6000), 10_000);
  assert.equal(press("ArrowRight", 10_000), 10_000);
  assert.equal(press("ArrowLeft", 8000), 4000);
  assert.equal(press("ArrowLeft", 4000), 4000);
  assert.equal(press("End", 0), 10_000);
  // Each step reads the bin it ends.
  assert.deepEqual(workAt(records, 4000, press("Home", 0) ?? -1).automatic, [10, 0, 0]);
  assert.deepEqual(workAt(records, 4000, press("ArrowRight", 4000) ?? -1).automatic, [7, 0, 0]);
});

test("a screen reader hears a tooltip's readout as one sentence", () => {
  assert.equal(
    spoken("young collection at 4 MB", ["objects"], [["work budget", "var(--text-primary)", ["-5,000"]]]),
    "young collection at 4 MB, in objects: work budget -5,000.",
  );
  assert.equal(
    spoken("young collection at 4 MB", ["MB", "before", "after"], [
      ["heap", "var(--text-muted)", ["5.80", "5.20"]],
      ["reachable", "var(--text-primary)", ["3.00", "2.80"]],
    ]),
    "young collection at 4 MB, in MB, before and after: heap 5.80, 5.20; reachable 3.00, 2.80.",
  );
});

test("a tooltip names the collections at its clock by kind", () => {
  assert.equal(collections(["young"]), "young collection");
  assert.equal(collections(["shutdown", "shutdown"]), "2 shutdown collections");
  assert.equal(collections(["old", "young"]), "old and young collections");
  assert.equal(collections(["full", "young", "young", "old"]), "full, 2 young and old collections");
});
