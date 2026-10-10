# Candidate features for v2

A capture list, not a commitment. Everything here was deliberately cut from v1
to get a pilot in front of a real team, and each entry records *why* it was cut
so the decision can be re-made with its original reasoning rather than
re-litigated from scratch. Expect to scope this down hard.

Infrastructure directions live separately in
[v2-infrastructure.md](./v2-infrastructure.md).

Terms are used as defined in [CONTEXT.md](../CONTEXT.md).

## Additive — a feature on its own, nothing else moves

These cost roughly what they look like. Most are a model change, a form, and a
template.

**Labels or tags on Cards.** The most commonly missed Kanban feature. Cut
because it teaches nothing that Cards did not already teach, and because
unlabelled boards stay readable at this size.

**Comments on Cards.** Cut as straightforward CRUD. Worth noting it is the
first feature where people will *expect* a notification to follow, which drags
in email — see below.

**Checklists or subtasks.** Cut as a second ordered collection inside a Card,
duplicating work already done for Card order.

**Attachments.** Cut because it is the only deferred feature that needs object
storage, a storage account, upload limits, and a decision about what happens to
files when a Card is deleted. Genuinely more work than it looks.

**Stage reordering.** Cut as a second drag-and-drop implementation for purely
cosmetic gain, after the Card one was already built.

**Board templates.** Cut as speculative: nobody knows what template they want
until they have made the same board three times.

**A visible `updated_at`.** Already recorded on every Card but shown nowhere.
Displaying it is a template change.

**Viewer role.** Owner and Member exist; a read-only third role was cut until
somebody asks for it. One value in one column plus checks.

## Requires something the product does not have

These are not expensive in themselves — they are expensive because of what they
pull in.

**Notifications of any kind.** Requires email infrastructure: a provider,
domain verification, and deliverability debugging. This directly reverses
[ADR 0002](./adr/0002-google-identity-no-email.md), which is worth reading
first — the absence of email is load-bearing, not an oversight, and it is also
why invitations are delivered by hand.

**Invitations delivered by the product.** Same dependency. Would remove the
one genuinely awkward step in onboarding, where an invitation reaches somebody
via a group chat rather than their inbox.

**Email or magic-link sign-in.** Same dependency again. Adding it alongside
Google sign-in is additive rather than a migration, so the user model does not
need revisiting — but every mail concern above applies.

**Activity log.** Cheaper than it looks, because `created_by`, `created_at` and
`updated_at` are already recorded on every Card specifically so this would be
possible later. What is *not* recorded is intermediate history — who moved a
Card between Stages, and when — so a log built later starts from the day it is
built. That history is unrecoverable, which is the one argument for doing this
sooner rather than later.

**Filtering by contact person.** Contact person is free text, so "Dave",
"dave" and "Dave Smith" are three different people to the database and nothing
can be filtered or counted reliably. Making this work means structuring the
field and cleaning existing values by hand — which is exactly the trade that was
accepted when the field was chosen.

**Search.** Needs a decision about what is searched (titles only, or markdown
descriptions too) and whether archived Cards are included. Postgres full-text
search is adequate and no new infrastructure is required.

## Changes the shape of the product

These are not features so much as different products. Each one should be
treated as its own grilling session rather than a ticket.

**Realtime collaboration and presence.** Reverses
[ADR 0001](./adr/0001-no-realtime-collaboration.md). The honest cost is not
WebSockets but everything around them: reconnection, missed-message replay,
optimistic rollback, and concurrent drags of the same Card. It would also
justify revisiting Card order — the current integer positions, renumbered per
Stage, were chosen *because* there is no realtime; concurrent editing is where
fractional indexing starts to earn its single-row writes.

**Collaborative text editing of descriptions.** CRDTs, Yjs or Automerge. A
multi-week project of its own and a different product wearing a Kanban costume.
Listed only so it is clear it was considered and rejected, not forgotten.

**Organisations or workspaces above Boards.** v1 is deliberately flat: Users
own Boards, Boards have Members, and the Board is the only access boundary.
Adding a tier above it is a data migration plus a rewrite of every
authorization check, and it triples query complexity. Going flat to tiered was
assessed as a migration rather than a rewrite, which is why flat was safe to
start with — but it is the single most invasive item on this page.

**Swimlanes.** Rows crossing the Stages, grouping Cards by assignee or label.
Needs labels first, and changes every board template and drag-and-drop target.

## Interaction and polish

**Responsive mobile layout.** The deliberate v1 gap. Mobile users can already
move a Card using the move-to-Stage dropdown, which was built precisely so
capability did not depend on layout. What is missing is making a horizontal row
of Stages usable on a 390px screen — horizontal scroll, one Stage at a time, or
collapsing to a list — which is a real design problem, not a styling pass.
Worth doing only once usage shows anyone opens it on a phone.

**Touch drag-and-drop.** Long-press to disambiguate drag from scroll,
auto-scroll near screen edges, and a lot of fiddling to get the feel right.
Strictly a nicety given the dropdown exists.

**Overdue beyond colour.** v1 draws the line at visual emphasis only. Sorting
by Due date, filtering to overdue, or an "overdue" view are the slope that was
deliberately not started down.

**An Effort unit label and ceiling.** Both were offered and declined in v1, so
the scale lives in the team's heads. Revisit when somebody new joins and guesses
wrong, which is the failure this would prevent.

**Effort reporting.** Totals per Stage and per Board exist. Anything
historical — effort completed per week, burndown — needs the Card history that
the activity log above would start recording.

## Explicitly rejected, kept here so they are not re-proposed

**Soft delete with a scheduled purge.** Considered as a safer Delete. Rejected
because it is a second archive mechanism requiring a task scheduler on day one,
to protect against a mistake that costs ten seconds to redo.

**Per-Board display names.** Rejected because it solves a problem a small team
does not have: one name per person, taken from their Google profile.

**Auto-archiving a "done" Stage.** Rejected because Stages are user-editable
and nothing marks one as semantically final — a board can have any Stage after
Done. Bulk archiving a Stage covers the real need without the product guessing.
