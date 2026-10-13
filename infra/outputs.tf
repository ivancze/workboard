output "service_url" {
  value = "https://${local.run_hostname}"
}

output "image_repository" {
  value = "${local.region}-docker.pkg.dev/${local.project}/${google_artifact_registry_repository.images.repository_id}/workboard"
}
