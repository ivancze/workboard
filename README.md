# workboard
A Kanban board for a small team to track their work.

## How it works

**Signing in.** Sign in with Google. Your display name, shown on Cards, can be
changed from your profile.

**Boards.** Create a board from the home page. It starts with three Stages:
To Do, In Progress and Done. *Members*, *Archive* and *Edit stages* are in the
⋯ menu beside *Add card*.

**Members.** The board's Owner invites people from *Members* by typing the
email address they sign in to Google with. Nothing is sent, so tell them
yourself: the board appears for them once they sign in with that address.
Until then the invitation is listed as waiting, and the Owner can withdraw it.
If someone signs in and sees no boards, the home page shows the address they
signed in with, so a mistyped invitation is easy to spot.

The Owner can also remove a Member. They lose access at once, and Cards
assigned to them become unassigned, though Cards they created still credit
them. A Member can leave a board the same way, from *Members*.

Every board has exactly one Owner. To step down, or before leaving, the Owner
hands ownership to another Member with *Make Owner*.

**Renaming a board.** Only the Owner can, with the pencil beside the board's
name: edit the name where it is, then press Enter, or Escape to leave it.
Everyone on the board sees the new name.

**Describing a board.** Under the name, the Owner can add a short line about
what the board is for, up to 200 characters: click it, type, then press
Enter. Until there is one, the board shows a playful line instead, different
each visit. Clear the description to bring the playful lines back.

**A board pet.** Anyone on the board can give it a pet, a dog, a pug, a duck,
a pig or Bruno the Labrador, from *Pet* in the board's ⋯ menu. It wanders along the bottom of the
board's page for everyone on the board, and naps now and then. Click it and
see what it does. Choose *None* to send it home.

**Deleting a board.** Only the Owner can, from *Delete board…* in the board's
⋯ menu. It deletes every Card, archived ones included, with no undo, so it
asks you to type the board's name exactly first.

**Stages.** *Edit stages* lets you add, rename,
reorder (↑ ↓) and delete Stages. Names are unique on a board. Only an empty
Stage can be deleted, and a board always keeps at least one.

**Cards.** *Add card*, beside the board's name, opens a blank Card. Only the
title is needed, and the Card goes to the bottom of the leftmost Stage. Click
a Card to open it, and *Edit* to change it:

- **Description**, written in Markdown
- **Priority**: Urgent, Must have, Should have or Could have, shown on the
  board as a coloured label. It's only a label: Cards stay where you put
  them. Leave it at No priority if it doesn't matter. It can also be set
  straight from the board: click a Card's label, or hover over a Card
  without one and click *+ Priority*
- **Assignee**, one Member of the board, or Unassigned
- **Contact persons**, free text for people outside the board
- **Due date**, for reference only. A Card due today gets an orange outline,
  and one past its date is marked Overdue in red. In the board's last Stage,
  every Card is outlined green and Overdue loses its red
- **Effort**, a number in steps of 0.1, in whatever unit your team uses:
  hours, days or a score. Leave it empty if it hasn't been estimated

**Effort totals.** The board and each Stage show their total Effort, with a
count of the Unestimated Cards it leaves out.

**Moving Cards.** Drag a Card to reorder it, or drop it into another Stage. Or
use its ⋯ menu, which moves it to the bottom of the Stage you pick. A Card
arriving in the board's last Stage gets confetti.

**Filtering.** *Show*, beside the board's totals, narrows the board to one
Member's Cards, to Unassigned ones, or to *Mine*. The choice is in the page's
address, so it survives a reload and can be shared. Hidden Cards are only out
of view: the totals still count the whole board, with the shown figures
labelled *Shown* beside them, and dragging still works.

**Staying current.** Changes others make don't appear live. A board catches up
when you come back to its tab or window, keeping your filter. It waits while
you're dragging or have a menu open, and says so if it can't refresh.

**Archive.** Archiving is how finished work leaves the board. Choose *Archive*
from a Card's ⋯ menu, or on the Card's page. The Card disappears from the
board and its totals, but nothing is lost:

- *Archive*, in the board's ⋯ menu, lists the board's archived Cards, most
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
