# workboard
A Kanban board for a small team to track their work.

## How it works

**Signing in.** Sign in with Google. Your display name, shown on Cards, can be
changed from your profile.

**Boards.** Create a board from the home page. It starts with three Stages:
To Do, In Progress and Done.

**Stages.** *Edit stages*, beside the board's name, lets you add, rename,
reorder (↑ ↓) and delete Stages. Names are unique on a board. Only an empty
Stage can be deleted, and a board always keeps at least one.

**Cards.** Add a Card by typing a title at the foot of any Stage. Click a Card
to open it, and *Edit* to change it:

- **Description**, written in Markdown
- **Assignee**, one Member of the board, or Unassigned
- **Contact persons**, free text for people outside the board
- **Due date**, for reference only. A Card past its date is marked Overdue
- **Effort**, a number in steps of 0.5, in whatever unit your team uses. Leave
  it empty if it hasn't been estimated

**Effort totals.** The board and each Stage show their total Effort, with a
count of the Unestimated Cards it leaves out.

**Moving Cards.** Drag a Card to reorder it, or drop it into another Stage. Or
use its ⋯ menu, which moves it to the bottom of the Stage you pick. A Card
arriving in the board's last Stage gets confetti.

**Archive.** Archiving is how finished work leaves the board. Choose *Archive*
from a Card's ⋯ menu, or on the Card's page. The Card disappears from the
board and its totals, but nothing is lost:

- *Archive*, beside the board's name, lists the board's archived Cards, most
  recently archived first.
- An archived Card can still be opened and edited, and is never Overdue.
- *Restore* puts it back at the bottom of the Stage it left. If that Stage has
  since been deleted, it goes to the board's first Stage.
- A Stage holding only archived Cards can be deleted.
- To clear a whole Stage at once, choose *Archive all Cards* from the ⋯ menu
  in its header. It asks first, saying how many Cards it will archive.

**Deleting a Card.** *Delete…* is at the bottom of a Card's ⋯ menu, on the
Card's page and in the archive. It asks first and can't be undone, so it's
for mistakes. Archive finished work instead.

**Theme.** The button in the header switches between System, Light and Dark.
