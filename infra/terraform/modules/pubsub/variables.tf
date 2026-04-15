variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "topic_name" {
  description = "Pub/Sub topic name for signal ingestion."
  type        = string
  default     = "grafanagent-signals"
}

variable "router_service_url" {
  description = "Cloud Run URL that receives the Pub/Sub push subscription."
  type        = string
}

variable "invoker_service_account" {
  description = "Service account email the subscription uses to invoke Cloud Run."
  type        = string
}

variable "labels" {
  description = "Resource labels."
  type        = map(string)
  default = {
    project = "grafanagent"
  }
}
