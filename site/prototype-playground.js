// @ts-nocheck
// PROTOTYPE, not for main (#153, #155): four layouts for the playground's editor
// around the real <gc-widget>, switched by ?variant=.
//
// A: a form beside the widget, run with a button.
// B: a table of structures above the widget, and sentences for the churn and the
//    run; each change runs both collectors again.
// C: the workload as Python source beside the widget, run with a button.
// D: the editor in the widget's own legend, beside the object graph; each change
//    runs both collectors again.
//
// Every layout starts from the stand-in or a preset (site/prototype-playground.json,
// from tools/prototype_playground.py), and any structure can take a shape of your
// own: Python that defines links(i), which pep848_sim.widget.prototype_playground
// runs. The widget gains a prototype `run(request)`.

import { describe, describeChurn } from "./graph.js";

const PRESETS = await (await fetch("prototype-playground.json")).json();
await customElements.whenDefined("gc-widget");

const OWN = [
  "def links(i):",
  "    # The links object i brings, as (source, target) pairs",
  "    # among objects 0 to i. Object 0 is the root.",
  "    if not i:",
  "        return []",
  "    # A doubly linked list: each object and the one before",
  "    # it hold each other.",
  "    return [(i - 1, i), (i, i - 1)]",
  "",
].join("\n");

const SHAPES = {
  chains: { title: "Chains", param: "Width", value: 16 },
  tree: { title: "Tree" },
  hierarchy: { title: "Hierarchy", param: "Branches", value: 6 },
  graph: { title: "Graph", param: "Edges a node", value: 2 },
  rings: { title: "Rings", param: "Length", value: 21 },
  own: { title: "Your own" },
};
const ROOTS = { module: "a module (sys)", frame: "a frame" };

const kindOf = (shape) => (typeof shape === "string" ? shape : Object.keys(shape)[0]);
const paramOf = (shape) => (typeof shape === "string" ? null : Object.values(shape)[0]);
function setKind(structure, kind) {
  structure.shape = kind === "tree" ? "tree" : { [kind]: kind === "own" ? OWN : SHAPES[kind].value };
}
function label(shape) {
  const value = paramOf(shape);
  switch (kindOf(shape)) {
    case "chains": return `${value} chains`;
    case "tree": return "a tree with parent pointers";
    case "hierarchy": return `a hierarchy of ${value} branches`;
    case "graph": return `a graph of ${value} edges a node`;
    case "rings": return `rings of ${value} object${value === 1 ? "" : "s"}`;
    default: return "a shape of your own";
  }
}
const newStructure = () => ({
  shape: "tree", size: 1000, root: "frame", lifetime: 2000, rebuild_interval: 4000, build_churn: 0, full_collections: false,
});

const gcd = (a, b) => (b ? gcd(b, a % b) : a);
const toPercent = (fraction) => {
  const [n, d = "1"] = String(fraction).split("/");
  return +((100 * Number(n)) / Number(d)).toFixed(2);
};
const toFraction = (percent) => {
  const n = Math.round(percent * 100), g = gcd(n, 10000) || 1;
  return n ? `${n / g}/${10000 / g}` : "0";
};
const kb = (value) => (value < 1000 ? `${value.toLocaleString("en")} kB` : `${(value / 1000).toLocaleString("en", { maximumFractionDigits: 1 })} MB`);
const py = (value) => (value >= 10000 ? String(value).replace(/\B(?=(\d{3})+(?!\d))/g, "_") : String(value));

