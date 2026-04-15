variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region for the Artifact Registry repo."
  type        = string
  default     = "us-central1"
}

variable "repo_id" {
  description = "Artifact Registry Docker repo that holds every GrafanAgent image."
  type        = string
  default     = "grafanagent"
}

variable "labels" {
  description = "Resource labels."
  type        = map(string)
  default = {
    project = "grafanagent"
  }
}
