// Drag and drop for Card order. A drop posts the Card's new Stage and the Card
// beside it to the same endpoint the Move buttons use. The server answers with the whole
// board, fresh from the database, which replaces the page's copy: totals stay
// right, and the page always shows where the server actually put the Card.
// If the save fails, the board is fetched again for the same reason. The drop
// animates at once, without waiting for that answer (see land).

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
      onStart() {
        drags++;
      },
      onEnd(event) {
        if (event.from === event.to && event.oldIndex === event.newIndex) return;
        // The drop names its neighbour, not an index: with a filter hiding
        // Cards, the index on screen isn't the Card's place in the Stage.
        const below = event.item.nextElementSibling;
        const above = event.item.previousElementSibling;
        const values = { stage: event.to.dataset.stage };
        if (below) values.before = below.dataset.cardId;
        else if (above) values.after = above.dataset.cardId;
        if (event.from !== event.to) land(event.item, event.to);
        htmx.ajax("POST", event.item.dataset.moveUrl, {
          target: "#board",
          swap: "outerHTML",
          values,
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

// A Card dropped in another Stage pulses, and in the board's last Stage it
// also celebrates, straight away rather than a round trip later with the
// server's board. That board replaces the Card mid-pulse, so the pulse is
// picked up again where it was once the board is swapped in (continueLanding).
// A Move from the menu loads a whole page, whose Card the server marks instead.
let landing = null; // the Card pulsing, and when it began

function land(card, list) {
  card.setAttribute("data-landed", "");
  landing = { id: card.dataset.cardId, began: performance.now() };
  const lists = document.querySelectorAll("[data-card-list]");
  if (list === lists[lists.length - 1]) celebrate(card);
}

function continueLanding() {
  if (!landing) return;
  const card = document.querySelector(`[data-card-id="${landing.id}"]`);
  // A negative delay starts the animation part-way through; once it is past
  // the end, nothing plays.
  if (card) {
    card.style.animationDelay = `-${performance.now() - landing.began}ms`;
    card.setAttribute("data-landed", "");
  }
  landing = null;
}

// A Card that landed in the board's last Stage throws confetti: a burst of
// small pieces in the theme's colours, flying up and out, then falling away.
// The animation is 1s (assets/app.css); the pieces are removed after 1.5s.
const CONFETTI_COLOURS = ["--color-accent", "--color-danger", "--color-accent-hover", "--color-text-muted"];

function celebrate(card) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
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

// The Assignee filter applies as soon as a choice is made. Delegated, so it
// survives the board being swapped in after a drag.
document.addEventListener("change", (event) => {
  if (event.target.closest("[data-filter]")) event.target.form.requestSubmit();
});

// The board is fetched again when you come back to its tab or its window, so a
// tab left open for hours shows the current state (ADR 0001). Nothing is
// fetched while the tab is hidden, and nothing on a timer. A refresh never
// interrupts you: none is sent during a drag, with a menu or dialog open, or
// while a move is being saved, whose answer is a fresh board anyway; and one
// that comes back after any of those has begun is dropped. Coming back again
// catches up.
let drags = 0;
let refresh = null; // the refresh in flight, with the drag count when it was sent

function interrupting() {
  return Sortable.dragged || document.querySelector("[data-menu][open], dialog[open]");
}

function refreshBoard() {
  // htmx sends one request at a time, marking the body while it is out.
  if (document.hidden || document.body.classList.contains("htmx-request") || interrupting()) return;
  const board = document.getElementById("board");
  refresh = { drags };
  htmx
    .ajax("GET", board.dataset.boardUrl, { target: "#board", select: "#board", swap: "outerHTML" })
    .catch(() => refreshFailed(true))
    .finally(() => (refresh = null));
}

// Says so, rather than leaving an old board looking current: the board may
// have been deleted, you may have been removed or signed out, or be offline.
function refreshFailed(failed) {
  document.getElementById("refresh-failed").hidden = !failed;
}

document.addEventListener("htmx:beforeSwap", (event) => {
  if (!refresh) return;
  const { isError, serverResponse } = event.detail;
  // A redirect to sign in arrives as a page without a board.
  const fresh = !isError && new DOMParser().parseFromString(serverResponse, "text/html").getElementById("board");
  refreshFailed(!fresh);
  if (!fresh || drags !== refresh.drags || interrupting()) event.detail.shouldSwap = false;
});

document.addEventListener("visibilitychange", refreshBoard);
window.addEventListener("focus", refreshBoard);

// A board swapped in would start its Stage row scrolled back to the first
// Stage. Keep it where it was.
let rowScroll = 0;
document.addEventListener("htmx:beforeSwap", () => {
  rowScroll = document.querySelector("[data-stage-row]").scrollLeft;
});
document.addEventListener("htmx:afterSwap", () => {
  document.querySelector("[data-stage-row]").scrollLeft = rowScroll;
  refreshFailed(false);
  continueLanding();
});

// Runs for the page and again for every board swapped in.
htmx.onLoad(makeSortable);
htmx.onLoad((root) => {
  const card = root.querySelector("[data-celebrate]");
  if (card) celebrate(card);
});
document.addEventListener("htmx:responseError", restoreBoard);
document.addEventListener("htmx:sendError", restoreBoard);

// Editing in place: the board's name, from the pencil beside it
// (board_heading.html), and its description, by clicking it
// (board_description.html). Each is a `data-in-place` element that htmx
// swaps for a form of the same id. What it replaced is kept while the form is
// out, so Escape, Cancel or a click elsewhere put it back without asking the
// server. htmx strips its listeners from what it swaps out, so this keeps a
// copy, and processes it again on the way back.
const replaced = {};

document.addEventListener("htmx:beforeSwap", (event) => {
  const target = event.detail.target;
  if (!target.matches("[data-in-place]")) return;
  if (!target.matches("form")) replaced[target.id] = target.cloneNode(true);
  // A refused value comes back as a 400 carrying its error. Show it, and
  // keep it from counting as a failure, which would reload the board.
  if (event.detail.xhr.status === 400) {
    event.detail.shouldSwap = true;
    event.detail.isError = false;
  }
});

htmx.onLoad((root) => {
  if (!root.matches("[data-in-place]")) return;
  if (root.matches("form")) {
    const input = root.querySelector("input:not([type=hidden])");
    input.focus();
    input.select();
  } else {
    // Back after a save: focus returns to what opened the form.
    root.querySelector("a").focus();
  }
});

function cancelEdit(form) {
  // Not once a save is under way: its answer replaces the form.
  if (form.classList.contains("htmx-request") || !replaced[form.id]) return;
  const restored = replaced[form.id];
  delete replaced[form.id];
  form.replaceWith(restored);
  htmx.process(restored);
  return restored;
}

document.addEventListener("keydown", (event) => {
  const form = event.target.closest("form[data-in-place]");
  if (event.key === "Escape" && form) cancelEdit(form)?.querySelector("a").focus();
});
document.addEventListener("click", (event) => {
  const cancel = event.target.closest("form[data-in-place] button[type=button]");
  if (cancel) cancelEdit(cancel.form)?.querySelector("a").focus();
});
document.addEventListener("pointerdown", (event) => {
  for (const form of document.querySelectorAll("form[data-in-place]")) {
    if (!form.contains(event.target)) cancelEdit(form);
  }
});
