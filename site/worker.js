// @ts-check
// The page's worker. It starts Pyodide as soon as the page makes it (ADR 0009),
// and makes every widget's runs, a part of one run at a time, in turn (ADR 0006).
// It answers each request with the controls the widget asked for and the ranges
// the request allows, then posts records as the runs yield them (ADR 0007), each
// part with its run's figures so far.

// @ts-expect-error: an editor cannot fetch Pyodide's types from jsDelivr.
import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs";

/** pep848_sim.widget's modules, once Pyodide has started and imported them. */
const simulator = (async () => {
  const pyodide = await loadPyodide({
    indexURL: "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/",
  });
  const zip = await (await fetch("sim.zip")).arrayBuffer();
  pyodide.unpackArchive(zip, "zip", { extractDir: "/home/pyodide" });
  pyodide.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
  return {
    request: pyodide.pyimport("pep848_sim.widget.request"),
    figures: pyodide.pyimport("pep848_sim.widget.figures"),
    controls: pyodide.pyimport("pep848_sim.widget.controls"),
  };
})();

/**
 * The runs still going, in the order they take turns, each with its figures so far.
 * @typedef {{ id: number, widget: string, collector: string, run: any, figures: any }} Turn
 * @type {Turn[]}
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

/** @param {Turn} turn */
function end(turn) {
  turn.run.destroy();
  turn.figures.destroy();
}

/** @param {string} widget */
function drop(widget) {
  for (const turn of turns) if (turn.widget === widget) end(turn);
  turns = turns.filter((turn) => turn.widget !== widget);
}

self.onmessage = async ({ data: { id, widget, request, controls: paths } }) => {
  let started, controls, runs;
  try {
    started = await simulator;
    // After the wait, so requests that arrive while Pyodide starts replace each
    // other in the order the widget sent them.
    drop(widget);
    const ranged = started.controls.controls(request, paths);
    controls = ranged.toJs({ depth: 2 });
    ranged.destroy();
    runs = started.request.runs(request);
  } catch (error) {
    self.postMessage({ id, kind: "error", message: lastLine(error) });
    return;
  }
  self.postMessage({ id, kind: "controls", controls });
  const [legacy, incremental] = runs.toJs({ depth: 1 });
  runs.destroy();
  turns.push(
    { id, widget, collector: "legacy", run: legacy, figures: started.figures.Figures() },
    { id, widget, collector: "incremental", run: incremental, figures: started.figures.Figures() },
  );
  if (!running) take();
};

async function take() {
  running = true;
  while (turns.length) {
    const turn = /** @type {Turn} */ (turns.shift());
    try {
      const part = turn.run.next();
      if (part.done) {
        end(turn);
        if (!turns.some((other) => other.id === turn.id)) {
          self.postMessage({ id: turn.id, kind: "done" });
        }
      } else {
        const records = part.value.toJs();
        const figures = turn.figures.add(part.value);
        part.value.destroy();
        turn.figures.destroy();
        turn.figures = figures;
        const row = figures.row();
        self.postMessage({ id: turn.id, kind: "records", collector: turn.collector, records, figures: row.toJs() });
        row.destroy();
        turns.push(turn);
      }
    } catch (error) {
      end(turn);
      drop(turn.widget);
      self.postMessage({ id: turn.id, kind: "error", message: lastLine(error) });
    }
    await toEventLoop();
  }
  running = false;
}
