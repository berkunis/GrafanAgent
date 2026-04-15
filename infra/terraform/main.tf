provider "google" {
  project = var.project_id
  region  = var.region
}

module "bigquery" {
  source     = "./modules/bigquery"
  project_id = var.project_id
  dataset_id = var.bq_dataset_id
  location   = var.bq_location
}

output "bq_dataset_short_id" {
  value       = module.bigquery.dataset_short_id
  description = "Short dataset id — pass to BQ_DATASET env on agents + MCP servers."
}

output "bq_tables" {
  value       = module.bigquery.tables
  description = "Fully qualified BQ tables the agents can reference."
}

module "cloudsql" {
  count      = var.enable_cloudsql ? 1 : 0
  source     = "./modules/cloudsql"
  project_id = var.project_id
  region     = var.region
}

output "cloudsql_dsn_secret_id" {
  value       = var.enable_cloudsql ? module.cloudsql[0].dsn_secret_id : null
  description = "Secret Manager id holding the pgvector DSN; null when CloudSQL is disabled."
}

# Further modules land in later phases:
#   - cloud_run (per agent + per MCP server)
#   - pubsub (signal-ingest topic + per-agent subscriptions)
#   - secret_manager (Anthropic key, Slack tokens, Customer.io creds, Grafana OTLP token)
