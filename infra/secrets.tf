# The application's four secrets, held in Singapore. Terraform creates the
# containers; the operator adds every value except DATABASE_URL's.
resource "google_secret_manager_secret" "app" {
  for_each = toset([
    "DATABASE_URL",
    "SECRET_KEY",
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
  ])

  secret_id = each.key

  replication {
    user_managed {
      replicas {
        location = local.region
      }
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "database_url" {
  secret                 = google_secret_manager_secret.app["DATABASE_URL"].id
  secret_data_wo_version = local.db_password_version
  secret_data_wo = format(
    "postgres://%s:%s@%s:5432/%s?sslmode=require",
    google_sql_user.workboard.name,
    ephemeral.random_password.db.result,
    google_sql_database_instance.main.private_ip_address,
    google_sql_database.workboard.name,
  )
}
