output "service_url" {
  value = "https://${local.run_hostname}"
}

output "image_repository" {
  value = "${local.region}-docker.pkg.dev/${local.project}/${google_artifact_registry_repository.images.repository_id}/workboard"
}

output "workload_identity_provider" {
  value = google_iam_workload_identity_pool_provider.github.name
}

output "deployer_service_account" {
  value = google_service_account.deployer.email
}
