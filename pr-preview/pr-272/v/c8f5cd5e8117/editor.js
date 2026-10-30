// @ts-check
// The playground's first editor (ADR 0013): the widget's legend, made to edit the
// request it describes. The other, source.js, writes the request as Python. Each
// structure's line opens fields for its shape, size, root, lifetime, rebuild
// interval, build's churn and gc.collect() calls, and the churn's line, the run's
// line and the constants' line open theirs. A change goes into the request, and
// the widget runs it again, as a control's release does. A structure can take
// a shape of the reader's own, its links written in Python (ADR 0014). The
// functions above the Editor class change a request without the DOM, so Node's
// test runner can load this module: see tests/editor.test.js.

import { describe, describeChurn, describeConstants, describeRun } from "./graph.js";

/** @typedef {import("./graph.js").Graph} Graph */
/**
 * A shape as a request names it: "tree", its name with its one parameter, such
 * as { chains: 16 }, or { own: code } for the reader's own.
 * @typedef {"tree" | { [name: string]: number | string }} Shape
 */
/**
 * One structure as a request holds it.
 * @typedef {{
 *   shape: Shape, size: number, root: "module" | "frame", lifetime: number | null,
 *   rebuild_interval: number | null, build_churn: number, full_collections: boolean,
 *   built_in_frame: boolean,
 * }} Structure
 */
/**
 * A request with its workload spelled out, as the editor changes it.
 * @typedef {{
 *   workload: {
 *     churn: import("./graph.js").Churn, structures: Structure[], seed: number, shutdown: boolean,
 *   },
 *   settings: { threshold0: number, threshold1: number, threshold2: number },
 *   run_length: number,
 *   every: number,
 *   constants: import("./graph.js").Constants,
 * }} Request
 */

/**
 * The shapes a structure can take: each one's title, and the label, default and
 * least value of its parameter, as pep848_sim.structures refuses less.
 * @type {{ [name: string]: { title: string, parameter?: { label: string, value: number, min: number } } }}
 */
export const SHAPES = {
  chains: { title: "Chains", parameter: { label: "Chains", value: 16, min: 1 } },
  tree: { title: "Tree with parent pointers" },
  hierarchy: { title: "Hierarchy", parameter: { label: "Branches", value: 6, min: 1 } },
  graph: { title: "Graph", parameter: { label: "Edges a node", value: 2, min: 0 } },
  rings: { title: "Rings", parameter: { label: "Objects a ring", value: 21, min: 1 } },
  own: { title: "Your own, in Python" },
};

/** The code a shape of the reader's own starts from: a doubly linked list. */
export const OWN = `def links(i):
    # The links object i brings, as (source, target) pairs
    # among objects 0 to i. One link from an earlier object
    # holds object i.
    if i == 0:
        return []
    # A doubly linked list: each object and the one before
    # it hold each other.
    return [(i - 1, i), (i, i - 1)]
`;

/** The name of a shape: "tree", "chains" and so on. */
export const nameOf = (/** @type {Shape} */ shape) => (typeof shape === "string" ? shape : Object.keys(shape)[0]);

/**
 * The shape of that name, with its parameter's default, or the code a shape of
 * the reader's own starts from.
 * @param {string} name
 * @returns {Shape}
 */
export function shapeNamed(name) {
  if (name === "own") return { own: OWN };
  const { parameter } = SHAPES[name];
  return parameter ? { [name]: parameter.value } : "tree";
}

/**
 * What Enter starts the next line of code with, after the line before the
 * caret: that line's indent, and four spaces more after a colon.
 * @param {string} line
 */
export function indentAfter(line) {
  const indent = /** @type {string} */ (/^[ \t]*/.exec(line)?.[0]);
  return line.trimEnd().endsWith(":") ? `${indent}    ` : indent;
}

/**
 * Make a textarea take code: Enter keeps the line's indent, with four spaces
 * more after a colon, and Ctrl+Enter commits the code.
 * @param {HTMLTextAreaElement} area
 * @param {() => void} commit
 */
export function typeCode(area, commit) {
  area.spellcheck = false;
  area.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    if (event.ctrlKey || event.metaKey) {
      commit();
      return;
    }
    const { selectionStart: start, selectionEnd: end, value } = area;
    const text = `\n${indentAfter(value.slice(value.lastIndexOf("\n", start - 1) + 1, start))}`;
    // insertText keeps the box's undo; setRangeText where a browser lacks it.
    if (!document.execCommand("insertText", false, text)) area.setRangeText(text, start, end, "end");
  });
}

