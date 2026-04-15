# GrafanAgent

A multi-agent marketing-ops copilot that turns product-usage signals into orchestrated cross-platform actions — fully instrumented with the **Grafana LGTM stack** (Loki, Grafana, Tempo, Mimir) so every prompt, token, latency, cost, and decision is observable in real time.

> **Status: Phase 1 of 9 shipped.** Router + BigQuery MCP + explicit Haiku → Sonnet → rule → HITL fallback chain are real, unit-tested (35 tests, <1s), and runnable locally. Remaining phases (lifecycle agent + RAG, Slack Bolt app, CLI, eval harness, dashboard, deploy) land in sequence.

---

## Build status

| Phase | Scope | State |
|---|---|---|
| 0 | Narrative alignment (CLAUDE.md, README, DESIGN.md) | ✅ shipped |
| 1 | Real router, BQ MCP, explicit fallback chain, golden BQ seed | ✅ shipped |
| 2 | Lifecycle agent + Customer.io MCP + RAG on pgvector with Vertex AI | ⏳ next |
| 3 | TypeScript Slack Bolt HITL app + Slack MCP + state machine | ⏳ planned |
| 4 | `grafanagent` CLI | ⏳ planned |
| 5 | Eval harness + LLM judge + Grafana regression alert + CI | ⏳ planned |
| 6 | Cost meter, full dashboard, OTel genai semconv polish | ⏳ planned |
| 7 | Lead-scoring + Attribution agents | ⏳ planned |
| 8 | Terraform apply + Cloud Run deploy | ⏳ planned |
| 9 | DESIGN.md polish + CONTRIBUTING + write-up + OSS signal | ⏳ planned |

See [`docs/DESIGN.md`](docs/DESIGN.md) for the rationale behind each non-obvious choice.

---

## Quickstart (local, no credentials required)

```bash
git clone https://github.com/berkunis/GrafanAgent.git && cd GrafanAgent
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Unit + integration tests (Anthropic + BigQuery are mocked).
pytest -q

# Boot each agent/MCP stub once, emit a span, exit.
make smoke
```

With an `ANTHROPIC_API_KEY` set you can hit the real router end to end:

```bash
uvicorn agents.router.app:create_app --factory --reload
curl -s -X POST localhost:8000/signal -H 'content-type: application/json' -d '{
  "id":"golden-aha-001","type":"aha_moment_threshold","source":"cli","user_id":"user-aha-001"
}' | jq
```

---

## The problem

Marketing-ops teams burn hours daily on the same loop:

- A signal fires (free user crosses a usage threshold, an enterprise account opens a support ticket, an MQL goes stale)
- Someone manually pulls context from BigQuery + Salesforce + product analytics
- Someone decides what action to take (sequence enrollment, SDR alert, lifecycle email tweak)
- Someone executes in Customer.io / Salesforce / Slack
- Nobody measures whether it worked

GrafanAgent collapses that loop into a 24/7 agentic workflow with a human-in-the-loop escape hatch — and surfaces the entire decision pipeline through the same observability stack engineering teams already use for production systems.

---

