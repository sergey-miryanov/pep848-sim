// @ts-nocheck
// PROTOTYPE, not for main: a floating bar that switches how the guide fits a
// phone (#229), through ?variant= in the page's address. The [ and ] keys
// switch too, since the arrow keys step.

const VARIANTS = [
  ["A", "Folded rail, columns fit"],
  ["B", "Step docked at the foot"],
  ["C", "One collector, notes in place"],
];

const bar = document.createElement("div");
// In the page's flow above the nav, so it covers none of the variants' parts.
bar.style.cssText = `width: max-content; margin: 6px auto 0;
  display: flex; align-items: center; gap: 6px; padding: 3px 6px; border-radius: 999px;
  background: #111; color: #fff; font: 11px system-ui, sans-serif; box-shadow: 0 4px 16px rgb(0 0 0 / 0.35);`;
const button = (text, step) => {
  const made = document.createElement("button");
  made.textContent = text;
  made.style.cssText = "border: 0; background: #333; color: #fff; border-radius: 999px; width: 22px; height: 22px; cursor: pointer;";
  made.addEventListener("click", () => go(step));
  return made;
};
const label = document.createElement("span");
const params = () => new URLSearchParams(location.search);
bar.append(button("‹", -1), label, button("›", 1));
document.body.prepend(bar);

const current = () => Math.max(0, VARIANTS.findIndex(([key]) => key === (params().get("variant") ?? "A")));
const show = () => {
  const [key, name] = VARIANTS[current()];
  label.textContent = `${key}: ${name}`;
};

function go(step) {
  const [key] = VARIANTS[(current() + step + VARIANTS.length) % VARIANTS.length];
  const next = params();
  next.set("variant", key);
  history.replaceState(null, "", `?${next}${location.hash}`);
  location.reload();
}

addEventListener("keydown", (event) => {
  if (event.key !== "[" && event.key !== "]") return;
  const target = event.composedPath()[0];
  if (target.closest?.("input, select, textarea, [contenteditable]")) return;
  go(event.key === "[" ? -1 : 1);
});
show();
