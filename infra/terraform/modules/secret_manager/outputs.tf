output "secrets" {
  description = "Map of secret name → Secret Manager resource id. Mount these into Cloud Run."
  value       = { for name, s in google_secret_manager_secret.secret : name => s.id }
}
