variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "dataset_id" {
  description = "BigQuery dataset id."
  type        = string
  default     = "grafanagent_demo"
}

variable "location" {
  description = "BigQuery dataset location."
  type        = string
  default     = "US"
}

variable "default_table_expiration_ms" {
  description = "Default table expiration; protects free-tier accounts from runaway storage."
  type        = number
  default     = 7776000000 # 90 days
}

variable "labels" {
  description = "Resource labels."
  type        = map(string)
  default = {
    project = "grafanagent"
    env     = "demo"
  }
}
