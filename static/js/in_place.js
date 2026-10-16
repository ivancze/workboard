// Editing in place: the board's name, from the pencil beside it
// (board_heading.html), and its description, by clicking it
// (board_description.html); and on a Card's page, each of its fields
// (card_field.html). Each is a `data-in-place` element that htmx swaps for a
// form of the same id. What it replaced is kept while the form is out, so
// Escape, Cancel or a click elsewhere put it back without asking the server.
// A form marked `data-keep-open`, a Card's description, stays open on a
// click elsewhere, so a stray click never loses a long draft. htmx strips its
// listeners from what it swaps out, so this keeps a copy, and processes it
// again on the way back.
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
    const field = root.querySelector("input:not([type=hidden]), textarea, select");
    field.focus();
    // A one-line value is selected, to type over; a description is added
    // to, so the caret goes to its end.
    if (field.matches("input[type=text]")) field.select();
    if (field.matches("textarea")) field.setSelectionRange(field.value.length, field.value.length);
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
  for (const form of document.querySelectorAll("form[data-in-place]:not([data-keep-open])")) {
    if (!form.contains(event.target)) cancelEdit(form);
  }
});
