// @ts-check
// The digests tests/digests.json pins under CPython, checked under Pyodide in
// Node, at the version the site's worker loads (ADR 0007): `just test-pyodide`.
// Each pinned request runs through pep848_sim.widget.request, the worker's own
// path, from the simulator's sources as `just site` zips them.

// @ts-expect-error: tsc has no types for Node's modules, and the project takes
// no package for them.
import { test } from "node:test";
// @ts-expect-error: as above.
import assert from "node:assert/strict";
// @ts-expect-error: as above.
import { readFileSync } from "node:fs";
// @ts-expect-error: as above.
import { fileURLToPath } from "node:url";
import { loadPyodide, version } from "pyodide";

const read = (/** @type {string} */ path) => readFileSync(new URL(path, import.meta.url), "utf-8");

/** @type {Record<string, { request: object, legacy: string, incremental: string }>} */
const PINNED = JSON.parse(read("digests.json"));

test("the check loads the Pyodide the site's worker loads", () => {
  assert.equal(read("../site/worker.js").match(/pyodide\/v([\d.]+)\//)?.[1], version);
});

test("each pinned request's records keep their digests under Pyodide", async (/** @type {{ test: (name: string, run: () => void) => Promise<void> }} */ t) => {
  const pyodide = await loadPyodide();
  pyodide.FS.mkdirTree("/sim");
  pyodide.FS.mount(pyodide.FS.filesystems.NODEFS, { root: fileURLToPath(new URL("../src", import.meta.url)) }, "/sim");
  pyodide.runPython("import sys; sys.path.insert(0, '/sim')");
  // test_run.digest, which pins them under CPython.
  const digests = pyodide.runPython(`
import hashlib
import json
from pep848_sim.widget.request import runs

def digest(parts):
    records = [record for part in parts for record in part]
    return hashlib.sha256(json.dumps(records, separators=(",", ":")).encode()).hexdigest()[:16]

def digests(request):
    legacy, incremental = runs(request)
    return [digest(legacy), digest(incremental)]

digests
`);
  for (const [name, { request, legacy, incremental }] of Object.entries(PINNED)) {
    await t.test(name, () => {
      const got = digests(JSON.stringify(request));
      assert.deepEqual(got.toJs(), [legacy, incremental]);
      got.destroy();
    });
  }
  digests.destroy();
});
