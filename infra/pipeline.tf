# GitHub Actions signs in to Google with the short-lived token GitHub issues
# each workflow run, so no service account key exists anywhere.
locals {
  # The numeric ID, which survives a rename and can't be claimed by a new
  # repository that takes the old name.
  github_repository_id = "1409981740"

  # Pushes to these branches may deploy. A pull request's ref is
  # refs/pull/<n>/merge, so pull requests never get a token.
  deploy_refs = [
    "refs/heads/main",
    # Only while the migration is being built; removed once the site is live.
    "refs/heads/feat/migrate-gcp",
  ]
}

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"

  depends_on = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-actions"
  display_name                       = "Deploy branches"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }

  attribute_mapping = {
    "google.subject"          = "assertion.sub"
    "attribute.repository_id" = "assertion.repository_id"
    "attribute.ref"           = "assertion.ref"
  }

  # Checked before any token is issued: any other repository or branch is
  # refused here.
  attribute_condition = "assertion.repository_id == \"${local.github_repository_id}\" && assertion.ref in ${jsonencode(local.deploy_refs)}"
}

# What the pipeline acts as. Every grant is on one named resource; it holds no
# project-wide role.
resource "google_service_account" "deployer" {
  account_id   = "workboard-deployer"
  display_name = "Workboard: the GitHub Actions pipeline"
}

resource "google_service_account_iam_member" "deployer_from_github" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository_id/${local.github_repository_id}"
}

resource "google_artifact_registry_repository_iam_member" "deployer" {
  repository = google_artifact_registry_repository.images.name
  location   = local.region
  role       = "roles/artifactregistry.writer"
  member     = google_service_account.deployer.member
}

resource "google_cloud_run_v2_service_iam_member" "deployer" {
  name     = google_cloud_run_v2_service.workboard.name
  location = local.region
  role     = "roles/run.developer"
  member   = google_service_account.deployer.member
}

resource "google_cloud_run_v2_job_iam_member" "deployer" {
  for_each = google_cloud_run_v2_job.jobs

  name     = each.value.name
  location = local.region
  role     = "roles/run.developer"
  member   = google_service_account.deployer.member
}

# A revision or execution runs as the runtime account, and deploying one
# requires being allowed to act as it.
resource "google_service_account_iam_member" "deployer_acts_as_runtime" {
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.deployer.member
}