/** The workload as Python source, for C. */
function toSource(request) {
  const { workload: { churn, structures, shutdown }, settings, run_length } = request;
  const lines = [
    "# The workload both runs share. Sizes, lifetimes and intervals are",
    "# in kB: one simulated object is 1 kB, 16 real objects.",
    "# Press Run, or Ctrl+Enter.",
    "",
    `churn = Churn(lifetime_mean=${py(churn.lifetime_mean)}, cycle_share="${churn.cycle_share}", cycle_size=${churn.cycle_size},`,
    `              long_share="${churn.long_share}", long_lifetimes=(${py(churn.long_lifetimes[0])}, ${py(churn.long_lifetimes[1])}))`,
    "",
  ];
  const names = new Map();
  structures.forEach((structure, i) => {
    if (kindOf(structure.shape) !== "own") return;
    const name = `shape_${i + 1}`;
    names.set(i, name);
    lines.push(structure.shape.own.replace(/def links\(/, `def ${name}(`).trimEnd(), "");
  });
  if (!names.size) {
    lines.push(
      "# A shape of your own: a function of i that gives the links object i",
      "# brings, as (source, target) pairs among objects 0 to i. Use it as",
      '# Structure(Own(doubly_linked), size=1000, root="frame").',
      "def doubly_linked(i):",
      "    if not i:",
      "        return []",
      "    return [(i - 1, i), (i, i - 1)]",
      "",
    );
  }
  const shapePy = (shape, name) => {
    const value = paramOf(shape);
    switch (kindOf(shape)) {
      case "chains": return `Chains(${value})`;
      case "tree": return "Tree()";
      case "hierarchy": return `Hierarchy(${value})`;
      case "graph": return `Graph(${value})`;
      case "rings": return `Rings(${value})`;
      default: return `Own(${name})`;
    }
  };
  lines.push("structures = [");
  structures.forEach((structure, i) => {
    const first = [shapePy(structure.shape, names.get(i)), `size=${py(structure.size)}`, `root="${structure.root}"`];
    const more = [];
    if (structure.lifetime !== null) more.push(`lifetime=${py(structure.lifetime)}`);
    if (structure.rebuild_interval !== null) more.push(`rebuild_interval=${py(structure.rebuild_interval)}`);
    if (structure.build_churn) more.push(`build_churn=${structure.build_churn}`);
    if (structure.full_collections) more.push("full_collections=True");
    lines.push(more.length
      ? `    Structure(${first.join(", ")},\n              ${more.join(", ")}),`
      : `    Structure(${first.join(", ")}),`);
  });
  lines.push(
    "]",
    "",
    `run_length = ${py(run_length)}`,
    `settings = Settings(threshold0=${settings.threshold0}, threshold1=${settings.threshold1}, threshold2=${settings.threshold2})`,
    `shutdown = ${shutdown ? "True" : "False"}`,
    "",
  );
  return lines.join("\n");
}

const state = { preset: "stand-in", request: structuredClone(PRESETS["stand-in"]), source: "", open: new Set() };
state.source = toSource(state.request);
const variant = () => new URLSearchParams(location.search).get("variant") ?? "A";
const sent = () => (variant() === "C" ? { source: state.source, every: state.request.every } : state.request);

/** What the current layout does when the reader edits a field, and after a run. */
let hooks = {};
let timer;
const showState = () => { document.querySelector("#state pre").textContent = JSON.stringify(sent(), null, 1); };
function edited() {
  showState();
  hooks.edited?.();
}
function run() {
  clearTimeout(timer);
  widget.run(sent());
  showState();
  hooks.ran?.();
}
const soon = () => { clearTimeout(timer); timer = setTimeout(run, 400); };

const widget = document.createElement("gc-widget");
widget.id = "playground";
const json = document.createElement("script");
json.type = "application/json";
json.textContent = JSON.stringify(sent());
widget.append(json);

// Small builders.
function el(tag, className, ...children) {
  const made = document.createElement(tag);
  if (className) made.className = className;
  made.append(...children);
  return made;
}
function button(text, onClick, className = "") {
  const made = el("button", className, text);
  made.type = "button";
  made.addEventListener("click", onClick);
  return made;
}
function number(value, set, { nullable = false, placeholder = "", step = 1 } = {}) {
  const input = el("input");
  input.type = "number";
  input.min = "0";
  input.step = String(step);
  input.value = value === null ? "" : String(value);
  input.placeholder = placeholder;
  input.addEventListener("change", () => {
    set(input.value === "" && nullable ? null : Number(input.value));
    edited();
  });
  return input;
}
function choice(options, value, set) {
  const select = el("select");
  for (const [key, text] of Object.entries(options)) select.append(new Option(text, key));
  select.value = value;
  select.addEventListener("change", () => set(select.value));
  return select;
}
function check(text, value, set) {
  const input = el("input");
  input.type = "checkbox";
  input.checked = value;
  input.addEventListener("change", () => { set(input.checked); edited(); });
  return el("label", "check", input, text);
}
const field = (text, control, className = "") => el("label", className, text, control);
function code(structure, rows = 9) {
  const area = el("textarea");
  area.rows = rows;
  area.spellcheck = false;
  area.value = structure.shape.own;
  area.addEventListener("input", () => { structure.shape.own = area.value; showState(); hooks.typed?.(); });
  area.addEventListener("change", () => edited());
  return area;
}
function startFrom() {
  const titles = Object.fromEntries(Object.keys(PRESETS).map((name) => [name, name === "stand-in" ? "Stand-in" : name]));
  return choice(titles, state.preset, (name) => {
    state.preset = name;
    state.request = structuredClone(PRESETS[name]);
    state.source = toSource(state.request);
    state.open.clear();
    render();
    run();
  });
}

// The fields of one structure, the churn and the run, as A and D lay them out.
function structureFields(structure, i, redraw) {
  const structures = state.request.workload.structures;
  const kind = kindOf(structure.shape);
  const fields = [
    field("Shape", choice(Object.fromEntries(Object.entries(SHAPES).map(([k, s]) => [k, s.title])), kind, (picked) => {
      setKind(structure, picked);
      redraw();
      edited();
    })),
  ];
  if (SHAPES[kind].param) {
    fields.push(field(SHAPES[kind].param, number(paramOf(structure.shape), (v) => { structure.shape[kind] = v; redraw(); })));
  } else {
    fields.push(el("span"));
  }
  if (kind === "own") fields.push(field("links(i), in Python", code(structure), "full"));
  fields.push(
    field("Size (kB)", number(structure.size, (v) => { structure.size = v; })),
    field("Held by", choice(ROOTS, structure.root, (v) => { structure.root = v; edited(); })),
    field("Lifetime (kB)", number(structure.lifetime, (v) => { structure.lifetime = v; }, { nullable: true, placeholder: "to the end" })),
    field("Rebuilt every (kB)", number(structure.rebuild_interval, (v) => { structure.rebuild_interval = v; }, { nullable: true, placeholder: "never" })),
    field("Churn per object (kB)", number(structure.build_churn, (v) => { structure.build_churn = v; })),
    el("span"),
    el("div", "full", check("gc.collect() before each build and after each drop", structure.full_collections, (v) => { structure.full_collections = v; })),
  );
  const remove = button("Remove", () => { structures.splice(i, 1); redraw(); edited(); });
  return { fields, remove };
}
function churnFields() {
  const churn = state.request.workload.churn;
  return [
    field("Lifetime, about (kB)", number(churn.lifetime_mean, (v) => { churn.lifetime_mean = v; })),
    field("In cycles (%)", number(toPercent(churn.cycle_share), (v) => { churn.cycle_share = toFraction(v); }, { step: 0.1 })),
    field("Cycle size", number(churn.cycle_size, (v) => { churn.cycle_size = v; })),
    field("Living longer (%)", number(toPercent(churn.long_share), (v) => { churn.long_share = toFraction(v); }, { step: 0.1 })),
    field("Longer, from (kB)", number(churn.long_lifetimes[0], (v) => { churn.long_lifetimes[0] = v; })),
    field("to (kB)", number(churn.long_lifetimes[1], (v) => { churn.long_lifetimes[1] = v; })),
  ];
}
function runFields() {
  const { request } = state;
  return [
    field("Run length (kB)", number(request.run_length, (v) => { request.run_length = v; })),
    field("threshold0 (kB)", number(request.settings.threshold0, (v) => { request.settings.threshold0 = v; })),
    field("threshold1", number(request.settings.threshold1, (v) => { request.settings.threshold1 = v; })),
    field("threshold2", number(request.settings.threshold2, (v) => { request.settings.threshold2 = v; })),
    el("div", "full", check("Shut down at the end, as a worker does", request.workload.shutdown, (v) => { request.workload.shutdown = v; })),
  ];
}

const stage = document.querySelector("#stage");

// A: the form beside the widget.
function variantA() {
  const editor = el("aside", "a-editor ed");
  const holder = el("div");
  stage.append(el("div", "a-grid", editor, holder));
  holder.append(widget);
  const status = el("span", "hint");
  const draw = () => {
    editor.replaceChildren(el("label", "start", "Start from", startFrom()), el("h3", "", "Structures"));
    state.request.workload.structures.forEach((structure, i) => {
      const { fields, remove } = structureFields(structure, i, draw);
      const legend = el("legend", "", `${i + 1} · ${label(structure.shape)}`, remove);
      editor.append(el("fieldset", "a-card", legend, el("div", "a-fields", ...fields)));
    });
    editor.append(
      button("+ Add a structure", () => { state.request.workload.structures.push(newStructure()); draw(); edited(); }),
      el("h3", "", "Churn"), el("div", "a-fields", ...churnFields()),
      el("h3", "", "Run"), el("div", "a-fields", ...runFields()),
      el("div", "a-run", button("Run", run, "primary"), status),
    );
  };
  const fresh = () => { status.textContent = "Ctrl+Enter runs too"; status.className = "hint"; };
  const stale = () => { status.textContent = "Changed since the last run"; status.className = "hint stale"; };
  hooks = { edited: stale, typed: stale, ran: fresh };
  draw();
  fresh();
}

// B: a table above the widget, and each change runs.
function variantB() {
  const ed = el("div", "ed");
  stage.append(ed);
  const holder = el("div", "b-widget");
  stage.append(holder);
  holder.append(widget);
  const draw = () => {
    const structures = state.request.workload.structures;
    const head = el("tr", "", ...["", "Shape", "", "Size (kB)", "Held by", "Lifetime (kB)", "Rebuilt every (kB)", "Churn per object (kB)", "gc.collect()", ""].map((t) => el("th", "", t)));
    const body = el("tbody");
    structures.forEach((structure, i) => {
      const kind = kindOf(structure.shape);
      const cell = (...children) => el("td", "", ...children);
      const param = SHAPES[kind].param
        ? field("", number(paramOf(structure.shape), (v) => { structure.shape[kind] = v; }))
        : el("span", "hint", kind === "own" ? "code below" : "");
      if (SHAPES[kind].param) param.title = SHAPES[kind].param;
      body.append(el("tr", "",
        el("td", "n", String(i + 1)),
        cell(choice(Object.fromEntries(Object.entries(SHAPES).map(([k, s]) => [k, s.title])), kind, (picked) => { setKind(structure, picked); draw(); edited(); })),
        cell(param),
        cell(number(structure.size, (v) => { structure.size = v; })),
        cell(choice(ROOTS, structure.root, (v) => { structure.root = v; edited(); })),
        cell(number(structure.lifetime, (v) => { structure.lifetime = v; }, { nullable: true, placeholder: "to the end" })),
        cell(number(structure.rebuild_interval, (v) => { structure.rebuild_interval = v; }, { nullable: true, placeholder: "never" })),
        cell(number(structure.build_churn, (v) => { structure.build_churn = v; })),
        cell(check("", structure.full_collections, (v) => { structure.full_collections = v; })),
        cell(button("×", () => { structures.splice(i, 1); draw(); edited(); })),
      ));
      if (kind === "own") {
        const area = code(structure, 8);
        const td = el("td", "", el("div", "hint", `Structure ${i + 1}'s links(i), in Python. Leaving the box runs it.`), area);
        td.colSpan = 10;
        body.append(el("tr", "", td));
      }
    });
    const churn = state.request.workload.churn;
    const { request } = state;
    ed.replaceChildren(
      el("div", "b-bar", el("label", "start", "Start from", startFrom()), el("span", "hint", "Each change runs both collectors again.")),
      el("table", "b-table", el("thead", "", head), body),
      el("p", "", button("+ Add a structure", () => { structures.push(newStructure()); draw(); edited(); })),
      el("div", "b-sentence",
        el("strong", "", "Churn:"), "objects live about", number(churn.lifetime_mean, (v) => { churn.lifetime_mean = v; }), "kB;",
        number(toPercent(churn.long_share), (v) => { churn.long_share = toFraction(v); }, { step: 0.1 }), "% live",
        number(churn.long_lifetimes[0], (v) => { churn.long_lifetimes[0] = v; }), "to",
        number(churn.long_lifetimes[1], (v) => { churn.long_lifetimes[1] = v; }), "kB;",
        number(toPercent(churn.cycle_share), (v) => { churn.cycle_share = toFraction(v); }, { step: 0.1 }), "% fall into cycles of",
        number(churn.cycle_size, (v) => { churn.cycle_size = v; }), "."),
      el("div", "b-sentence",
        el("strong", "", "Run:"), number(request.run_length, (v) => { request.run_length = v; }), "kB on the allocation clock under gc.set_threshold(",
        number(request.settings.threshold0, (v) => { request.settings.threshold0 = v; }), ",",
        number(request.settings.threshold1, (v) => { request.settings.threshold1 = v; }), ",",
        number(request.settings.threshold2, (v) => { request.settings.threshold2 = v; }), ")",
        check("then shut down", request.workload.shutdown, (v) => { request.workload.shutdown = v; })),
    );
  };
  hooks = { edited: soon };
  draw();
}

// C: Python source beside the widget.
function variantC() {
  state.source = toSource(state.request);
  const area = el("textarea");
  area.spellcheck = false;
  area.value = state.source;
  const status = el("span", "hint");
  area.addEventListener("input", () => { state.source = area.value; showState(); stale(); });
  const editor = el("div", "c-editor ed",
    el("div", "start", el("label", "start", "Start from", startFrom()), button("Run", run, "primary"), status),
    area,
    el("span", "hint", "Prototype: edits here stay in this layout. An error shows above the widget's figures."),
  );
  const holder = el("div");
  stage.append(el("div", "c-grid", editor, holder));
  holder.append(widget);
  const fresh = () => { status.textContent = "Ctrl+Enter runs too"; status.className = "hint"; };
  const stale = () => { status.textContent = "Changed since the last run"; status.className = "hint stale"; };
  hooks = { ran: fresh };
  fresh();
}

// D: the editor in the widget's legend, and each change runs.
const D_CSS = `
  .key-list { display: none !important; }
  .d-editor { font-size: 12px; color: var(--text-secondary); }
  .d-editor h3 { margin: 0 0 4px; font-size: 13px; font-weight: 600; color: var(--text-primary); }
  .d-editor p { margin: 0 0 8px; }
  .d-editor ol { list-style: none; margin: 0 0 4px; padding: 0; display: grid; gap: 4px; }
  .d-editor li > .line { display: flex; gap: 6px; align-items: baseline; }
  .d-editor .badge {
    flex: none; display: inline-grid; place-items: center; width: 15px; height: 15px; border-radius: 50%;
    border: 1.5px solid var(--text-secondary); font-size: 10px; font-weight: 600; color: var(--text-primary);
  }
  .d-editor .edit { border: 0; background: none; padding: 0; color: var(--text-primary); text-decoration: underline; cursor: pointer; font: inherit; }
  .d-fields { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px 10px; margin: 6px 0 10px 21px; padding: 8px; border-left: 2px solid var(--grid); }
  .d-fields .full { grid-column: 1 / -1; }
  .d-fields label { display: grid; gap: 2px; }
  .d-fields label.check { display: flex; gap: 6px; align-items: center; }
  .d-editor input, .d-editor select, .d-editor textarea, .d-editor button:not(.edit) {
    font: inherit; color: var(--text-primary); background: var(--surface); border: 1px solid var(--grid); border-radius: 4px; padding: 2px 5px;
  }
  .d-editor input[type=number] { width: 100%; box-sizing: border-box; }
  .d-editor textarea { font: 12px/1.45 ui-monospace, "Cascadia Code", Consolas, monospace; width: 100%; box-sizing: border-box; }
  .d-start { display: flex; align-items: center; gap: 8px; margin: 0 0 16px; font-size: 13px; }
  .d-line { margin: 6px 0 0; display: flex; gap: 6px; align-items: baseline; }
`;
function variantD() {
  const holder = el("div", "b-widget");
  stage.append(holder);
  holder.append(widget);
  const root = widget.shadowRoot;
  const style = el("style");
  style.dataset.proto = "";
  style.textContent = D_CSS;
  const panel = el("div", "d-editor");
  panel.dataset.proto = "";
  root.append(style);
  root.querySelector(".top > div:first-child").prepend(panel);
  const toggle = (key) => button(state.open.has(key) ? "done" : "edit", () => {
    if (state.open.has(key)) state.open.delete(key); else state.open.add(key);
    draw();
  }, "edit");
  // The summary lines, which each change rewrites in place, so a field keeps focus.
  let summaries = [];
  const summary = (read) => {
    const span = el("span", "", read(), " ");
    summaries.push(() => { span.textContent = `${read()} `; });
    return span;
  };
  const draw = () => {
    summaries = [];
    const { request } = state;
    const structures = request.workload.structures;
    const list = el("ol");
    structures.forEach((structure, i) => {
      const line = el("div", "line", el("span", "badge", String(i + 1)), summary(() => describe({ ...structure, shape: label(structure.shape) })), toggle(`s${i}`));
      const item = el("li", "", line);
      if (state.open.has(`s${i}`)) {
        const { fields, remove } = structureFields(structure, i, draw);
        item.append(el("div", "d-fields", ...fields, el("div", "full", remove)));
      }
      list.append(item);
    });
    const churn = el("div", "", el("div", "d-line", summary(() => describeChurn(request.workload.churn)), toggle("churn")));
    if (state.open.has("churn")) churn.append(el("div", "d-fields", ...churnFields()));
    const runLine = () => {
      const { threshold0, threshold1, threshold2 } = request.settings;
      return `Run: ${kb(request.run_length)} on the allocation clock, gc.set_threshold(${threshold0}, ${threshold1}, ${threshold2})${request.workload.shutdown ? ", then shutdown" : ""}`;
    };
    const runs = el("div", "", el("div", "d-line", summary(runLine), toggle("run")));
    if (state.open.has("run")) runs.append(el("div", "d-fields", ...runFields()));
    panel.replaceChildren(
      el("label", "d-start", "Workload", startFrom()),
      el("h3", "", "Object graph"),
      el("p", "", "A few objects of each structure, as its shape links them. One dot is one simulated object, 16 real ones. A red link lies on a cycle. Edit a line to change it; each change runs both collectors again."),
      list,
      button("+ Add a structure", () => { structures.push(newStructure()); state.open.add(`s${structures.length - 1}`); draw(); edited(); }, "edit"),
      churn,
      runs,
    );
  };
  hooks = { edited: () => { for (const rewrite of summaries) rewrite(); soon(); } };
  draw();
}

function render() {
  clearTimeout(timer);
  for (const part of widget.shadowRoot?.querySelectorAll("[data-proto]") ?? []) part.remove();
  stage.replaceChildren();
  const key = variant();
  document.querySelector("main").classList.toggle("wide", key === "A" || key === "C");
  (({ A: variantA, B: variantB, C: variantC, D: variantD })[key] ?? variantA)();
  showState();
}

addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    run();
  }
});
addEventListener("prototype-variant", () => {
  render();
  // C sends source, the others the request the form holds.
  run();
});
render();
