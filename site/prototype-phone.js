// @ts-nocheck
// PROTOTYPE, not for main: how the guide fits a phone (#229). Three variants,
// through ?variant= and the bar prototype-switcher.js adds, at under 900 px:
//   A  the rail folds to its head, the step's title and two lines of text, with
//      More for the rest; the widget's columns fit the screen under it;
//   B  the step docks at the foot of the screen, and the page above it scrolls
//      to the first part the step marks;
//   C  one collector at a time, picked by tabs that carry their badges, and
//      each note beside its badge inside the widget, not in the rail.
// Every variant scrolls the step's first mark into view and starts with the
// settings collapsed.
import { SIZES, fitted, heapHeight } from "./panels.js";

// The guide (ADR 0020): its chapters a step at a time, beside one compact
// <gc-widget>. guide.json lists the chapters and their steps. Each step is one
// of the widget's entries, with its request and the parts it marks, so the
// page steps by writing the entry's name into the URL fragment, which the
// widget follows, and the browser's Back steps back. The
// rail beside the widget shows the step's text and a note for each part it
// marks, under the badge's number. Beside the widget, the side holds still
// from step to step, and the widget's charts end at the window's foot (#232).

/**
 * A part a step marks, as the widget names it, and what to see there.
 * @typedef {{ part: string, note: string }} Mark
 * @typedef {{ title: string, text: string, request: any, marks: Mark[] }} Step
 * A chapter's steps share its controls.
 * @typedef {{ id: string, title: string, controls: string[], steps: Step[] }} Chapter
 * @typedef {{ chapter: Chapter, step: Step, index: number, name: string }} Stop
 */

const ID = "guide";

/** @type {{ chapters: Chapter[] }} */
const guide = await (await fetch(new URL("guide.json", import.meta.url))).json();
/** Every chapter's steps in turn, which Back and Next walk. @type {Stop[]} */
const stops = guide.chapters.flatMap((chapter) =>
  chapter.steps.map((step, index) => ({ chapter, step, index, name: `${chapter.id}-${index + 1}` })));

const named = () => new URLSearchParams(location.hash.slice(1)).get(ID);
const current = () => Math.max(0, stops.findIndex(({ name }) => name === named()));
const go = (/** @type {number} */ at) => {
  if (at < 0 || at >= stops.length || at === current()) return;
  location.hash = `${ID}=${stops[at].name}`;
};

/**
 * @template {keyof HTMLElementTagNameMap} K
 * @param {K} tag
 * @param {string} [className]
 * @param {string} [text]
 * @returns {HTMLElementTagNameMap[K]}
 */
function el(tag, className, text) {
  const made = document.createElement(tag);
  if (className) made.className = className;
  if (text !== undefined) made.textContent = text;
  return made;
}

// The widget opens on the step the address names, or the first.
if (!stops.some(({ name }) => name === named())) history.replaceState(null, "", `#${ID}=${stops[0].name}`);
const widget = document.createElement("gc-widget");
widget.id = ID;
widget.setAttribute("compact", "");
widget.setAttribute("changes", "");
// Beside the rail, the widget fits the window; on a phone, under it, #229 fits it.
const wide = matchMedia("(width >= 900px)");
const fit = () => widget.toggleAttribute("fit", wide.matches);
fit();
wide.addEventListener("change", fit);
const json = el("script");
json.type = "application/json";
json.textContent = JSON.stringify({
  entries: stops.map(({ chapter, step, name }) => ({
    name, title: step.title, request: step.request, controls: chapter.controls, marks: step.marks.map(({ part }) => part),
  })),
});
widget.append(json);

