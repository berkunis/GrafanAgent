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

# Further modules land in later phases:
#   - cloud_run (per agent + per MCP server)
#   - pubsub (signal-ingest topic + per-agent subscriptions)
#   - cloudsql (pgvector instance for RAG)
#   - secret_manager (Anthropic key, Slack tokens, Customer.io creds, Grafana OTLP token)
