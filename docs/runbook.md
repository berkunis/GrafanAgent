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

## Deploy a service to Cloud Run (template)

```bash
docker build --build-arg SERVICE_MODULE=agents.router.main \
  -t us-central1-docker.pkg.dev/$GCP_PROJECT_ID/grafanagent/router:latest .
docker push us-central1-docker.pkg.dev/$GCP_PROJECT_ID/grafanagent/router:latest
gcloud run deploy router \
  --image us-central1-docker.pkg.dev/$GCP_PROJECT_ID/grafanagent/router:latest \
  --region us-central1 --no-allow-unauthenticated \
  --set-env-vars OTEL_EXPORTER_OTLP_ENDPOINT=$OTEL_ENDPOINT \
  --set-secrets ANTHROPIC_API_KEY=anthropic-key:latest,OTEL_EXPORTER_OTLP_HEADERS=otlp-headers:latest
```

Phase 8 replaces this manual template with Terraform-managed Cloud Run services + Secret Manager mounts.