## Architecture

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │  Signal Ingestion: BigQuery / Pub/Sub / webhooks / `grafanagent` CLI │
  └─────────────────────────────────────┬────────────────────────────────┘
                                        │
                            ┌───────────▼────────────┐
                            │   Router Agent (Haiku) │   structured output
                            │   classify → dispatch  │   Pydantic schema
                            └───────────┬────────────┘
                                        │
              ┌─────────────── fallback chain ───────────────┐
              │  conf ≥ 0.8 → dispatch                       │
              │  0.5 ≤ conf < 0.8 → re-ask Sonnet            │
              │  conf < 0.5 → deterministic rule → HITL      │
              └──────────────────────────────────────────────┘
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        │                               │                               │
┌───────▼────────┐           ┌──────────▼─────────┐           ┌─────────▼────────┐
│ Lead-Scoring   │           │  Lifecycle (Sonnet)│           │  Attribution     │
│ Agent          │           │  parallel fan-out: │           │  Analyst Agent   │
│                │           │   ├ BQ user ctx    │           │                  │
│ Tools (MCP):   │           │   ├ RAG playbook   │           │ Tools (MCP):     │
│ - BQ           │           │   └ Customer.io    │           │ - BQ             │
│ - Salesforce   │           │  → synth Sonnet    │           │ - Slack          │
│ - Clearbit     │           │  Tools (MCP):      │           │                  │
│                │           │   - BQ / Cust.io   │           │                  │
│                │           │   - Slack          │           │                  │
└───────┬────────┘           └──────────┬─────────┘           └─────────┬────────┘
        │                               │                               │
        └───────────────────────────────┼───────────────────────────────┘
                                        │
                            ┌───────────▼────────────┐
                            │  HITL Slack Approval   │   Block Kit cards
                            │  (TypeScript Bolt)     │   draft → posted →
                            │  state machine         │   approved/rejected/
                            └───────────┬────────────┘   edited/timed_out
                                        │
                            ┌───────────▼────────────┐
                            │   Action Executor      │   idempotent writes
                            │   (Customer.io,        │   keyed by signal_id
                            │    Salesforce, Slack)  │
                            └────────────────────────┘

  ┌─── RAG layer ──────────────────────────────────────────────────────┐
  │  pgvector on Cloud SQL ← Vertex AI text-embedding-004              │
  │  Corpus: lifecycle playbooks, segmentation guides, internal docs   │
  └────────────────────────────────────────────────────────────────────┘

  ┌─── Eval harness ───────────────────────────────────────────────────┐
  │  golden_set.jsonl → runner → Sonnet judge → Mimir metric           │
  │  GitHub Actions runs eval on every prompt-touching PR              │
  │  Grafana alert fires on regression (pass-rate < 0.85)              │
  └────────────────────────────────────────────────────────────────────┘

  ╔══════════════════════════════════════════════════════════════════════╗
  ║              OBSERVABILITY (the core idea — LGTM for AI)              ║
  ║                                                                       ║
  ║   Tempo  ← OTel traces w/ genai semconv: prompts, completions,       ║
  ║            tokens, cost-per-call, MCP tool spans                      ║
  ║   Loki   ← Structured JSON logs (PII-scrubbed), HITL audit trail     ║
  ║   Mimir  ← Metrics: $ spend, p50/p95/p99 latency, eval pass rate     ║
  ║   Grafana← Dashboards + alerts; trace explorer drills span → prompt  ║
  ╚══════════════════════════════════════════════════════════════════════╝
```

---

## Stack

| Concern | Choice |
|---|---|
| Orchestration | Anthropic SDK + Model Context Protocol (MCP). No LangChain / CrewAI. |
| Agents | Router (Haiku, low latency) + 3 specialized agents (Sonnet) |
| Fallback chain | Haiku (≥0.8) → Sonnet (0.5–0.8) → deterministic rule → HITL |
| Orchestration patterns | Router/dispatcher (Haiku); parallel fan-out (lifecycle, asyncio.gather) |
| MCP servers | Python servers for BigQuery (read, allow-list, PII redaction), Customer.io (sandbox writes, idempotent), Slack |
| HITL UI | TypeScript Slack Bolt app with Block Kit approval cards + state machine |
| RAG | pgvector on Cloud SQL; embeddings from **Vertex AI `text-embedding-004`** (GCP-native) |
| CLI | `grafanagent` (typer) — `trigger`, `replay`, `list`, `describe`, `eval` |
| Eval harness | Golden set + Sonnet judge → Mimir metric → Grafana regression alert + GitHub Actions on every prompt PR |
| Compute | Cloud Run services per agent + per MCP server (single shared Dockerfile, build-arg entrypoint) |
| Eventing | Cloud Pub/Sub for signal fan-out |
| Secrets | GCP Secret Manager (Anthropic key, Slack creds, Customer.io creds, Grafana OTLP token) |
| Observability | OpenTelemetry SDK → Grafana Cloud (Tempo/Loki/Mimir) using **OTel genai semantic conventions** (spans carry prompt + completion + tokens + $ cost) |
| Governance | Confidence-scored routing, fallback chain, Slack approval gate, Loki audit trail, structlog PII scrubber |
| Cost control | Prompt caching, model tiering, per-agent Mimir budget alarms, $-per-signal panel |
| IaC | Terraform |
| CI/CD | GitHub Actions: lint + test + golden-eval-on-PR + image build |

---

## Repository layout

```
grafanagent/
├── README.md
├── pyproject.toml              ← single Python project, multiple services
├── Dockerfile                  ← shared image; SERVICE_MODULE build-arg picks entrypoint
├── Makefile                    ← install / smoke / lint / test / eval / deploy
├── observability/              ← shared OTel bootstrap; every service imports init_telemetry()
├── agents/
│   ├── router/                 ← Haiku, structured output, fallback chain
│   ├── lifecycle/              ← Sonnet, parallel fan-out, RAG-backed
│   ├── lead_scoring/
│   └── attribution/
├── mcp_servers/
│   ├── bigquery/               ← read-only, allow-list, PII redaction
│   ├── customer_io/            ← sandbox writes, idempotent
│   └── slack/                  ← Python MCP that talks to the Bolt app
├── apps/
│   └── slack-approver/         ← TypeScript Slack Bolt app, Block Kit, HITL state machine
├── rag/
│   ├── embeddings.py           ← Vertex AI text-embedding-004
│   ├── store.py                ← pgvector adapter
│   ├── ingest.py
│   └── corpus/                 ← lifecycle playbooks (markdown)
├── cli/                        ← `grafanagent` CLI (typer)
├── evals/
│   ├── golden_set.jsonl
│   ├── runner.py
│   └── judge.py                ← Sonnet-based LLM judge
├── infra/
│   ├── terraform/              ← Cloud Run + Pub/Sub + Cloud SQL + Secret Manager + Artifact Registry
│   └── otel/                   ← OTel collector config → Grafana Cloud
├── dashboards/
│   ├── grafanagent.json        ← exported Grafana dashboard
│   └── alerts.json
├── tests/
└── docs/
    ├── DESIGN.md               ← decision records
    ├── runbook.md
    └── adding_a_new_skill.md
