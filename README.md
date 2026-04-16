# GrafanAgent

[![CI](https://github.com/berkunis/GrafanAgent/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/berkunis/GrafanAgent/actions/workflows/ci.yml)
[![Eval (nightly)](https://github.com/berkunis/GrafanAgent/actions/workflows/eval-nightly.yml/badge.svg)](https://github.com/berkunis/GrafanAgent/actions/workflows/eval-nightly.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-3776ab)](pyproject.toml)
[![Node 22](https://img.shields.io/badge/node-22-339933)](apps/slack-approver/package.json)
[![Ruff](https://img.shields.io/badge/lint-ruff-orange)](https://github.com/astral-sh/ruff)
[![Built with Claude Code](https://img.shields.io/badge/built%20with-Claude%20Code-d97757)](https://www.anthropic.com/claude-code)

A multi-agent marketing-ops copilot that turns product-usage signals into orchestrated cross-platform actions — fully instrumented with the **Grafana LGTM stack** (Loki, Grafana, Tempo, Mimir) so every prompt, token, latency, cost, and decision is observable in real time.

> **Status: shipped.** All 9 phases complete. Every agent + MCP server + the Slack Bolt UI + the full Terraform deploy stack + a Sonnet-judge eval harness with Grafana regression alerts + a production runbook are real, unit-tested (147+ Python tests + 17 TypeScript tests, all <1s), and deployable to Cloud Run in one `make deploy` command.
>
> Read the companion blog post: [**Building production AI agents with the Grafana LGTM stack**](docs/blog/building-ai-agents-with-lgtm.md).

## Contents

- [Build status](#build-status)
- [Quickstart](#quickstart-local-no-credentials-required)
- [What you can do right now](#what-you-can-do-right-now) — runnable demos, no credentials
- [The problem](#the-problem)
- [Architecture](#architecture)
- [Stack](#stack)
- [Repository layout](#repository-layout)
- [Demo flows](#demo-flows-mvp)
- [Verification checklist](#verification-checklist)
- [Design principles](#design-principles)
- [Deploying](docs/runbook.md#deploy) — runbook covers GCP bootstrap, secrets, deploy, rollback, teardown
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- [License](LICENSE)

---

## Build status

| Phase | Scope | State |
|---|---|---|
| 0 | Narrative alignment (CLAUDE.md, README, DESIGN.md) | ✅ shipped |
| 1 | Real router, BQ MCP, explicit fallback chain, golden BQ seed | ✅ shipped |
| 2 | Lifecycle agent (parallel fan-out) + Customer.io MCP + RAG on pgvector with Vertex AI + 8-playbook corpus | ✅ shipped |
| 3 | TypeScript Slack Bolt HITL app (Block Kit + state machine + edit modal) + Python Slack MCP + PII scrubber + lifecycle execution loop | ✅ shipped |
| 4 | `grafanagent` CLI (trigger / replay / list / describe / eval) + 10-case golden set + rule-table gate | ✅ shipped |
| 5 | Sonnet LLM-as-judge + Mimir metrics + Grafana regression alert rule + GitHub Actions CI + nightly LLM-eval | ✅ shipped |
| 6 | Cache-aware cost model + per-signal attribution + latency histogram + genai semconv polish + real Grafana dashboard + 4 more alert rules + collector polish | ✅ shipped |
| 7 | Lead-Scoring agent (conditional HITL) + Attribution agent (multi-touch report) + 4 new RAG playbooks + self-service skill-addition doc | ✅ shipped |
| 8 | Terraform (Artifact Registry + Pub/Sub + Secret Manager + generic Cloud Run module) + deploy/seed/smoke-remote scripts + TS Dockerfile + production runbook | ✅ shipped |
| 9 | DESIGN.md finalised + CONTRIBUTING + SECURITY + blog post + README polish + seed good-first-issues | ✅ shipped |

See [`docs/DESIGN.md`](docs/DESIGN.md) for the rationale behind every non-obvious choice.

---

## Quickstart (local, no credentials required)

```bash
git clone https://github.com/berkunis/GrafanAgent.git && cd GrafanAgent
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Python: unit + integration tests (Anthropic, BigQuery, Customer.io, Vertex AI,
# and the Slack approver are all mocked or faked — runs offline in <1s).
pytest -q

# TypeScript: Slack Bolt approval app (Block Kit, state machine, HTTP API).
make bolt-test

# Boot each agent/MCP stub once, emit a span, exit.
make smoke

# Local pgvector + ingest the 8-playbook RAG corpus (HashEmbedder by default,
# flip to Vertex AI with RAG_EMBEDDER=vertex once ADC is set up).
make db-up && make ingest

# Bring up the Slack Bolt approver alongside pgvector (HTTP-only without
# SLACK_BOT_TOKEN — the state machine + API work; Slack interactivity is
# stubbed out until you wire a real workspace).
make bolt-up
curl -s localhost:3030/healthz | jq
```

---

## What you can do right now

The build is phased, but the shipped parts are fully runnable on your laptop without any cloud credentials.

### 1. Run the full lifecycle pipeline end-to-end — with HITL — offline

```bash
python -m scripts.demo_lifecycle                          # approved path
HITL_DECISION=rejected python -m scripts.demo_lifecycle   # rejected path
```

Runs the real lifecycle orchestrator against the real 8-playbook RAG corpus, a `FakeMcpClient` that simulates BigQuery + Customer.io + the Slack HITL resolution, and a canned Sonnet synthesis — so you can see the full `LifecycleOutput` JSON (including `hitl_state`, `executed`, and the downstream Customer.io execution detail) without hitting any external service.

<details><summary>Abridged output</summary>

```json
{
  "signal_id": "golden-aha-001",
  "enrichment": {
    "user_context": {
      "user_id": "user-aha-001",
      "plan": "free",
      "lifecycle_stage": "activated",
      "company": "Lattice Loop",
      "recent_event_types": [
        "dashboard_created", "alert_configured",
        "integration_added", "invite_sent"
      ]
    },
    "playbooks": [
      {"playbook_slug": "invite-momentum",        "score": 0.192, "section": "Trigger"},
      {"playbook_slug": "trial-expiring-dormant", "score": 0.192, "section": "Trigger"},
      {"playbook_slug": "aha-moment-free-user",   "score": 0.183, "section": "Guardrails"}
    ],
    "current_campaigns": [],
    "partial": false
  },
  "draft": {
    "signal_id": "golden-aha-001",
    "user_id": "user-aha-001",
    "audience_segment": "free_activated_today",
    "channel": "email",
    "subject": "You just wired the exact pattern our best teams use",
    "body_markdown": "In the last hour you set up a dashboard, wired an alert, added an integration, and invited a teammate...",
    "call_to_action": "Share your dashboard",
    "playbook_slug": "aha-moment-free-user",
    "rationale": "aha-moment + invite momentum; playbook emphasises inviter recognition."
  },
  "latency_ms": 2,
  "hitl_id": "hitl_demo_1",
  "hitl_state": "approved",
  "hitl_decided_by": "isil",
  "hitl_decided_at": "2026-04-15T00:00:05Z",
  "executed": true,
  "execution_detail": {
    "ok": true,
    "idempotency_key": "cio:broadcast:golden-aha-001"
  }
}
```

</details>

### 2. See the OTel trace shape

The same run emits this span tree to stdout (via the `ConsoleSpanExporter` when `OTEL_EXPORTER_OTLP_ENDPOINT` is unset):

```
lifecycle.run                         ← root; signal_id, user_id, latency_ms
├── lifecycle.enrich                  ← parallel fan-out parent
│   ├── lifecycle.bq.user_context
│   ├── lifecycle.rag.retrieve
│   │   └── rag.retrieve              ← rag.hits=3, rag.top_playbooks=[...]
│   └── lifecycle.cio.current_campaigns
├── anthropic.structured_output       ← gen_ai.* semconv + prompt/completion events
│     gen_ai.system=anthropic
│     gen_ai.request.model=claude-sonnet-4-5
│     gen_ai.usage.input_tokens=120
│     gen_ai.usage.output_tokens=40
│     grafanagent.cost_usd=0.00096
├── lifecycle.cio.create_draft
├── hitl.request                      ← Block Kit card posted; hitl.id attr
├── hitl.wait                         ← long-poll until terminal state
├── lifecycle.cio.execute             ← trigger_broadcast w/ idempotency_key
└── hitl.mark_executed
```

Every rung of the router fallback chain, every MCP tool call, and every LLM call emits a span with the same `gen_ai.*` semantic conventions — Phase 6 wires these into a Grafana dashboard, but they're already visible today.

### 3. Hit the router over HTTP with a real Anthropic key

```bash
export ANTHROPIC_API_KEY=sk-...
uvicorn agents.router.app:create_app --factory --reload

curl -s -X POST localhost:8000/signal -H 'content-type: application/json' -d '{
  "id":"golden-aha-001","type":"aha_moment_threshold","source":"cli","user_id":"user-aha-001"
}' | jq
```

Returns the real `RoutingDecision` from Claude Haiku plus the fallback `rung_used` and the list of models consulted.

### 4. Use the `grafanagent` CLI

Installed as a console script by `pip install -e .`:

```bash
grafanagent --help                        # subcommand list
grafanagent list agents                   # 4 agents + 3 MCP servers
grafanagent list signals                  # rule-table signal types → skills
grafanagent list playbooks                # every RAG playbook with metadata
grafanagent describe agent router         # fallback thresholds + rule table
grafanagent describe mcp bigquery         # allow-list + PII policy
grafanagent eval                          # rule-mode gate (deterministic, offline)
grafanagent eval --mode llm --emit-metrics  # Sonnet judge + Mimir metrics (needs ANTHROPIC_API_KEY)
grafanagent trigger signal.json           # POST → local router
grafanagent trigger signal.json -u $URL   # POST → deployed router
grafanagent replay signal.json            # replay a stored signal (prompt regression)
```

Agents should be invokable from wherever operators live — Slack, dashboards, internal apps, **and CLIs**. A real console script keeps the CLI path first-class rather than a hand-run shim. `grafanagent eval` is also the CI gate Phase 5 layers a Sonnet judge on top of — see `.github/workflows/ci.yml` (rule-mode on every PR) and `.github/workflows/eval-nightly.yml` (LLM-judge at 09:00 UTC with Mimir metrics).

### 5. Drive the Slack approval app by HTTP (no Slack token required)

```bash
make bolt-up
HITL_ID=$(curl -s -X POST localhost:3030/approvals -H 'content-type: application/json' -d '{
  "signal_id":"sig-demo","channel_id":"C-demo",
  "draft":{"signal_id":"sig-demo","user_id":"u1","audience_segment":"free_activated_today",
    "channel":"email","subject":"Hi","body_markdown":"body","call_to_action":"Go","rationale":"r","playbook_slug":null}
}' | jq -r .hitl_id)
curl -s localhost:3030/approvals/$HITL_ID | jq '{state, signal_id, history}'
```

The Bolt app state machine enforces `draft → posted → approved | rejected | edited | timed_out → executed | cancelled` — disallowed transitions throw. With a real `SLACK_BOT_TOKEN` + `SLACK_SIGNING_SECRET`, Block Kit cards post to the configured channel and the three action buttons (Approve / Reject / Edit+modal) drive the same state machine via Slack Events.

### 6. Probe the BigQuery MCP security layer

```bash
python -c "
from mcp_servers.bigquery.security import validate_query, SecurityPolicy
pol = SecurityPolicy.from_env()
validate_query('DROP TABLE grafanagent_demo.users', pol)  # raises SecurityError
"
```

The same guard rejects DML, unqualified tables, and disallowed datasets; PII columns are redacted from any rows returned to an agent.

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

See [`docs/DESIGN.md`](docs/DESIGN.md) for the full rationale — 16 decisions with the reasoning and when we'd reconsider.

---

## Built with Claude Code

Every commit in this repo's history ships with a `Co-Authored-By:` line crediting Claude. The authorship model is simple: every line of code has a human owner who read it, wrote the "why" in the commit message, and answers questions on the review. The `git log` is a working artefact of the collaboration.

---

## Screenshots

*Placeholders — add after first deployment to Grafana Cloud:*

- `docs/img/dashboard-cost.png` — the cost row showing per-bucket breakdown + top-10 most expensive signals
- `docs/img/dashboard-latency.png` — p50/p95/p99 by agent + success rate + error rate
- `docs/img/dashboard-eval.png` — pass-rate gauge + judge score trendline + per-skill bar
- `docs/img/tempo-span-drilldown.png` — clicking an `anthropic.structured_output` span to see the full prompt + completion
- `docs/img/slack-approval-card.png` — the HITL Block Kit card with Approve / Reject / Edit buttons

---

## Contributing + security

- [`CONTRIBUTING.md`](CONTRIBUTING.md) — dev setup, test loop, commit conventions
- [`SECURITY.md`](SECURITY.md) — private disclosure policy and scope
- [`docs/adding_a_new_skill.md`](docs/adding_a_new_skill.md) — 10-step template for adding a new agent
- [`docs/FIRST_ISSUES.md`](docs/FIRST_ISSUES.md) — seed good-first-issues a new contributor can pick up

---

## License

[MIT](LICENSE) © 2026 Isil Berkun