/**
 * What can hold a structure, as the legend offers it: sys from the structure's
 * first object, a frame, or a frame while the structure builds and sys once it
 * has, as a module-level `X = build()` does.
 */
const HOLDERS = { module: "sys", frame: "a frame", built: "a frame, then sys" };

/**
 * Which of the holders holds the structure.
 * @param {Structure} structure
 */
const holderOf = (structure) => (structure.root === "module" && structure.built_in_frame ? "built" : structure.root);

/**
 * A structure to add: a 1 MB tree in a frame, rebuilt every 4 MB and dropped
 * 2 MB after each build.
 * @returns {Structure}
 */
export const newStructure = () => ({
  shape: "tree", size: 1000, root: "frame", lifetime: 2000, rebuild_interval: 4000, build_churn: 0, full_collections: false,
  built_in_frame: false,
});

/**
 * Move the structure at `i` by `by` places, if the list has room, and return
 * where it went.
 * @param {Structure[]} structures
 * @param {number} i
 * @param {number} by
 */
export function move(structures, i, by) {
  const j = i + by;
  if (j < 0 || j >= structures.length) return i;
  [structures[i], structures[j]] = [structures[j], structures[i]];
  return j;
}

/**
 * The real objects one simulated object, 1 kB, stands for when a real object
 * takes `bytes`: "16 real ones" at 64 B, "about 21.3 real ones" at 48 B.
 * @param {number} bytes
 */
export function realOnes(bytes) {
  const count = 1024 / bytes;
  const shown = Number.isInteger(count) ? count : +count.toFixed(count < 100 ? 1 : 0);
  return `${shown === count ? "" : "about "}${shown} real ${shown === 1 ? "one" : "ones"}`;
}

/** A share as the editor shows it, a percentage to a tenth: "1/50" is 2. */
export function percentOf(/** @type {string} */ share) {
  const [numerator, denominator = "1"] = share.split("/");
  return Math.round((1000 * Number(numerator)) / Number(denominator)) / 10;
}

/** A percentage as the request holds it, in thousandths: 2.5 is "25/1000". */
export const shareOf = (/** @type {number} */ percent) => `${Math.round(percent * 10)}/1000`;

/** The editor's own styles, which the widget adds to its shadow root. */
export const EDITOR_STYLE = `
  /* Each structure's fields go under its line, as do the churn's and the run's. */
  .editing li { display: block; }
  .editing > .line, .editing > .fields, .editing .add { font-size: 12px; color: var(--text-secondary); }
  .editing .line { display: flex; gap: 6px; align-items: baseline; }
  .editing h3:not(:first-child) { margin-top: 12px; }
  .editing .toggle, .editing .add {
    border: 0; padding: 0; background: none; font: inherit; color: var(--text-primary);
    text-decoration: underline; cursor: pointer;
  }
  .editing .add { margin: 2px 0 6px; }
  .editing .fields {
    display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px 10px;
    margin: 6px 0 10px 21px; padding: 4px 0 4px 10px; border-left: 2px solid var(--grid);
  }
  .editing .fields label { display: grid; gap: 2px; align-content: start; }
  .editing .fields .check { display: flex; gap: 6px; align-items: center; grid-column: span 2; }
  .editing .fields .wide { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 8px; }
  .editing input, .editing select, .editing .fields button {
    font: inherit; color: var(--text-primary); background: var(--surface);
    border: 1px solid var(--baseline); border-radius: 4px; padding: 2px 5px;
  }
  .editing input[type="number"] { width: 100%; box-sizing: border-box; font-variant-numeric: tabular-nums; }
  .editing input[type="checkbox"] { margin: 0; accent-color: var(--text-secondary); }
  .editing .fields button:disabled { color: var(--text-muted); }
  .editing .problem { grid-column: 1 / -1; margin: 0; color: var(--text-primary); font-weight: 600; }
  .editing .code { grid-column: 1 / -1; display: grid; gap: 4px; }
  .editing .code p { margin: 0; }
  .editing .code button { justify-self: start; }
  .editing textarea {
    width: 100%; box-sizing: border-box; resize: vertical; padding: 4px 6px; tab-size: 4;
    font: 12px/1.45 ui-monospace, "Cascadia Code", Consolas, monospace; white-space: pre;
    color: var(--text-primary); background: var(--surface); border: 1px solid var(--baseline); border-radius: 4px;
  }
`;