// The rail: the chapter beside the arrows that step, above the step, so that a
// longer step never moves them, then the step's title, text and notes.
const label = el("p", "chapter");
const back = el("button", "back", "←");
const next = el("button", "next", "→");
back.type = next.type = "button";
back.setAttribute("aria-label", "Back");
next.setAttribute("aria-label", "Next");
back.addEventListener("click", () => go(current() - 1));
next.addEventListener("click", () => go(current() + 1));
const count = el("span", "count");
const buttons = el("div", "buttons");
buttons.append(back, count, next);
const head = el("div", "head");
head.append(label, buttons);
// A box of steps a chapter, each box as tall as its longest step, and beside
// the widget as tall as the guide's longest.
const boxes = new Map(guide.chapters.map((chapter) => {
  const box = el("div", "steps");
  for (const step of chapter.steps) {
    const part = el("div");
    const notes = el("ol", "notes");
    step.marks.forEach(({ note }, i) => {
      const item = el("li");
      item.append(el("span", "badge", String(i + 1)), el("span", "", note));
      notes.append(item);
    });
    part.append(el("h2", "", step.title), el("p", "", step.text), notes);
    box.append(part);
  }
  return [chapter, box];
}));
const all = el("div", "boxes");
all.append(...boxes.values());
const rail = el("div", "rail");
rail.append(head, all);
const toc = el("ol", "toc");
toc.setAttribute("aria-label", "Chapters");
// The widget's controls, in a block the reader collapses, which stays as they
// left it from step to step.
const settings = el("details", "settings");
settings.open = true;
const controls = document.createElement("gc-controls");
controls.setAttribute("for", ID);
settings.append(el("summary", "", "Settings"), controls);
const side = el("div", "side");
side.append(rail, toc, settings);
/** @type {HTMLElement} */ (document.querySelector(".guide")).append(side, widget);

/** Beside the widget, the side as tall as the window below its top. */
function size() {
  side.style.height = wide.matches ? `${innerHeight - (side.getBoundingClientRect().top + scrollY) - 12}px` : "";
}
size();
addEventListener("resize", size);
wide.addEventListener("change", size);

// The intro's Close, which the page remembers.
const intro = /** @type {HTMLElement} */ (document.querySelector(".intro"));
intro.querySelector("button")?.addEventListener("click", () => {
  intro.hidden = true;
  try {
    localStorage.setItem("pep848-sim.guide-intro", "closed");
  } catch {
    // A browser that keeps nothing closes it on this page alone.
  }
  size();
});

/** The chapters, each a link to its first step, with the steps of the one shown. */
function chapters() {
  const { chapter: shown, index: at } = stops[current()];
  toc.replaceChildren(...guide.chapters.map((chapter) => {
    const item = el("li");
    const link = el("a", "", chapter.title);
    link.href = `#${ID}=${chapter.id}-1`;
    item.append(link);
    if (chapter !== shown) return item;
    item.className = "open";
    const steps = el("ol");
    chapter.steps.forEach((step, index) => {
      const button = el("button");
      button.type = "button";
      button.append(el("span", "n", String(index + 1)), el("span", "", step.title));
      if (index === at) button.setAttribute("aria-current", "step");
      button.addEventListener("click", () => go(stops.findIndex((stop) => stop.chapter === chapter && stop.index === index)));
      const entry = el("li");
      entry.append(button);
      steps.append(entry);
    });
    item.append(steps);
    return item;
  }));
}

function show() {
  const at = current();
  const { chapter, index } = stops[at];
  label.textContent = label.title = chapter.title;
  count.textContent = `${index + 1} / ${chapter.steps.length}`;
  back.disabled = at === 0;
  next.disabled = at === stops.length - 1;
  for (const [owner, box] of boxes) {
    box.hidden = owner !== chapter;
    [...box.children].forEach((part, i) => part.toggleAttribute("aria-current", owner === chapter && i === index));
  }
  chapters();
  // The chapters scroll inside the side: keep the one shown in view.
  const open = toc.querySelector(".open");
  if (open) {
    const list = toc.getBoundingClientRect(), item = open.getBoundingClientRect();
    if (item.top < list.top || item.bottom > list.bottom) toc.scrollTop += item.top - list.top - 20;
  }
}

// PROTOTYPE (#229) from here to the next marker.
const VARIANT = new URLSearchParams(location.search).get("variant") ?? "A";
document.body.classList.add(`v-${VARIANT}`);
const phone = () => !wide.matches;
const root = () => widget.shadowRoot;
const HEAP_LANES = 4;
if (phone()) settings.open = false;

// A: the folded rail, and the columns fitted under it.
const more = el("button", "more");
more.type = "button";
if (VARIANT === "A") {
  rail.classList.add("folded");
  more.addEventListener("click", () => {
    rail.classList.toggle("folded");
    label_more();
    fitA();
  });
  rail.append(more);
}
function label_more() {
  const n = stops[current()].step.marks.length;
  more.textContent = rail.classList.contains("folded") ? `More${n ? ` · ${n} note${n > 1 ? "s" : ""}` : ""}` : "Less";
}
let sizes = SIZES;
function fitA() {
  if (VARIANT !== "A" || !phone() || !root()) return;
  const columns = root().querySelector(".columns");
  const sum = heapHeight(HEAP_LANES, sizes.lane) + sizes.work + sizes.budget;
  const rest = columns.getBoundingClientRect().height - sum;
  const room = innerHeight - rail.getBoundingClientRect().height - 16 - rest;
  const next = fitted(room, HEAP_LANES);
  if (next.lane === sizes.lane && next.work === sizes.work && next.budget === sizes.budget) return;
  sizes = next;
  widget.protoSizes = next;
  widget.protoRedraw();
}

