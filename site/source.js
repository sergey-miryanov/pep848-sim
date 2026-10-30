// @ts-check
// The playground's other editor (ADR 0015): the workload, the run length, the
// collector settings and the constants as Python source beside the widget, which
// the reader runs with a button or Ctrl+Enter. pep848_sim.widget.source reads it
// in the worker, and the request comes back spelled out, as one that names a
// preset does.
// `toSource` writes the source of a request without the DOM, so Node's test
// runner can load this module: see tests/source.test.js.

import { nameOf, SHAPES, typeCode } from "./editor.js";

/** @typedef {import("./editor.js").Request} Request */
/** @typedef {import("./editor.js").Shape} Shape */

// The names a workload source sees and sets, which a shape's function keeps
// clear of.
const TAKEN = [
  "Chains", "Tree", "Hierarchy", "Graph", "Rings", "Own", "Structure", "Churn", "Settings", "Constants",
  "churn", "structures", "run_length", "settings", "seed", "shutdown", "constants",
];
// The widest line a call's arguments fill before the next line takes them, so
// that a line fits the box beside the widget.
const WIDTH = 66;
// The seed of a source that sets none, as pep848_sim.widget.source reads it.
const SEED = 848;

const ABOUT = `# The workload both runs share, as Python. Sizes, lifetimes
# and intervals are in kB: one simulated object is 1 kB.
# Press Run or Ctrl+Enter to run it.`;

const ABOUT_OWN = `# A shape of your own is a function of i that gives the links
# object i brings, as (source, target) pairs among objects 0
# to i, one of them from an earlier object that holds object i.
# Own(...) takes it. It sees only i and what it imports itself.`;

const ABOUT_CONSTANTS = `# Numbers no Python API changes. The incremental collector's
# work budget starts at initial_work_budget real objects, and
# gains freed_credit for each object an increment frees. The
# legacy collector's gen 2 waits for long_lived_ratio of the
# objects the last gen 2 left. A real object takes
# real_object_size bytes: at 64, 16 make a simulated object.`;

// What the source offers when no structure takes a shape of its own.
const EXAMPLE = `def doubly_linked(i):
    if i == 0:
        return []
    # Each object and the one before it hold each other.
    return [(i - 1, i), (i, i - 1)]`;

// The source writes a request's values as Python literals and refuses any it
// cannot, so that a link's code lies in a shape of the reader's own, which
// waits for Run (ADR 0016).

/** A number as Python takes it, in groups of three from 10,000 up. */
const py = (/** @type {unknown} */ value) => {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new TypeError(`${JSON.stringify(value)} is not a number`);
  return Math.abs(value) >= 10_000 ? String(value).replace(/\B(?=(\d{3})+(?!\d))/g, "_") : String(value);
};

/** Text, such as a share or a root, as a Python string on one line. */
const pyText = (/** @type {unknown} */ value) => {
  if (typeof value !== "string") throw new TypeError(`${JSON.stringify(value)} is not text`);
  return JSON.stringify(value);
};

/** A setting's name as a keyword, which Settings refuses unless it takes it. */
const setting = (/** @type {string} */ name) => {
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) throw new TypeError(`no setting ${JSON.stringify(name)}`);
  return name;
};

/**
 * Text as a Python string: triple-quoted, a line to each of its lines, unless
 * it holds what would end or escape such a string.
 * @param {string} text
 */
