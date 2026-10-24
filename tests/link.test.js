// @ts-check
// How the playground writes a request into a link and opens it again, under
// Node's test runner: `just test-js`.

// @ts-expect-error: tsc has no types for Node's modules, and the project takes
// no package for them.
import { test } from "node:test";
// @ts-expect-error: as above.
import assert from "node:assert/strict";
// @ts-expect-error: as above.
import { readFileSync } from "node:fs";
import { decode, encode, holdsCode } from "../site/link.js";

/**
 * A spelled-out request with shapes of the reader's own, constants and text
 * that needs escaping: the source's fixture.
 * @type {import("../site/editor.js").Request}
 */
const REQUEST = JSON.parse(readFileSync(new URL("fixtures/source.json", import.meta.url), "utf8"));

/**
 * The request with its structures' shapes swapped for these.
 * @param {...any} shapes
 * @returns {any}
 */
const shaped = (...shapes) => ({
  ...REQUEST,
  workload: { ...REQUEST.workload, structures: shapes.map((shape) => ({ ...REQUEST.workload.structures[0], shape })) },
});

test("a request goes into a link's text and opens to the same request", async () => {
  const text = await encode(REQUEST);

  assert.match(text, /^[\w-]+$/);
  assert.ok(text.length < JSON.stringify(REQUEST).length / 2);
  assert.deepEqual(await decode(text), REQUEST);
});

test("a link refuses text that opens to no request the playground wrote", async () => {
  const text = await encode(REQUEST);
  const damaged = { message: "The link is cut short or damaged: it opens no workload." };
  const foreign = { message: "The link holds no workload the playground wrote." };

  await assert.rejects(decode("not a link!"), damaged);
  await assert.rejects(decode(text.slice(0, text.length / 2)), damaged);
  await assert.rejects(decode(await encode(/** @type {any} */ ([1, 2]))), foreign);
  await assert.rejects(decode(await encode(/** @type {any} */ ({ ...REQUEST, source: "import js" }))), foreign);
  const { constants, ...rest } = REQUEST;
  await assert.rejects(decode(await encode(/** @type {any} */ (rest))), foreign);
});

test("a link that opens past 1 MB is refused before it fills the page", async () => {
  const swollen = await encode(/** @type {any} */ ({ ...REQUEST, workload: "x".repeat(2 << 20) }));

  assert.ok(swollen.length < 10_000);
  await assert.rejects(decode(swollen), {
    message: "The link opens to more than 1 MB, more than any workload the playground writes.",
  });
});

test("a request holds code when a shape is the reader's own or not plainly a named one", () => {
  assert.equal(holdsCode(REQUEST), true);
  assert.equal(holdsCode(shaped("tree", { chains: 16 }, { rings: 21 })), false);
  assert.equal(holdsCode(shaped()), false);
  assert.equal(holdsCode(shaped("tree", { own: "def links(i):\n    return []\n" })), true);
  assert.equal(holdsCode(shaped({ chains: 16, own: "" })), true);
  assert.equal(holdsCode(shaped(undefined)), true);
  assert.equal(holdsCode(shaped(null)), true);
  assert.equal(holdsCode(/** @type {any} */ ({ ...REQUEST, workload: { structures: "tree" } })), true);
  assert.equal(holdsCode(/** @type {any} */ ({ ...REQUEST, workload: null })), true);
});
