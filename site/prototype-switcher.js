// @ts-nocheck
// PROTOTYPE, not for main: a floating bar that switches how the guide fits its
// widget in a window, through ?variant= in the page's address. The [ and ] keys
// switch too, since the arrow keys step.

const VARIANTS = [
  ["A", "Intro and settings in the rail, shorter charts"],
  ["B", "Intro strip, settings in the rail, charts fill the window"],
  ["C", "About button, marked panels tall, the rest short"],
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
bar.append(button("‹", -1), label, button("›", 1));
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
