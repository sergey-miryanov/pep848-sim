// @ts-check
// What the widget's object graph draws, under Node's test runner: `just test-js`.

// @ts-expect-error: tsc has no types for Node's modules, and the project takes
// no package for them.
import { test } from "node:test";
// @ts-expect-error: as above.
import assert from "node:assert/strict";
import { describe, describeChurn, describeConstants, describeRun, describeYoung, fit, network } from "../site/graph.js";

/**
 * A structure with the fields a test names, and the rest of a small chain.
 * @param {Partial<import("../site/graph.js").Structure>} fields
 * @returns {import("../site/graph.js").Structure}
 */
function structure(fields = {}) {
  return {
    shape: "1 chains", size: 2, root: "module", lifetime: null, rebuild_interval: null, full_collections: false,
    built_in_frame: false, objects: [[0, 0], [1, 1]], links: [[0, 1, false]],
    ...fields,
  };
}

const CHURN = { cycle_share: "0", cycle_size: 1, lifetime_mean: 4, long_share: "0", long_lifetimes: /** @type {[number, number]} */ ([1, 1]) };

test("sys holds the module's structures, and each structure a frame holds gets a frame", () => {
  const graph = {
    structures: [
      structure(),
      structure({ root: "frame", links: [[0, 1, true], [1, 0, true]] }),
      structure({ root: "frame" }),
    ],
    churn: CHURN,
  };

  const { nodes, links } = network(graph);

  assert.deepEqual(nodes.filter((node) => node.root).map(({ key }) => key), ["sys", "frame 1", "frame 2"]);
  assert.deepEqual(nodes.filter((node) => node.first).map(({ key }) => key), ["0:0", "1:0", "2:0"]);
  assert.deepEqual(links.filter(({ kind }) => kind === "held"), [
    { source: "sys", target: "0:0", kind: "held" },
    { source: "frame 1", target: "1:0", kind: "held" },
    { source: "frame 2", target: "2:0", kind: "held" },
  ]);
  assert.deepEqual(links.filter(({ kind }) => kind === "cycle").map(({ source, target }) => [source, target]), [["1:0", "1:1"], ["1:1", "1:0"]]);
});

test("a graph with nothing held by a module draws no sys, and an empty structure draws nothing", () => {
  const graph = { structures: [structure({ root: "frame" }), structure({ objects: [], links: [] })], churn: CHURN };

  const { nodes } = network(graph);

  assert.deepEqual(nodes.map(({ key }) => key), ["frame 0", "0:0", "0:1"]);
});

test("a layout fills its frame less the margin, scaled alike both ways and centred", () => {
  const placed = [{ key: "a", x: 0, y: 0 }, { key: "b", x: 100, y: 10 }];

  const places = fit(placed, 220, 100, 10, 5);

  // Its width limits it: 200 px for 100, so twice its size.
  assert.deepEqual(places.get("a"), [10, 40]);
  assert.deepEqual(places.get("b"), [210, 60]);
});

test("a small layout grows no more than its most", () => {
  const places = fit([{ key: "a", x: 0, y: 0 }, { key: "b", x: 10, y: 0 }], 220, 100, 10, 1.5);

  assert.deepEqual(places.get("a"), [102.5, 50]);
  assert.deepEqual(places.get("b"), [117.5, 50]);
});

test("the legend says what holds each structure, and when the workload builds and drops it", () => {
  assert.equal(describe(structure({ shape: "16 chains", size: 350 })), "16 chains, 350 objects, held by sys: built first, kept to the end");
  assert.equal(
    describe(structure({ shape: "a hierarchy of 50 branches", size: 322, root: "frame", lifetime: 840, rebuild_interval: 420 })),
    "a hierarchy of 50 branches, 322 objects, held by a frame: rebuilt every 420 kB, each dropped 840 kB later",
  );
  assert.equal(
    describe(structure({ shape: "rings of 1 object", size: 132, root: "frame", lifetime: 0, rebuild_interval: 140, full_collections: true })),
    "rings of 1 object, 132 objects, held by a frame: rebuilt every 140 kB, each dropped as soon as built, gc.collect() before each build and after each drop",
  );
  assert.equal(describe(structure({ size: 89_007, lifetime: 25_298 })), "1 chains, 89,007 objects, held by sys: built first, dropped 25.3 MB later");
  assert.equal(
    describe(structure({ shape: "a graph of 2 edges a node", size: 89_007, built_in_frame: true })),
    "a graph of 2 edges a node, 89,007 objects, held by a frame while built, then by sys: built first, kept to the end",
  );
});

test("the legend gives the churn's lifetimes and the cycles it makes", () => {
  assert.equal(describeChurn(CHURN), "Churn: objects that live about 4 kB, no cycles");
  assert.equal(
    describeChurn({ cycle_share: "1/50", cycle_size: 2, lifetime_mean: 4, long_share: "1/20", long_lifetimes: [100, 1000] }),
    "Churn: objects that live about 4 kB, 5% living 100 kB to 1 MB, 2% in cycles of 2",
  );
});

test("the playground's legend gives the run's length, its thresholds and its shutdown", () => {
  const settings = { threshold0: 2000, threshold1: 10, threshold2: 10 };

  assert.equal(
    describeRun({ run_length: 150_000, settings, workload: { shutdown: false } }),
    "Run: 150 MB on the allocation clock, gc.set_threshold(2000, 10, 10)",
  );
  assert.equal(
    describeRun({ run_length: 524_900, settings, workload: { shutdown: true } }),
    "Run: 524.9 MB on the allocation clock, gc.set_threshold(2000, 10, 10), then shutdown",
  );
});

test("the thresholds make a nursery of two half-spaces and aging of threshold1 half-spaces", () => {
  assert.deepEqual(describeYoung(2000, 10), {
    nursery: "Incremental nursery: 4 MB",
    aging: "Incremental aging: 5 spaces, 20 MB",
  });
  // threshold1 / 2 aging spaces, rounded up.
  assert.deepEqual(describeYoung(100, 1), {
    nursery: "Incremental nursery: 200 kB",
    aging: "Incremental aging: 1 space, 200 kB",
  });
  assert.equal(describeYoung(2000, 9).aging, "Incremental aging: 5 spaces, 20 MB");
  // One at least, as the incremental collector runs a threshold1 below 1 as 1.
  assert.equal(describeYoung(2000, 0).aging, "Incremental aging: 1 space, 4 MB");
});

test("the playground's legend gives the collector constants and the real object's size", () => {
  assert.equal(
    describeConstants({ initial_work_budget: -100_000, freed_credit: 2, long_lived_ratio: "1/4", real_object_size: 64 }),
    "Work budget from -100,000 real objects, plus 2 for each object freed, a long-lived ratio of 25%, 64 B to a real object",
  );
  assert.equal(
    describeConstants({ initial_work_budget: 0, freed_credit: 0, long_lived_ratio: "125/1000", real_object_size: 48 }),
    "Work budget from 0 real objects, plus 0 for each object freed, a long-lived ratio of 12.5%, 48 B to a real object",
  );
});
