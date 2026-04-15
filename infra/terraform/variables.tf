variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run, Pub/Sub, Cloud SQL."
  type        = string
  default     = "us-central1"
}

variable "image_repo" {
  description = "Artifact Registry repo for service images."
  type        = string
  default     = "grafanagent"
}

variable "agent_services" {
  description = "Agent services deployed to Cloud Run."
  type        = list(string)
  default     = ["router", "lifecycle", "lead-scoring", "attribution"]
}

variable "mcp_services" {
  description = "MCP servers deployed to Cloud Run."
  type        = list(string)
  default     = ["bigquery", "customer-io", "slack"]
}

variable "bq_dataset_id" {
  description = "BigQuery dataset id for the demo."
  type        = string
  default     = "grafanagent_demo"
}

variable "bq_location" {
  description = "BigQuery dataset location."
  type        = string
  default     = "US"
}