const pyString = (text) => (/"""|\\/.test(text) || text.endsWith('"') ? JSON.stringify(text) : `"""\\\n${text}"""`);

/**
 * A call, its arguments filling each line up to WIDTH, and the next line
 * taking them on under the first.
 * @param {string} start what the call's first line starts with, its "(" last
 * @param {string[]} args
 */
function call(start, args) {
  const indent = " ".repeat(start.length);
  const lines = [];
  let line = start;
  args.forEach((arg, i) => {
    const piece = `${arg}${i < args.length - 1 ? "," : ""}`;
    const fresh = line === start || line === indent;
    if (!fresh && line.length + 1 + piece.length > WIDTH) {
      lines.push(line);
      line = indent + piece;
    } else {
      line += fresh ? piece : ` ${piece}`;
    }
  });
  lines.push(`${line})`);
  return lines.join("\n");
}

/**
 * The function a shape's code defines, when the code holds that function alone:
 * its first line defines it, and every line after is indented or blank. Its
 * name, and its text without blank lines around it.
 * @param {string} code
 */
export function functionOf(code) {
  const lines = code.replace(/\s+$/, "").split("\n");
  while (lines.length && !lines[0].trim()) lines.shift();
  const name = /^def\s+([A-Za-z_]\w*)\s*\(/.exec(lines[0] ?? "")?.[1];
  if (!name || lines.slice(1).some((line) => line.trim() && !/^\s/.test(line))) return null;
  return { name, text: lines.join("\n") };
}

/**
 * The request's workload, run length, collector settings and constants as
 * Python source, as pep848_sim.widget.source reads it. A shape of the reader's
 * own goes in as its function, under its own name unless another takes it, or
 * as code in a string when it holds more than a function.
 * @param {Request} request
 */
export function toSource(request) {
  const { workload: { churn, structures, seed, shutdown }, settings, run_length: runLength, constants } = request;
  const taken = new Set(TAKEN);
  const unique = (/** @type {string} */ name) => {
    let free = name;
    for (let n = 2; taken.has(free); n++) free = `${name}_${n}`;
    taken.add(free);
    return free;
  };
  /** Each shape's code, by the name the source gives it. */
  /** @type {Map<string, string>} */
  const names = new Map();
  /** Each shape's definition: its function, or its code in a string. */
  /** @type {string[]} */
  const shapes = [];
  structures.forEach(({ shape }, i) => {
    if (nameOf(shape) !== "own") return;
    const code = String(/** @type {{ own: string }} */ (shape).own);
    if (names.has(code)) return;
    const alone = functionOf(code);
    const name = unique(alone ? alone.name : `shape_${i + 1}`);
    names.set(code, name);
    shapes.push(alone ? alone.text.replace(/^def\s+\w+/, `def ${name}`) : `${name} = ${pyString(code)}`);
  });
  const shapeOf = (/** @type {Shape} */ shape) => {
    const name = nameOf(shape);
    if (!Object.hasOwn(SHAPES, name)) throw new TypeError(`no shape ${JSON.stringify(name)}`);
    if (name === "tree") return "Tree()";
    const value = /** @type {{ [name: string]: number | string }} */ (shape)[name];
    if (name === "own") return `Own(${names.get(String(value))})`;
    return `${name[0].toUpperCase()}${name.slice(1)}(${py(Number(value))})`;
  };
  const [low, high] = churn.long_lifetimes;
  const lines = [
    ABOUT,
    "",
    ABOUT_OWN,
    shapes.length ? shapes.join("\n\n\n") : `# Give it to a structure as Own(doubly_linked).\n${EXAMPLE}`,
    "",
    "",
    call("churn = Churn(", [
      `lifetime_mean=${py(churn.lifetime_mean)}`, `cycle_share=${pyText(churn.cycle_share)}`,
      `cycle_size=${py(churn.cycle_size)}`, `long_share=${pyText(churn.long_share)}`,
      `long_lifetimes=(${py(low)}, ${py(high)})`,
    ]),
    "",
    structures.length ? "structures = [" : "structures = []",
    ...structures.map((structure) => {
      const args = [shapeOf(structure.shape), `size=${py(structure.size)}`, `root=${pyText(structure.root)}`];
      if (structure.lifetime !== null) args.push(`lifetime=${py(structure.lifetime)}`);
      if (structure.rebuild_interval !== null) args.push(`rebuild_interval=${py(structure.rebuild_interval)}`);
      const churn = structure.build_churn;
      if (churn) args.push(`build_churn=${typeof churn === "string" ? pyText(churn) : py(churn)}`);
      if (structure.full_collections) args.push("full_collections=True");
      if (structure.built_in_frame) args.push("built_in_frame=True");
      if (structure.built_in_c) args.push("built_in_c=True");
      return `${call("    Structure(", args)},`;
    }),
    ...(structures.length ? ["]"] : []),
    "",
    `run_length = ${py(runLength)}`,
    call("settings = Settings(", Object.entries(settings).map(([name, value]) => `${setting(name)}=${py(value)}`)),
    `shutdown = ${shutdown ? "True" : "False"}`,
    ...(seed === SEED ? [] : [`seed = ${py(seed)}`]),
    "",
    ABOUT_CONSTANTS,
    call("constants = Constants(", [
      `initial_work_budget=${py(constants.initial_work_budget)}`, `freed_credit=${py(constants.freed_credit)}`,
      `long_lived_ratio=${pyText(constants.long_lived_ratio)}`, `real_object_size=${py(constants.real_object_size)}`,
    ]),
  ];
  return `${lines.join("\n")}\n`;
}

/** The source's own styles, which the widget adds to its shadow root. */
export const SOURCE_STYLE = `
  .source { display: grid; gap: 8px; align-content: start; margin: 0 0 24px; font-size: 12px; color: var(--text-secondary); }
  .source[hidden] { display: none; }
  .source .head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .source h3 { margin: 0 8px 0 0; font-size: 13px; font-weight: 600; color: var(--text-primary); }
  .source button {
    font: inherit; color: var(--text-primary); background: var(--surface);
    border: 1px solid var(--baseline); border-radius: 4px; padding: 2px 8px; cursor: pointer;
  }
  .source button:disabled { color: var(--text-muted); cursor: default; }
  .source textarea {
    box-sizing: border-box; width: 100%; height: 60vh; min-height: 320px; resize: vertical;
    padding: 6px 8px; tab-size: 4; white-space: pre;
    font: 12px/1.45 ui-monospace, "Cascadia Code", Consolas, monospace;
    color: var(--text-primary); background: var(--surface); border: 1px solid var(--baseline); border-radius: 4px;
  }
  .source .problem { margin: 0; color: var(--text-primary); font-weight: 600; white-space: pre-wrap; }
  .source .note { margin: 0; padding: 2px 0 2px 8px; border-left: 2px solid var(--baseline); color: var(--text-primary); }
  .modes { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; }
  .modes label { display: flex; align-items: center; gap: 4px; }
  .modes input { margin: 0; accent-color: var(--text-secondary); }
  /* Beside the widget where the panels keep room, and above it where they do not. */
  @media (min-width: 1200px) {
    :host([source]) .frame {
      display: grid; grid-template-columns: minmax(440px, 0.8fr) minmax(0, 1.4fr); gap: 24px; align-items: start;
    }
    :host([source]) .source { position: sticky; top: 8px; margin: 0; }
    .source textarea { height: calc(100vh - 120px); }
  }
`;

/**
 * The source beside a widget that edits its request. It keeps each entry's text
 * while the entry's request stays the one the text made or was written from.
 */
export class Source {
  #area = document.createElement("textarea");
  #run = document.createElement("button");
  #status = document.createElement("span");
  #note = document.createElement("p");
  #problem = document.createElement("p");
  /**
   * Each entry's text, the text it last ran or was written as, and the request,
   * as JSON, that the text made or was written from.
   * @type {WeakMap<object, { text: string, ran: string, of: string }>}
   */
  #texts = new WeakMap();
  /** The entry whose text the box shows. */
  /** @type {{ request: any } | null} */
  #entry = null;

  /**
   * @param {HTMLElement} root where the source goes
   * @param {{ run: () => void, stop: () => void }} actions what runs the text,
   *   and what ends the runs
   */
  constructor(root, { run, stop }) {
    const heading = document.createElement("h3");
    heading.textContent = "The workload, in Python";
    const start = () => {
      // Ctrl+Enter, as the button, waits for a preset's source.
      if (this.#run.disabled) return;
      this.#problem.hidden = this.#note.hidden = true;
      run();
    };
    this.#run.type = "button";
    this.#run.textContent = "Run";
    this.#run.addEventListener("click", start);
    const end = document.createElement("button");
    end.type = "button";
    end.textContent = "Stop the runs";
    end.addEventListener("click", stop);
    const head = document.createElement("div");
    head.className = "head";
    head.append(heading, this.#run, end, this.#status);
    this.#area.setAttribute("aria-label", "The workload, in Python");
    this.#area.addEventListener("input", () => {
      const kept = this.#kept();
      if (kept) kept.text = this.#area.value;
      this.#mark();
    });
    typeCode(this.#area, start);
    this.#note.className = "note";
    this.#note.hidden = true;
    this.#problem.className = "problem";
    this.#problem.setAttribute("role", "alert");
    this.#problem.hidden = true;
    root.append(head, this.#note, this.#area, this.#problem);
  }

  /** The text in the box. */
  get text() {
    return this.#area.value;
  }

  /** Whether the box holds text that has not run. */
  get changed() {
    const kept = this.#kept();
    return kept !== undefined && kept.text !== kept.ran;
  }

  /**
   * Show the entry's source: the reader's text, while the entry's request stays
   * the one it made or was written from, and else the request written afresh.
   * A request that still names a preset has no source until the worker spells
   * it out. False when the playground cannot write the request as Python.
   * @param {{ request: any }} entry
   * @returns {boolean}
   */
  show(entry) {
    this.#entry = entry;
    const waiting = "preset" in entry.request;
    this.#area.disabled = this.#run.disabled = waiting;
    this.#problem.hidden = this.#note.hidden = true;
    if (waiting) {
      this.#area.value = "";
      this.#mark();
      return true;
    }
    const of = JSON.stringify(entry.request);
    let kept = this.#texts.get(entry);
    if (!kept || kept.of !== of) {
      let text;
      try {
        text = toSource(entry.request);
      } catch (error) {
        // A request the playground did not write, such as a link's: nothing to run.
        this.#area.value = "";
        this.#area.disabled = this.#run.disabled = true;
        this.fail(`The playground cannot write this request as Python: ${error instanceof Error ? error.message : error}.`);
        this.#mark();
        return false;
      }
      kept = { text, ran: text, of };
      this.#texts.set(entry, kept);
    }
    // Setting the same text would move the caret to its end.
    if (this.#area.value !== kept.text) this.#area.value = kept.text;
    this.#mark();
    return true;
  }

  /**
   * Note that the text ran and made the entry's request, which the worker sent
   * back spelled out.
   * @param {{ request: any }} entry
   * @param {string} text
   */
  ran(entry, text) {
    const kept = this.#texts.get(entry);
    if (!kept) return;
    kept.ran = text;
    kept.of = JSON.stringify(entry.request);
    this.#mark();
  }

  /**
   * Show the simulator's refusal, or a run's error, in its own words under the
   * box.
   * @param {string} message
   */
  fail(message) {
    this.#problem.textContent = message.replace(/^ValueError: /, "");
    this.#problem.hidden = false;
    return true;
  }

  /**
   * Say something above the box until the reader runs the text or another
   * entry shows, such as why a link's code waits for Run.
   * @param {string} message
   */
  note(message) {
    this.#note.textContent = message;
    this.#note.hidden = false;
  }

  #kept() {
    return this.#entry ? this.#texts.get(this.#entry) : undefined;
  }

  #mark() {
    this.#status.textContent = this.changed ? "Changed since it last ran" : "";
  }
}
