# Workboard

Django 6.1 + HTMX Kanban tracker for a small team. Deployed to Render against
Neon Postgres.

## Everything runs in Compose

```
docker compose exec -T web python manage.py test
docker compose exec -T web python manage.py shell -c "..."
```

`.venv/` exists so editors can resolve imports. Running `manage.py` from it
fails: `DATABASE_URL` names the `db` service, which only resolves inside the
Compose network.

**A new app's first migration** needs a one-off container. The startup command
runs `migrate`, which refuses while an installed app has no migrations, so the
service crash-loops before you can `exec` into it:

```
docker compose run --rm --no-deps web python manage.py makemigrations <app>
```

**After editing `.env`**, recreate rather than restart. `env_file` is read when
the container is created, so a restart keeps the old environment and the change
appears to have no effect:

```
docker compose up -d --force-recreate web
```

**Autoreload works by polling**, which is what survives Colima's virtiofs mount.
Keep `watchdog` out of the dependencies: it switches Django to inotify, which
never sees host edits, and reloads stop with no error.

## Styling

Tailwind v4, built by the `css` Compose service, which polls because file
events from the host never reach the container. Colours come only from
semantic tokens, there are no arbitrary values, and components are template
partials. Read [docs/frontend.md](docs/frontend.md) before writing markup.

## Which database am I talking to

`.env` holds the local URL, pointing at the `db` service. Production credentials
live in Render and nowhere else.

`/health` prints the server version, which tells you where you are.
`(Debian ...)` is the local container; a bare commit hash like `(7d7ea2a)` is
Neon.

## Reading boards

Read boards through `Board.objects.for_user(user)`, and reach Stages and Cards
from a board already scoped that way. Scoping at the query **fails closed**: a
forgotten check yields a 404 rather than another team's board. See
[ADR 0003](docs/adr/0003-membership-scoped-queries.md).

## Writing Card order

Anything that adds, moves, archives or deletes a Card rewrites Card order.
Lock every Stage it touches with `lock_stages` before reading or writing any
Card: locking a Card first deadlocks against a concurrent move. A deferred
unique constraint on (Stage, position) catches what the code gets wrong, at
commit.

Locks are always taken in the same order: the board (`Board.lock`, only for
adding or deleting Stages, for invitations, and for deleting the board), then
Stages, then Cards. `Board.lock` is `FOR NO KEY UPDATE`: a plain `FOR UPDATE`
blocks the key-share lock Postgres takes on the board whenever a Card is
inserted, and deleting a board then deadlocks against a Card being added. `lock_stages` raises
`Stage.DoesNotExist` if a Stage was deleted first. A Card's Stage and its
board are both PROTECT, so nothing that deletes a Stage, or a board, can take
Cards with it by accident.

Saving a Card that names an Assignee first locks that person's membership
(`lock_membership`), and removing a Member locks theirs before clearing their
Cards, so a Card can never end up assigned to someone with no access. This
lock comes before any Stage lock.

An archived Card has no Stage and no position, and a database check keeps it
from being half of each. `stage.cards` therefore holds only the Cards on the
board; reach archived Cards, or a board's Cards in general, through
`board.cards`.

## Settings that look like mistakes

- `HTTPS_ONLY` is its own flag rather than `not DEBUG`, because Django forces
  `DEBUG` off while running tests and an SSL redirect would turn every test
  request into a 301.
- There is no `django.contrib.admin` and no `create_superuser`, so
  `createsuperuser` does not exist here.

## Tests

- **Drive library input through the library.** Asking allauth's own provider to
  normalise a payload tests the integration; hand-building the dict it would
  have produced tests your belief about the library, and passes while the
  feature is broken.
- **Templates escape HTML.** `assertContains(response, "Ada's")` can never match
  `Ada&#x27;s`, and the negated form then passes vacuously. Use fixture names
  without apostrophes.
- **Prove a new test goes red.** Break the behaviour it covers, watch it fail,
  restore. Several tests here have passed for the wrong reason.
- `{# #}` is a single-line comment. Multi-line needs `{% comment %}`, or the
  text renders on the page.

## Where things are written down

- [CONTEXT.md](CONTEXT.md) — the glossary. Read it before naming an entity,
  adding a field, or writing anything a user will see; it lists the rejected
  synonyms as well as the chosen terms.
- [docs/adr/](docs/adr/) — decisions and the trade-offs behind them.
- [docs/frontend.md](docs/frontend.md) — the design system: tokens, partials,
  the theme toggle, and how the stylesheet is built.
- [docs/deployment.md](docs/deployment.md) — how a deploy works, and why
  compute and database sit with two providers.
- [docs/v2-features.md](docs/v2-features.md) and
  [docs/v2-infrastructure.md](docs/v2-infrastructure.md) — what was cut from v1
  and why. Check here before building something that feels missing.
- `.scratch/workboard-v1/issues/` — the v1 tickets (01–19, plus lettered
  follow-ups such as 05a), in dependency order, each with acceptance criteria,
  a record of what was verified, and the commit that landed it. v1 is closed;
  only 19, the nightly backup, is deferred. Deliberately uncommitted: they are
  local working notes, not a repo artefact.
