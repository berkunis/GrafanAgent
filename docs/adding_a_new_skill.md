# Adding a new skill agent

A concrete replay of the Phase 7 lead-scoring + attribution adds. Follow this
when you need a fourth/fifth skill alongside `lifecycle` / `lead_scoring` /
`attribution` — the total time, following this doc, is under an hour.

## The template

Every skill agent follows the same shape, which makes reviewing a new agent's
PR a diff against the template rather than a design exercise:

```
agents/<skill>/
  ├── __init__.py          # empty
  ├── schemas.py           # Pydantic models: Task, Enrichment, <SkillOutput>, ...
  ├── agent.py             # Sonnet synthesis — one function, takes Enrichment, returns the structured decision
  ├── orchestrator.py      # fan-out (asyncio.gather) → synthesize → optional HITL → optional execution
  ├── app.py               # create_app(orchestrator=None) FastAPI factory with POST /run + /healthz
  └── main.py              # SMOKE=1 boot; uvicorn on $PORT otherwise
```

## Checklist

1. **Confirm the signal types the skill owns**
   - Add them to `agents/router/rules.py::RULE_TABLE` so the deterministic rung picks them up.
   - Add one golden-set case per signal type to `evals/golden_set.jsonl`.

2. **Author the RAG playbook(s)**
   - Markdown with frontmatter — `slug`, `signal_types`, `audience`, `channel`.
   - Body uses `##` H2 sections: Trigger, Audience cut, Scoring rubric or Analysis rubric,
     Recommended action, Guardrails, Success metric. The ingester splits on H2.
   - Drop in `rag/corpus/<slug>.md`. `make ingest` picks it up.

3. **Write `schemas.py`**
   - `<Skill>Task` (wraps the router's Signal + RoutingDecision).
   - An `Enrichment` dataclass capturing every fan-out leg's output + a `partial: bool`
     flag + an `errors: dict` so degraded runs are visible.
   - The structured output the Sonnet tool-use call emits (`LeadScore`, `AttributionReport`, ...).
   - A `<Skill>Output` with at least: `signal_id`, `enrichment`, the structured output,
     `latency_ms`, and (if HITL-gated) the HITL fields from `lifecycle.schemas` for shape
     parity.

4. **Write `agent.py`**
   - Keep it to one function: `synthesize_*(llm, task, enrichment, model=...) -> <Output>`.
   - System prompt is one string constant at module top. `cache_system=True` always.
   - Use forced tool-use (`tool_name="record_*"`) via `llm.structured_output(...)` — never
     ask the model for freeform JSON.

5. **Write `orchestrator.py`**
   - Wrap `run()` body in:
     ```python
     with signal_context(task.signal.id, task.signal.type), \
          _tracer.start_as_current_span("<skill>.run") as span:
     ```
     Every downstream LLM/MCP call will inherit the signal labels for the Mimir cost
     panel and the Tempo trace filter.
   - Fan-out with `asyncio.gather(..., return_exceptions=True)`. Translate exceptions
     into `errors[leg]` entries; never raise out of `_enrich()`.
   - If the skill gates on HITL, check `self._hitl is not None` and follow the lifecycle
     pattern: request → wait → on approved execute + mark_executed.
   - If only some outputs gate on HITL (e.g. lead_scoring: only `priority == "high"`),
     branch on the structured output before requesting approval.

6. **Write `app.py` + `main.py`**
   - Copy the lifecycle versions, swap the imports. The `create_app(orchestrator=None)`
     factory pattern makes tests trivial and keeps the production entrypoint ≤ 30 lines.

7. **Register in the CLI**
   - `cli/_registry.py::AGENTS` — add an `AgentSpec` entry so `grafanagent list agents`
     and `describe agent <name>` pick it up.
   - (Optional) extend `describe_agent` in `cli/commands/describe.py` with an
     orchestration panel so `describe agent <skill>` shows the fan-out legs,
     synthesis model, and HITL policy.

8. **Write tests**
   - `tests/<skill>/test_orchestrator.py` mirrors the lifecycle suite:
     - happy path: fan-out + synthesis + execution.
     - partial-failure path: one leg raises → enrichment marks `partial=True`, downstream
       still runs.
     - HITL paths: approved → execute; rejected/timed_out → skip execute.
     - Any skill-specific invariants (e.g. attribution weights sum to 1.0).
   - Re-use the `ScriptedMcp` pattern from the lifecycle tests — route
     `(server, tool) → canned response` with a record list for assertions.

9. **Update documentation**
   - `README.md` architecture diagram if the skill adds a new MCP server or signal source.
   - `docs/DESIGN.md` — a short paragraph on any new design decision (e.g. "lead-scoring
     only gates HITL on `priority='high'` because the playbook says low-fit leads should
     drop to nurture silently").
   - This doc, if the template itself evolved.

10. **Smoke + eval + commit**
    ```bash
    SMOKE=1 python -m agents.<skill>.main
    pytest -q
    grafanagent eval                              # rule-mode regression catches unmapped signals
    grafanagent describe agent <skill>            # manual visual check
    git add . && git commit -m "Phase N: <skill> agent"
    ```

## Worked examples

- **Lifecycle** (Phase 2) — three-leg fan-out (BQ + RAG + Customer.io), HITL on every draft,
  executes via `trigger_broadcast`. See `agents/lifecycle/orchestrator.py`.
- **Lead-scoring** (Phase 7) — two-leg fan-out (BQ + RAG), **priority-conditional HITL**
  (only `high`), priority-conditional execution (`low` drops to nurture silently). See
  `agents/lead_scoring/orchestrator.py`.
- **Attribution** (Phase 7) — two-leg fan-out (BQ + RAG), **no HITL** (reports are
  informational), posts directly to the RevOps Slack channel. Validates that multi-touch
  weights sum to 1.0 via a Pydantic `@field_validator`. See
  `agents/attribution/orchestrator.py`.

## Anti-patterns we deliberately avoided

- ❌ A shared "SkillOrchestrator" base class. The three skills vary in fan-out leg count,
  HITL policy, and execution path — the abstraction ran ahead of the concrete uses. We
  pay some duplication to keep each orchestrator independently readable.
- ❌ A registry decorator like `@skill("lifecycle")` that auto-discovers agents. The
  single `cli/_registry.py` dataclass list is explicit, grep-able, and survives a
  rename without a hidden-import failure.
- ❌ One big Sonnet prompt that handles every skill by switching on `task.signal.type`.
  Each skill's rubric belongs next to its code, not folded into a megaprompt.
