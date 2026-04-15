# GrafanAgent — Design Decisions

> A living record of non-obvious choices and the reasoning behind them. Each section gets filled as the corresponding component lands. If a decision changes, we don't rewrite history — we add a new dated entry below the original.

---

## Why MCP (not LangChain, CrewAI, or bespoke RPC)

**Status:** committed.

We bet on the **Anthropic SDK + Model Context Protocol (MCP)** directly rather than a higher-level framework.

**Reasoning:**
- **Observability surface area.** Every framework abstraction is a place where OTel attribution gets lossy. MCP is a thin wire protocol; we own the spans.
- **Native to the model provider.** MCP is Anthropic-first; staying close to the vendor's primitives means fewer impedance mismatches and faster access to new features (tool use, prompt caching, structured output).
- **Skill composability without re-implementation.** A BigQuery MCP server is reusable across all four agents without per-agent client code or framework-specific adapters.
- **The JD lists frameworks as examples, not requirements.** "LangChain, CrewAI, Anthropic MCP, or similar" — picking the most direct option is itself a signal.

**When we'd reconsider:** if we needed multi-provider routing across Anthropic + OpenAI + Gemini in production, a thin abstraction layer would help. We don't, so we don't pay for it.

---

## Model tiering: Haiku routes, Sonnet acts

**Status:** committed.

The router uses **Claude Haiku** (cheap, low-latency, structured-output-capable). Skill agents use **Claude Sonnet** for the actual reasoning + content generation.

**Reasoning:**
- Routing is a classification problem with a fixed schema — Haiku is more than capable.
- ~10× cost difference between tiers; the router runs on every signal, the skill agent only after dispatch.
- Sonnet's quality matters where the output is customer-facing (lifecycle email drafts).

---

## Explicit fallback chain (Haiku → Sonnet → rule → HITL)

**Status:** committed.

Router confidence drives an explicit degradation ladder:

| Confidence | Action |
|---|---|
| ≥ 0.8 | Dispatch to skill agent immediately |
| 0.5 – 0.8 | Re-ask Sonnet; if Sonnet agrees with Haiku's class, dispatch; if not, drop to next rung |
| < 0.5 (or Sonnet disagrees) | Apply deterministic rule table by signal type |
| Rule miss | Send to HITL queue (Slack approval card asking for human classification) |

**Reasoning:**
- The JD names "confidence thresholds, fallback logic, human escalation" as a specific production-mitigation requirement.
- A silent fallback is worse than no fallback — we want every degradation to be a Tempo span you can count and alert on (`router.fallback_used{rung=...}`).
- Deterministic rules give us a non-LLM safety net for known signal types so we never page a human for an unambiguous case.

---

## Parallel fan-out for the lifecycle agent

**Status:** committed.

The lifecycle agent issues **three concurrent MCP tool calls** (BQ user enrichment + RAG playbook lookup + Customer.io campaign membership) before synthesizing a draft.

**Reasoning:**
- All three are read-only, independent, and required for the synthesis prompt — sequential would waste latency.
- Demonstrates the JD's named pattern: "parallel fan-out".
- The synthesis call is cache-friendly (same system prompt + retrieved playbooks per signal type), so prompt caching + parallel fan-out compound the latency win.

**Trade-off:** error handling is harder. If one of the three fails we choose to proceed with partial context rather than fail-closed (and we annotate the trace so the dashboard can count partial-context completions).

---

## RAG: pgvector + Vertex AI embeddings

**Status:** committed.

Retrieval is **pgvector on Cloud SQL** with embeddings from **Vertex AI `text-embedding-004`**.

**Reasoning:**
- **GCP-native end-to-end.** No extra vendor, no extra API key, reuses the same ADC the agents use for BigQuery. One IAM story, one secret rotation cadence.
- **pgvector over a dedicated vector DB.** The corpus is small (dozens to low hundreds of docs); a Postgres extension is operationally simpler than running Pinecone / Weaviate / Qdrant. We can swap in AlloyDB or a dedicated store later if scale demands.
- **`text-embedding-004` over Voyage / OpenAI.** Comparable quality, native auth, no cross-vendor data movement.

---

## Why TypeScript for the Slack approval app

**Status:** committed.

The Slack HITL UI is a **TypeScript Bolt app** sitting alongside the Python services.

