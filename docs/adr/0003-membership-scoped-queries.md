# Membership-scoped queries instead of per-view permission checks

Views contain no authorization checks. Every board read starts at
`Board.objects.for_user(user)`, which filters by Membership, and Stages and
Cards are reached only from a board already scoped that way.

The decision is about which way a mistake fails. A forgotten explicit check
fails open and serves another team's board; a forgotten scope yields a
confusing 404 — visible, harmless, and quickly fixed. HTMX means many small
endpoints each touching one object, so the number of places to forget is high
enough that the structural fix beats discipline.

A consequence worth stating: a non-member receives 404 rather than 403, which
also avoids confirming that a board exists.
