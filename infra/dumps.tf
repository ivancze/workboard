# Where a pg_dump of Neon waits for Cloud SQL to import it. A dump holds
# Members' email addresses, so it is deleted by hand straight after the import,
# and anything forgotten is deleted after a day regardless.
resource "google_storage_bucket" "dumps" {
  name     = "${local.project}-dumps"
  location = local.region

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  lifecycle_rule {
    condition {
      age = 1
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.apis]
}

# The import runs on Google's side as the instance's own service account, so
# the private-only database never needs a public address.
resource "google_storage_bucket_iam_member" "sql_reads_dumps" {
  bucket = google_storage_bucket.dumps.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_sql_database_instance.main.service_account_email_address}"
}
