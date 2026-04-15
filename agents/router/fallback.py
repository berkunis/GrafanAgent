"""Fallback chain — the explicit degradation ladder for the router.

Confidence-driven escalation:

    Haiku ≥ 0.8                               → dispatch
    0.5 ≤ Haiku < 0.8                         → re-ask Sonnet
        Sonnet agrees with Haiku's skill      → dispatch
        Sonnet picks a different skill        → use Sonnet's decision
    Haiku < 0.5  OR  Sonnet < 0.5             → deterministic rule table
        Rule matches                          → dispatch
        Rule misses                           → HITL queue

Every rung is a span and increments a Mimir counter labeled by `rung`. That
way the dashboard shows fallback usage at a glance and an alert can fire if
HITL escalations spike.
"""
from __future__ import annotations

from dataclasses import dataclass

from opentelemetry import metrics, trace
from opentelemetry.trace import Status, StatusCode

from agents._llm import LLMClient
from agents.router.classifier import classify
from agents.router.rules import rule_lookup
from agents.router.schemas import FallbackRung, RoutingDecision, Signal

_tracer = trace.get_tracer("agents.router.fallback")
_meter = metrics.get_meter("agents.router.fallback")
_rung_counter = _meter.create_counter(
    "grafanagent_router_rung_total",
    description="Number of router classifications resolved at each fallback rung.",
)

# Sensible defaults; override via constructor or env in main.py.
DEFAULT_HAIKU_MODEL = "claude-haiku-4-5"
DEFAULT_SONNET_MODEL = "claude-sonnet-4-5"
DEFAULT_HIGH_CONFIDENCE = 0.8
DEFAULT_MIN_CONFIDENCE = 0.5


@dataclass(frozen=True)
class FallbackResult:
    decision: RoutingDecision
    rung: FallbackRung
    models_consulted: list[str]


@dataclass(frozen=True)
class FallbackConfig:
    haiku_model: str = DEFAULT_HAIKU_MODEL
    sonnet_model: str = DEFAULT_SONNET_MODEL
    high_confidence: float = DEFAULT_HIGH_CONFIDENCE
    min_confidence: float = DEFAULT_MIN_CONFIDENCE


class FallbackChain:
    """Runs a signal through Haiku → Sonnet → rule → HITL until something sticks."""

    def __init__(self, llm: LLMClient, config: FallbackConfig | None = None):
        self._llm = llm
        self._cfg = config or FallbackConfig()

    async def decide(self, signal: Signal) -> FallbackResult:
        cfg = self._cfg
        models_consulted: list[str] = []

        with _tracer.start_as_current_span("router.fallback_chain") as span:
            span.set_attribute("grafanagent.signal_id", signal.id)
            span.set_attribute("grafanagent.signal_type", signal.type)

            # Rung 1: Haiku
            haiku = await self._classify_with_span(
                signal, cfg.haiku_model, "router.haiku"
            )
            models_consulted.append(cfg.haiku_model)
            if haiku.confidence >= cfg.high_confidence:
                return self._finalize(span, haiku, FallbackRung.HAIKU, models_consulted)

            # Rung 2: Sonnet
            sonnet = await self._classify_with_span(
                signal, cfg.sonnet_model, "router.sonnet"
            )
            models_consulted.append(cfg.sonnet_model)
            if sonnet.confidence >= cfg.min_confidence:
                # If Sonnet agrees with Haiku above min_confidence, take Haiku's payload (more specific
                # because Haiku saw the signal first); otherwise take Sonnet's full decision.
                chosen = haiku if sonnet.skill == haiku.skill else sonnet
                return self._finalize(span, chosen, FallbackRung.SONNET, models_consulted)

            # Rung 3: deterministic rule
            ruled = rule_lookup(signal.type)
            if ruled is not None:
                return self._finalize(span, ruled, FallbackRung.RULE, models_consulted)

            # Rung 4: HITL escape hatch
            hitl_decision = RoutingDecision(
                skill="hitl",
                confidence=max(haiku.confidence, sonnet.confidence),
                rationale=(
                    f"Both LLMs uncertain (haiku={haiku.confidence:.2f}, "
                    f"sonnet={sonnet.confidence:.2f}) and no rule matches signal type "
                    f"'{signal.type}'. Escalating for human review."
                ),
                payload={"haiku": haiku.model_dump(), "sonnet": sonnet.model_dump()},
            )
            span.set_status(Status(StatusCode.OK, "escalated to HITL"))
            return self._finalize(span, hitl_decision, FallbackRung.HITL, models_consulted)

    # ---------- internal ----------

    async def _classify_with_span(
        self, signal: Signal, model: str, span_name: str
    ) -> RoutingDecision:
        with _tracer.start_as_current_span(span_name) as span:
            decision = await classify(llm=self._llm, signal=signal, model=model)
            span.set_attribute("grafanagent.decision.skill", decision.skill)
            span.set_attribute("grafanagent.decision.confidence", decision.confidence)
            return decision

    def _finalize(
        self,
        span: trace.Span,
        decision: RoutingDecision,
        rung: FallbackRung,
        models_consulted: list[str],
    ) -> FallbackResult:
        span.set_attribute("grafanagent.fallback.rung", rung.value)
        span.set_attribute("grafanagent.decision.skill", decision.skill)
        span.set_attribute("grafanagent.decision.confidence", decision.confidence)
        _rung_counter.add(1, {"rung": rung.value, "skill": decision.skill})
        return FallbackResult(decision=decision, rung=rung, models_consulted=models_consulted)
