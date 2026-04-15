# GrafanAgent Runbook

> Operational notes. Filled out as components land.

## Local dev

```bash
make install
cp .env.example .env       # leave OTEL_EXPORTER_OTLP_ENDPOINT blank for stdout exporter
make smoke                 # boots each agent stub once, emits one span, exits
```

## Deploy a service to Cloud Run (template)

```bash
docker build --build-arg SERVICE_MODULE=agents.router.main \
  -t us-central1-docker.pkg.dev/$GCP_PROJECT_ID/grafanagent/router:latest .
docker push us-central1-docker.pkg.dev/$GCP_PROJECT_ID/grafanagent/router:latest
gcloud run deploy router \
  --image us-central1-docker.pkg.dev/$GCP_PROJECT_ID/grafanagent/router:latest \
  --region us-central1 --no-allow-unauthenticated
```

## Observability

- Traces  → Grafana Tempo (OTLP)
- Metrics → Grafana Mimir (OTLP)
- Logs    → Grafana Loki (container stdout, JSON via structlog)
- Dashboard: import `dashboards/grafanagent.json`

## Incident playbooks
TBD as components land:
- Token budget breach
- LLM timeout / 5xx spike
- HITL approval queue stalled
- MCP server failure
