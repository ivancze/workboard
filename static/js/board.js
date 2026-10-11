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
      // The Move toggle and its buttons stay clickable rather than dragging.
      filter: "summary, button",
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

// Runs for the page and again for every board swapped in.
htmx.onLoad(makeSortable);
document.addEventListener("htmx:responseError", restoreBoard);
document.addEventListener("htmx:sendError", restoreBoard);
