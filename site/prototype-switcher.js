// @ts-nocheck
// PROTOTYPE, not for main (#220): a floating bar that switches the guide's
// layout, through ?variant= in the page's address. The [ and ] keys switch too,
// since the arrow keys step. Its last button shows the widget compact, without
// the object graph, or in full, through ?widget=.

const VARIANTS = [
  ["A", "Rail of steps beside the widget"],
  ["B", "Caption bar over the widget"],
  ["C", "Cards that scroll past a pinned widget"],
];

const bar = document.createElement("div");
bar.style.cssText = `position: fixed; top: 8px; right: 8px; z-index: 10;
  display: flex; align-items: center; gap: 8px; padding: 4px 8px; border-radius: 999px;
  background: #111; color: #fff; font: 12px system-ui, sans-serif; box-shadow: 0 4px 16px rgb(0 0 0 / 0.35);`;
const button = (text, step) => {
  const made = document.createElement("button");
  made.textContent = text;
  made.style.cssText = "border: 0; background: #333; color: #fff; border-radius: 999px; width: 24px; height: 24px; cursor: pointer;";
  made.addEventListener("click", () => go(step));
  return made;
};
const label = document.createElement("span");
const params = () => new URLSearchParams(location.search);
const full = document.createElement("button");
full.style.cssText = "border: 0; background: #333; color: #fff; border-radius: 999px; padding: 0 10px; height: 24px; cursor: pointer;";
full.textContent = params().get("widget") === "full" ? "Widget: full" : "Widget: compact";
full.addEventListener("click", () => {
  const next = params();
  if (next.get("widget") === "full") next.delete("widget");
  else next.set("widget", "full");
  location.search = next.toString();
});
bar.append(button("‹", -1), label, button("›", 1), full);
document.body.append(bar);

const current = () => Math.max(0, VARIANTS.findIndex(([key]) => key === (new URLSearchParams(location.search).get("variant") ?? "A")));
const show = () => {
  const [key, name] = VARIANTS[current()];
  label.textContent = `${key}: ${name}`;
};

function go(step) {
  const [key] = VARIANTS[(current() + step + VARIANTS.length) % VARIANTS.length];
  const next = params();
  next.set("variant", key);
  history.replaceState(null, "", `?${next}${location.hash}`);
  show();
  dispatchEvent(new Event("prototype-variant"));
}

addEventListener("keydown", (event) => {
  if (event.key !== "[" && event.key !== "]") return;
  const target = event.composedPath()[0];
  if (target.closest?.("input, select, textarea, [contenteditable]")) return;
  go(event.key === "[" ? -1 : 1);
});
show();
