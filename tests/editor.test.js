// @ts-check
// How the playground's editor changes a request, under Node's test runner:
// `just test-js`.

// @ts-expect-error: tsc has no types for Node's modules, and the project takes
// no package for them.
import { test } from "node:test";
// @ts-expect-error: as above.
import assert from "node:assert/strict";
import { SHAPES, move, nameOf, newStructure, percentOf, shapeNamed, shareOf } from "../site/editor.js";

test("a shape takes its name's default parameter, and a tree takes none", () => {
  assert.deepEqual(shapeNamed("chains"), { chains: 16 });
  assert.deepEqual(shapeNamed("graph"), { graph: 2 });
  assert.equal(shapeNamed("tree"), "tree");
  assert.deepEqual(Object.keys(SHAPES).map((name) => nameOf(shapeNamed(name))), Object.keys(SHAPES));
});

test("a move swaps a structure with its neighbour, and goes nowhere past either end", () => {
  const [a, b, c] = [newStructure(), newStructure(), newStructure()];
  const structures = [a, b, c];

  assert.equal(move(structures, 1, -1), 0);
  assert.deepEqual(structures, [b, a, c]);
  assert.equal(move(structures, 0, -1), 0);
  assert.equal(move(structures, 2, 1), 2);
  assert.deepEqual(structures, [b, a, c]);
});

test("a share shows as a percentage to a tenth, and goes back in thousandths", () => {
  assert.equal(percentOf("1/50"), 2);
  assert.equal(percentOf("3/100"), 3);
  assert.equal(percentOf("1/3"), 33.3);
  assert.equal(percentOf("0"), 0);
  assert.equal(shareOf(2.5), "25/1000");
  assert.equal(shareOf(percentOf("1/20")), "50/1000");
});

test("a new structure builds within its rebuild interval", () => {
  const { size, build_churn: churn, rebuild_interval: interval } = newStructure();

  assert.ok(size * (1 + churn) <= /** @type {number} */ (interval));
});
