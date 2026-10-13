# Firebase Hosting is the front door: it serves prj-app-workboard.web.app now,
# and the custom domain later, passing every request on to Cloud Run. It only
# ever forwards the cookie named __session; see docs/deployment.md.
resource "google_firebase_project" "default" {
  provider = google-beta

  depends_on = [google_project_service.apis]
}

resource "google_firebase_hosting_site" "default" {
  provider = google-beta
  site_id  = local.project

  # The project's default site can't be deleted, only forgotten.
  deletion_policy = "ABANDON"

  depends_on = [google_firebase_project.default]
}

# No files are uploaded, so every path falls through to the rewrite. Firebase's
# CDN caches only responses marked public, which no page is.
resource "google_firebase_hosting_version" "default" {
  provider = google-beta
  site_id  = google_firebase_hosting_site.default.site_id

  config {
    rewrites {
      glob = "**"
      run {
        service_id = google_cloud_run_v2_service.workboard.name
        region     = local.region
      }
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "google_firebase_hosting_release" "default" {
  provider     = google-beta
  site_id      = google_firebase_hosting_site.default.site_id
  version_name = google_firebase_hosting_version.default.name
  message      = "Every path to Cloud Run"
}
