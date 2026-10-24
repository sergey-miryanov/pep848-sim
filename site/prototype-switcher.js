// @ts-nocheck
// PROTOTYPE, not for main (#153): a floating bar that switches the playground's
// layout, through ?variant= in the page's address. The arrow keys switch too,
// unless a field has focus.

const VARIANTS = [
  ["A", "Form beside the widget, Run button"],
  ["B", "Table above the widget, each change runs"],
  ["C", "Python source beside the widget, Run button"],
  ["D", "Edit in the widget's legend, each change runs"],
];

const bar = document.createElement("div");
bar.style.cssText = `position: fixed; bottom: 16px; left: 50%; transform: translateX(-50%); z-index: 10;
  display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 999px;
  background: #111; color: #fff; font: 13px system-ui, sans-serif; box-shadow: 0 4px 16px rgb(0 0 0 / 0.35);`;
const button = (text, step) => {
  const made = document.createElement("button");
  made.textContent = text;
  made.style.cssText = "border: 0; background: #333; color: #fff; border-radius: 999px; width: 28px; height: 28px; cursor: pointer;";
  made.addEventListener("click", () => go(step));
  return made;
};
const label = document.createElement("span");
label.style.minWidth = "360px";
label.style.textAlign = "center";
bar.append(button("‹", -1), label, button("›", 1));
document.body.append(bar);

const current = () => Math.max(0, VARIANTS.findIndex(([key]) => key === (new URLSearchParams(location.search).get("variant") ?? "A")));
const show = () => {
  const [key, name] = VARIANTS[current()];
  label.textContent = `${key} — ${name}`;
};

function go(step) {
  const [key] = VARIANTS[(current() + step + VARIANTS.length) % VARIANTS.length];
  history.replaceState(null, "", `?variant=${key}${location.hash}`);
  show();
  dispatchEvent(new Event("prototype-variant"));
}

addEventListener("keydown", (event) => {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  const target = event.composedPath()[0];
  if (target.closest?.("input, select, textarea, [contenteditable]")) return;
  go(event.key === "ArrowLeft" ? -1 : 1);
});
show();
