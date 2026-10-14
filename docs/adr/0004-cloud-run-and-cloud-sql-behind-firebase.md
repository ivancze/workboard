# Cloud Run and Cloud SQL behind Firebase Hosting, in a private network

Workboard moves from Render and Neon to Google Cloud, in the
`prj-app-workboard` project that already holds the sign-in client, all in
Singapore. A Cloud Run service scales between zero and two instances. It
reaches Cloud SQL for PostgreSQL 17, which has only a private IP, over Direct
VPC egress in a custom network. Firebase Hosting is the front door, and
everything is declared in Terraform and deployed by GitHub Actions. There are
two reasons. The first is learning: Terraform and a deploy pipeline only teach
judgement once there are real, interdependent resources (see
[v2-infrastructure.md](../v2-infrastructure.md)). The second is recovery: Neon's
free plan restores only the last 6 hours, while Cloud SQL keeps a week of daily
backups. The network is sized for more services than this one.

## Considered Options

- **Stay on Render and Neon.** It works, and costs about $7 a month. It teaches
  nothing new, and keeps the 6-hour recovery window.
- **Cloud Run with Neon.** This sits inside Google's free allowances, at about
  $0 a month. It keeps Neon's recovery window, and leaves the database on the
  public internet, outside the network future services would join.
- **A load balancer in front of Cloud Run.** This is the standard way to put a
  custom domain on Cloud Run, but its forwarding rule alone costs about $18 a
  month, more than everything else together.
- **Cloud Run domain mapping.** It's free, but only a Preview in
  `asia-southeast1`, and Google doesn't recommend it for production.
- **A Raspberry Pi behind a Cloudflare Tunnel.** It teaches a different set of
  things, but makes the operator the operations team: power cuts, patching,
  and off-device backups.

## Consequences

- **Cost:** about $11–14 a month (estimated), against Render's $7. Cloud SQL's
  smallest instance is nearly all of it, since it has no free tier.
- **Cold starts:** with no minimum instance, the first request after a quiet
  spell waits a few seconds.
- **Cookies:** Firebase Hosting forwards only a cookie named `__session`. So
  the session cookie takes that name, and CSRF tokens and messages live in the
  session instead of their own cookies. Renaming the cookie would sign
  everyone out. That costs nothing here: Members move to a new address at
  switch-over and sign in again anyway.
- **One service in a network built for more:** the VPC, private services access
  and Direct VPC egress are more parts than a single service needs. This is
  accepted, because the network is meant to outlive it.
- **Migrations:** Render's pre-deploy command becomes a Cloud Run job that the
  pipeline runs before each deploy. The old revision serves while it runs, so
  a migration that removes something the old code reads still needs splitting
  across two deploys, as [deployment.md](../deployment.md) already
  describes.
