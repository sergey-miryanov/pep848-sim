// @ts-nocheck
// PROTOTYPE, not for main (#220): the young generation's chapter of the guide as
// steps beside one <gc-widget>, laid out three ways, switched by ?variant=.
//
// Each step is one of the widget's entries, so stepping needs nothing new from
// the widget: the page writes the step's entry into the URL fragment, and the
// widget follows it, as a link to an entry does. The page reaches into the
// widget's shadow root to hide the entry picker, outline what a step talks about
// and mark the figures that moved.

const CHAPTER = "The young generation";
const settings = (threshold0, threshold1 = 10) => ({ threshold0, threshold1, threshold2: 10 });

// marks: what a step outlines, each with a note on what to see there, which the
// rail lists under the step's text by the number on the outline's badge.
// "<collector> <panel>" outlines a panel, "figure:<label>" a figure.
const STEPS = [
  {
    title: "Every object is work",
    text: "json_loads models a worker that calls json.loads 60 times a loop. No result holds a cycle, so each object a collection examines is work that frees nothing.",
    settings: settings(1000),
    marks: [
      ["legacy work", "Survived, in violet, fills each bar: the collection examined objects still in use."],
      ["incremental work", "The same violet. Freed, in red, stays a sliver until shutdown."],
    ],
  },
  {
    title: "The legacy collector looks twice",
    text: "A gen 0 collection examines the nursery every threshold0 kB, here 1,000. At 12 MB, a gen 1 collection examines the survivors again before they reach the old generation.",
    settings: settings(1000),
    marks: [
      ["legacy work", "From 1 to 5 MB, gen 0 collections examine the objects the worker builds. The tall bar at 12 MB is the gen 1 collection examining all 1,145 again."],
    ],
  },
  {
    title: "The incremental collector looks once",
    text: "The incremental collector first examines an object when its aging space is the oldest: 12 MB after its allocation at this threshold0.",
    settings: settings(1000),
    marks: [
      ["incremental heap", "The aging lane holds the worker's objects until 12 MB. Young collections then move them into visited, an aging space at a time."],
      ["incremental work", "Three bars, at 12, 14 and 16 MB, examine each object once."],
    ],
  },
  {
    title: "Work per MB adds it up",
    text: "Work per MB divides each collector's work, shutdown's included, by the 21 MB the run allocates.",
    settings: settings(1000),
    marks: [
      ["figure:Work per MB", "192 against 136: the legacy collector examined the worker's objects twice."],
    ],
  },
  {
    title: "The PEP's threshold0",
    text: "At the PEP's threshold0 of 2,000 kB, the young generation holds 24 MB and the 21 MB run ends first. The incremental collector examines nothing before shutdown.",
    settings: settings(2000),
    marks: [
      ["incremental work", "No bar before shutdown."],
      ["figure:Work per MB", "Both fall. The incremental collector's 82 is shutdown's work alone, and the legacy collector's run ends before its first gen 1."],
    ],
  },
  {
    title: "Gen 2 fits the run",
    text: "Lower threshold0 to 120 kB, and gen 1 collections come often enough for a gen 2 collection to fit. It examines the worker's objects a third time: 249 work per MB against 136.",
    settings: settings(120),
    marks: [
      ["legacy work", "Gen 1 bars every 1.4 MB, and the gen 2 collection's tall bar at 16 MB."],
      ["figure:Gen 2 collections / sweeps", "One gen 2 collection for the legacy collector. The incremental collector runs no sweep."],
    ],
  },
  {
    title: "A longer aging generation",
    text: "Raise threshold1 to 20, and the aging generation holds 10 aging spaces. The young generation grows to 22 MB, past the run, and the incremental collector examines nothing again.",
    settings: settings(1000, 20),
    marks: [
      ["incremental heap", "The aging lane holds the worker's objects to the end, and visited stays empty."],
      ["incremental work", "No bar before shutdown."],
    ],
  },
];

const ID = "guide-widget";
const nameOf = (index) => `young-${index + 1}`;
const variant = () => new URLSearchParams(location.search).get("variant") ?? "A";
const compact = () => new URLSearchParams(location.search).get("widget") !== "full";
const current = () => {
  const name = new URLSearchParams(location.hash.slice(1)).get(ID);
  return Math.max(0, STEPS.findIndex((_, index) => nameOf(index) === name));
};

// The widget's one request a step, as entries.
const widget = document.createElement("gc-widget");
widget.id = ID;
const json = document.createElement("script");
json.type = "application/json";
json.textContent = JSON.stringify({
  controls: ["settings.threshold0", "settings.threshold1"],
  entries: STEPS.map((step, index) => ({
    name: nameOf(index),
    title: step.title,
    request: { preset: "json_loads", settings: step.settings, every: 1 },
  })),
});
widget.append(json);
// The widget opens on the step the address names, or the first.
if (!new URLSearchParams(location.hash.slice(1)).has(ID)) history.replaceState(null, "", `${location.search}#${ID}=${nameOf(0)}`);

