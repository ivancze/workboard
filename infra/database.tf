resource "google_sql_database_instance" "main" {
  name             = "workboard"
  database_version = "POSTGRES_17"
  region           = local.region

  # Terraform's own protection; the settings below hold Cloud SQL's.
  deletion_protection = true

  settings {
    edition                     = "ENTERPRISE"
    tier                        = "db-f1-micro"
    disk_type                   = "PD_SSD"
    disk_size                   = 10
    deletion_protection_enabled = true

    ip_configuration {
      ipv4_enabled    = false # no public IP
      private_network = google_compute_network.main.id
      ssl_mode        = "ENCRYPTED_ONLY"
    }

    backup_configuration {
      enabled                        = true
      start_time                     = "18:00" # UTC, so 02:00 in Malaysia
      point_in_time_recovery_enabled = false
      backup_retention_settings {
        retained_backups = 7
      }
    }

    # Sunday 03:00 in Malaysia, which is Saturday 19:00 UTC.
    maintenance_window {
      day  = 6
      hour = 19
    }
  }

  # A destroy deletes the database before reaching the instance's protection,
  # so this one refuses at plan time instead.
  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_service_networking_connection.google_services]
}

resource "google_sql_database" "workboard" {
  name     = "workboard"
  instance = google_sql_database_instance.main.name

  lifecycle {
    prevent_destroy = true
  }
}

# The password exists only while Terraform runs: write-only arguments send it
# to Cloud SQL and Secret Manager without keeping it in state. Both are sent it
# only when this number changes, so bump it to change the password, or if the
# two ever disagree.
locals {
  db_password_version = 1
}

ephemeral "random_password" "db" {
  length  = 32
  special = false # it goes into a URL
}

resource "google_sql_user" "workboard" {
  name                = "workboard"
  instance            = google_sql_database_instance.main.name
  password_wo         = ephemeral.random_password.db.result
  password_wo_version = local.db_password_version
}
