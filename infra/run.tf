data "google_project" "this" {}

locals {
  # Cloud Run's address for a service is fixed by its name, project and region.
  run_hostname = "workboard-${data.google_project.this.number}.${local.region}.run.app"
  web_hostname = "${local.project}.web.app"

  # Terraform creates the service and jobs with Google's sample image. Every
  # real image after that is deployed outside Terraform, which ignores it.
  placeholder_image = "us-docker.pkg.dev/cloudrun/container/hello"
}

# Runs the service and both jobs. It can read the four secrets and nothing
# else; the database is reached over the network with a password, which needs
# no Cloud SQL role.
resource "google_service_account" "runtime" {
  account_id   = "workboard-runtime"
  display_name = "Workboard: the service and its jobs"
}

resource "google_secret_manager_secret_iam_member" "runtime" {
  for_each = google_secret_manager_secret.app

  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.runtime.member
}

resource "google_cloud_run_v2_service" "workboard" {
  name     = "workboard"
  location = local.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  # A public site: anyone may send a request, and the application decides who
  # is signed in.
  invoker_iam_disabled = true

  template {
    service_account = google_service_account.runtime.email

    # gunicorn runs two sync workers, each handling one request at a time.
    max_instance_request_concurrency = 2

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    vpc_access {
      network_interfaces {
        network    = google_compute_network.main.id
        subnetwork = google_compute_subnetwork.singapore.id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = local.placeholder_image

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        # CPU only while handling a request, so an idle instance costs
        # nothing. It's the default only when no limits are set.
        cpu_idle = true
      }

      # Not HTTP: a probe arrives without the public hostname, which
      # ALLOWED_HOSTS turns away. Checked every second: at the default 10, a
      # first check that runs before gunicorn listens (about 1.5 s) leaves a
      # cold request waiting ~10 s more. 30 attempts still allow 30 s to start.
      startup_probe {
        tcp_socket {}
        period_seconds    = 1
        timeout_seconds   = 1
        failure_threshold = 30
      }

      env {
        name  = "HTTPS_ONLY"
        value = "True"
      }
      env {
        name  = "PUBLIC_HOSTNAMES"
        value = "${local.run_hostname},${local.web_hostname}"
      }
      # The only cookie Firebase Hosting forwards.
      env {
        name  = "SESSION_COOKIE_NAME"
        value = "__session"
      }
      env {
        name  = "USE_X_FORWARDED_HOST"
        value = "True"
      }
      dynamic "env" {
        for_each = google_secret_manager_secret.app
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value.secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  # The pipeline owns which image runs and which revision takes traffic. An
  # apply after a rollback must not send traffic back to the broken revision.
  lifecycle {
    ignore_changes = [template[0].containers[0].image, traffic, client, client_version]
  }

  depends_on = [google_secret_manager_secret_iam_member.runtime]
}

# Both jobs run manage.py with the service's network and identity, and only the
# two secrets settings can't start without.
locals {
  jobs = {
    # Run by the pipeline on each new image, before the service gets it.
    "workboard-migrate" = ["migrate", "--noinput"]
    # Any command, passed with --args when executed. Lists migrations by default.
    "workboard-manage" = ["showmigrations"]
  }
}

resource "google_cloud_run_v2_job" "jobs" {
  for_each = local.jobs

  name     = each.key
  location = local.region

  template {
    template {
      service_account = google_service_account.runtime.email
      max_retries     = 0
      timeout         = "600s"

      vpc_access {
        network_interfaces {
          network    = google_compute_network.main.id
          subnetwork = google_compute_subnetwork.singapore.id
        }
        egress = "PRIVATE_RANGES_ONLY"
      }

      containers {
        image   = local.placeholder_image
        command = ["python", "manage.py"]
        args    = each.value

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }

        dynamic "env" {
          for_each = toset(["DATABASE_URL", "SECRET_KEY"])
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = google_secret_manager_secret.app[env.key].secret_id
                version = "latest"
              }
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }

  depends_on = [google_secret_manager_secret_iam_member.runtime]
}
