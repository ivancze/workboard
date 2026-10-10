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

## Which database am I talking to

`.env` holds the local URL, pointing at the `db` service. Production credentials
live in Render and nowhere else.

Two **fingerprints** tell you where you are, and both have been wrong before:

- `/healthz` prints the server version. `(Debian ...)` is the local container;
  a bare commit hash like `(7d7ea2a)` is Neon.
- The test suite takes under a second locally. Nine seconds means every query
  is crossing the network to Singapore.

## Reading boards

Read boards through `Board.objects.for_user(user)`, and reach Stages and Cards
from a board already scoped that way. Scoping at the query **fails closed**: a
forgotten check yields a 404 rather than another team's board. See
[ADR 0003](docs/adr/0003-membership-scoped-queries.md).

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
- [docs/deployment.md](docs/deployment.md) — how a deploy works, and why
  compute and database sit with two providers.
- [docs/v2-features.md](docs/v2-features.md) and
  [docs/v2-infrastructure.md](docs/v2-infrastructure.md) — what was cut from v1
  and why. Check here before building something that feels missing.
- `.scratch/workboard-v1/issues/` — the 19 tickets, in dependency order, each
  with acceptance criteria and a record of what was verified. Deliberately
  uncommitted: they are local working notes, not a repo artefact.
