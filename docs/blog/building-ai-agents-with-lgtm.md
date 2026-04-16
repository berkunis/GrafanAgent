# Building production AI agents with the Grafana LGTM stack

*A working reference for how to observe, govern, and regression-test a multi-agent system without reinventing your observability stack.*

---

## The problem with most agent demos

You have seen this talk. Someone ships a multi-agent workflow. It classifies a signal, calls a tool, writes a draft. The demo works. Then the speaker opens LangSmith, or Weights & Biases, or a homegrown dashboard, and says "and here is where we would monitor it in production."

That last bit is the part that never actually ships. Observability gets bolted on after the agent code is written, which is exactly backwards. By the time you realise your prompt is costing $4 per signal and drifting into the wrong skill, you have spent weeks without the telemetry to prove either claim.

I spent a week building [GrafanAgent](https://github.com/berkunis/GrafanAgent) as a reference for the other approach: **observability first, agents second.** Every token, every prompt, every tool call, every dollar, every regression — visible in Grafana before the agent body exists.

The thesis is simple. If you are already running Grafana's LGTM stack for your application, you do not need separate AI observability tooling. You need to emit OpenTelemetry with the genai semantic conventions and you need a disciplined cost model. Both are lightweight. Together they solve the problem the demos skip.

---

## The stack in one picture

```
  Signal (BQ / Pub/Sub / webhook / CLI)
        │
        ▼
  Router (Claude Haiku)
    │ fallback chain
    │   ≥ 0.8 confidence  → dispatch
    │   0.5 – 0.8          → re-ask Sonnet
    │   < 0.5 or disagree  → deterministic rule → HITL
    ▼
  Skill agents (Claude Sonnet)
    ├── Lifecycle       — parallel fan-out: BQ + RAG + Customer.io → synthesise → HITL → execute
    ├── Lead-Scoring    — fan-out: BQ + RAG → score → conditional HITL → SDR alert
    └── Attribution     — fan-out: BQ + RAG → multi-touch report → Slack post
        │
        ▼
  HITL gate (TypeScript Slack Bolt app, Block Kit cards)
        │
        ▼
  Customer.io (sandbox) / Slack post / CRM enrichment

  Observability (OTel → Grafana Cloud):
    Tempo — every anthropic.* span carries gen_ai.prompt + gen_ai.completion events
    Loki  — PII-scrubbed JSON logs
    Mimir — grafanagent_llm_{tokens,cost,calls,latency}, router_rung, eval scores
```

Seven Cloud Run services (four agents + three MCP servers) + one TypeScript Bolt app. Deployable in one `make deploy` command. 145 Python tests + 17 TypeScript tests, all green under a second. Every claim in this post is something the repo's tests enforce or the dashboard renders.

---

## What observability first actually looks like

The shared LLM wrapper at [`agents/_llm.py`](https://github.com/berkunis/GrafanAgent/blob/main/agents/_llm.py) is the centre of mass. Every call to Anthropic — from any agent, anywhere — flows through it. In return, every call gets:

- **OTel span with genai semantic conventions.** `gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.cache_read_input_tokens`, `gen_ai.response.finish_reasons`, plus a `gen_ai.prompt` event containing the serialised messages and a `gen_ai.completion` event containing the response. Click any span in Tempo, see exactly what we sent and what came back.
- **Cache-aware cost counter.** Four buckets (input, output, cache-read, cache-write) with Anthropic's real multipliers. The Grafana cost panel breaks down spend per bucket so you can *see* prompt caching working.
- **Latency histogram.** p50 / p95 / p99 come from metrics, not trace sampling.
- **Per-signal attribution.** A `contextvars.ContextVar` called `signal_context` rides downstream through `asyncio.gather`; every LLM call inherits the signal ID as a metric label. The dashboard answers "what did this one signal cost?" directly.

None of this is a framework. It is 280 lines of Python that sits between agents and the Anthropic SDK. The design principle: **if you can't see a token, a dollar, or a decision in Grafana, it does not exist.**

---

## The explicit fallback chain

Most agent router patterns I have seen use a single LLM call with a confidence threshold: "if confidence ≥ X, dispatch; else escalate to a human." That works until the model is overconfident on a wrong answer, which is the whole problem with calibration.

GrafanAgent's router uses an explicit four-rung ladder:

1. **Haiku classification.** Confidence ≥ 0.8 dispatches immediately.
2. **Sonnet re-ask.** If Haiku was 0.5 – 0.8, ask Sonnet the same question. If Sonnet agrees with Haiku's skill, dispatch. If Sonnet picks a different skill, use Sonnet's decision.
3. **Deterministic rule table.** If both LLMs were below 0.5, look up the signal type in a hand-curated mapping. The rule rung is the non-LLM safety net — we never page a human for a signal type that has an obvious owner.
4. **HITL escape hatch.** If no rule matches, route to a Slack approval queue with both LLMs' decisions attached.

Every rung increments a Mimir counter labelled by rung. The Grafana dashboard shows rung usage as a timeseries, which immediately surfaces prompt drift: if sonnet + rule escalations spike, the Haiku prompt has gotten less calibrated. We fire an alert when HITL share exceeds 20 percent over 15 minutes.

Any production LLM path needs named mitigations for low-confidence outputs. "Confidence threshold + fallback + escalation" is the canonical trio, but the common implementation is "ask LLM, check a number, maybe page someone" — which collapses the three into one decision at one threshold. The explicit-ladder version keeps each rung a first-class, countable, alertable unit.

---

## Eval as first-class code

The most unusual part of the project, and the one I think matters most for production AI work.

GrafanAgent ships a CLI subcommand, `grafanagent eval`, with two modes. The deterministic `rule` mode runs the signal type through the router's rule table and passes if the mapping matches the expected skill — fast, offline, zero API cost. Every pull request runs this as a CI gate. The full `llm` mode runs each golden case through the real Haiku + Sonnet fallback chain, then scores the decision with a Sonnet-as-judge using an explicit 4-dimension rubric (skill correctness, confidence calibration, rationale quality, overall). Results land in Mimir.

A nightly GitHub Actions workflow runs the LLM-judge mode against the deployed services and pushes metrics to Grafana Cloud. The dashboard has a pass-rate gauge, a per-skill bar, and a per-dimension trendline. An alert rule fires when the pass rate drops below 85 percent sustained for 15 minutes, with a runbook link explaining how to triage.

This closes the loop the demos leave open. Prompt changes go through the same regression bar as code changes. The eval is not a notebook someone ran once — it is a command, a metric, an alert, and a runbook.

---

## The HITL state machine

Human-in-the-loop is where things get serious. GrafanAgent's HITL gate is a TypeScript Slack Bolt app with a full state machine — `draft → posted → approved | rejected | edited | timed_out → executed | cancelled`. Disallowed transitions throw. A stale-approval reaper moves anything past its TTL to `timed_out`.

The UI is Block Kit: a rich approval card with user context, draft preview, approve / reject / edit buttons, and a three-field edit modal. When an operator edits a draft, the new content round-trips through the Python orchestrator into the outbound Customer.io payload — the edit is authoritative, not advisory.

Two things worth calling out. First, the HITL policy varies by skill. Lifecycle gates every draft. Lead-scoring gates only high-priority SDR alerts — medium fires without a human gate, low drops to nurture silently because the playbook says "do not ping a human." Attribution has no HITL at all because the reports are informational. Three skills, three policies, one state machine.

Second, the Bolt app is TypeScript. Slack's Bolt SDK has first-class TypeScript support; Block Kit modals are natural in the language the ecosystem treats as primary. Splitting the user-facing surface off the Python runtime also means the HITL channel is isolated by a process boundary, not just a function boundary — one less thing that can go wrong during a deploy.

---

## Things I deliberately did not build

- **No LangChain / CrewAI.** Anthropic SDK + MCP is the bet. Every framework abstraction is a place where OTel attribution gets lossy.
- **No n8n / Workato / Temporal.** Pub/Sub + Cloud Run is the orchestration layer.
- **No Salesforce integration.** Customer.io is sufficient proof of "marketing platform integration." Adding more CRMs is template work.
- **No canary deploys.** Atomic revision cutover with eval gate in CI. When the scale justifies canary, Cloud Run supports weighted revisions without rewriting the module.
- **No shared SkillOrchestrator base class.** The three skills vary in fan-out leg count, HITL policy, and execution path. The abstraction ran ahead of the concrete uses.

---

## What this unlocks

If you already run the LGTM stack for production observability, an AI workload built this way is just another thing you watch on the same dashboards you already have open during an incident. When someone asks "is the lifecycle agent expensive?" the answer is not "let me pull it up in LangSmith" — it's "it's on the cost panel next to the API latency graph."

That is the integration I care about. AI systems are not special infrastructure. They should be observable the same way everything else is. The LGTM stack does not need a special mode for AI. You just need to emit the right telemetry, from the right layer, once.

The repo, tests, dashboards, and runbooks are all at **github.com/berkunis/GrafanAgent**. Built with Claude Code — the authorship model is a working artefact of the collaboration: every line has a human owner who read it, wrote the "why" in the commit message, and answers questions on the review.

---

*Isil Berkun — April 2026*
