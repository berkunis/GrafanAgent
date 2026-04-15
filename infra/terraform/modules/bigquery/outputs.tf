output "dataset_id" {
  description = "Fully qualified dataset id (project:dataset)."
  value       = "${var.project_id}:${google_bigquery_dataset.demo.dataset_id}"
}

output "dataset_short_id" {
  description = "Short dataset id (no project prefix)."
  value       = google_bigquery_dataset.demo.dataset_id
}

output "tables" {
  description = "Table refs as 'project.dataset.table'."
  value = {
    users        = "${var.project_id}.${google_bigquery_dataset.demo.dataset_id}.${google_bigquery_table.users.table_id}"
    usage_events = "${var.project_id}.${google_bigquery_dataset.demo.dataset_id}.${google_bigquery_table.usage_events.table_id}"
    signals      = "${var.project_id}.${google_bigquery_dataset.demo.dataset_id}.${google_bigquery_table.signals.table_id}"
  }
}