// C: the tabs, and the notes inside the widget.
const tabs = el("div", "tabs");
let one = "legacy";
const tabButtons = ["legacy", "incremental"].map((kind) => {
  const button = el("button");
  button.type = "button";
  button.addEventListener("click", () => pick(kind));
  return [kind, button];
});
function pick(kind) {
  one = kind;
  if (phone()) widget.dataset.one = kind;
  const marks = stops[current()].step.marks;
  for (const [k, button] of tabButtons) {
    button.setAttribute("aria-pressed", String(k === kind));
    button.replaceChildren(el("span", "", k === "legacy" ? "Legacy" : "Incremental"));
    marks.forEach(({ part }, i) => {
      if (part.startsWith(`${k}.`)) button.append(el("span", "badge", String(i + 1)));
    });
  }
}
if (VARIANT === "C") {
  tabs.append(...tabButtons.map(([, button]) => button));
  widget.before(tabs);
}
function notesC() {
  const r = root();
  if (!r.querySelector(".proto-style")) {
    const style = el("style", "proto-style");
    style.textContent = `
      :host([data-one="legacy"]) [data-collector="incremental"], :host([data-one="incremental"]) [data-collector="legacy"] {
        height: 0; overflow: hidden; visibility: hidden; }
      :host([data-one]) .columns { grid-template-columns: minmax(0, 1fr) !important; }
      .proto-note { display: flex; gap: 6px; align-items: baseline; margin: 6px 0; font-size: 13px; color: var(--text-secondary); }
      .proto-note b { flex: none; display: inline-grid; place-items: center; width: 16px; height: 16px; border-radius: 50%;
        font-size: 10px; background: var(--text-primary); color: var(--surface); }
      .proto-notes { margin: 0 0 12px; }`;
    r.append(style);
  }
  for (const old of r.querySelectorAll(".proto-note, .proto-notes")) old.remove();
  const figureNotes = el("div", "proto-notes");
  stops[current()].step.marks.forEach(({ part, note }, i) => {
    const line = el("div", "proto-note");
    line.append(el("b", "", String(i + 1)), el("span", "", note));
    const [kind, name] = part.split(".");
    if (kind === "figure") figureNotes.append(line);
    else r.querySelector(`[data-collector="${kind}"] [data-panel="${name}"] figcaption`)?.after(line);
  });
  if (figureNotes.children.length) r.querySelector(".figures").after(figureNotes);
}

/** Scroll the step's first mark into view, under a rail on top or above one at the foot. */
function reveal() {
  if (!phone()) return;
  const r = root();
  const marks = [...r.querySelectorAll("[data-mark]")].sort((a, b) => a.dataset.mark - b.dataset.mark);
  const first = marks.find((part) => part.offsetParent !== null);
  if (!first) return;
  // Room for the mark's outline and badge.
  let top = 24;
  if (VARIANT !== "B") top += rail.getBoundingClientRect().height;
  if (VARIANT === "C") top += tabs.getBoundingClientRect().height;
  scrollTo({ top: first.getBoundingClientRect().top + scrollY - top, behavior: "smooth" });
}

function variantStep() {
  requestAnimationFrame(() => {
    if (VARIANT === "A") {
      label_more();
      fitA();
    }
    if (VARIANT === "C") {
      tabs.style.top = `${rail.getBoundingClientRect().height}px`;
      const panel = stops[current()].step.marks.find(({ part }) => !part.startsWith("figure."));
      pick(panel ? panel.part.split(".")[0] : one);
      notesC();
    }
    requestAnimationFrame(reveal);
  });
}
if (VARIANT === "A") new ResizeObserver(() => fitA()).observe(widget);
addEventListener("resize", () => fitA());
// PROTOTYPE (#229) ends.

show();
variantStep();
addEventListener("hashchange", show);
addEventListener("hashchange", variantStep);
addEventListener("keydown", (event) => {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
  // The widget's panels and sliders take the arrow keys themselves.
  const target = /** @type {Element} */ (event.composedPath()[0]);
  if (target.closest?.("input, select, textarea, [contenteditable], [role=slider]")) return;
  event.preventDefault();
  go(current() + (event.key === "ArrowLeft" ? -1 : 1));
});