**Reasoning:**
- Slack Bolt has first-class TypeScript support; the Python Bolt SDK is a step behind for Block Kit interactivity.
- The JD requires "Strong proficiency in Python and JavaScript/Node.js" — splitting the user-facing surface into TS gives us a real, non-trivial Node service rather than a token Hello World.
- Block Kit + interactivity is the natural place to demonstrate the "frontend frameworks" bonus.
- Architectural cleanliness: the user-facing channel is isolated from the agent runtime by a process boundary, not just a function boundary.

---

## Eval as a first-class loop

**Status:** committed.

A golden set, an LLM-judge, a Mimir metric, a Grafana alert, and a GitHub Actions PR check — the same regression bar code changes face.

**Reasoning:**
- The JD lists "model evaluation, prompt iteration" alongside logging and metrics. They're treated as one observability stack.
- Without an eval gate, prompt changes are unreviewed merges by definition. With one, prompts are first-class engineering artifacts.
- Pushing eval results into Mimir means the same dashboard that shows cost and latency shows quality, and the same alerting fabric flags regressions.

---

## Why LGTM for AI specifically

**Status:** committed.

We use Grafana's stack to observe AI workloads, not generic AI-observability tooling (LangSmith, W&B, etc.).

**Reasoning:**
- **The team already runs it.** A reviewer at Grafana doesn't need a tool walkthrough to evaluate the work.
- **Unified pane.** The same Grafana that watches the application's request latency watches the LLM's token cost. No tab switching, no context loss when an incident spans both.
- **OTel as the contract.** We emit OTel genai semantic conventions; any LGTM consumer (or any other OTel-compatible backend) can ingest. We aren't locked in.

---

## Eval as code, not as a notebook

**Status:** committed.

`grafanagent eval` is a first-class CLI command with two modes: deterministic `rule` (rule-table lookup, runs offline, ~50ms) and full `llm` (router fallback chain + Sonnet judge with a 4-dimension rubric, ~30s at concurrency 3). Both emit `grafanagent_eval_*` metrics labelled `set` + `mode` so rule-mode from every PR and llm-mode from the nightly cron coexist in the same Grafana dashboard without collision.

**Reasoning:**
- **Prompt changes need the same regression bar as code changes.** Without this gate, every prompt edit is an unreviewed merge by definition.
- **Two modes, one contract.** CI gets a deterministic check that fails fast; the nightly gets the full LLM judge that can surface calibration drift.
- **Results in Mimir.** The same dashboard that shows cost and latency shows quality. The alert rule that fires on pass-rate regression uses the same infrastructure as the cost-spike alert.

**Trade-off:** the judge is itself an LLM, so its scoring drifts over time. We mitigate by pinning the judge model and keeping the rubric explicit + short. Long-term, a small set of human-annotated "canary" cases should catch judge drift itself.

---

## Cache-aware cost model

**Status:** committed.

`observability.cost.cost_breakdown()` returns a 4-bucket breakdown (input, output, cache-read, cache-write) with Anthropic's real multipliers (cache-read = 10% of input, cache-write = 125% of input). Every LLM call emits four `grafanagent_llm_cost_usd_total` counter points labelled by `bucket` + `agent` + `model`, so the Grafana cost panel can show exactly how much prompt caching is saving at a glance.

**Reasoning:**
- **Caching is a real cost knob, not a vibe.** Without per-bucket breakdown, the dashboard would show total cost and the cache would look invisible. With it, toggling `cache_system=True` on a call shows up as a step function in the cache-write line the first time and cache-read savings thereafter.
- **Unknown-model safety.** If a new model ships before we update the price table, cost reports zero — telemetry never breaks a request or crashes an agent.

---

## Per-signal attribution via contextvars

**Status:** committed.

`observability.signal_context(signal_id, signal_type)` sets Python `contextvars`. The router and every skill orchestrator scope their request body in that context; the LLM wrapper reads `current_signal_id()` on every call and writes it as both a span attribute and a metric label. A dedicated `grafanagent_signal_cost_usd_total` counter drives the "top-10 most expensive signals" table in the dashboard.

**Reasoning:**
- **Context survives `asyncio.gather`.** Python's contextvars propagate through task boundaries by default, which is exactly what lifecycle's parallel fan-out needs. An explicit argument-threading approach would have meant plumbing a `signal_id` through every MCP call — ugly and error-prone.
- **"What did this one signal cost?"** is the single most useful question in a per-user cost demo, and answering it well is the thing that will surprise a reviewer during the interview.

---

## Cloud Run over Cloud Functions

**Status:** committed.

All seven services run on Cloud Run (v2), not Cloud Functions.

