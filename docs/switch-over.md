# Switching Members from Render to Google Cloud

> **A record, not a procedure to follow.** The move was done on 2026-10-14,
> and Render and Neon have since been deleted. It's kept for how the copy and
> the cutover went.

The one-time move from Render and Neon to Cloud Run and Cloud SQL behind
Firebase Hosting ([ADR 0004](adr/0004-cloud-run-and-cloud-sql-behind-firebase.md)).
Written from the trial run of 2026-10-13/14, which did every step here except
the domain.

It's a hard cutover. Members move to a new address, `<domain>`, and sign in
there again with Google. Their Boards, Cards and invitations come with them.
Their sessions don't, which is why nothing here copies Render's `SECRET_KEY`.

## Days before

None of this is visible to Members. Render keeps serving them throughout.

1. **Turn off Render's auto-deploy** (the service's Settings, then
   Auto-Deploy, set to No). Render then keeps the code Members have used
   against Neon all along, which is what rolling back resumes.
2. **Merge `feat/migrate-gcp` into `main`.** Push it, and the pipeline
   deploys it to Cloud Run. Check that Render's Events show no new deploy.
3. **Only `main` deploys from now on.** Take `feat/migrate-gcp` out of the
   workflow's `push` branches and out of `deploy_refs` in
   `infra/pipeline.tf`. Push, which doesn't deploy, then `terraform apply`.
4. **Firebase serves the domain.** In the Firebase console, go to Hosting,
   then Add custom domain. Add the DNS records it lists, and wait until the
   certificate shows as issued.
5. **The application accepts the domain.** Add `<domain>` to
   `PUBLIC_HOSTNAMES` in `infra/run.tf`, then `terraform apply`.
6. **Check the HSTS header with `curl`, before anyone opens the domain in a
   browser.** Follow the HSTS test in the custom domain spec.
7. **Sign-in accepts the domain.** Add
   `https://<domain>/accounts/google/login/callback/` to the sign-in client.
8. **The pipeline checks the domain.** `SITE` in
   `.github/workflows/deploy.yml` becomes `https://<domain>`. Push, which
   doesn't deploy, then `gh workflow run deploy.yml --ref main` and
   `gh run watch`. Its smoke check now goes through the domain, and must
   pass.
9. **Sign in on the domain once,** to see the whole path work. It shows
   the trial's copy of the data, which the window replaces. So don't share
   the address yet.
10. **Announce the window to Members.** Allow 30 minutes; the trial's copy
   took well under 5. Say they'll sign in again at a new address, and give
   it when the window ends.

## The window

1. **Suspend Render** (the service's Settings, then Suspend). Nothing writes to
   Neon from here, so the counts in step 2 must match exactly.
2. **Copy the data:** [data-copy.md](data-copy.md), steps 1–6. In the trial,
   the dump took about 4 s and the import about 10 s, and each count takes
   about a minute. The `diff` must show nothing at all. If it shows anything,
   stop and roll back.
3. **Check on `<domain>`:**
   - `/health` shows Cloud SQL's fingerprint (see `CLAUDE.md`)
   - sign in, and the team's Boards are there
   - drag a Card, then archive and restore it
   - claim an invitation with a second account
4. **Tell Members the new address.** They sign in again with Google.

No release is needed. The service reads the database on every request, and
the sessions the copy brings over are unusable: they were signed with Render's
key and belong to Render's address. They expire on their own.

## Rolling back

- **Before any Member has written to Cloud SQL:** resume Render, and tell
  Members to stay on the old address. Neon is exactly as it was when Render
  was suspended.
- **After Members have written to Cloud SQL:** announce a pause, then copy the
  data back the other way. Use `gcloud sql export sql` to the dumps bucket,
  download, and load into Neon. Only then resume Render. This direction
  hasn't been rehearsed.

## Afterwards, by the operator

- Delete Render after two quiet weeks. Until then its address shows Render's
  suspended page, not a redirect.
- Delete Neon after 30 days.
- Remove the old sign-in redirect addresses: Render's and `run.app`'s.
- Retire Render from the repository (GCP ticket 08): rewrite
  `docs/deployment.md` for Google Cloud, and remove `render.yaml` and the
  `RENDER_EXTERNAL_HOSTNAME` fallback.
