// Subtasks on a Card's page (components/subtasks.html). Every action there is
// a form that htmx posts, answered with the whole section, swapped in place.

// A refused value comes back as a 400 carrying its error. Show it, rather
// than htmx's default of ignoring an error response.
document.addEventListener("htmx:beforeSwap", (event) => {
  if (event.detail.target.id === "subtasks" && event.detail.xhr.status === 400) {
    event.detail.shouldSwap = true;
    event.detail.isError = false;
  }
});

// A Subtask's text is edited where it is. Enter saves it, as the form's one
// field. Escape, or leaving it unsaved, puts it back as it was.
function putBack(input) {
  input.value = input.defaultValue;
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && event.target.matches("[data-subtask-text]")) {
    putBack(event.target);
    event.target.blur();
  }
});
document.addEventListener("focusout", (event) => {
  const input = event.target;
  // Not while its save is under way: the answer replaces it.
  if (input.matches("[data-subtask-text]") && !input.form.classList.contains("htmx-request")) {
    putBack(input);
  }
});

// New card and Edit (components/subtask_rows.html): + Add copies the
// formset's empty form into a new row and counts it in TOTAL_FORMS, unless
// the last row is still blank, which it focuses instead. Hidden
// without JavaScript, where the one blank row stands in for it, and once the
// rows reach the most a Card holds.
document.querySelectorAll("[data-subtask-rows]").forEach((rows) => {
  const more = rows.querySelector("[data-subtask-more]");
  const total = rows.querySelector('input[name$="-TOTAL_FORMS"]');
  const most = Number(rows.querySelector('input[name$="-MAX_NUM_FORMS"]').value);
  const template = rows.querySelector("[data-subtask-template]");
  const list = rows.querySelector("[data-subtask-list]");
  const fits = () => Number(total.value) < most;
  more.hidden = !fits();
  more.addEventListener("click", () => {
    // The blank row the page always ends with comes first.
    const last = list.lastElementChild?.querySelector('input[type="text"]');
    if (last && !last.value.trim()) {
      last.focus();
      return;
    }
    const index = Number(total.value);
    list.insertAdjacentHTML("beforeend", template.innerHTML.replaceAll("__prefix__", index));
    total.value = index + 1;
    list.lastElementChild.querySelector('input[type="text"]').focus();
    more.hidden = !fits();
  });
});