/**
 * The legend of a widget that edits its request. The widget hands it the
 * request once the worker has spelled it out, and each sample of the object
 * graph the worker sends, whose structures' words fill the lines.
 */
export class Editor {
  /** The widget's legend, which the editor fills. */
  #root;
  /** What runs the request again after a change. */
  #change;
  /** What ends the runs, Python stuck in the reader's code included. */
  #stop;
  /** @type {Request | null} */
  #request = null;
  /** The structures, by object, and the lines, "churn", "run" and "constants", whose fields show. */
  /** @type {Set<Structure | string>} */
  #open = new Set();
  /** Each structure's words from the last sample, kept across a move. */
  /** @type {WeakMap<Structure, string>} */
  #words = new WeakMap();
  /** Where each structure's words show. */
  /** @type {Map<Structure, HTMLElement>} */
  #lines = new Map();
  /** The field the reader changed last, beside which a refusal shows. */
  #last = "";
  /** Where the churn's, the run's and the constants' words show. */
  #churn = document.createElement("span");
  #run = document.createElement("span");
  #constants = document.createElement("span");
  /** Where the real objects a dot stands for show. */
  #count = document.createElement("span");

  /**
   * @param {HTMLElement} root the widget's legend
   * @param {{ change: () => void, stop: () => void }} actions what runs the
   *   request again, and what ends the runs
   */
  constructor(root, { change, stop }) {
    this.#root = root;
    this.#change = change;
    this.#stop = stop;
  }

  /** The request the editor changes. */
  get request() {
    return this.#request;
  }

