// @ts-check
// The page's worker. It starts Pyodide as soon as the page makes it (ADR 0009),
// and makes every widget's runs, a part of one run at a time, in turn (ADR 0006).
// Records reach the page as the runs yield them (ADR 0007).

// @ts-expect-error: an editor cannot fetch Pyodide's types from jsDelivr.
import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs";

/** pep848_sim.request, once Pyodide has started and imported it. */
const simulator = (async () => {
  const pyodide = await loadPyodide({
    indexURL: "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/",
  });
  const zip = await (await fetch("sim.zip")).arrayBuffer();
  pyodide.unpackArchive(zip, "zip", { extractDir: "/home/pyodide" });
  pyodide.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
  return pyodide.pyimport("pep848_sim.request");
})();

/**
 * The runs still going, in the order they take turns.
 * @type {{ id: number, widget: string, collector: string, run: any }[]}
 */
let turns = [];
let running = false;

/** @param {unknown} error */
const lastLine = (error) => String(error instanceof Error ? error.message : error).trim().split("\n").at(-1);

// Back to the event loop, so a message from the page can run. A nested
// setTimeout(0) waits at least 4 ms; a message on a channel made for this one
// yield does not.
const toEventLoop = () => new Promise((resolve) => {
  const channel = new MessageChannel();
  channel.port1.onmessage = () => { channel.port1.close(); resolve(null); };
  channel.port2.postMessage(null);
});

/** @param {string} widget */
function drop(widget) {
  for (const turn of turns) if (turn.widget === widget) turn.run.destroy();
  turns = turns.filter((turn) => turn.widget !== widget);
}

self.onmessage = async ({ data: { id, widget, request } }) => {
  let runs;
  try {
    const started = await simulator;
    // After the wait, so requests that arrive while Pyodide starts replace each
    // other in the order the widget sent them.
    drop(widget);
    runs = started.runs(request);
  } catch (error) {
    self.postMessage({ id, kind: "error", message: lastLine(error) });
    return;
  }
  const [legacy, incremental] = runs.toJs({ depth: 1 });
  runs.destroy();
  turns.push(
    { id, widget, collector: "legacy", run: legacy },
    { id, widget, collector: "incremental", run: incremental },
  );
  if (!running) take();
};

async function take() {
  running = true;
  while (turns.length) {
    const turn = /** @type {(typeof turns)[number]} */ (turns.shift());
    try {
      const part = turn.run.next();
      if (part.done) {
        turn.run.destroy();
        if (!turns.some((other) => other.id === turn.id)) {
          self.postMessage({ id: turn.id, kind: "done" });
        }
      } else {
        const records = part.value.toJs();
        part.value.destroy();
        self.postMessage({ id: turn.id, kind: "records", collector: turn.collector, records });
        turns.push(turn);
      }
    } catch (error) {
      turn.run.destroy();
      drop(turn.widget);
      self.postMessage({ id: turn.id, kind: "error", message: lastLine(error) });
    }
    await toEventLoop();
  }
  running = false;
}
