# Project context for Claude

## What this is
GrafanAgent — a portfolio/interview project for a **Staff AI Engineer (AI & Automation)** role at Grafana Labs. Hiring manager: Ryan, Staff AI Growth Engineer. Full JD at `docs/role.md` (gitignored — private context only).

## Why it exists
Demonstrate end-to-end ability to ship multi-agent AI systems on GCP that connect marketing/ops platforms (Customer.io, Salesforce, BigQuery, Slack), with **the Grafana LGTM stack as the AI observability layer** — that last bit is the differentiator.

## What's done
- **All 9 phases shipped.** 154 Python tests + 17 TypeScript tests green; ruff clean.
- Four working agents (router + lifecycle + lead_scoring + attribution) with explicit Haiku → Sonnet → rule → HITL fallback chain on the router, Sonnet synthesis on skill agents, parallel fan-out where it makes sense.
- Three Python MCP servers (BigQuery read-only + PII-redacted, Customer.io sandbox-only idempotent, Slack proxy to Bolt app).
- TypeScript Slack Bolt approval app with full state machine + Block Kit UI + edit modal.
- RAG on pgvector + Vertex AI `text-embedding-004`, 12 hand-authored playbooks.
- `grafanagent` CLI (trigger / replay / list / describe / eval).
- Sonnet LLM-as-judge eval harness with Mimir metrics + Grafana regression alert + GitHub Actions CI + nightly workflow.
- Cache-aware cost model + per-signal contextvars attribution + latency histogram + full OTel genai semconv.
- Real Grafana dashboard (13 panels, 5 rows) + 6 alert rules with runbook links.
- Full Terraform stack (Artifact Registry + Pub/Sub with DLQ + Secret Manager + reusable Cloud Run module + runtime SA with minimal IAM).
- `make deploy` / `make seed` / `make smoke-remote` + multi-stage TS Dockerfile + production runbook.
- LICENSE (MIT) + CONTRIBUTING.md + SECURITY.md + blog post + seed good-first-issues list.
- Repo public at https://github.com/berkunis/GrafanAgent.

## MVP scope (JD-aligned, executes in 9 phases)

The full build plan lives at `~/.claude/plans/vast-swimming-bachman.md`. Phases are reviewed and committed individually.

1. **Router agent** (Cloud Run, Anthropic SDK, Haiku) — classifies signals, dispatches to skill agents, **explicit fallback chain** Haiku → Sonnet → deterministic rule → HITL
2. **Lifecycle Personalization agent** (Sonnet) — first end-to-end skill agent, uses **parallel fan-out** (asyncio.gather) across BQ + RAG + Customer.io
3. **3 MCP servers** — BigQuery (read, allow-list, PII redaction), Customer.io (sandbox writes, idempotent), Slack (post + approval)
4. **RAG layer** — pgvector on Cloud SQL, **Vertex AI `text-embedding-004`** (GCP-native), corpus of lifecycle playbooks
5. **TypeScript Slack Bolt app** — Block Kit approval cards, HITL state machine (closes JS/Node + frontend signal in one move)
6. **`grafanagent` CLI** — `trigger`, `replay`, `list`, `describe`, `eval` (closes "skills invoked across CLIs")
7. **Eval harness** — golden set + Sonnet judge + Mimir metric + Grafana regression alert + GitHub Actions integration
8. **OTel instrumentation → Grafana Cloud** — Tempo / Loki / Mimir, using **OTel genai semantic conventions** so spans carry prompt/completion/token/cost attrs
9. **One Grafana dashboard** — cost ($/hr, $/signal, by model), latency p50/p95/p99, success rate, eval pass rate, trace explorer that drills span → prompt
10. **HITL flow** — Slack approval gate before any external write, full audit trail in Loki
11. **Lead-Scoring + Attribution agents** — replicate the lifecycle pattern; proves "self-service skill addition"
12. **Demo signal**: simulated "free user hit aha-moment threshold" event in BQ → end-to-end execution

## What NOT to do
- Don't sprawl to 12 agents. Three skill agents + router proves the pattern.
- Don't skip the Grafana dashboard — it IS the project's differentiator.
- Don't hit real Salesforce/Customer.io. Sandbox/mock writes only.
- Don't reach for LangChain / CrewAI / n8n / Temporal — Anthropic SDK + MCP + Pub/Sub + Cloud Run is the bet. Document the *why* in DESIGN.md.
- Don't add real customer data anywhere. Synthetic users only; PII redaction exists for demo authenticity.
- Don't surface interview-strategy framing in committed files. Pitch as a real project.

## Stack defaults
- **Python** for agents and MCP servers; **TypeScript** for the Slack Bolt app
- **Anthropic SDK + MCP** (no LangChain unless there's a specific reason)
- **GCP**: Cloud Run, Pub/Sub, Cloud SQL (pgvector), Vertex AI (embeddings), Secret Manager, Artifact Registry
- **Terraform** for infra
- **OTel SDK → Grafana Cloud** with genai semantic conventions
- **GCP-native first**: when a GCP primitive exists for the job, use it before reaching for third-party SaaS

## Working notes
- User is Isil Berkun (founder of DigiFab.ai). Treat as senior engineer; skip basics, surface trade-offs.
- Public repo — keep interview-strategy framing OUT of committed files. Pitch as a real project, not "an interview demo." `docs/role.md` is gitignored.
- **Phases 0–9 complete.** The application-ready state.
- Current plan file (phases + rationale): `~/.claude/plans/vast-swimming-bachman.md`.
- Original brainstorm plan (with interview strategy): `~/.claude/plans/eager-toasting-wadler.md`.
- Next meaningful work: actually deploying to GCP (requires user credentials), or follow-on PRs from `docs/FIRST_ISSUES.md` if inviting contributors.
