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
