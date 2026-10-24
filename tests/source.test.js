// @ts-check
// How the playground writes a request as Python source, under Node's test
// runner: `just test-js`. tests/test_source.py reads the same fixture back.

// @ts-expect-error: tsc has no types for Node's modules, and the project takes
// no package for them.
import { test } from "node:test";
// @ts-expect-error: as above.
import assert from "node:assert/strict";
// @ts-expect-error: as above.
import { readFileSync } from "node:fs";
import { OWN, newStructure } from "../site/editor.js";
import { functionOf, toSource } from "../site/source.js";

/** @param {string} name */
const fixture = (name) => readFileSync(new URL(`fixtures/${name}`, import.meta.url), "utf8");

/**
 * A request with the structures given, and the PEP's settings.
 * @returns {import("../site/editor.js").Request}
 */
const holding = (/** @type {any[]} */ ...structures) => ({
  workload: {
    churn: { cycle_share: "0", cycle_size: 2, lifetime_mean: 5, long_share: "0", long_lifetimes: [1, 1] },
    structures,
    seed: 848,
    shutdown: false,
  },
  settings: { threshold0: 2000, threshold1: 10, threshold2: 10 },
  run_length: 10_000,
  every: 1,
});

test("a request's source spells out each structure, the churn and the run", () => {
  assert.equal(toSource(JSON.parse(fixture("source.json"))), fixture("source.txt"));
});

test("a source without a shape of the reader's own offers one, and leaves the PEP's seed out", () => {
  const source = toSource(holding(newStructure()));

  assert.match(source, /# Give it to a structure as Own\(doubly_linked\)\.\ndef doubly_linked\(i\):/);
  assert.match(source, /^ {4}Structure\(Tree\(\), size=1000, root="frame", lifetime=2000,$/m);
  assert.doesNotMatch(source, /seed/);
  assert.match(toSource(holding()), /^structures = \[\]$/m);
});

test("a shape's code holds a function alone when every line after its def is indented", () => {
  assert.deepEqual(functionOf(`\n\n${OWN}\n`), { name: "links", text: OWN.trimEnd() });
  assert.equal(functionOf("WIDTH = 4\ndef links(i):\n    return []\n"), null);
  assert.equal(functionOf("def links(i):\n    return []\n# after\n"), null);
  assert.equal(functionOf("links = lambda i: []\n"), null);
});
