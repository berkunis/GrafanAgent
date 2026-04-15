# Project context for Claude

## What this is
GrafanAgent — a portfolio/interview project for a **Staff AI Engineer (AI & Automation)** role at Grafana Labs. Hiring manager: Ryan, Staff AI Growth Engineer.

## Why it exists
Demonstrate end-to-end ability to ship multi-agent AI systems on GCP that connect marketing/ops platforms (Customer.io, Salesforce, BigQuery, Slack), with **the Grafana LGTM stack as the AI observability layer** — that last bit is the differentiator.

## What's done
- README.md with full pitch, architecture, stack, repo layout, demo flows
- Repo published at https://github.com/DigiFabAI/GrafanAgent
- No code yet — design + architecture only

## What's next (MVP scope)
1. **Router agent** (Cloud Run, Anthropic SDK, Haiku) — classifies signals, dispatches to skill agents
2. **Lifecycle Personalization agent** (Sonnet) — first end-to-end skill agent
3. **3 MCP servers** — BigQuery (read), Customer.io (sandbox writes), Slack (post + approval buttons)
4. **OTel instrumentation → Grafana Cloud free tier** (Tempo traces, Loki logs, Mimir metrics)
5. **One Grafana dashboard** showing tokens, cost, p95 latency, success rate, agent traces
6. **HITL flow** — Slack approval gate before any external write
7. **Demo signal**: simulated "free user hit aha-moment threshold" event in BQ → end-to-end execution

## What NOT to do
- Don't sprawl to 12 agents. Three + router proves the pattern.
- Don't skip the Grafana dashboard — it IS the project's differentiator.
- Don't hit real Salesforce/Customer.io. Sandbox/mock writes only.
- Don't build a behavioral-eval framework before there's anything to evaluate.

## Stack defaults
- Python for agents and MCP servers
- Anthropic SDK + MCP (no LangChain unless there's a specific reason)
- GCP: Cloud Run, Pub/Sub, Cloud SQL (pgvector)
- Terraform for infra
- OTel SDK → Grafana Cloud

## Working notes
- User is Isil Berkun (founder of DigiFab.ai). Treat as senior engineer; skip basics, surface trade-offs.
- Public repo — keep interview-strategy framing OUT of committed files. Pitch as a real project, not "an interview demo."
- Original full plan (with interview-strategy sections) lives at `~/.claude/plans/eager-toasting-wadler.md`
