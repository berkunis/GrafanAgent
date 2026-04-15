# GrafanAgent Runbook

Operational notes. Sections match the alert `runbook_url` links.

---

## Local dev

```bash
make install
cp .env.example .env           # leave OTEL_EXPORTER_OTLP_ENDPOINT blank for stdout exporter
make smoke                     # each agent / MCP boots, emits a span, exits
pytest -q                      # 104 Python tests
make bolt-test                 # 17 TypeScript tests
python -m scripts.demo_lifecycle  # full end-to-end offline
```

With an `ANTHROPIC_API_KEY` set you can hit real traffic:

```bash
uvicorn agents.router.app:create_app --factory --reload
grafanagent trigger evals/examples/golden-aha-001.json
```

---

## Observability data flow

```
  agents + MCP servers
          │ OTel SDK (traces / logs / metrics)
          ▼
  OTel Collector (optional; infra/otel/collector.yaml)
          │ OTLP
          ▼
  Grafana Cloud
    ├─ Tempo  — spans (every anthropic.* carries gen_ai.prompt + gen_ai.completion events)
    ├─ Loki   — JSON logs via structlog (PII-scrubbed)
    └─ Mimir  — metrics (grafanagent_llm_*, grafanagent_router_rung_total, grafanagent_eval_*)
          │
          ▼
  Dashboard (dashboards/grafanagent.json) + Alerts (dashboards/alerts.json)
```

For local dev leave `OTEL_EXPORTER_OTLP_ENDPOINT` unset; signals go to stdout exporters.

For Grafana Cloud, set:
```
OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-<region>.grafana.net/otlp
OTEL_EXPORTER_OTLP_HEADERS=authorization=Basic <base64(instance_id:token)>
OTEL_SERVICE_NAME=grafanagent
OTEL_RESOURCE_ATTRIBUTES=deployment.environment=prod
```

---

## Dashboard navigation

Import `dashboards/grafanagent.json` into Grafana Cloud. Panels:

| Row | Panel | Metric / datasource |
|---|---|---|
| Cost | Spend last 1h, cost-rate by bucket | `grafanagent_llm_cost_usd_total` |
| Cost | Tokens/sec, cost by model/agent | `grafanagent_llm_tokens_total` |
| Cost | Top-10 most expensive signals | `grafanagent_signal_cost_usd_total` |
| Latency | p50/p95/p99 by agent | `grafanagent_llm_latency_seconds_bucket` |
| Latency | Success rate, error rate | `grafanagent_llm_calls_total{outcome}` |
| Router | Fallback rung usage + share | `grafanagent_router_rung_total{rung}` |
| Eval | Pass rate gauge, judge score, per-skill bar | `grafanagent_eval_*` |
| Traces | Last-hour traces in namespace | Tempo via `service.namespace = "grafanagent"` |

Every `anthropic.*` span in Tempo carries `gen_ai.prompt` + `gen_ai.completion` events — click a span to see exact prompt sent + response received + token counts + USD cost.

---

## Alert runbooks

### eval-regression

**Alert:** golden-set pass rate < 0.85 sustained for 15 minutes.

1. Check the nightly workflow run at Actions → `Eval (nightly LLM judge)`.
2. Diff prompts in the last 24h of merged PRs. Most regressions come from:
   - A system prompt change that moved skill boundaries.
   - A new signal type added without a rule-table entry.
3. If a PR caused it, revert or add a regression case to `evals/golden_set.jsonl`.
4. Verify locally: `grafanagent eval --mode llm --verbose`.

### cost-spike

**Alert:** >$5/hour LLM spend for 10+ minutes.

1. Dashboard → Cost row. Which model + agent dominates?
2. If `sonnet` on `router-eval` spiked, the nightly eval is likely running in a loop — check workflow run count.
3. If `claude-opus-4-6` shows up anywhere unexpected, the model tier config is wrong.
4. Check `grafanagent_router_rung_total` — stuck rung can loop calls.
5. Kill switch: revoke the Anthropic key from Secret Manager to stop the bleed.

### latency

**Alert:** LLM p95 latency > 5s sustained for 5m.

