# No realtime collaboration

Workboard is a shared board for a small team, so the obvious expectation is live
sync. We deliberately serve plain request-response state instead: boards refetch
when a tab regains focus, and there are no WebSockets, no presence, and no
polling. A handful of people editing a board rarely collide, and the
connection-lifecycle work that realtime demands — reconnection, missed-message
replay, optimistic rollback — bought nothing we needed for a pilot. Adding it
later is additive rather than a rewrite.
