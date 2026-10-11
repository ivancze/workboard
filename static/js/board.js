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
      // The Card's menu stays clickable rather than dragging.
      filter: "[data-card-menu]",
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

// An open Card menu closes on a click outside it, or on Escape, which returns
// focus to its ⋯ button. Opening another menu is a click outside this one.
function closeCardMenus(keep) {
  document.querySelectorAll("[data-card-menu][open]").forEach((menu) => {
    if (menu !== keep) menu.open = false;
  });
}

document.addEventListener("click", (event) => closeCardMenus(event.target.closest("[data-card-menu]")));
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  const menu = document.querySelector("[data-card-menu][open]");
  if (!menu) return;
  closeCardMenus(null);
  menu.querySelector("summary").focus();
});

// Runs for the page and again for every board swapped in.
htmx.onLoad(makeSortable);
htmx.onLoad(celebrate);
document.addEventListener("htmx:responseError", restoreBoard);
document.addEventListener("htmx:sendError", restoreBoard);
