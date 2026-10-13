# Every API the migration needs, enabled up front so later tickets only add
# resources.
resource "google_project_service" "apis" {
  for_each = toset([
    "artifactregistry.googleapis.com",     # images
    "billingbudgets.googleapis.com",       # the budget below
    "cloudresourcemanager.googleapis.com", # project IAM bindings
    "compute.googleapis.com",              # the network
    "firebase.googleapis.com",             # the front door
    "firebasehosting.googleapis.com",
    "iam.googleapis.com",            # service accounts, the pipeline's identity pool
    "iamcredentials.googleapis.com", # the pipeline acting as its service account
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com", # Cloud SQL's private IP
    "sqladmin.googleapis.com",
    "storage.googleapis.com", # the data copy's bucket
    "sts.googleapis.com",     # the pipeline's token exchange
  ])

  service = each.key

  # Destroying this configuration must never switch an API off under something
  # still using it.
  disable_on_destroy = false
}
