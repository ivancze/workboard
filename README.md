# workboard
A Kanban board for a small team to track their work.

## How it works

**Signing in.** Sign in with Google. You can change your display name from
your profile.

**Boards.** Create a board from the home page. It starts with three Stages:
To Do, In Progress and Done. The ⋯ menu beside *Add card* holds the board's
settings: *Members*, *Archive*, *Edit stages*, *Pet* and *Delete board…*.

**Members.** The board's Owner invites people from *Members* by typing the
email address they use for Google. No email is sent, so let them know: the
board appears once they sign in with that address. The Owner can also remove
Members, or hand ownership to someone else with *Make Owner*. Anyone can leave
a board from *Members*.

**Naming and describing a board.** The Owner can rename the board with the
pencil beside its name, and add a short description underneath: click, type,
then press Enter.

**Stages.** *Edit stages* lets you add, rename, reorder and delete Stages. A
Stage must be empty before it can be deleted.

**Cards.** Click *Add card* and give it a title; it lands at the bottom of the
first Stage. Click a Card to open it, then click any part of it to edit it in
place: Enter saves, Escape cancels. A Card can have:

- a **Description**, written in Markdown (see below)
- a **Priority**: Urgent, Must have, Should have or Could have, shown as a
  coloured label. You can also set it from the board by clicking the label
- an **Assignee** from the board's Members
- **Contact persons** outside the board
- a **Due date**. Cards due today are outlined orange, and overdue ones are
  marked red
- an **Effort** estimate, in whatever unit your team uses. The board and each
  Stage show their total

**Subtasks.** On a Card's page, type into *Add a Subtask* and press Enter.
Tick them off as you go; a progress bar shows on the Card and its tile.

**Moving Cards.** Drag a Card to reorder it or move it to another Stage, or use
its ⋯ menu. A Card reaching the last Stage gets confetti. To put a Stage in
order of Priority, Urgent first and Cards with none last, choose *Sort by
Priority* from the Stage's ⋯ menu; you can rearrange it by hand afterwards.

**Filtering.** Use *Show* to see only one Member's Cards, Unassigned ones, or
your own.

**Seeing others' changes.** Changes made by others show up when you come back
to the board's tab.

**Archive.** When work is finished, choose *Archive* from a Card's ⋯ menu. It
leaves the board but isn't lost: find it under *Archive* in the board's ⋯ menu,
where you can open it or *Restore* it. To clear a whole Stage, choose *Archive
all Cards* from the Stage's ⋯ menu.

**Deleting.** *Delete…* in a Card's ⋯ menu removes it for good, so use it for
mistakes and archive finished work instead. The Owner can delete a whole board
from *Delete board…*.

**A board pet.** Choose a pet from *Pet* in the board's ⋯ menu: Chico, a pug,
a duck, a pig, Bruno the Labrador or a chicken. It wanders along the bottom of
the page and naps now and then. Click it to see how it reacts, or to wake it
up. The chicken lays eggs: click one to hatch a chick, which follows her
around. The other pets leave poop behind: click it to clean it up. Choose
*None* to send the pet home.

**Theme.** The button in the header switches between System, Light and Dark.

## Writing a description

Descriptions use Markdown. A new line starts a new line, and a blank line
starts a new paragraph.

| To get | Write |
|---|---|
| Headings | `# Heading`, `## Smaller` |
| Bold and italic | `**bold**`, `*italic*` |
| Code | `` `inline` ``, or a block between lines of ```` ``` ```` |
| Lists | `- item` or `1. item`; indent to nest |
| Quotes | `> quoted text` |
| A dividing line | `---` on its own line, after a blank line |
| Links | `[text](https://example.com)`, or `<https://example.com>` |
| Images | `![what it shows](https://example.com/picture.png)` |

Tables, strikethrough and checkboxes aren't supported; use Subtasks for
checklists.
