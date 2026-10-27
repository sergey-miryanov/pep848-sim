// @ts-nocheck
// PROTOTYPE, not for main: how the guide fits its widget in one window. Three
// variants, through ?variant= and the bar prototype-switcher.js adds:
//   A  the intro and the settings in the rail, charts at fixed shorter heights;
//   B  the intro as a strip you can close, the settings in the rail, charts
//      sized to fill the window;
//   C  the intro behind an About button, the settings in the rail, and the
//      panels a step marks at full height while the rest shrink.
// The guide (ADR 0020): its chapters a step at a time, beside one compact
// <gc-widget>. guide.json lists the chapters and their steps. Each step is one
// of the widget's entries, with its request and the parts it marks, so the
// page steps by writing the entry's name into the URL fragment, which the
// widget follows, and the browser's Back steps back. The
// rail beside the widget shows the step's text and a note for each part it
// marks, under the badge's number.

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
const json = el("script");
json.type = "application/json";
json.textContent = JSON.stringify({
  entries: stops.map(({ chapter, step, name }) => ({
    name, title: step.title, request: step.request, controls: chapter.controls, marks: step.marks.map(({ part }) => part),
  })),
});
widget.append(json);

const VARIANT = new URLSearchParams(location.search).get("variant") ?? "A";
addEventListener("prototype-variant", () => location.reload());
const intro = /** @type {HTMLElement} */ (document.querySelector(".lede"));
// The settings in the rail: a host whose shadow root takes the widget's own
// styles, so its sliders look as they do inside it.
let controlsHost = null;
{
  controlsHost = el("div", "controls-host");
  const shadow = controlsHost.attachShadow({ mode: "open" });
  const row = el("div", "controls");
  row.hidden = true;
  shadow.append(row);
  widget.protoControls = row;
}

// The rail: the chapter beside the arrows that step, above the step, so that a
// longer step never moves them, then the step's title, text and notes.
const label = el("p", "chapter");
const back = el("button", "back", "←");
const next = el("button", "next", "→");
back.setAttribute("aria-label", "Back");
next.setAttribute("aria-label", "Next");
back.type = next.type = "button";
back.addEventListener("click", () => go(current() - 1));
next.addEventListener("click", () => go(current() + 1));
const count = el("span", "count");
const buttons = el("div", "buttons");
buttons.append(back, count, next);
const head = el("div", "head");
head.append(label, buttons);
// A box of steps a chapter, each box as tall as its longest step.
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
const rail = el("div", "rail");
rail.append(head, ...boxes.values());
if (VARIANT === "A") {
  // The intro opens the rail, open until the reader first steps.
  const about = el("details", "about");
  about.open = true;
  const summary = el("summary", "", "About this guide");
  const text = el("p");
  text.innerHTML = intro.innerHTML;
  about.append(summary, text);
  rail.prepend(about);
  addEventListener("hashchange", () => { about.open = false; }, { once: true });
} else if (VARIANT === "B") {
  // The intro as a strip over the guide, which the reader closes.
  const strip = el("div", "strip");
  const text = el("p");
  text.innerHTML = intro.innerHTML;
  const close = el("button", "", "Close");
  close.type = "button";
  close.addEventListener("click", () => { strip.remove(); fit(); sizeSide(); });
  strip.append(text, close);
  /** @type {HTMLElement} */ (document.querySelector(".guide")).before(strip);
} else {
  // The intro behind an About button beside the chapter's name.
  const about = el("button", "about-button", "About");
  about.type = "button";
  const pop = el("div", "pop");
  pop.hidden = true;
  const text = el("p");
  text.innerHTML = intro.innerHTML;
  pop.append(text);
  about.addEventListener("click", () => { pop.hidden = !pop.hidden; });
  label.after(about);
  head.after(pop);
}
const toc = el("ol", "toc");
toc.setAttribute("aria-label", "Chapters");
const side = el("div", "side");
// The settings in a block the reader collapses, which stays as they left it.
const settings = el("details", "settings");
settings.open = true;
settings.append(el("summary", "", "Settings"), controlsHost);
side.append(rail, toc, settings);
/** @type {HTMLElement} */ (document.querySelector(".guide")).append(side, widget);
if (controlsHost) {
  controlsHost.shadowRoot.prepend(/** @type {ShadowRoot} */ (widget.shadowRoot).querySelector("style").cloneNode(true));
  controlsHost.style.cssText = "padding: 8px 0 0; background: none; box-sizing: border-box; border: 0;";
  // Open, the block keeps the height of the tallest chapter's settings, which
  // the prototype measured: 174 px of sliders over 8 of padding. So neither a
  // step's refill nor a new chapter moves it.
  controlsHost.style.minHeight = "182px";
}
// Every chapter's step box as tall as the guide's longest step, so nothing
// under it moves from one chapter to the next.
function steady() {
  const all = [...boxes.values()];
  for (const box of all) box.style.minHeight = "";
  const shown = all.map((box) => box.hidden);
  all.forEach((box) => { box.hidden = false; });
  const tallest = Math.max(...all.map((box) => box.getBoundingClientRect().height));
  all.forEach((box, i) => { box.hidden = shown[i]; box.style.minHeight = `${tallest}px`; });
}
document.fonts.ready.then(steady);
addEventListener("resize", steady);
// The column as tall as the window below its top, the chapters at its foot.
function sizeSide() {
  if (innerWidth < 900) return void (side.style.height = "");
  side.style.height = `${innerHeight - (side.getBoundingClientRect().top + scrollY) - 12}px`;
}
sizeSide();
addEventListener("resize", sizeSide);

