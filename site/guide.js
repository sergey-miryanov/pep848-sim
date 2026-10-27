// @ts-check
// The guide (ADR 0020): its chapters a step at a time, beside one compact
// <gc-widget>. guide.json lists the chapters. A chapter with steps runs them
// here, and one without links to its section in the long form until it moves
// over. Each step is one of the widget's entries, with its request and the
// parts it marks, so the page steps by writing the entry's name into the URL
// fragment, which the widget follows, and the browser's Back steps back. The
// rail beside the widget shows the step's text and a note for each part it
// marks, under the badge's number.

/**
 * A part a step marks, as the widget names it, and what to see there.
 * @typedef {{ part: string, note: string }} Mark
 * @typedef {{ title: string, text: string, request: any, marks: Mark[] }} Step
 * A chapter's steps share its controls. One without steps lives in the long form.
 * @typedef {{ id: string, title: string, controls?: string[], steps?: Step[] }} Chapter
 * @typedef {{ chapter: Chapter, step: Step, index: number, name: string }} Stop
 */

const ID = "guide";
const LONG = "guide-long.html";

/** @type {{ chapters: Chapter[] }} */
const guide = await (await fetch(new URL("guide.json", import.meta.url))).json();
/** Every chapter's steps in turn, which Back and Next walk. @type {Stop[]} */
const stops = guide.chapters.flatMap((chapter) =>
  (chapter.steps ?? []).map((step, index) => ({ chapter, step, index, name: `${chapter.id}-${index + 1}` })));

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
const json = el("script");
json.type = "application/json";
json.textContent = JSON.stringify({
  entries: stops.map(({ chapter, step, name }) => ({
    name, title: step.title, request: step.request, controls: chapter.controls ?? [], marks: step.marks.map(({ part }) => part),
  })),
});
widget.append(json);

// The rail: the chapter, Back and Next above the step, so that a longer step
// never moves them, then the step's title, text and notes.
const label = el("p", "chapter");
const back = el("button", "back", "Back");
const next = el("button", "next", "Next");
back.type = next.type = "button";
back.addEventListener("click", () => go(current() - 1));
next.addEventListener("click", () => go(current() + 1));
const count = el("span", "count");
const buttons = el("div", "buttons");
buttons.append(back, next, count);
// A box of steps a chapter, each box as tall as its longest step.
const boxes = new Map(guide.chapters.filter(({ steps }) => steps).map((chapter) => {
  const box = el("div", "steps");
  for (const step of chapter.steps ?? []) {
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
const rail = el("div", "rail");
rail.append(label, buttons, ...boxes.values());
const toc = el("ol", "toc");
toc.setAttribute("aria-label", "Chapters");
const side = el("div", "side");
side.append(rail, toc);
/** @type {HTMLElement} */ (document.querySelector(".guide")).append(side, widget);

/** The chapters, each a link to its first step or its long form, with the steps of the one shown. */
function chapters() {
  const { chapter: shown, index: at } = stops[current()];
  toc.replaceChildren(...guide.chapters.map((chapter) => {
    const item = el("li");
    const first = stops.find((stop) => stop.chapter === chapter);
    const link = el("a", "", chapter.title);
    if (first) link.href = `#${ID}=${first.name}`;
    else {
      link.href = `${LONG}#${chapter.id}`;
      link.append(el("span", "long", "long form"));
    }
    item.append(link);
    if (chapter !== shown) return item;
    item.className = "open";
    const steps = el("ol");
    (chapter.steps ?? []).forEach((step, index) => {
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
  label.textContent = chapter.title;
  count.textContent = `Step ${index + 1} of ${chapter.steps?.length}`;
  back.disabled = at === 0;
  next.disabled = at === stops.length - 1;
  for (const [owner, box] of boxes) {
    box.hidden = owner !== chapter;
    [...box.children].forEach((part, i) => part.toggleAttribute("aria-current", owner === chapter && i === index));
  }
  chapters();
}

show();
addEventListener("hashchange", show);
addEventListener("keydown", (event) => {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
  // The widget's panels and sliders take the arrow keys themselves.
  const target = /** @type {Element} */ (event.composedPath()[0]);
  if (target.closest?.("input, select, textarea, [contenteditable], [role=slider]")) return;
  event.preventDefault();
  go(current() + (event.key === "ArrowLeft" ? -1 : 1));
});