```

---

## Demo flows (MVP)

1. **End-to-end happy path**: `grafanagent trigger evals/golden_signal.json` → router classifies (Haiku, structured output) → lifecycle agent fans out in parallel (BQ user context + RAG playbook + Customer.io membership) → Sonnet synthesizes a Customer.io campaign draft → posts a Block Kit approval card to Slack → operator clicks Approve → idempotent sandbox write to Customer.io
2. **Fallback path**: low-confidence signal → router escalates Haiku → Sonnet → deterministic rule → HITL queue. Every step a span in Tempo with the model + tokens + cost.
3. **Eval regression**: edit a router prompt in a PR → GitHub Action runs the golden set → Sonnet judge scores it → Mimir metric drops below threshold → Grafana alert fires → PR check fails before merge.
4. **Trace drilldown**: open Grafana Tempo → click any span → see exact prompt sent + completion + token count + dollar cost (OTel genai semantic conventions).

---

## Verification checklist

- [ ] `make smoke` — every service boots and emits a span
- [ ] `pytest -q` + `npm test --prefix apps/slack-approver` — all green
- [ ] `grafanagent trigger evals/golden_signal.json` — full local end-to-end < 30s, ~15-span trace
- [ ] `grafanagent eval` — golden set scores ≥ 0.85
- [ ] HITL: Block Kit approval card renders, Approve / Reject / Edit each drive correct state transitions, full audit chain in Loki
- [ ] Trace in Tempo shows parent-child spans (router → fallback steps → skill agent → 3 parallel MCP fetches → synthesis → Slack post → Customer.io write) with `gen_ai.*` attrs populated
- [ ] Grafana dashboard: cost ticks up by signal, p95 < 4s, success-rate gauge moves, eval pass-rate trendline visible
- [ ] Regression test: tweak a prompt, watch the alert fire, revert, watch it clear

---

## Design principles

- **Three agents + one router proves the pattern.** More is noise. The fourth agent is the proof you can replicate, not the proof you can scale.
- **Observability is not optional.** If you can't see a token count, a tool call, a prompt, or a dollar cost in Grafana, the system isn't production-ready.
- **MCP over bespoke RPC.** Skills compose; integrations don't get rewritten per agent.
- **GCP-native first.** Vertex AI for embeddings, Cloud SQL for vector storage, Secret Manager for secrets — reach for the platform's primitives before bolting on third parties.
- **Explicit fallback chain over silent failures.** Haiku → Sonnet → deterministic rule → HITL. Every degradation is a span.
- **Eval is a first-class loop.** Prompt changes go through the same regression bar as code changes — golden set on every PR, alert on regression.
- **HITL by default for high-blast-radius actions.** Confidence threshold gates, never auto-fire on customer-facing writes without an audit trail.
- **Sandbox the writes.** Real CRMs in dev = real outages.
- **Built with Claude Code.** This repo is a working example of pragmatic AI-assisted development paired with strong code review.

See [`docs/DESIGN.md`](docs/DESIGN.md) for the rationale behind each non-obvious choice.

---

## License

MIT
