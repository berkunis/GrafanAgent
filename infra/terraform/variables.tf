variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run, Pub/Sub, Cloud SQL."
  type        = string
  default     = "us-central1"
}

variable "image_tag" {
  description = "Image tag every Cloud Run service pulls. Typically the short git SHA produced by `make deploy`."
  type        = string
  default     = "latest"
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

variable "enable_cloudsql" {
  description = "Create the Cloud SQL pgvector instance."
  type        = bool
  default     = false
}

variable "enable_deploy" {
  description = "Create Artifact Registry + Secret Manager + Cloud Run + Pub/Sub resources. Off by default so the repo ships without hard requirements on those APIs; flip to true in your tfvars when Phase 8 credentials are wired."
  type        = bool
  default     = false
}

variable "attribution_post_channel" {
  description = "Slack channel id the attribution agent posts RevOps reports to. Empty string disables posting."
  type        = string
  default     = ""
}

variable "slack_approval_channel" {
  description = "Slack channel id the HITL approval cards post to."
  type        = string
  default     = ""
}

variable "otel_exporter_otlp_endpoint" {
  description = "Grafana Cloud OTLP gateway, e.g. https://otlp-gateway-prod-us-east-0.grafana.net/otlp"
  type        = string
  default     = ""
}
