output "instance_name" {
  value = google_sql_database_instance.pgvector.name
}

output "database_name" {
  value = google_sql_database.db.name
}

output "dsn_secret_id" {
  value       = google_secret_manager_secret.pgvector_dsn.secret_id
  description = "Secret Manager id holding the DSN; Cloud Run mounts this."
}

output "connection_name" {
  value       = google_sql_database_instance.pgvector.connection_name
  description = "Cloud SQL connection name for the auth proxy."
}
