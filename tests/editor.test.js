// @ts-check
// How the playground's editor changes a request, under Node's test runner:
// `just test-js`.

// @ts-expect-error: tsc has no types for Node's modules, and the project takes
// no package for them.
import { test } from "node:test";
// @ts-expect-error: as above.
import assert from "node:assert/strict";
import {
  OWN, SHAPES, churnFrom, churnOf, indentAfter, move, nameOf, newStructure, percentOf, realOnes, shapeNamed, shareOf,
} from "../site/editor.js";

test("a shape takes its name's default parameter, a tree none, and the reader's own a list's code", () => {
  assert.deepEqual(shapeNamed("chains"), { chains: 16 });
  assert.deepEqual(shapeNamed("graph"), { graph: 2 });
  assert.equal(shapeNamed("tree"), "tree");
  assert.deepEqual(shapeNamed("own"), { own: OWN });
  assert.deepEqual(Object.keys(SHAPES).map((name) => nameOf(shapeNamed(name))), Object.keys(SHAPES));
});

test("Enter keeps a line's indent, and indents four spaces more after a colon", () => {
  assert.equal(indentAfter("    return []"), "    ");
  assert.equal(indentAfter("def links(i):"), "    ");
  assert.equal(indentAfter("    if i == 0:  "), "        ");
  assert.equal(indentAfter(""), "");
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

test("a build's churn shows to a hundredth, and goes back whole or in hundredths", () => {
  assert.equal(churnOf(3), 3);
  assert.equal(churnOf("13/50"), 0.26);
  assert.equal(churnOf("1/3"), 0.33);
  assert.equal(churnFrom(2), 2);
  assert.equal(churnFrom(0.26), "26/100");
  assert.equal(churnFrom(churnOf("121/100")), "121/100");
});

test("a dot stands for the real objects that fill 1 kB", () => {
  assert.equal(realOnes(64), "16 real ones");
  assert.equal(realOnes(48), "about 21.3 real ones");
  assert.equal(realOnes(1000), "about 1 real one");
  assert.equal(realOnes(1024), "1 real one");
  assert.equal(realOnes(3), "about 341 real ones");
});

test("a new structure builds within its rebuild interval", () => {
  const { size, build_churn: churn, rebuild_interval: interval } = newStructure();

  assert.ok(size * (1 + churnOf(churn)) <= /** @type {number} */ (interval));
});
