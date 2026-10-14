# Switching Members from Render to Google Cloud

The one-time move from Render and Neon to Cloud Run and Cloud SQL behind
Firebase Hosting ([ADR 0004](adr/0004-cloud-run-and-cloud-sql-behind-firebase.md)).
Written from the trial run of 2026-10-13/14, which did every step here except
the domain.

`<domain>` is Workboard's own address. Before this starts, it already serves
Render, with Render's session cookie named `__session`; both come from the
custom domain work. Members keep the address and stay signed in.

## Days before

1. **Firebase knows the domain.** In the Firebase console, go to Hosting, then
   Add custom domain, and pick the advanced setup if offered. That issues the
   certificate from TXT records while the domain still points at Render. Wait
   until it shows as issued. Whether the certificate really comes before DNS
   moves is still to be confirmed. If not, expect a few minutes of
   certificate errors at "The window", step 6.
2. **The application accepts the domain.** Add `<domain>` to
   `PUBLIC_HOSTNAMES` in `infra/run.tf`, then `terraform apply`.
3. **Sign-in accepts it.** `https://<domain>/accounts/google/login/callback/`
   is on the sign-in client. The custom domain work added it for Render.
4. **Prepare the pipeline commit, but don't push it:**
   - `SITE` in `.github/workflows/deploy.yml` becomes `https://<domain>`
   - `feat/migrate-gcp` comes out of the workflow's `push` branches, and out of
     `deploy_refs` in `infra/pipeline.tf`
5. **Announce the window to Members.** Allow 30 minutes; the trial's copy took
   well under 5.

## The window

1. **Suspend Render** (the service's Settings, then Suspend). Nothing writes to
   Neon from here, so the counts in step 3 must match exactly, sessions
   included.
2. **Render's `SECRET_KEY` goes to Cloud Run**, so the sessions about to be
   copied stay valid. Copy it from Render's Environment:

   ```
   printf 'Value: '; read -rs VALUE; echo
   printf '%s' "$VALUE" | gcloud secrets versions add SECRET_KEY --data-file=-
   unset VALUE
   ```

3. **Copy the data:** [data-copy.md](data-copy.md), steps 1–6. In the trial,
   the dump took about 4 s and the import about 10 s, and each count takes
   about a minute. The `diff` must show nothing at all. If it shows anything,
   stop and roll back.
4. **Release with Render's key:** `gh workflow run deploy.yml --ref main`,
   then `gh run watch`. The new revision starts fresh instances, which read
   the new `SECRET_KEY`. Two things about the timing:
   - **Before the commit in step 5:** `SITE` is still `web.app`, so the
     smoke check can pass.
   - **Before DNS moves:** an instance still holding the trial's key can't
     read a copied session, so it treats the Member as signed out. The
     first page it serves then saves over that session.
5. **Push the commit from "Days before", step 4.** It changes only
   `.github/` and `infra/`, so it doesn't deploy. Then `terraform apply` the
   `deploy_refs` change.
6. **Point the domain at Firebase:** replace the DNS record that points at
   Render with the records the Firebase console lists.
7. **Check the HSTS header with `curl`, before anyone opens the domain in a
   browser,** following the HSTS test in the custom domain spec.
8. **Check:**
   - `https://<domain>/health` shows Cloud SQL's fingerprint (see `CLAUDE.md`)
   - a browser that was signed in on Render is still signed in
   - drag a Card, then archive and restore it
   - claim an invitation with a second account
   - `gh workflow run deploy.yml --ref main` passes, its smoke check now
     going through `<domain>`
9. **Tell Members the board is back.**

## Rolling back

- **Before any Member has written to Cloud SQL:** point DNS back at Render,
  and resume Render. Neon is exactly as it was when Render was suspended.
- **After Members have written to Cloud SQL:** announce a pause, then copy the
  data back the other way. Use `gcloud sql export sql` to the dumps bucket,
  download, and load into Neon. Only then point DNS back and resume Render.
  This direction hasn't been rehearsed.

## Afterwards, by the operator

- Delete Render after two quiet weeks.
- Delete Neon after 30 days.
- Remove the old sign-in redirect addresses: Render's and `run.app`'s.
- Retire Render from the repository (GCP ticket 08): rewrite
  `docs/deployment.md` for Google Cloud, and remove `render.yaml` and the
  `RENDER_EXTERNAL_HOSTNAME` fallback.
