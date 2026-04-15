output "repo_id" {
  value = google_artifact_registry_repository.grafanagent.repository_id
}

output "repo_url" {
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.grafanagent.repository_id}"
  description = "Base Docker URL. Append /<service>:<tag> to get the full image ref."
}
