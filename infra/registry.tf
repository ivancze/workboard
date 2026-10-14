# Images are tagged with their commit. Only the newest 5 are kept, which stays
# inside the free storage allowance and still leaves releases to roll back to.
resource "google_artifact_registry_repository" "images" {
  repository_id = "workboard"
  location      = local.region
  format        = "DOCKER"

  cleanup_policy_dry_run = false

  # KEEP wins over DELETE, so this deletes everything but the newest 5.
  cleanup_policies {
    id     = "keep-newest-5"
    action = "KEEP"
    most_recent_versions {
      keep_count = 5
    }
  }
  cleanup_policies {
    id     = "delete-the-rest"
    action = "DELETE"
    condition {
      tag_state = "ANY"
    }
  }

  depends_on = [google_project_service.apis]
}
