// Drag and drop for Card order. A drop posts the Card's new Stage and position
// to the same endpoint the Move buttons use. The server answers with the whole
// board, fresh from the database, which replaces the page's copy: totals stay
// right, and the page always shows where the server actually put the Card.
// If the save fails, the board is fetched again for the same reason.

function makeSortable(root) {
  root.querySelectorAll("[data-card-list]").forEach((list) => {
    Sortable.create(list, {
      group: "cards",
      animation: 150,
      // Where the Card will land shows as an empty outline (assets/app.css).
      ghostClass: "card-placeholder",
      // The Card's menu and its dialogs stay clickable rather than dragging.
      filter: "[data-menu], dialog",
      preventOnFilter: false,
      onEnd(event) {
        if (event.from === event.to && event.oldIndex === event.newIndex) return;
        htmx.ajax("POST", event.item.dataset.moveUrl, {
          target: "#board",
          swap: "outerHTML",
          values: { stage: event.to.dataset.stage, position: event.newIndex },
        });
      },
    });
  });
}

function restoreBoard(event) {
  // Only after a failed move: a failed refetch must not retry itself forever.
  if (event.detail.requestConfig.verb !== "post") return;
  const board = document.getElementById("board");
  htmx.ajax("GET", board.dataset.boardUrl, {
    target: "#board",
    select: "#board",
    swap: "outerHTML",
  });
}

// A Card that landed in the board's last Stage throws confetti: a burst of
// small pieces in the theme's colours, flying up and out, then falling away.
// The animation is 1s (assets/app.css); the pieces are removed after 1.5s.
const CONFETTI_COLOURS = ["--color-accent", "--color-danger", "--color-accent-hover", "--color-text-muted"];

function celebrate(root) {
  const card = root.querySelector("[data-celebrate]");
  if (!card || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const { left, top, width } = card.getBoundingClientRect();
  for (let i = 0; i < 40; i++) {
    const piece = document.createElement("span");
    piece.className = "confetti";
    const angle = (-160 + Math.random() * 140) * (Math.PI / 180); // mostly upwards
    const distance = 60 + Math.random() * 120;
    piece.style.left = `${left + width / 2}px`;
    piece.style.top = `${top + 20}px`;
    piece.style.background = `var(${CONFETTI_COLOURS[i % CONFETTI_COLOURS.length]})`;
    piece.style.setProperty("--dx", `${Math.cos(angle) * distance}px`);
    piece.style.setProperty("--dy", `${Math.sin(angle) * distance}px`);
    piece.style.setProperty("--spin", `${Math.random() * 720 - 360}deg`);
    document.body.append(piece);
  }
  // A timer rather than animationend: a tab hidden mid-burst suspends
  // animation events, and the finished pieces would linger unseen.
  setTimeout(() => document.querySelectorAll(".confetti").forEach((piece) => piece.remove()), 1500);
}

// A Card's or a Stage's ⋯ menu closes on a click outside it, or on Escape,
// which returns focus to its ⋯ button. Opening another menu is a click
// outside this one, and an item that opens a dialog closes the menu behind it.
function closeMenus(keep) {
  document.querySelectorAll("[data-menu][open]").forEach((menu) => {
    if (menu !== keep) menu.open = false;
  });
}

document.addEventListener("click", (event) => {
  const opensDialog = event.target.closest("[commandfor]");
  closeMenus(opensDialog ? null : event.target.closest("[data-menu]"));
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  const menu = document.querySelector("[data-menu][open]");
  if (!menu) return;
  closeMenus(null);
  menu.querySelector("summary").focus();
});

// The Stage row scrolls sideways, which also clips anything overflowing its
// bottom, so an open menu is pinned to the window instead: below its ⋯
// button, or above it when there is no room below. Scrolling closes it rather
// than leaving it behind.
function placeMenu(event) {
  const menu = event.target;
  if (!menu.matches("[data-menu]") || !menu.open) return;
  const panel = menu.querySelector("[data-menu-panel]");
  const button = menu.querySelector("summary").getBoundingClientRect();
  const below = button.bottom + 4;
  const fits = below + panel.offsetHeight <= window.innerHeight;
  panel.style.position = "fixed";
  panel.style.margin = "0";
  panel.style.top = `${fits ? below : button.top - 4 - panel.offsetHeight}px`;
  panel.style.left = `${button.right - panel.offsetWidth}px`;
}

document.addEventListener("toggle", placeMenu, true); // toggle doesn't bubble
document.addEventListener("scroll", () => closeMenus(null), true);

// Runs for the page and again for every board swapped in.
htmx.onLoad(makeSortable);
htmx.onLoad(celebrate);
document.addEventListener("htmx:responseError", restoreBoard);
document.addEventListener("htmx:sendError", restoreBoard);