1. Check Anthropic status page first.
2. Dashboard → Latency panel, filter by agent/model.
3. If only `lifecycle` is slow, the synthesis prompt may have grown — check recent RAG corpus changes.
4. If all agents are slow, it's probably upstream; wait it out + document any SLO breach.

### llm-errors

**Alert:** >5% of LLM calls errored in 10 minutes.

1. Check the Tempo trace of one failed span — the exception is recorded as a `gen_ai.*` span event.
2. Common causes: revoked key (401), quota exceeded (429), Anthropic outage (5xx).
3. Tenacity retries handle 3 attempts with exponential backoff; sustained errors mean the retry budget is exhausted.

### hitl-escalation-spike

**Alert:** >20% of signals routed to HITL in 15 minutes.

1. Likely cause: an unknown signal type started firing.
2. Dashboard → Router fallback chain → "Rung share" panel.
3. Check `grafanagent list signals` — if the new signal type is legitimate, add it to `agents/router/rules.py` (and the golden set).

---

## Deploy

### One-time GCP bootstrap

Enable every API the stack needs, in one shot:

```bash
export GCP_PROJECT_ID=your-project-id
export GCP_REGION=us-central1

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  pubsub.googleapis.com \
  bigquery.googleapis.com \
  sqladmin.googleapis.com \
  aiplatform.googleapis.com \
  servicenetworking.googleapis.com \
  --project "$GCP_PROJECT_ID"

make auth   # ADC login + docker registry auth
```

### One-time secret population

Secret shells are created by Terraform; the values go in out-of-band so
nothing sensitive ever lives in state:

```bash
for secret in anthropic-api-key otel-exporter-otlp-headers \
              slack-bot-token slack-signing-secret \
              customerio-site-id customerio-api-key; do
  read -r -p "Paste value for $secret: " value
  printf '%s' "$value" | \
    gcloud secrets versions add "$secret" --data-file=- --project "$GCP_PROJECT_ID"
done
```

Rotate any secret later by running that same `versions add` — no `terraform apply` needed.

### First-time deploy

```bash
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars
# Edit terraform.tfvars: flip enable_cloudsql=true, enable_deploy=true, fill
# slack_approval_channel / attribution_post_channel / otel_exporter_otlp_endpoint.

make tf-init

# Build, push, and roll every service in one command.
make deploy

# Idempotent BQ seed + pgvector corpus ingest against the deployed DSN.
make seed

# Smoke the deployed router end-to-end.
make smoke-remote
```

`make deploy` uses the short git SHA as the image tag by default, so each
deploy is an atomic revision shift — the `TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST`
config in the Cloud Run module does the cutover.

### Redeploy one service

```bash
IMAGE_TAG=$(git rev-parse --short HEAD)
REPO="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/grafanagent"
docker build --platform linux/amd64 \
  --build-arg SERVICE_MODULE=agents.router.main \
  -t "$REPO/router:$IMAGE_TAG" .
docker push "$REPO/router:$IMAGE_TAG"
terraform -chdir=infra/terraform apply \
  -target=module.agent_router \
  -var "image_tag=$IMAGE_TAG" \
  -var "enable_deploy=true" \
  -auto-approve
```

### Rollback

```bash
# image_tag is the one knob that changes; point it at a known-good SHA.
terraform -chdir=infra/terraform apply \
  -var "image_tag=sha-lastgood" \
  -var "enable_deploy=true" \
  -auto-approve
```

### Cost controls

- `min_instances = 0` on every service — cold starts, but no $ when idle.
- `max_instances = 5` caps the blast radius of a retry storm.
- Artifact Registry `cleanup_policies` keep the 30 most recent tags + auto-delete untagged images after 7 days.
- Pub/Sub dead-letter topic caps delivery attempts at 10 — bad payloads can't drain the Anthropic budget.
- The `grafanagent-cost-spike` alert pages at $5/hour.

### Teardown

```bash
terraform -chdir=infra/terraform destroy \
  -var "project_id=$GCP_PROJECT_ID" \
  -var "enable_deploy=true" \
  -var "enable_cloudsql=true"
```

Cloud SQL is deletion-protected by default — set `deletion_protection=false`
in the cloudsql module if you genuinely want to drop the instance.