  /** Show the fields of this request, unless they show already. */
  edit(/** @type {Request} */ request) {
    if (request === this.#request) return;
    this.#request = request;
    this.#open.clear();
    this.#last = "";
    this.#render();
  }

  /** Word each structure's line from a sample of the request's object graph. */
  describe(/** @type {Graph} */ graph) {
    const structures = this.#request?.workload.structures ?? [];
    graph.structures.forEach((sampled, i) => {
      if (i < structures.length) this.#words.set(structures[i], describe(sampled));
    });
    for (const [structure, words] of this.#lines) words.textContent = this.#words.get(structure) ?? "";
  }

  /**
   * Show the simulator's refusal, in its own words, beside the field the reader
   * changed last, and say whether that field shows.
   * @param {string} message
   */
  fail(message) {
    return this.#refuse(this.#last, message.replace(/^ValueError: /, ""));
  }

  /** Draw the lines and the open fields, and focus the field of that key. */
  #render(focus = "") {
    const request = this.#request;
    if (!request) return;
    const { structures } = request.workload;
    this.#lines.clear();
    const heading = document.createElement("h3");
    heading.textContent = "Object graph";
    const about = document.createElement("p");
    about.append("A few objects of each structure, as its shape links them. One dot is one simulated object, ",
      this.#count, ". A red link lies on a cycle, so dropping its structure leaves cyclic garbage. Edit a line "
      + "to change it, and each change runs both collectors again.");
    const list = document.createElement("ol");
    structures.forEach((structure, i) => {
      const item = document.createElement("li");
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = String(i + 1);
      const words = document.createElement("span");
      words.textContent = this.#words.get(structure) ?? "";
      this.#lines.set(structure, words);
      item.append(this.#line(structure, `${i}:toggle`, badge, words));
      if (this.#open.has(structure)) item.append(this.#structureFields(structure, i));
      list.append(item);
    });
    const add = document.createElement("button");
    add.type = "button";
    add.className = "add";
    add.textContent = "Add a structure";
    add.dataset.focus = "add";
    add.addEventListener("click", () => {
      const structure = newStructure();
      structures.push(structure);
      this.#open.add(structure);
      this.#changed(`${structures.length - 1}:shape`, true);
    });
    this.#reword();
    this.#root.replaceChildren(heading, about, list, add, this.#line("churn", "churn:toggle", this.#churn));
    if (this.#open.has("churn")) this.#root.append(this.#churnFields());
    this.#root.append(this.#line("run", "run:toggle", this.#run));
    if (this.#open.has("run")) this.#root.append(this.#runFields());
    const constants = document.createElement("h3");
    constants.textContent = "Constants no Python API changes";
    this.#root.append(constants, this.#line("constants", "constants:toggle", this.#constants));
    if (this.#open.has("constants")) this.#root.append(this.#constantsFields());
    if (focus) /** @type {HTMLElement | null} */ (this.#root.querySelector(`[data-focus="${focus}"]`))?.focus();
  }

  /**
   * A line: its words, and a button that shows or hides its fields.
   * @param {Structure | string} what
   * @param {string} key
   * @param {...HTMLElement} parts
   */
  #line(what, key, ...parts) {
    const line = document.createElement("div");
    line.className = "line";
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "toggle";
    toggle.dataset.focus = key;
    const open = this.#open.has(what);
    toggle.textContent = open ? "done" : "edit";
    toggle.setAttribute("aria-expanded", String(open));
    toggle.addEventListener("click", () => {
      if (open) this.#open.delete(what);
      else this.#open.add(what);
      this.#render(key);
    });
    line.append(...parts, toggle);
    return line;
  }

  /**
   * The fields of the structure at `i`.
   * @param {Structure} structure
   * @param {number} i
   */
  #structureFields(structure, i) {
    const { structures } = /** @type {Request} */ (this.#request).workload;
    const name = nameOf(structure.shape);
    const titles = Object.fromEntries(Object.entries(SHAPES).map(([shape, { title }]) => [shape, title]));
    const fields = this.#fields(
      this.#label("Shape", this.#select(`${i}:shape`, titles, name, (picked) => {
        structure.shape = shapeNamed(picked);
        return true;
      })),
    );
    const { parameter } = SHAPES[name];
    if (parameter && typeof structure.shape !== "string") {
      const shape = structure.shape;
      fields.append(this.#label(parameter.label, this.#number(`${i}:parameter`, Number(shape[name]), (value) => {
        shape[name] = /** @type {number} */ (value);
      }, { min: parameter.min })));
    } else {
      fields.append(document.createElement("span"));
    }
    fields.append(this.#label("Size (objects)", this.#number(`${i}:size`, structure.size, (value) => {
      structure.size = /** @type {number} */ (value);
    }, { min: 1 })));
    if (name === "own" && typeof structure.shape !== "string") fields.append(this.#code(`${i}:code`, structure.shape));
    fields.append(
      this.#label("Held by", this.#select(`${i}:root`, HOLDERS, holderOf(structure), (holder) => {
        structure.root = holder === "frame" ? "frame" : "module";
        structure.built_in_frame = holder === "built";
        return false;
      })),
      this.#label("Lifetime (kB)", this.#number(`${i}:lifetime`, structure.lifetime, (value) => {
        structure.lifetime = value;
      }, { nullable: "to the end" })),
      this.#label("Rebuilt every (kB)", this.#number(`${i}:rebuild_interval`, structure.rebuild_interval, (value) => {
        structure.rebuild_interval = value;
      }, { min: 1, nullable: "never" })),
      this.#label("Churn after each object (kB)", this.#number(`${i}:build_churn`, structure.build_churn, (value) => {
        structure.build_churn = /** @type {number} */ (value);
      })),
      this.#check(`${i}:full_collections`, "gc.collect() before each build and after each drop", structure.full_collections,
        (checked) => { structure.full_collections = checked; }),
    );
    const buttons = document.createElement("div");
    buttons.className = "wide";
    buttons.append(
      this.#button(`${i}:up`, "Move up", i === 0, () => `${move(structures, i, -1)}:up`),
      this.#button(`${i}:down`, "Move down", i === structures.length - 1, () => `${move(structures, i, 1)}:down`),
      this.#button(`${i}:remove`, "Remove", false, () => {
        structures.splice(i, 1);
        return "add";
      }),
    );
    fields.append(buttons);
    return fields;
  }

  /**
   * The code of a shape of the reader's own. Leaving the box or Ctrl+Enter runs
   * it, and Enter keeps the line's indent, with four spaces more after a colon.
   * A button ends runs stuck in it.
   * @param {string} key
   * @param {{ [name: string]: number | string }} shape
   */
  #code(key, shape) {
    const area = document.createElement("textarea");
    area.dataset.focus = key;
    area.value = String(shape.own);
    area.rows = area.value.split("\n").length + 1;
    const commit = () => {
      if (area.value === shape.own) return;
      shape.own = area.value;
      this.#changed(key, false);
    };
    area.addEventListener("change", commit);
    typeCode(area, commit);
    const label = document.createElement("label");
    label.append("links(i), in Python", area);
    const hint = document.createElement("p");
    hint.textContent = "Leaving the box or Ctrl+Enter runs it. The simulator calls links(i) more than once "
      + "for each object, so its answer must depend on i alone.";
    const stop = document.createElement("button");
    stop.type = "button";
    stop.textContent = "Stop the runs";
    stop.addEventListener("click", () => this.#stop());
    const code = document.createElement("div");
    code.className = "code";
    code.append(label, hint, stop);
    return code;
  }

  #churnFields() {
    const churn = /** @type {Request} */ (this.#request).workload.churn;
    const [low, high] = churn.long_lifetimes;
    return this.#fields(
      this.#label("Lifetime mean (kB)", this.#number("churn:lifetime_mean", churn.lifetime_mean, (value) => {
        churn.lifetime_mean = /** @type {number} */ (value);
      }, { min: 1 })),
      this.#label("Living longer (%)", this.#number("churn:long_share", percentOf(churn.long_share), (value) => {
        churn.long_share = shareOf(/** @type {number} */ (value));
      }, { step: 0.1, max: 100 })),
      document.createElement("span"),
      this.#label("Longer, from (kB)", this.#number("churn:long_from", low, (value) => {
        churn.long_lifetimes = [/** @type {number} */ (value), churn.long_lifetimes[1]];
      }, { min: 1 })),
      this.#label("to (kB)", this.#number("churn:long_to", high, (value) => {
        churn.long_lifetimes = [churn.long_lifetimes[0], /** @type {number} */ (value)];
      }, { min: 1 })),
      document.createElement("span"),
      this.#label("In cycles (%)", this.#number("churn:cycle_share", percentOf(churn.cycle_share), (value) => {
        churn.cycle_share = shareOf(/** @type {number} */ (value));
      }, { step: 0.1, max: 100 })),
      this.#label("Cycle size (objects)", this.#number("churn:cycle_size", churn.cycle_size, (value) => {
        churn.cycle_size = /** @type {number} */ (value);
      }, { min: 1 })),
    );
  }

  #runFields() {
    const request = /** @type {Request} */ (this.#request);
    const { settings } = request;
    return this.#fields(
      this.#label("Run length (kB)", this.#number("run:run_length", request.run_length, (value) => {
        request.run_length = /** @type {number} */ (value);
      }, { min: 1 })),
      this.#check("run:shutdown", "Shutdown at the end", request.workload.shutdown, (checked) => {
        request.workload.shutdown = checked;
      }),
      this.#label("threshold0 (kB)", this.#number("run:threshold0", settings.threshold0, (value) => {
        settings.threshold0 = /** @type {number} */ (value);
      }, { min: 1 })),
      this.#label("threshold1", this.#number("run:threshold1", settings.threshold1, (value) => {
        settings.threshold1 = /** @type {number} */ (value);
      })),
      this.#label("threshold2", this.#number("run:threshold2", settings.threshold2, (value) => {
        settings.threshold2 = /** @type {number} */ (value);
      })),
    );
  }

  #constantsFields() {
    const { constants } = /** @type {Request} */ (this.#request);
    return this.#fields(
      this.#label("Initial work budget (real objects)", this.#number(
        "constants:initial_work_budget",
        constants.initial_work_budget,
        (value) => { constants.initial_work_budget = /** @type {number} */ (value); },
        { min: null },
      )),
      this.#label("Freed-credit multiplier", this.#number("constants:freed_credit", constants.freed_credit, (value) => {
        constants.freed_credit = /** @type {number} */ (value);
      })),
      this.#label("Long-lived ratio (%)", this.#number(
        "constants:long_lived_ratio",
        percentOf(constants.long_lived_ratio),
        (value) => { constants.long_lived_ratio = shareOf(/** @type {number} */ (value)); },
        { step: 0.1 },
      )),
      this.#label("Real object (B)", this.#number("constants:real_object_size", constants.real_object_size, (value) => {
        constants.real_object_size = /** @type {number} */ (value);
      }, { min: 1 })),
    );
  }

  /** @param {...HTMLElement} parts */
  #fields(...parts) {
    const fields = document.createElement("div");
    fields.className = "fields";
    fields.append(...parts);
    return fields;
  }

  /** @param {string} text @param {HTMLElement} control */
  #label(text, control) {
    const label = document.createElement("label");
    label.append(text, control);
    return label;
  }

  /**
   * A whole number field, or a share's to a tenth, from 0 unless `min` gives
   * another least value, or null for none. An empty field reads as null where
   * `nullable` gives the placeholder that says what null means.
   * @param {string} key
   * @param {number | null} value
   * @param {(value: number | null) => void} set
   * @param {{ min?: number | null, max?: number, step?: number, nullable?: string }} options
   */
  #number(key, value, set, { min = 0, max, step = 1, nullable } = {}) {
    const input = document.createElement("input");
    input.type = "number";
    input.dataset.focus = key;
    Object.assign(input, { step: String(step), required: nullable === undefined });
    if (min !== null) input.min = String(min);
    if (max !== undefined) input.max = String(max);
    if (nullable !== undefined) input.placeholder = nullable;
    input.value = value === null ? "" : String(value);
    input.addEventListener("change", () => {
      if (!input.checkValidity()) {
        this.#refuse(key, input.validationMessage);
        return;
      }
      set(input.value === "" ? null : Number(input.value));
      this.#changed(key, false);
    });
    return input;
  }

  /**
   * A select of `options`, keys to titles. `set` says whether the change needs
   * the fields drawn again.
   * @param {string} key
   * @param {{ [value: string]: string }} options
   * @param {string} value
   * @param {(value: string) => boolean} set
   */
  #select(key, options, value, set) {
    const select = document.createElement("select");
    select.dataset.focus = key;
    select.append(...Object.entries(options).map(([option, title]) => new Option(title, option)));
    select.value = value;
    select.addEventListener("change", () => this.#changed(key, set(select.value)));
    return select;
  }

  /**
   * @param {string} key
   * @param {string} text
   * @param {boolean} checked
   * @param {(checked: boolean) => void} set
   */
  #check(key, text, checked, set) {
    const label = document.createElement("label");
    label.className = "check";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.dataset.focus = key;
    input.checked = checked;
    input.addEventListener("change", () => {
      set(input.checked);
      this.#changed(key, false);
    });
    label.append(input, text);
    return label;
  }

  /**
   * A button that changes the structures and draws the fields again, focusing
   * the key `act` returns.
   * @param {string} key
   * @param {string} text
   * @param {boolean} disabled
   * @param {() => string} act
   */
  #button(key, text, disabled, act) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.focus = key;
    button.textContent = text;
    button.disabled = disabled;
    button.addEventListener("click", () => this.#changed(act(), true));
    return button;
  }

  /**
   * After a change, run the request again. A change to the structures draws the
   * fields again and focuses the key's; a change of a value leaves the fields as
   * they are, so that focus moves on as the reader tabs, and rewords the churn's,
   * the run's and the constants' lines.
   * @param {string} key the field to focus, and to show a refusal beside
   * @param {boolean} redraw
   */
  #changed(key, redraw) {
    this.#last = key;
    this.#root.querySelector(".problem")?.remove();
    if (redraw) this.#render(key);
    else this.#reword();
    this.#change();
  }

  #reword() {
    const request = /** @type {Request} */ (this.#request);
    this.#churn.textContent = describeChurn(request.workload.churn);
    this.#run.textContent = describeRun(request);
    this.#constants.textContent = describeConstants(request.constants);
    this.#count.textContent = realOnes(request.constants.real_object_size);
  }

  /**
   * Show a refusal under the field of that key, and say whether the field shows.
   * @param {string} key
   * @param {string} message
   */
  #refuse(key, message) {
    this.#root.querySelector(".problem")?.remove();
    const field = key && this.#root.querySelector(`[data-focus="${key}"]`);
    if (!field || !field.closest(".fields")) return false;
    const problem = document.createElement("p");
    problem.className = "problem";
    problem.setAttribute("role", "alert");
    problem.textContent = message;
    (field.closest("label") ?? field).after(problem);
    return true;
  }
}
