provider "google" {
  project = var.project_id
  region  = var.region
}

###############################################################################
# BigQuery (always on)
###############################################################################

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

###############################################################################
# Cloud SQL pgvector (enable_cloudsql)
###############################################################################

module "cloudsql" {
  count      = var.enable_cloudsql ? 1 : 0
  source     = "./modules/cloudsql"
  project_id = var.project_id
  region     = var.region
}

output "cloudsql_dsn_secret_id" {
  value       = var.enable_cloudsql ? module.cloudsql[0].dsn_secret_id : null
  description = "Secret Manager id holding the pgvector DSN; null when CloudSQL is disabled."
}

###############################################################################
# Deploy stack (enable_deploy) — Artifact Registry, Secret Manager, Cloud Run,
# Pub/Sub. Gated so the repo ships without requiring those APIs enabled; flip
# `enable_deploy = true` in a tfvars file once credentials are wired.
###############################################################################

locals {
  deploy_enabled = var.enable_deploy

  # Runtime service account. Separate from the deploy identity so rotation
  # doesn't take the running services down.
  runtime_sa_account_id = "grafanagent-runtime"

  # Image base URL only resolvable when the Artifact Registry module runs.
  image_repo_url = local.deploy_enabled ? module.artifact_registry[0].repo_url : ""

  # Every Cloud Run service image follows the same naming convention.
  # TS slack-approver uses the "-ts" suffix so its Dockerfile.node can be
  # built + pushed separately from the Python shared Dockerfile.
  agent_services = {
    router        = "agents.router.main"
    lifecycle     = "agents.lifecycle.main"
    lead-scoring  = "agents.lead_scoring.main"
    attribution   = "agents.attribution.main"
  }
  mcp_services = {
    bigquery    = "mcp_servers.bigquery.server"
    customer-io = "mcp_servers.customer_io.server"
    slack       = "mcp_servers.slack.server"
  }

  common_env = {
    OTEL_SERVICE_NAMESPACE      = "grafanagent"
    OTEL_EXPORTER_OTLP_ENDPOINT = var.otel_exporter_otlp_endpoint
    DEPLOY_ENV                  = "prod"
    BQ_DATASET                  = var.bq_dataset_id
    SLACK_APPROVAL_CHANNEL      = var.slack_approval_channel
    ATTRIBUTION_POST_CHANNEL    = var.attribution_post_channel
  }

  common_secret_env = {
    ANTHROPIC_API_KEY              = "anthropic-api-key"
    OTEL_EXPORTER_OTLP_HEADERS     = "otel-exporter-otlp-headers"
  }

  slack_secret_env = {
    SLACK_BOT_TOKEN      = "slack-bot-token"
    SLACK_SIGNING_SECRET = "slack-signing-secret"
  }

  customerio_secret_env = {
    CUSTOMERIO_SITE_ID = "customerio-site-id"
    CUSTOMERIO_API_KEY = "customerio-api-key"
  }
}

resource "google_service_account" "runtime" {
  count        = local.deploy_enabled ? 1 : 0
  project      = var.project_id
  account_id   = local.runtime_sa_account_id
  display_name = "GrafanAgent runtime service account"
}

# Minimal IAM for the runtime SA. BigQuery read-only gives the BQ MCP what it
# needs; everything else goes through Secret Manager + Cloud Run invoker.
resource "google_project_iam_member" "runtime_bq" {
  count   = local.deploy_enabled ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.runtime[0].email}"
}

resource "google_project_iam_member" "runtime_bq_jobs" {
  count   = local.deploy_enabled ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.runtime[0].email}"
}

resource "google_project_iam_member" "runtime_vertex" {
  count   = local.deploy_enabled ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.runtime[0].email}"
}

module "artifact_registry" {
  count      = local.deploy_enabled ? 1 : 0
  source     = "./modules/artifact_registry"
  project_id = var.project_id
  region     = var.region
}

module "secret_manager" {
  count      = local.deploy_enabled ? 1 : 0
  source     = "./modules/secret_manager"
  project_id = var.project_id
  accessors  = [google_service_account.runtime[0].email]
}

# ---- Python agents ---------------------------------------------------------

module "agent_router" {
  count   = local.deploy_enabled ? 1 : 0
  source  = "./modules/cloud_run_service"
  project_id            = var.project_id
  region                = var.region
  service_name          = "router"
  image                 = "${local.image_repo_url}/router:${var.image_tag}"
  service_account_email = google_service_account.runtime[0].email
  ingress               = "INGRESS_TRAFFIC_ALL"
  env                   = local.common_env
  env_from_secret       = local.common_secret_env
  min_instances         = 0
  max_instances         = 5
  depends_on            = [module.artifact_registry, module.secret_manager]
}

module "agent_lifecycle" {
  count   = local.deploy_enabled ? 1 : 0
  source  = "./modules/cloud_run_service"
  project_id               = var.project_id
  region                   = var.region
  service_name             = "lifecycle"
  image                    = "${local.image_repo_url}/lifecycle:${var.image_tag}"
  service_account_email    = google_service_account.runtime[0].email
  env                      = local.common_env
  env_from_secret          = merge(local.common_secret_env, local.customerio_secret_env)
  invoker_service_accounts = [google_service_account.runtime[0].email]
  depends_on               = [module.artifact_registry, module.secret_manager]
}

