// @ts-check
// The page's theme, light or dark (ADR 0018): the reader's choice from the
// switch in the nav, kept across pages and visits, or else the system's scheme.
// A page loads this as a plain script in its head, so that data-theme is on
// <html> before the body paints, and theme.css reads it. The switch names the
// theme it changes to.
{
  const KEY = "pep848-sim.theme";
  const system = matchMedia("(prefers-color-scheme: dark)");

  /** The reader's choice, if they made one and the browser kept it. */
  const stored = () => {
    try {
      const theme = localStorage.getItem(KEY);
      return theme === "light" || theme === "dark" ? theme : null;
    } catch {
      return null;
    }
  };
  let chosen = stored();
  const current = () => chosen ?? (system.matches ? "dark" : "light");

  const show = () => {
    const theme = current();
    document.documentElement.dataset.theme = theme;
    const button = document.querySelector(".theme-switch");
    if (button) button.textContent = theme === "dark" ? "Light theme" : "Dark theme";
  };

  show();
  // Until the reader chooses, the page follows the system, and another tab's
  // choice reaches this one.
  system.addEventListener("change", show);
  addEventListener("storage", (event) => {
    if (event.key !== KEY) return;
    chosen = stored();
    show();
  });
  addEventListener("DOMContentLoaded", () => {
    document.querySelector(".theme-switch")?.addEventListener("click", () => {
      chosen = current() === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(KEY, chosen);
      } catch {
        // A browser that keeps nothing switches this page alone.
      }
      show();
    });
    show();
  });
}
