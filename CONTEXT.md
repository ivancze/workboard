# Workboard

A Kanban board for a small, trusted team to track their own work. Each board is
self-contained: it carries its own members, its own workflow stages, and its own
cards, and shares nothing with any other board.

## Language

### People and access

**User**:
A person who has signed in. Identity always comes from an external provider; the
system holds no credentials of its own.
_Avoid_: Account, profile, login

**Board**:
The unit of both workflow and access. A board is the only boundary that exists:
there is no organisation, team, or workspace above it.
_Avoid_: Project, workspace, team, org

**Board description**:
An optional short line of plain text under a board's name, written by its
owner, saying what the board is for. A board without one shows a playful line
instead, picked at random on each visit. That line belongs to the product,
not the board, and is never stored.
_Avoid_: Tagline, subtitle, summary, about

**Board pet**:
A small animal that wanders along the bottom of a board's page and reacts
when clicked: a pug, a duck, a pig, a chicken, or one of two dogs with names,
Chico (a tan mixed breed) and Bruno (a black Labrador). Chosen by any member,
one per board, and the same one for everyone on it; a board has none until
someone picks one. The chicken lays eggs that hatch, when clicked, into
chicks that follow her; they belong to that one visit by that one viewer and
are gone when they leave. Purely for fun: a pet carries no information about
the board and nothing acts on it. "Pet" for short.
_Avoid_: Mascot, companion, buddy, avatar

**Member**:
A user who has access to a board. Members may do anything to its cards and
stages, choose its pet, and may leave a board of their own accord; the acts that cannot be
undone are reserved to the owner.
_Avoid_: Collaborator, participant, user of the board

**Owner**:
The single member who may invite, remove members, rename, describe or delete a
board, and hand ownership to another member. Every board has exactly one. Always means this
board-level role, never the person a card is assigned to and never the person
who created it.
_Avoid_: Admin, lead, maintainer

**Membership**:
The link between a user and a board, carrying their role. Memberships are the
only record of who can see what.

**Pending member**:
A membership created against an email address that no user has yet signed in
with. It is a full membership in waiting, not a separate kind of thing — the
invitation and the membership are the same record in two different states.
_Avoid_: Invitation, invite (as a noun), request

**Invite**:
To create a pending member by naming an email address. A verb only. Nothing is
sent: the system has no way to contact anyone, so reaching the person is done
by hand, outside the product.

### Board structure

**Stage**:
A named step in a board's workflow. Every card sits in exactly one stage at a
time, and moving a card between stages is how work progresses. Stages belong to
a board and differ from board to board.
_Avoid_: Column, list, status, state, bucket

**Card**:
One unit of work. The smallest thing a team member can be accountable for, and
the only thing that carries effort, a due date, a priority, or an assignee.
_Avoid_: Issue, ticket, task, story, item

**Card order**:
The deliberate top-to-bottom sequence of cards within a stage, arranged by hand
and read as the team's working order. Never derived from dates, effort,
priority, or when a card was created.
_Avoid_: Rank, sort

### What a card carries

**Assignee**:
The one member accountable for a card. A card may have none, which is a visible
absence rather than a default. Only members of the card's board may be named.
_Avoid_: Owner, reporter, responsible party

**Creator**:
The user who first made the card. Recorded permanently and never reassigned,
including when that user is removed from the board — a card may name a creator
who is no longer a member, because creation is a historical fact rather than a
statement about who is accountable now.
_Avoid_: Owner, author, reporter

**Contact person**:
Freely typed names of people connected to a card who need no access to it.
Purely a human-readable note: the system never matches a contact person to a
user, and they can neither see nor be notified of anything.
_Avoid_: Collaborators, members, watchers, followers, CC

**Due date**:
The calendar date a card is meant to be finished by. A plain date with no time
and no timezone — "the 14th" means the 14th wherever you are. Entirely
advisory: nothing in the system ever acts on it. No reminders, no notifications,
no blocking, no sorting.
_Avoid_: Deadline, target date, ETA

**Overdue**:
A card still on the board whose due date has passed. Overdue is read off the
date alone, so the way a card stops being overdue is by leaving the board
through the archive. In the board's last stage it is still overdue, and still
says so, but without the alarm colour: see last stage.
_Avoid_: Late, breached, at risk

**Last stage**:
The rightmost stage of a board, whatever it is named. The board shows it as
finished work: a card arriving there gets confetti, every card in it is
outlined green, and an overdue one there loses its red. That is display only.
Cards in the last stage still count in every total, stay overdue by their
date, and leave the board only through the archive.
_Avoid_: Done, complete, closed

**Priority**:
How much a card matters, declared as one of four levels, from highest: Urgent,
Must have, Should have, Could have. A card may have none, which is the default
and shows nothing. Purely a label: it never moves a card in card order, and
nothing sorts or filters by it. An Urgent card can sit below a Could have one
if that is where the team put it.
_Avoid_: Severity, importance, rank, label, tag

**Effort**:
How much work a card is judged to represent, in whatever unit the team has
agreed between themselves. The system holds a bare number and attaches no
meaning to it, so the scale lives in the team's heads rather than in the
product.
_Avoid_: Estimate, points, size, weight

**Unestimated**:
A card carrying no effort at all. Deliberately distinct from an effort of zero:
zero says this is free, unestimated says nobody has looked yet.

**Effort total**:
The summed effort of the cards still on a board or in one stage, always paired
with a count of the unestimated cards it could not include. Archived cards count
towards nothing.

### Leaving the board

**Archive**:
To take a card off the board while keeping it. Archiving is the ordinary way
work ends — the team's habit is to archive what is finished, which is what keeps
a board readable. An archived card is an ordinary card kept somewhere else: it
stays fully editable and is reached through the board's archive.
_Avoid_: Close, complete, resolve, hide

**Restore**:
To return an archived card to the board, back to the stage it left from, or to
the board's first stage when that stage no longer exists.
_Avoid_: Unarchive, reopen, revive

**Delete**:
To destroy a card permanently. Exists for mistakes and rubbish, not for finished
work, and is the only act on a card that cannot be undone.
_Avoid_: Remove, archive, trash
