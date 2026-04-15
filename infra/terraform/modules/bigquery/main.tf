###############################################################################
# BigQuery module — demo dataset, three tables, and one golden signal row.
#
# Tables are intentionally tiny so the demo runs against free-tier BQ. The
# `signals` row inserted by `google_bigquery_job.seed_golden_signal` is the
# fixture every demo path keys off of (signal id `golden-aha-001`).
###############################################################################

resource "google_bigquery_dataset" "demo" {
  dataset_id    = var.dataset_id
  friendly_name = "GrafanAgent demo dataset"
  description   = "Synthetic users, usage events, and signals for the GrafanAgent demo."
  location      = var.location
  labels        = var.labels

  # Free-tier guardrail: tables auto-expire after 90 days unless overridden.
  default_table_expiration_ms = var.default_table_expiration_ms
}

resource "google_bigquery_table" "users" {
  dataset_id          = google_bigquery_dataset.demo.dataset_id
  table_id            = "users"
  deletion_protection = false
  description         = "Synthetic user accounts."

  schema = jsonencode([
    { name = "user_id",          type = "STRING",    mode = "REQUIRED" },
    { name = "email",            type = "STRING",    mode = "NULLABLE", description = "PII — redacted by the BQ MCP." },
    { name = "plan",             type = "STRING",    mode = "REQUIRED" },
    { name = "company",          type = "STRING",    mode = "NULLABLE" },
    { name = "country",          type = "STRING",    mode = "NULLABLE" },
    { name = "signed_up_at",     type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "first_active_at",  type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "lifecycle_stage",  type = "STRING",    mode = "REQUIRED" },
  ])
}

resource "google_bigquery_table" "usage_events" {
  dataset_id          = google_bigquery_dataset.demo.dataset_id
  table_id            = "usage_events"
  deletion_protection = false
  description         = "Per-event product usage stream."

  time_partitioning {
    type  = "DAY"
    field = "occurred_at"
  }

  schema = jsonencode([
    { name = "event_id",     type = "STRING",    mode = "REQUIRED" },
    { name = "user_id",      type = "STRING",    mode = "REQUIRED" },
    { name = "event_type",   type = "STRING",    mode = "REQUIRED" },
    { name = "value",        type = "FLOAT",     mode = "NULLABLE" },
    { name = "occurred_at",  type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "context",      type = "JSON",      mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "signals" {
  dataset_id          = google_bigquery_dataset.demo.dataset_id
  table_id            = "signals"
  deletion_protection = false
  description         = "Marketing-ops signals the router consumes."

  time_partitioning {
    type  = "DAY"
    field = "occurred_at"
  }

  schema = jsonencode([
    { name = "id",            type = "STRING",    mode = "REQUIRED", description = "Stable signal id; idempotency key." },
    { name = "type",          type = "STRING",    mode = "REQUIRED" },
    { name = "source",        type = "STRING",    mode = "REQUIRED" },
    { name = "user_id",       type = "STRING",    mode = "NULLABLE" },
    { name = "occurred_at",   type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "payload",       type = "JSON",      mode = "NULLABLE" },
    { name = "metadata",      type = "JSON",      mode = "NULLABLE" },
  ])
}

###############################################################################
# Seed: one golden signal + one user + a small usage_events tail. The agent
# demos hit signal id `golden-aha-001`.
###############################################################################

resource "google_bigquery_job" "seed_golden_signal" {
  job_id   = "grafanagent-seed-${replace(timestamp(), ":", "-")}"
  location = var.location

  query {
    use_legacy_sql = false
    query = templatefile("${path.module}/sql/seed.sql", {
      dataset = google_bigquery_dataset.demo.dataset_id
      project = var.project_id
    })
  }

  depends_on = [
    google_bigquery_table.users,
    google_bigquery_table.usage_events,
    google_bigquery_table.signals,
  ]

  lifecycle {
    # The job_id includes a timestamp, so terraform sees a "changed" job each apply
    # but the underlying data is idempotent (DELETE+INSERT in seed.sql).
    ignore_changes = [job_id]
  }
}
