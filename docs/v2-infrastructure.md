# Infrastructure options for v2

Nothing here is decided. v1 deliberately deferred all infrastructure learning
(see ticket 05 of the grilling: a weekend to a pilot, infra when release cadence
justifies it), and this records the two candidate directions so the reasoning
is not lost. It is a roadmap note rather than an ADR, because no decision has
been made and nothing is hard to reverse yet.

The two options are **alternatives**, not stages. Both replace Render. They
differ in what they teach.

## What is already portable

Whichever direction wins, the application needs very little work, because v1
avoided provider lock-in on purpose:

- One `Dockerfile`, no provider-specific build system
- All configuration from environment variables
- `PORT` is read from the environment, which is what Cloud Run also sets
- `DATABASE_URL` points at Neon, which is reachable from anywhere, so the
  database need not move at all
- No provider primitives — no managed key-value store, blob storage, or cron to
  find replacements for

This is the dividend from rejecting serverless hosting in v1. The work in either
migration is the platform around the app, not the app.

## Option A: Google Cloud Run, with Terraform and GitHub Actions

The draw is that this is where **Terraform stops being ceremony**. On Render the
entire infrastructure is one web service and one database — two resources
nobody would ever recreate by hand, so writing Terraform for them teaches syntax
and no judgement. A Cloud Run deployment is a service, an Artifact Registry
repository, Secret Manager secrets, a service account, IAM bindings, and a build
trigger: genuinely interdependent resources with an ordering, which is the
problem Terraform actually exists to solve.

It also makes room for a real CI/CD pipeline in GitHub Actions: build the image,
push to Artifact Registry, deploy the new revision, run migrations.

### What has to be built

1. **The hostname.** `RENDER_EXTERNAL_HOSTNAME` does not exist on GCP, so
   `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` need their own environment
   variable. Roughly five lines of settings.
2. **Migrations.** This is the real work. Cloud Run has no equivalent of
   Render's `preDeployCommand`, so the guarantee that migrations run *before*
   traffic reaches new code has to be rebuilt by hand — a Cloud Run Job invoked
   by the pipeline between build and deploy. Getting the ordering wrong means a
   window where new code queries an old schema.
3. **Build automation.** Render builds on git push for free. Here it is a
   GitHub Actions workflow with a service account and Workload Identity
   Federation, which is the CI/CD work v1 deferred.
4. **Secrets.** Dashboard environment variables become Secret Manager secrets
   mounted into the service.

Estimate: a weekend while keeping Neon. Substantially longer if the database
also moves to Cloud SQL, because that pulls in VPC connectors or the Cloud SQL
auth proxy.

### Cost

Verified October 2026:

| Service | Always Free allowance | Expected usage |
| --- | --- | --- |
| Cloud Run | 2M requests, 180k vCPU-seconds, 360k GiB-seconds per month | A handful of people a few times daily — thousands of requests |
| Artifact Registry | 0.5 GB storage | A Django image is 200–400 MB, so **old image versions must be pruned** |
| Cloud Build | 2,500 build-minutes per month | Builds take roughly two minutes |
| Neon | unchanged | free plan, no expiry |

**Cloud Run plus Neon sits inside the Always Free tier at around $0/month,
permanently — not merely during a trial.** That is cheaper than Render's ~$7.

Moving the database to Cloud SQL would change that: there is **no permanent free
tier for Cloud SQL**, only a 30-day trial instance, and the cheapest real
instance is roughly $10–15/month.

### About the $300 trial credit

The Google Cloud free trial is **$300 valid for 90 days, and unused credit
expires.** The binding constraint is therefore the 90 days, not the money — and
this application is far too small to spend it. On Cloud Run plus Neon you would
reach day 90 having consumed almost none of it.

The sensible use of the credit is as a **90-day sandbox for learning Terraform
against real GCP resources**, in parallel with the application staying wherever
it already is. It is a reason to experiment, not a reason to relocate something
people are using.

### The known trade-off

Cloud Run scales to zero, so the first request after an idle period pays a cold
start — on the order of a few seconds for a Django container (estimated, not
measured). That is far better than Render's free tier, which takes about a
minute, but it is not the always-warm behaviour the paid Render instance buys.

Removing it means `min-instances=1`, which leaves the Always Free tier and costs
roughly $10–15/month: more than Render, while still requiring the pipeline above
to be built. **A few seconds is considered acceptable**, so the free
scale-to-zero configuration is the intended target.

## Option B: Raspberry Pi behind a Cloudflare Tunnel

The draw here is different: it teaches reverse proxies, TLS, systemd, tunnels,
and backups — the things a managed platform hides. Because v1 runs everything
through Docker Compose, **the same `compose.yaml` is the Pi deployment**; the
only build change is targeting `arm64`.

Expose it with a **Cloudflare Tunnel**, not port forwarding. The tunnel makes an
outbound connection, so no inbound ports open, the home IP is never exposed, and
it works behind carrier-grade NAT. Port forwarding puts a public service inside
the home network perimeter, where a compromise lands next to every other device
on the LAN.

Hardware caveat: boot from a USB3 SSD. Database write patterns destroy SD cards,
and the failure mode is silent corruption.

The real cost is not security but becoming the operations team: power cuts, ISP
outages, OS patching, and above all **off-device backups**, since a Pi with one
SSD is a single hardware failure from total data loss.

## Prerequisite for either: a custom domain

Both options change the application's hostname, and the hostname is registered
with Google as an OAuth authorised redirect URI, matched literally with no
wildcards. Every move therefore means editing the Google Cloud console and
waiting out a propagation delay, with a mismatch meaning nobody can sign in at
all.

A custom domain registered once makes every future move invisible — to Google,
to users' bookmarks, and to the application's own configuration. It is also
effectively required for a stable Cloudflare Tunnel setup under Option B.

Deferred for v1 on the grounds that the Render hostname is permanent and
adequate. Revisit before the first move.

## Related

Deferred product features are captured separately in
[v2-features.md](./v2-features.md).
