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

**Member**:
A user who has access to a board. Members may do anything to its cards and
stages, and may leave a board of their own accord; the acts that cannot be
undone are reserved to the owner.
_Avoid_: Collaborator, participant, user of the board

**Owner**:
The single member who may invite, remove members, rename or delete a board, and
hand ownership to another member. Every board has exactly one. Always means this
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
the only thing that carries effort, a due date, or an assignee.
_Avoid_: Issue, ticket, task, story, item

**Card order**:
The deliberate top-to-bottom sequence of cards within a stage, arranged by hand
and read as priority. Never derived from dates, effort, or when a card was
created.
_Avoid_: Rank, sort, priority (as a field — there is no priority field)

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
date alone — the system has no concept of a card being finished — so the way a
card stops being overdue is by leaving the board through the archive.
_Avoid_: Late, breached, at risk

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