module "agent_lead_scoring" {
  count   = local.deploy_enabled ? 1 : 0
  source  = "./modules/cloud_run_service"
  project_id               = var.project_id
  region                   = var.region
  service_name             = "lead-scoring"
  image                    = "${local.image_repo_url}/lead-scoring:${var.image_tag}"
  service_account_email    = google_service_account.runtime[0].email
  env                      = local.common_env
  env_from_secret          = merge(local.common_secret_env, local.customerio_secret_env)
  invoker_service_accounts = [google_service_account.runtime[0].email]
  depends_on               = [module.artifact_registry, module.secret_manager]
}

module "agent_attribution" {
  count   = local.deploy_enabled ? 1 : 0
  source  = "./modules/cloud_run_service"
  project_id               = var.project_id
  region                   = var.region
  service_name             = "attribution"
  image                    = "${local.image_repo_url}/attribution:${var.image_tag}"
  service_account_email    = google_service_account.runtime[0].email
  env                      = local.common_env
  env_from_secret          = local.common_secret_env
  invoker_service_accounts = [google_service_account.runtime[0].email]
  depends_on               = [module.artifact_registry, module.secret_manager]
}

# ---- MCP servers -----------------------------------------------------------

module "mcp_bigquery" {
  count   = local.deploy_enabled ? 1 : 0
  source  = "./modules/cloud_run_service"
  project_id               = var.project_id
  region                   = var.region
  service_name             = "mcp-bigquery"
  image                    = "${local.image_repo_url}/mcp-bigquery:${var.image_tag}"
  service_account_email    = google_service_account.runtime[0].email
  env                      = local.common_env
  env_from_secret          = local.common_secret_env
  invoker_service_accounts = [google_service_account.runtime[0].email]
  depends_on               = [module.artifact_registry, module.secret_manager]
}

module "mcp_customer_io" {
  count   = local.deploy_enabled ? 1 : 0
  source  = "./modules/cloud_run_service"
  project_id               = var.project_id
  region                   = var.region
  service_name             = "mcp-customer-io"
  image                    = "${local.image_repo_url}/mcp-customer-io:${var.image_tag}"
  service_account_email    = google_service_account.runtime[0].email
  env                      = merge(local.common_env, { CUSTOMERIO_SANDBOX = "1", CUSTOMERIO_ENV = "sandbox" })
  env_from_secret          = merge(local.common_secret_env, local.customerio_secret_env)
  invoker_service_accounts = [google_service_account.runtime[0].email]
  depends_on               = [module.artifact_registry, module.secret_manager]
}

module "mcp_slack" {
  count   = local.deploy_enabled ? 1 : 0
  source  = "./modules/cloud_run_service"
  project_id               = var.project_id
  region                   = var.region
  service_name             = "mcp-slack"
  image                    = "${local.image_repo_url}/mcp-slack:${var.image_tag}"
  service_account_email    = google_service_account.runtime[0].email
  env                      = local.common_env
  env_from_secret          = local.common_secret_env
  invoker_service_accounts = [google_service_account.runtime[0].email]
  depends_on               = [module.artifact_registry, module.secret_manager]
}

# ---- TS Slack Bolt approver ------------------------------------------------

module "slack_approver" {
  count   = local.deploy_enabled ? 1 : 0
  source  = "./modules/cloud_run_service"
  project_id            = var.project_id
  region                = var.region
  service_name          = "slack-approver"
  image                 = "${local.image_repo_url}/slack-approver:${var.image_tag}"
  service_account_email = google_service_account.runtime[0].email
  # Public — Slack Events needs to reach /slack/events. Auth is enforced via
  # the signing-secret header at the app layer.
  ingress               = "INGRESS_TRAFFIC_ALL"
  allow_unauthenticated = true
  env                   = local.common_env
  env_from_secret       = local.slack_secret_env
  depends_on            = [module.artifact_registry, module.secret_manager]
}

# ---- Pub/Sub signal ingest → router ---------------------------------------

module "pubsub" {
  count  = local.deploy_enabled ? 1 : 0
  source = "./modules/pubsub"
  project_id              = var.project_id
  router_service_url      = module.agent_router[0].url
  invoker_service_account = google_service_account.runtime[0].email
  depends_on              = [module.agent_router]
}

###############################################################################
# Outputs for CI / Makefile
###############################################################################

output "image_repo_url" {
  value       = local.deploy_enabled ? module.artifact_registry[0].repo_url : null
  description = "Base Docker registry URL. make docker-push-all resolves images here."
}

output "runtime_service_account" {
  value       = local.deploy_enabled ? google_service_account.runtime[0].email : null
  description = "Runtime SA email; grant additional roles out of band if needed."
}

output "router_url" {
  value       = local.deploy_enabled ? module.agent_router[0].url : null
  description = "Public router URL — curl <url>/signal with a Signal JSON."
}

output "slack_approver_url" {
  value       = local.deploy_enabled ? module.slack_approver[0].url : null
  description = "Slack Events URL — set to <url>/slack/events in the Slack app manifest."
}

output "pubsub_topic" {
  value       = local.deploy_enabled ? module.pubsub[0].topic : null
  description = "Publish Signal JSON messages here for production ingest."
}
