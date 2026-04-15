provider "google" {
  project = var.project_id
  region  = var.region
}

# Modules will be wired in subsequent plans:
#   - cloud_run (per agent + per MCP server)
#   - pubsub (signal-ingest topic + per-agent subscriptions)
#   - cloudsql (pgvector instance for retrieval)
#   - secret_manager (Anthropic key, Slack tokens, Customer.io creds, Grafana OTLP token)
#
# Kept empty intentionally so `terraform init` succeeds with no resources.
