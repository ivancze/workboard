// Cycles the theme choice System → Light → Dark and remembers it in this
// browser. base.html applies a stored choice before the first paint; System is
// stored as no choice at all, which leaves the stylesheet following the OS.
const NEXT = { system: "light", light: "dark", dark: "system" };

document.addEventListener("click", (event) => {
  if (!event.target.closest("[data-theme-toggle]")) return;

  const root = document.documentElement;
  const choice = NEXT[root.dataset.theme || "system"];
  root.dataset.themeSwitching = "";
  if (choice === "system") delete root.dataset.theme;
  else root.dataset.theme = choice;
  // Lift the transition block only after a frame has painted the new colours.
  requestAnimationFrame(() =>
    requestAnimationFrame(() => delete root.dataset.themeSwitching),
  );

  try {
    if (choice === "system") localStorage.removeItem("theme");
    else localStorage.setItem("theme", choice);
  } catch (e) {
    // Storage can be blocked; the choice then lasts until the page reloads.
  }
});
