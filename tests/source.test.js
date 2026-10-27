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
  constants: { initial_work_budget: -100_000, freed_credit: 2, long_lived_ratio: "1/4", real_object_size: 64 },
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

// Code a link could hide in a value: it ends the string or the call, then runs.
const INJECTED = '")\nimport js  #';

test("a request's text goes into the source as Python strings on one line each", () => {
  const request = holding({ ...newStructure(), root: `frame${INJECTED}` });
  request.workload.churn.cycle_share = `1/4${INJECTED}`;
  request.workload.churn.long_share = `0${INJECTED}`;
  request.constants.long_lived_ratio = `1/4${INJECTED}`;
  const source = toSource(request);

  assert.ok(!source.split("\n").some((line) => line.startsWith("import js")));
  assert.ok(source.includes(`root=${JSON.stringify(`frame${INJECTED}`)}`));
  assert.ok(source.includes(`cycle_share=${JSON.stringify(`1/4${INJECTED}`)}`));
  assert.ok(source.includes(`long_lived_ratio=${JSON.stringify(`1/4${INJECTED}`)}`));
});

test("a request whose values the source cannot write as literals is refused", () => {
  /** @type {[(request: any) => void, RegExp][]} */
  const cases = [
    [(request) => { request.workload.structures[0].size = `1${INJECTED}`; }, /is not a number/],
    [(request) => { request.workload.structures[0].shape = { chains: `16${INJECTED}` }; }, /is not a number/],
    [(request) => { request.workload.structures[0].shape = { [`exec${INJECTED}`]: 1 }; }, /no shape/],
    [(request) => { request.workload.structures[0].shape = `tree${INJECTED}`; }, /no shape/],
    [(request) => { request.workload.structures[0].root = 5; }, /is not text/],
    [(request) => { request.workload.churn.cycle_share = 0.25; }, /is not text/],
    [(request) => { request.workload.seed = `1${INJECTED}`; }, /is not a number/],
    [(request) => { request.run_length = Infinity; }, /is not a number/],
    [(request) => { request.settings.threshold0 = `2000${INJECTED}`; }, /is not a number/],
    [(request) => { request.settings[`x=1${INJECTED}`] = 1; }, /no setting/],
    [(request) => { request.constants.freed_credit = `2${INJECTED}`; }, /is not a number/],
  ];
  for (const [change, refusal] of cases) {
    const request = holding(newStructure());
    change(request);
    assert.throws(() => toSource(request), refusal);
  }
});
