# Good-first-issue seed list

Five curated issues a new contributor can pick up. Each one is small (under a day), touches one area, and leaves the repo more complete rather than less. Open these through GitHub's UI with the `good first issue` label when you want to invite contributors.

---

## 1. Add a `--since` filter to `grafanagent list signals`

**Area:** CLI
**Files:** `cli/commands/list_cmd.py`, `tests/cli/test_list_describe.py`

Today `grafanagent list signals` prints the rule table — a static view of what signal types the router knows. Add a `--since <duration>` flag (e.g. `--since 24h`) that pulls rows from the deployed `signals` BigQuery table through the BQ MCP instead and displays them alongside the rule table, marking any signal type not in the rule table with a `(UNMAPPED)` tag.

Why this is useful: surfaces new signal types that are already firing but haven't been added to the router. Catches the drift we alert on with `grafanagent-hitl-escalation-spike`.

**Acceptance:**
- `--since 24h` default when flag is present without value.
- Unmapped signal types show up with a visible flag in the table.
- One test covering the unmapped-flag rendering.

---

## 2. Add a Loki logs panel to the dashboard

**Area:** Observability
**Files:** `dashboards/grafanagent.json`

The dashboard has a Tempo traces panel but no Loki panel. Add a logs panel that filters on `service.namespace="grafanagent"` + level="error" so incident responders can jump from the error-rate stat to the raw log stream in one click.

**Acceptance:**
- New panel in the Latency & reliability row.
- LogQL query uses the resource attribute, not a hardcoded service.name.
- The `test_dashboard_json.py::test_every_dashboard_expr_references_an_emitted_metric` test still passes (logs panel uses a different datasource, so it should be exempt).

---

## 3. Add a webhook adapter for GitHub Issues as a signal source

**Area:** Signal ingestion
**Files:** new `adapters/github_issues.py` (or similar), `evals/golden_set.jsonl`

Today production signal ingestion goes through Pub/Sub. Add a small FastAPI adapter that accepts a GitHub webhook for issue events, normalises it into a `Signal` payload (signal type `support_ticket_filed`), and posts to the router. Add a golden-set case so the rule table covers it.

**Acceptance:**
- Runs behind a signing-secret check (match the Slack pattern).
- Maps `issue.opened` → `lifecycle`, `issue.labeled("bug")` → `lifecycle`, everything else ignored.
- Golden case + rule-table entry.

---

## 4. Support streaming responses in the LLM wrapper

**Area:** Core
**Files:** `agents/_llm.py`, `tests/test_llm_enriched.py`

Right now `LLMClient.chat()` awaits the full response. Add a `stream=True` flag that returns an async iterator of text deltas and still records the final span with complete usage + cost info.

**Acceptance:**
- Existing non-streaming callers unchanged.
- Span attributes populated once at stream end (on `finish_reason`).
- One test with a scripted fake stream.

---

## 5. Make the BigQuery MCP's PII regex configurable per-caller

**Area:** MCP security
**Files:** `mcp_servers/bigquery/security.py`, `mcp_servers/bigquery/server.py`

Today the PII column regex is fixed in `BQ_PII_COLUMNS_REGEX` at MCP server boot. Allow a stricter regex to be passed per-tool-call (but never looser). For example, the attribution agent might want to additionally redact `company` when aggregating across cohorts.

**Acceptance:**
- Tool accepts an optional `extra_pii_regex` argument.
- The effective regex for a call is the union of the server-default and the per-call override — calls can only tighten, not loosen.
- Two tests covering tighten-succeeds and loosen-is-rejected paths.

---

These are starters, not commitments. If you're looking at something else entirely, open an issue first so we can talk about scope.
