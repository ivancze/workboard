# Deployment

Workboard runs on Cloud Run with Cloud SQL Postgres, both in Singapore, behind
Firebase Hosting at `https://workboard.chongky.net`. Everything in Google Cloud
is declared in Terraform under [infra/](../infra/README.md) and deployed by
GitHub Actions. [ADR 0004](adr/0004-cloud-run-and-cloud-sql-behind-firebase.md)
explains why.

## What a request passes through

1. **Cloudflare DNS:** `workboard.chongky.net` is a CNAME to
   `prj-app-workboard.web.app`. It's DNS only, with Cloudflare's proxy off,
   so Firebase holds the certificate.
2. **Firebase Hosting** terminates HTTPS on Google's edge and rewrites every
   path to the Cloud Run service. It adds about 150 ms per request, and it
   forwards only one cookie (see "One cookie only").
3. **Cloud Run** (`workboard`, `asia-southeast1`) runs the image built from
   `Dockerfile`: gunicorn with two sync workers and `--preload`, serving
   Django. It scales from zero to two instances.
4. **Cloud SQL** (Postgres 17) has a private IP only. Cloud Run reaches it
   through the VPC by Direct VPC egress, and nothing on the internet can.

The service also answers on its own `run.app` address and on
`prj-app-workboard.web.app`. Both are in `PUBLIC_HOSTNAMES`.

## How a deploy works

A push to `main` runs `.github/workflows/deploy.yml`:

1. **Tests**, against a Postgres service container. Pull requests stop here.
2. **Sign-in to Google** with GitHub's short-lived token, through Workload
   Identity Federation. Google issues one only to this repository's `main`,
   so no service account key exists anywhere.
3. **Build and push** the image to Artifact Registry, tagged with the commit.
4. **Migrate:** the `workboard-migrate` job runs the new image's `migrate` to
   completion, while the old revision keeps serving. A failed migration stops
   the deploy there.
5. **Deploy** a new revision and send it all traffic.
6. **Smoke check:** `/health` through the domain must answer 200 with HSTS
   and Cloud SQL's version string. If it doesn't, traffic rolls back to the
   previous revision and the run fails.
7. **Point the admin job** (`workboard-manage`) at the new image.

`collectstatic` runs during the build, so a starting container does no work
and needs no writable filesystem.

**Pushes that change nothing in the image don't deploy:** those touching only
`.github/`, `docs/`, `infra/` or Markdown. The Run workflow button deploys
`main` on demand, for instance after a secret changes.

**Infrastructure changes** go live through `terraform apply`, run by hand.
Terraform ignores which image runs, so an apply never undoes a deploy.

Because migrations run while the *old* code is still serving, a migration that
removes something the old code reads will break during that window. Every
migration so far is additive. The first rename or column drop needs splitting
across two deploys.

## Cold starts

With no minimum instance, Cloud Run stops the last instance after about 15
idle minutes, and the next request waits for a new one: about 5 s, measured
through the domain. Most of that is Django loading. Two settings keep it from
being longer:
- the startup probe checks every second, not every ten
- `--preload` loads Django once, before the port opens, so the probe passes
  only when the app can answer

Every other request is warm, about 0.2 s through Firebase.

## Health page

`/health` queries the database and shows its version string, which tells you
which database a server reached (see `CLAUDE.md`). The smoke check reads it.

The startup probe is TCP, not HTTP. An HTTP probe arrives without a public
hostname, which `ALLOWED_HOSTS` turns away.

## Configuration

Set in `infra/run.tf`:

| Variable | Value |
| --- | --- |
| `HTTPS_ONLY` | `True`: SSL redirect, secure cookies, and HSTS |
| `PUBLIC_HOSTNAMES` | the `run.app`, `web.app` and custom domain addresses |
| `USE_X_FORWARDED_HOST` | `True` (see "One cookie only") |

From Secret Manager, read when an instance starts:

| Secret | Written by |
| --- | --- |
| `DATABASE_URL` | Terraform, with a password that never enters its state |
| `SECRET_KEY` | the operator |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` | the operator |

A new secret value reaches only instances started after it. Release with the
Run workflow button to replace the running ones.

`PUBLIC_HOSTNAMES` feeds both `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`, so a
new address is one change in `infra/run.tf`. Google's sign-in client also
needs the address's `/accounts/google/login/callback/`, added in the console.

`HTTPS_ONLY` is a flag of its own rather than being derived from `DEBUG`,
because Django forces `DEBUG` off while running tests and an SSL redirect would
turn every test request into a 301.

HSTS is set to one hour, not a year. A browser that has seen an HSTS header
will refuse plain HTTP for that hostname until it expires, and that cannot be
revoked. An hour stays recoverable. Firebase leaves Django's header alone on
the custom domain, but replaces it with its own year on `web.app`.

## One cookie only

Firebase Hosting forwards exactly one cookie to Cloud Run: the one named
`__session`. Every other cookie still reaches the browser, but never comes
back to the server, so anything kept in one silently vanishes. The application
therefore keeps everything in the session:

- **The session cookie** is named `__session`, everywhere, locally too.
- **CSRF tokens:** `CSRF_USE_SESSIONS`. htmx reads the token from the page,
  never from a cookie.
- **Messages:** session storage.

**Don't add a cookie.** Put the value in the session instead.
`config/tests/test_cookies.py` sends a form and reads its message with every
cookie but `__session` stripped, as Firebase would.

Firebase also hands Cloud Run requests addressed to Cloud Run's own hostname,
so `USE_X_FORWARDED_HOST` is on. Sign-in then builds Google's callback address
from the host the browser used.

## Database connections

Django's default: each request opens its own connection and closes it at the
end. It was once pinned at 0 because Neon billed by active time. Cloud SQL
bills the same either way, so `CONN_MAX_AGE` could be set to keep connections
open between requests, if a handshake per request ever shows up in timings.

## Static files

Collected at build time and served by whitenoise. Files are compressed but not
content-hashed: hashed names need a manifest written by `collectstatic`, and the
development bind mount hides the manifest baked into the image, so templates
would fail locally for any file the stale manifest lacked. The cost is weaker
browser caching, which is irrelevant at this size.

## Local development

Unrelated to the above: `docker compose up` runs the application against a
Postgres container, with source bind-mounted. `.env` holds local values only and
is never committed. Production values live in Secret Manager and
`infra/run.tf`, nowhere else.

## Before Google Cloud

Until 2026-10-14, Workboard ran on Render against Neon's free Postgres. The
move is recorded in [switch-over.md](switch-over.md) and
[data-copy.md](data-copy.md). The options weighed for it are in
[v2-infrastructure.md](v2-infrastructure.md).
