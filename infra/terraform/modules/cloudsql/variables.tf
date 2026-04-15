variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region."
  type        = string
  default     = "us-central1"
}

variable "instance_name" {
  description = "Cloud SQL instance name. Keep stable — deletion is destructive."
  type        = string
  default     = "grafanagent-pgvector"
}

variable "database_name" {
  description = "Database the lifecycle agent connects to."
  type        = string
  default     = "grafanagent"
}

variable "tier" {
  description = "Cloud SQL tier. `db-custom-1-3840` = 1 vCPU / 3.75 GB; fine for demo."
  type        = string
  default     = "db-custom-1-3840"
}

variable "deletion_protection" {
  description = "Block `terraform destroy` from removing the instance."
  type        = bool
  default     = true
}

variable "labels" {
  description = "Resource labels."
  type        = map(string)
  default = {
    project = "grafanagent"
    env     = "demo"
  }
}
