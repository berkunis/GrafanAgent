variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region to deploy the service to."
  type        = string
  default     = "us-central1"
}

variable "service_name" {
  description = "Cloud Run service name (must be unique in the region)."
  type        = string
}

variable "image" {
  description = "Fully-qualified container image, e.g. us-central1-docker.pkg.dev/project/grafanagent/router:sha-abc."
  type        = string
}

variable "service_account_email" {
  description = "Runtime service account the container runs as. Grant Cloud Run / Secret Manager / BQ roles to this SA upstream."
  type        = string
}

variable "env" {
  description = "Plain environment variables. Do NOT put secrets here — use env_from_secret."
  type        = map(string)
  default     = {}
}

variable "env_from_secret" {
  description = "Map of env var name → Secret Manager secret id (short form, just the secret name)."
  type        = map(string)
  default     = {}
}

variable "min_instances" {
  description = "Minimum Cloud Run instances. 0 = scale-to-zero with cold starts."
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "Upper bound on instances to cap the blast radius of a retry storm."
  type        = number
  default     = 5
}

variable "concurrency" {
  description = "Max concurrent requests per instance."
  type        = number
  default     = 80
}

variable "cpu" {
  description = "CPU limit (e.g. '1', '2', '4')."
  type        = string
  default     = "1"
}

variable "memory" {
  description = "Memory limit (e.g. '512Mi', '1Gi')."
  type        = string
  default     = "512Mi"
}

variable "timeout_seconds" {
  description = "Per-request timeout in seconds."
  type        = number
  default     = 300
}

variable "ingress" {
  description = "INGRESS_TRAFFIC_ALL, INGRESS_TRAFFIC_INTERNAL_ONLY, or INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER."
  type        = string
  default     = "INGRESS_TRAFFIC_INTERNAL_ONLY"
}

variable "allow_unauthenticated" {
  description = "If true, anonymous callers can reach the service. Leave false for everything except a gateway."
  type        = bool
  default     = false
}

variable "invoker_service_accounts" {
  description = "Service account emails that get roles/run.invoker. Empty means no cross-service invocations."
  type        = list(string)
  default     = []
}

variable "labels" {
  description = "Resource labels merged with per-service defaults."
  type        = map(string)
  default = {
    project = "grafanagent"
  }
}
