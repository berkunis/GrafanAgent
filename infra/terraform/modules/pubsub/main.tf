###############################################################################
# Pub/Sub — signal ingestion topic + router push subscription.
#
# Two event paths into the router are supported:
#   1. Direct HTTP: `grafanagent trigger` or curl against /signal — local dev,
#      demos, CLI replays. No Pub/Sub involvement.
#   2. Pub/Sub push: production signal producers (BQ change streams, webhook
#      adapters) publish to the topic; Pub/Sub POSTs each message to the
#      router's /signal endpoint with OIDC auth.
#
# Both paths land at the same handler; the router does not care.
###############################################################################

resource "google_pubsub_topic" "signals" {
  project = var.project_id
  name    = var.topic_name
  labels  = var.labels

  message_retention_duration = "604800s" # 7 days — match Cloud Run request retry budget
}

resource "google_pubsub_subscription" "router_push" {
  project = var.project_id
  name    = "${var.topic_name}-router-push"
  topic   = google_pubsub_topic.signals.name
  labels  = var.labels

  ack_deadline_seconds       = 60
  message_retention_duration = "604800s"
  enable_message_ordering    = false

  # Retry a failed push for up to 10 minutes with exponential backoff — the
  # router's tenacity retries handle transient Anthropic / MCP blips on top.
  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  push_config {
    push_endpoint = "${var.router_service_url}/signal"

    oidc_token {
      service_account_email = var.invoker_service_account
      audience              = var.router_service_url
    }

    attributes = {
      x-goog-version = "v1"
    }
  }

  expiration_policy {
    ttl = "" # never expire
  }

  # Dead-letter to a side topic after 10 failed delivery attempts so bad
  # payloads don't wedge the main subscription.
  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letters.id
    max_delivery_attempts = 10
  }
}

resource "google_pubsub_topic" "dead_letters" {
  project = var.project_id
  name    = "${var.topic_name}-dlq"
  labels  = var.labels
}

resource "google_pubsub_subscription" "dead_letter_audit" {
  project = var.project_id
  name    = "${var.topic_name}-dlq-audit"
  topic   = google_pubsub_topic.dead_letters.name
  labels  = var.labels
  # Retain long enough for a human to triage.
  message_retention_duration = "2592000s" # 30 days
  ack_deadline_seconds       = 60
}