const FULL = { lane: 64, work: 160, budget: 130 };
/** Charts that fill the window below the widget's top (B). */
function fit(pass = 0) {
  // A phone stacks the rail over the widget, which #229 fits.
  if (VARIANT !== "B" || innerWidth < 900) return;
  requestAnimationFrame(() => {
    const root = /** @type {ShadowRoot} */ (widget.shadowRoot);
    const heights = ["heap", "work", "budget"].map((panel) =>
      Math.max(...[...root.querySelectorAll(`[data-panel="${panel}"] .chart`)].map((chart) => chart.getBoundingClientRect().height)));
    const rest = widget.getBoundingClientRect().height - heights.reduce((a, b) => a + b, 0);
    const room = innerHeight - (widget.getBoundingClientRect().top + scrollY) - 12 - rest;
    // Only the plots scale: the heap panel's 5 lanes over 144 px of margins,
    // and the work and budget plots inside their 48 px of axes.
    const k = Math.min(1.3, Math.max(0.3, (room - 240) / (5 * FULL.lane + FULL.work - 48 + FULL.budget - 48)));
    widget.protoHeights({ lane: Math.round(FULL.lane * k), work: 48 + Math.round((FULL.work - 48) * k), budget: 48 + Math.round((FULL.budget - 48) * k) });
    // The legends and axes do not scale, so measure again once it redraws.
    if (pass < 2) setTimeout(() => fit(pass + 1), 100);
  });
}
/** The panels the step marks at full height, the rest short (C). */
function focus() {
  if (VARIANT !== "C") return;
  const parts = stops[current()].step.marks.map(({ part }) => part.split(".")[1]);
  const marked = (panel) => parts.includes(panel);
  const any = ["heap", "work", "budget"].some(marked);
  if (!any) return widget.protoHeights({ lane: 36, work: 110, budget: 90 });
  widget.protoHeights({ lane: marked("heap") ? 56 : 18, work: marked("work") ? 160 : 60, budget: marked("budget") ? 130 : 50 });
}
if (VARIANT === "A") widget.protoHeights({ lane: 40, work: 120, budget: 100 });
addEventListener("resize", () => fit());
addEventListener("hashchange", () => { fit(); focus(); });
// Refit as the widget's height settles, once its runs draw.
new ResizeObserver(() => fit()).observe(widget);
focus();

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
  // The list scrolls inside the column: keep the chapter shown in view.
  const open = toc.querySelector(".open");
  if (open) {
    const list = toc.getBoundingClientRect(), item = open.getBoundingClientRect();
    if (item.top < list.top || item.bottom > list.bottom) toc.scrollTop += item.top - list.top - 20;
  }
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