/** Go to a step: a new history entry, so the browser's Back steps back too. */
function go(index, { push = true } = {}) {
  if (index < 0 || index >= STEPS.length || index === current()) return;
  const hash = `#${ID}=${nameOf(index)}`;
  if (push) location.hash = hash;
  else {
    history.replaceState(null, "", `${location.search}${hash}`);
    dispatchEvent(new HashChangeEvent("hashchange"));
  }
}

// What the widget's figures read, by label: [legacy, incremental].
function figures() {
  const read = {};
  for (const figure of widget.shadowRoot?.querySelectorAll(".figure") ?? []) {
    const label = figure.querySelector("dt").textContent;
    read[label] = [...figure.querySelectorAll("dd .value")].map((value) => value.textContent);
  }
  return read;
}

// The figures the last step read once its runs finished, which the step shown
// compares against, and each step's last full reading.
let before = {};
const readings = {};
let watcher;
/**
 * Note under each figure that moved since the last step what it was, as soon as
 * the widget writes it: kept runs draw at once, new runs as their records arrive.
 */
function annotate() {
  const root = widget.shadowRoot;
  const now = figures();
  watcher.disconnect();
  for (const figure of root.querySelectorAll(".figure")) {
    const label = figure.querySelector("dt").textContent;
    const was = before[label];
    figure.querySelectorAll("dd").forEach((dd, column) => {
      dd.querySelector(".was")?.remove();
      const value = now[label][column];
      if (!was || value === "–" || value === was[column]) return;
      const note = document.createElement("span");
      note.className = "was";
      note.textContent = `was ${was[column]}`;
      dd.append(note);
    });
  }
  if (!JSON.stringify(now).includes("–")) readings[current()] = now;
  watcher.observe(root.querySelector(".figures"), { subtree: true, childList: true, characterData: true });
}

/** Outline what the step talks about, tint the numbers of the figures it names, and note what moved. */
function mark() {
  const root = widget.shadowRoot;
  if (!root) return;
  if (!root.querySelector("style[data-proto]")) {
    const style = document.createElement("style");
    style.dataset.proto = "";
    style.textContent = `
      .picks { display: none !important; }
      [data-proto-mark] { outline: 2px solid var(--text-primary); outline-offset: 6px; border-radius: 2px; }
      [data-proto-mark] { position: relative; }
      .proto-badge {
        position: absolute; top: -16px; right: -16px; z-index: 2; display: grid; place-items: center;
        width: 22px; height: 22px; border-radius: 50%; font: 600 12px system-ui, sans-serif;
        background: var(--text-primary); color: var(--surface);
      }
      .figure[data-proto-mark] .value { background: color-mix(in srgb, var(--aging) 35%, transparent); border-radius: 3px; padding: 0 3px; }
      .was { display: block; font-size: 11px; color: var(--text-muted); font-weight: 400; }
    `;
    // The compact widget drops the object graph and the legend beside it, and on
    // a phone keeps the two columns side by side.
    if (compact()) style.textContent += `
      .graph, .key-list { display: none !important; }
      .top { margin-bottom: 8px !important; }
      .controls { margin-bottom: 12px !important; }
      .figures { margin-bottom: 12px !important; }
      @container widget (width < 700px) {
        .columns { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) !important; gap: 12px !important; }
        .figure .value { font-size: 17px !important; }
      }
    `;
    root.append(style);
    watcher = new MutationObserver(annotate);
  }
  for (const part of root.querySelectorAll("[data-proto-mark]")) delete part.dataset.protoMark;
  for (const part of root.querySelectorAll(".proto-badge")) part.remove();
  for (const [index, [target]] of STEPS[current()].marks.entries()) {
    let part;
    if (target.startsWith("figure:")) {
      const label = target.slice(7);
      part = [...root.querySelectorAll(".figure")].find((figure) => figure.querySelector("dt").textContent === label);
    } else {
      const [collector, panel] = target.split(" ");
      part = root.querySelector(`[data-collector="${collector}"] [data-panel="${panel}"]`);
    }
    if (!part) continue;
    part.dataset.protoMark = "";
    part.append(el("span", "proto-badge", String(index + 1)));
  }
  annotate();
}

// The parts every layout shares.
const el = (tag, className, text) => {
  const made = document.createElement(tag);
  if (className) made.className = className;
  if (text !== undefined) made.textContent = text;
  return made;
};
function buttons() {
  const row = el("div", "buttons");
  const back = el("button", "back", "Back");
  const next = el("button", "next", "Next");
  back.addEventListener("click", () => go(current() - 1));
  next.addEventListener("click", () => go(current() + 1));
  row.append(back, next);
  return { row, update: () => { back.disabled = current() === 0; next.disabled = current() === STEPS.length - 1; } };
}
function dots() {
  const row = el("div", "dots");
  const all = STEPS.map((step, index) => {
    const dot = el("button");
    dot.title = step.title;
    dot.setAttribute("aria-label", `Step ${index + 1}: ${step.title}`);
    dot.addEventListener("click", () => go(index));
    row.append(dot);
    return dot;
  });
  return { row, update: () => all.forEach((dot, index) => dot.toggleAttribute("aria-current", index === current())) };
}
const count = () => `Step ${current() + 1} of ${STEPS.length}`;
/**
 * Every step's title and text in one grid cell, the current one shown, so the
 * box keeps the longest step's height and the buttons around it stay put.
 */
