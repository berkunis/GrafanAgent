###############################################################################
# Generic Cloud Run service — instantiated once per agent + per MCP server +
# for the TS slack-approver. The root main.tf stitches these together; this
# module only knows about a single service.
###############################################################################

resource "google_cloud_run_v2_service" "svc" {
  project  = var.project_id
  location = var.region
  name     = var.service_name
  ingress  = var.ingress

  labels = merge(var.labels, { service = var.service_name })

  template {
    service_account = var.service_account_email
    timeout         = "${var.timeout_seconds}s"

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = var.image

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      # Plain env vars.
      dynamic "env" {
        for_each = var.env
        content {
          name  = env.key
          value = env.value
        }
      }

      # Secret-backed env vars (mounted as "latest" version of each secret).
      dynamic "env" {
        for_each = var.env_from_secret
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }

      ports {
        container_port = 8080
      }

      startup_probe {
        http_get {
          path = "/healthz"
        }
        initial_delay_seconds = 2
        period_seconds        = 5
        timeout_seconds       = 2
        failure_threshold     = 10
      }
    }

    max_instance_request_concurrency = var.concurrency

    labels = merge(var.labels, { service = var.service_name })
  }

  # Re-deploys should shift traffic atomically. We don't use revisions for
  # canary in the demo — simplest deploy is the right one.
  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  lifecycle {
    # Image tag changes trigger replace; no accidental drift from
    # `gcloud run deploy` re-uploads.
    ignore_changes = []
  }
}

resource "google_cloud_run_v2_service_iam_member" "invoker" {
  for_each = toset(var.invoker_service_accounts)
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.svc.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${each.value}"
}

resource "google_cloud_run_v2_service_iam_member" "allUsers" {
  count    = var.allow_unauthenticated ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.svc.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
