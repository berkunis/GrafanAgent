"""Single source of truth for what the CLI lists / describes.

Kept as plain data so tests can assert against it and new agents/MCP servers
show up in the CLI the moment they register here.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSpec:
    name: str
    kind: str              # "router" or "skill"
    model: str | None
    default_port: int
    module: str
    description: str


@dataclass(frozen=True)
class McpSpec:
    name: str
    default_port: int
    module: str
    description: str
    tools: tuple[str, ...]


AGENTS: tuple[AgentSpec, ...] = (
    AgentSpec(
        name="router",
        kind="router",
        model="claude-haiku-4-5",
        default_port=8000,
        module="agents.router.app:create_app",
        description="Classifies signals with a Haiku→Sonnet→rule→HITL fallback chain.",
    ),
    AgentSpec(
        name="lifecycle",
        kind="skill",
        model="claude-sonnet-4-5",
        default_port=8001,
        module="agents.lifecycle.app:create_app",
        description="Parallel fan-out over BQ + RAG + Customer.io; Sonnet synthesis; HITL-gated.",
    ),
    AgentSpec(
        name="lead_scoring",
        kind="skill",
        model="claude-sonnet-4-5",
        default_port=8002,
        module="agents.lead_scoring.app:create_app",
        description="Fan-out over BQ + RAG; Sonnet emits LeadScore (fit_score, priority, drivers); HITL gates high-priority SDR alerts.",
    ),
    AgentSpec(
        name="attribution",
        kind="skill",
        model="claude-sonnet-4-5",
        default_port=8003,
        module="agents.attribution.app:create_app",
        description="Fan-out over BQ + RAG; Sonnet produces AttributionReport with first/last/multi-touch + verdict; posts to RevOps Slack.",
    ),
)

MCP_SERVERS: tuple[McpSpec, ...] = (
    McpSpec(
        name="bigquery",
        default_port=8081,
        module="mcp_servers.bigquery.server:create_app",
        description="Read-only SQL with dataset allow-list + PII redaction.",
        tools=("query", "describe_table", "list_signals"),
    ),
    McpSpec(
        name="customer_io",
        default_port=8082,
        module="mcp_servers.customer_io.server:create_app",
        description="Customer.io sandbox-only; idempotent writes keyed by signal_id.",
        tools=("create_campaign_draft", "trigger_broadcast", "add_to_segment", "get_campaign_membership"),
    ),
    McpSpec(
        name="slack",
        default_port=8083,
        module="mcp_servers.slack.server:create_app",
        description="Proxies the TypeScript Bolt approval app for HITL gating.",
        tools=("request_approval", "get_approval_status", "wait_for_approval", "cancel_approval", "mark_executed"),
    ),
)


def agent_by_name(name: str) -> AgentSpec | None:
    for a in AGENTS:
        if a.name == name:
            return a
    return None


def mcp_by_name(name: str) -> McpSpec | None:
    for m in MCP_SERVERS:
        if m.name == name:
            return m
    return None
