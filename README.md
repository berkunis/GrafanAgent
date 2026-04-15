# GrafanAgent

A multi-agent marketing-ops copilot that turns product-usage signals into orchestrated cross-platform actions — fully instrumented with the **Grafana LGTM stack** (Loki, Grafana, Tempo, Mimir) so every prompt, token, latency, cost, and decision is observable in real time.

> Status: design + reference architecture. Implementation in progress.

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
                    ┌─────────────────────┐
                    │   Signal Ingestion   │
                    │  (BigQuery / Pub/Sub │
                    │   / webhook events)  │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   Router Agent       │  ← LLM-based dispatcher
                    │  (classifies signal, │     w/ structured output
                    │   selects skill)     │
                    └──────────┬───────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
┌───────▼────────┐   ┌─────────▼────────┐   ┌─────────▼────────┐
│ Lead-Scoring   │   │  Lifecycle       │   │  Attribution     │
│ Agent          │   │  Personalization │   │  Analyst Agent   │
│                │   │  Agent           │   │                  │
│ Tools:         │   │  Tools:          │   │  Tools:          │
│ - BQ MCP       │   │  - Customer.io   │   │  - BQ MCP        │
│ - Salesforce   │   │    MCP           │   │  - Looker MCP    │
│   MCP          │   │  - Salesforce    │   │  - Slack MCP     │
│ - Clearbit/    │   │    MCP           │   │                  │
│   Apollo MCP   │   │  - Slack MCP     │   │                  │
└───────┬────────┘   └─────────┬────────┘   └─────────┬────────┘
        │                      │                      │
        └──────────────────────┼──────────────────────┘
                               │
                    ┌──────────▼───────────┐
                    │  Human-in-the-Loop   │  ← Slack approval for
                    │  Gate (confidence    │     low-confidence or
                    │  threshold)          │     high-blast-radius
                    └──────────┬───────────┘     actions
                               │
                    ┌──────────▼───────────┐
                    │   Action Executor    │
                    │  (idempotent calls   │
                    │   to Customer.io,    │
                    │   Salesforce, Slack) │
                    └──────────────────────┘

  ╔══════════════════════════════════════════════════════════╗
  ║              OBSERVABILITY (the core idea)                ║
  ║                                                           ║
  ║   Tempo  ← OTel traces: every agent step + tool call      ║
  ║   Loki   ← Structured logs: prompts, completions, tools   ║
  ║   Mimir  ← Metrics: tokens, cost, latency, success rate   ║
  ║   Grafana← Dashboards + alerts on cost/latency/failures   ║
  ╚══════════════════════════════════════════════════════════╝
```

---

## Stack

| Concern | Choice |
|---|---|
| Orchestration | Anthropic SDK + Model Context Protocol (MCP) |
| Agents | Router (Haiku, low latency) + 3 specialized agents (Sonnet) |
| MCP servers | Custom servers for BigQuery, Customer.io, Salesforce (sandbox) |
| Compute | Cloud Run services per agent + per MCP server |
| Eventing | Cloud Pub/Sub for signal fan-out |
| Retrieval | pgvector on Cloud SQL over internal playbooks + product docs |
| Observability | OpenTelemetry SDK → Grafana Cloud (Tempo/Loki/Mimir) |
| Governance | Confidence-scored router output, Slack approval gate, Loki audit trail |
| Cost control | Prompt caching, model tiering (Haiku route → Sonnet act), per-agent Mimir budget alarms |
| IaC | Terraform |

---

## Repository layout

```
grafanagent/
├── README.md
├── ARCHITECTURE.md            ← deeper design doc
├── agents/
│   ├── router/                ← Cloud Run service, Anthropic SDK
│   ├── lifecycle/
│   ├── lead_scoring/
│   └── attribution/
├── mcp_servers/
│   ├── bigquery/
│   ├── customer_io/
│   └── salesforce/
├── infra/
│   ├── terraform/             ← Cloud Run + Pub/Sub + Cloud SQL
│   └── otel/                  ← OTel collector config → Grafana Cloud
├── dashboards/
│   └── grafanagent.json       ← exported Grafana dashboard
├── evals/
│   └── golden_set.jsonl
└── docs/
    ├── runbook.md
    └── adding_a_new_skill.md
```

---

## Demo flows (MVP)

1. **End-to-end happy path**: simulated "free user hit aha-moment threshold" event in BigQuery → router classifies → lifecycle agent pulls user context → drafts a Customer.io campaign payload → posts to Slack for approval → executes
2. **HITL path**: a synthetic low-confidence signal hits the approval gate; a human approves or rejects in Slack with the rationale captured to Loki
3. **Eval harness**: small golden-set of signals → expected actions, scored by an LLM judge, results piped into Mimir as a regression metric

---

## Verification checklist

- [ ] Trigger a synthetic signal → router classifies it correctly in Tempo within 3 sec
- [ ] Full agent trace renders in Tempo with parent-child spans (router → skill agent → MCP tool calls)
- [ ] Grafana dashboard shows token cost ticking up, p95 latency under 4s, success-rate gauge moving
- [ ] HITL flow: Slack approval message → approve executes; reject logs rationale
- [ ] Audit trail in Loki for any signal-to-action chain
- [ ] Eval dashboard shows a regression caught and fixed via prompt change

---

## Design principles

- **Three agents + one router proves the pattern.** More is noise.
- **Observability is not optional.** If you can't see a token count, a tool call, or a latency, the system isn't production-ready.
- **MCP over bespoke RPC.** Skills compose; integrations don't get rewritten per agent.
- **HITL by default for high-blast-radius actions.** Confidence threshold gates, never auto-fire on customer-facing writes without an audit trail.
- **Sandbox the writes.** Real CRMs in dev = real outages.

---

## License

MIT
