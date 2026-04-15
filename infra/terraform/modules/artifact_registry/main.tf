###############################################################################
# Artifact Registry — one Docker repo holds every GrafanAgent service image.
# Keeping the repo singular (not per-service) means `make docker-push-all`
# loops once and every service resolves the same registry auth.
###############################################################################

resource "google_artifact_registry_repository" "grafanagent" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repo_id
  format        = "DOCKER"
  description   = "GrafanAgent service images (agents + MCP servers + slack-approver)."
  labels        = var.labels

  docker_config {
    immutable_tags = false
  }

  cleanup_policies {
    id     = "keep-recent-30"
    action = "KEEP"
    most_recent_versions {
      keep_count = 30
    }
  }

  cleanup_policies {
    id     = "expire-untagged-7d"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "604800s" # 7 days
    }
  }
}