**Reasoning:**
- **Container images are the deploy unit.** One Dockerfile template, SERVICE_MODULE build arg, consistent across services — vs. Functions' source-deploy model which couples packaging to the platform.
- **MCP's streamable-HTTP transport needs long-lived request handling.** Cloud Run gives us per-request timeouts up to 60 minutes and keeps connections open for SSE. Cloud Functions' request model is tighter.
- **Same image runs locally, in docker-compose, and in Cloud Run.** `make smoke` exercises the exact binary the production service runs.
- **Scaling semantics match.** `min_instances=0` means we pay nothing when idle (same as Functions); `max_instances` bounds the retry-storm blast radius.

---

## Atomic revision cutover, no canary

**Status:** committed.

Every Cloud Run service uses `TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST`. A `make deploy` tagged with a new git SHA flips 100% of traffic atomically.

**Reasoning:**
- **Canary without an eval gate is theatre.** We have one — the golden-set LLM eval in CI — and it catches prompt regressions before the image ever gets pushed.
- **Seven services × canary ratios = operational complexity we don't need yet.** When the project grows to a scale where this matters, Cloud Run's built-in `traffic { ... }` block supports weighted revisions without rewriting the module.
- **Rollback is image-tag-scoped.** `terraform apply -var image_tag=sha-lastgood` reverts every service at once. Simpler than managing per-service canary state.

---

## Secret values never in Terraform state

**Status:** committed.

The Secret Manager module declares secret *shells* (empty `google_secret_manager_secret` resources). Values go in out-of-band with `gcloud secrets versions add` — the state file never contains a key.

**Reasoning:**
- **Rotation without `terraform apply`.** A secret rotation touches Secret Manager only; Terraform stays untouched, avoiding unnecessary diffs and locking contention.
- **State is a shared artifact.** In team contexts, anyone with read access to the remote state could otherwise grep out every key. The tfvars file isn't a safer home — it'd live in source control or CI secrets. The current pattern is safer by construction.

---

## Pub/Sub DLQ with a 10-retry cap

**Status:** committed.

The push subscription retries for up to 10 minutes with exponential backoff; after 10 failed deliveries a message routes to a dead-letter topic with a 30-day retention audit subscription.

**Reasoning:**
- **Bad payloads can't wedge the main subscription.** Without a DLQ, a poison pill keeps retrying forever, eating quota and obscuring real traffic.
- **30 days is long enough for a human to triage.** The DLQ audit subscription is the entrypoint for the `grafanagent-hitl-escalation-spike` alert investigation path.
- **10 retries matches the runtime budget.** Cloud Run's request timeout + tenacity's retry window inside the agent are shorter; 10 retries covers the gap for genuinely transient upstream failures.

---

## `grafanagent` CLI as the demo driver

**Status:** committed.

The CLI is installed as a console script via `pyproject.toml`'s `[project.scripts]`. Five subcommands: `trigger`, `replay`, `list`, `describe`, `eval`.

**Reasoning:**
- **The JD explicitly lists CLIs alongside Slack + dashboards as skill-invocation surfaces.** Building it this way — not as a standalone script — means the agent surface is genuinely multi-modal.
- **Grep-able registry.** `cli/_registry.py::AGENTS` is a dataclass list, not a decorator auto-discovery. Renaming an agent fails loudly at import time, not silently at command-dispatch.
- **`grafanagent eval --mode rule` is the CI gate.** The same command a developer runs locally is the one that runs in Actions. No bash-wrapper drift.

---

## What we deliberately are not building

- **No LangChain / CrewAI / n8n / Temporal.** Anthropic SDK + MCP + Cloud Run + Pub/Sub is the bet. Documented above.
- **No Salesforce / HubSpot integration.** Customer.io is sufficient proof of "marketing platform integration"; adding more CRMs is template work, not new signal.
- **No real customer data.** Synthetic users only; PII redaction exists for demo authenticity.
- **No multi-region or multi-tenant isolation.** Single project, single region, single tenant. Documented as out-of-scope so it's a deliberate gap, not an oversight.

---

## Decisions deferred

- **Pub/Sub vs. direct HTTP for signal ingestion.** Currently both work — `grafanagent trigger` POSTs directly; production listens on a Pub/Sub push subscription. We keep both paths.
- **Caching strategy for RAG retrieval.** First pass: no cache. If retrieval latency becomes the bottleneck, add a small in-memory LRU keyed by `signal_type + hash(query)`.
- **Authentication on the router endpoint.** First pass: Cloud Run IAM with service-account-only invocation. If we ever expose externally, add a signed-webhook layer.