function stack() {
  const box = el("div", "stack");
  const all = STEPS.map((step) => {
    const part = el("div");
    const notes = el("ol", "notes");
    step.marks.forEach(([, note], index) => {
      const item = el("li");
      item.append(el("span", "badge", String(index + 1)), el("span", "", note));
      notes.append(item);
    });
    part.append(el("h2", "step-title", step.title), el("p", "step-text", step.text), notes);
    box.append(part);
    return part;
  });
  return { box, update: () => all.forEach((part, index) => part.toggleAttribute("aria-current", index === current())) };
}

/** A: a rail beside the widget, with the step, Back and Next, and the chapter's list of steps. */
function variantA(stage) {
  const grid = el("div", "a-grid");
  const rail = el("div", "a-rail");
  const counter = el("div", "count");
  const steps = stack();
  const { row, update } = buttons();
  row.append(counter);
  const list = el("ol", "a-list");
  const items = STEPS.map((step, index) => {
    const button = el("button");
    button.append(el("span", "n", String(index + 1)), el("span", "", step.title));
    button.addEventListener("click", () => go(index));
    const item = el("li");
    item.append(button);
    list.append(item);
    return button;
  });
  // The buttons above the step's text, so a longer text never moves them.
  rail.append(el("p", "chapter", CHAPTER), row, steps.box, list);
  grid.append(rail, widget);
  stage.append(grid);
  return () => {
    steps.update();
    counter.textContent = count();
    update();
    items.forEach((item, index) => item.toggleAttribute("aria-current", index === current()));
  };
}

/** B: the widget at full width, and the step in a caption bar fixed over its foot. */
function variantB(stage) {
  const caption = el("div", "b-caption");
  const head = el("div", "b-head");
  const counter = el("span", "count");
  head.append(el("p", "chapter", CHAPTER), counter);
  const steps = stack();
  const foot = el("div", "b-foot");
  const progress = dots();
  const { row, update } = buttons();
  foot.append(progress.row, row);
  caption.append(head, steps.box, foot);
  stage.append(widget, el("div", "b-pad"), caption);
  return () => {
    steps.update();
    counter.textContent = count();
    update();
    progress.update();
  };
}

/** C: the steps as cards that scroll past the widget pinned beside them; no buttons. */
function variantC(stage) {
  const grid = el("div", "c-grid");
  const cards = el("div", "c-cards");
  const all = STEPS.map((step, index) => {
    const card = el("article", "c-card");
    card.dataset.index = index;
    card.append(el("p", "chapter", `${CHAPTER} · ${index + 1} of ${STEPS.length}`), el("h2", "step-title", step.title), el("p", "step-text", step.text));
    cards.append(card);
    return card;
  });
  const pin = el("div", "c-pin");
  pin.append(widget);
  grid.append(cards, pin);
  stage.append(grid);
  // The card across the screen's middle is the step, once the page has scrolled
  // to the step the address names.
  all[current()].scrollIntoView({ block: "center" });
  const seen = new IntersectionObserver((entries) => {
    for (const entry of entries) if (entry.isIntersecting) go(Number(entry.target.dataset.index), { push: false });
  }, { rootMargin: "-50% 0px -50% 0px" });
  requestAnimationFrame(() => requestAnimationFrame(() => all.forEach((card) => seen.observe(card))));
  stepKeys = (delta) => all[Math.max(0, Math.min(STEPS.length - 1, current() + delta))].scrollIntoView({ block: "center", behavior: "smooth" });
  return () => all.forEach((card, index) => card.toggleAttribute("aria-current", index === current()));
}

let stepKeys = (delta) => go(current() + delta);
const stage = document.getElementById("stage");
const show = ({ A: variantA, B: variantB, C: variantC })[variant()] ?? variantA;
const update = show(stage);
let shown = current();
update();
customElements.whenDefined("gc-widget").then(() => requestAnimationFrame(mark));
addEventListener("hashchange", () => {
  if (current() === shown) return;
  before = readings[shown] ?? {};
  shown = current();
  update();
  mark();
});
addEventListener("keydown", (event) => {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  if (event.altKey || event.ctrlKey || event.metaKey) return;
  // The widget's panels read the arrow keys themselves, and the sliders move by them.
  const target = event.composedPath()[0];
  if (target.closest?.("input, select, textarea, [contenteditable], [role=slider]")) return;
  event.preventDefault();
  stepKeys(event.key === "ArrowLeft" ? -1 : 1);
});
addEventListener("prototype-variant", () => location.reload());
