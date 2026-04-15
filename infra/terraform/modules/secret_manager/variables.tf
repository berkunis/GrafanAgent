variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "labels" {
  description = "Resource labels applied to every secret."
  type        = map(string)
  default = {
    project = "grafanagent"
  }
}

# Runtime secrets. We declare the secret *shells* here; the actual version
# values are written out-of-band with `gcloud secrets versions add`:
#
#   gcloud secrets versions add anthropic-api-key --data-file=/path/to/key.txt
#
# Keeping the values out of Terraform state means we can rotate without a
# `terraform apply`, and the state file never contains a key.

variable "secret_names" {
  description = "Every secret the deployed Cloud Run services expect to mount."
  type        = list(string)
  default = [
    "anthropic-api-key",
    "otel-exporter-otlp-headers",
    "slack-bot-token",
    "slack-signing-secret",
    "customerio-site-id",
    "customerio-api-key",
  ]
}

variable "accessors" {
  description = "Service account emails that get roles/secretmanager.secretAccessor on every secret."
  type        = list(string)
  default     = []
}
