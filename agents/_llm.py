"""Shared Anthropic client wrapper.

Every LLM call in GrafanAgent goes through here so it inherits:

- OTel spans following the genai semantic conventions (gen_ai.* attrs),
  including cache-read / cache-creation tokens and the list of tools offered.
- Token + dollar cost recorded as both span attrs and Mimir counters,
  broken down by cache vs non-cache buckets for the Grafana cost panel.
- Latency recorded as a histogram so the dashboard gets real p50/p95/p99
  derived from metrics, not trace-sampling.
- Per-signal attribution via `observability.signal_context(...)` — the
  active signal_id rides on every metric label and span attr.
- Optional structured output via Anthropic tool-forcing.
- Optional prompt caching on system messages (`cache_system=True`).
- Tenacity retries on transient API errors.

The wrapper is intentionally thin — it does not hide the Anthropic SDK;
agents still see real `Message` objects. We only wrap the things every call
needs.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from anthropic import APIError, APIStatusError, AsyncAnthropic
from anthropic.types import Message
from opentelemetry import metrics, trace
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from observability.cost import cost_breakdown
from observability.signal_ctx import current_signal_id

_tracer = trace.get_tracer("agents._llm")
_meter = metrics.get_meter("agents._llm")

_tokens_counter = _meter.create_counter(
    "grafanagent_llm_tokens_total",
    unit="{token}",
    description="LLM tokens consumed by GrafanAgent calls.",
)
_cost_counter = _meter.create_counter(
    "grafanagent_llm_cost_usd_total",
    unit="USD",
    description="Estimated USD spend on LLM calls.",
)
_call_counter = _meter.create_counter(
    "grafanagent_llm_calls_total",
    description="Number of LLM calls dispatched.",
)
_latency_hist = _meter.create_histogram(
    "grafanagent_llm_latency_seconds",
    unit="s",
    description="Wall-clock latency of Anthropic messages.create calls.",
)
_signal_cost_counter = _meter.create_counter(
    "grafanagent_signal_cost_usd_total",
    unit="USD",
    description=(
        "USD spend attributed to a single signal. Drives the per-signal cost "
        "panel and the cost-spike alert."
    ),
)


class LLMError(RuntimeError):
    """Raised when an LLM call fails after retries or returns an unparseable response."""


class LLMClient:
    """Thin wrapper over `AsyncAnthropic`. Construct once per service.

    Inject a fake `client` in tests; production wiring uses the default
    `AsyncAnthropic()` which reads ANTHROPIC_API_KEY from env.
    """

    def __init__(self, *, client: AsyncAnthropic | None = None, agent: str = "unknown"):
        self._client = client or AsyncAnthropic()
        self._agent = agent

    # ---------- public API ----------

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        system: str | list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        cache_system: bool = False,
        operation: str = "chat",
    ) -> Message:
        """Plain chat completion with OTel + cost instrumentation."""
        return await self._call(
            model=model,
            messages=messages,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
            tool_choice=tool_choice,
            cache_system=cache_system,
            operation=operation,
        )

    async def structured_output(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        schema: type[BaseModel],
        system: str | None = None,
        tool_name: str = "record_decision",
        max_tokens: int = 1024,
        temperature: float = 0.0,
        cache_system: bool = False,
    ) -> BaseModel:
        """Force the model to emit a JSON object matching `schema` via tool use.

        Returns an instance of `schema`. Raises `LLMError` if the model refuses,
        emits no tool call, or returns JSON that does not validate.
        """
        json_schema = schema.model_json_schema()
        tool = {
            "name": tool_name,
            "description": (schema.__doc__ or f"Record a {schema.__name__}.").strip(),
            "input_schema": _strip_pydantic_meta(json_schema),
        }
        message = await self._call(
            model=model,
            messages=messages,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool_name},
            cache_system=cache_system,
            operation="structured_output",
        )

        for block in message.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
                try:
                    return schema.model_validate(block.input)
                except Exception as exc:  # noqa: BLE001
                    raise LLMError(f"structured output failed validation: {exc}") from exc

        raise LLMError(
            f"model returned no tool_use block for tool {tool_name!r}; got "
            f"{[getattr(b, 'type', '?') for b in message.content]}"
        )

    # ---------- internal ----------

    @retry(
        retry=retry_if_exception_type((APIStatusError, APIError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )
    async def _call(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        system: str | list[dict[str, Any]] | None,
        max_tokens: int,
        temperature: float,
        tools: list[dict[str, Any]] | None,
        tool_choice: dict[str, Any] | None,
        cache_system: bool,
        operation: str,
    ) -> Message:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system is not None:
            kwargs["system"] = _as_cached_system(system) if cache_system else system
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        signal_id = current_signal_id()
        base_attrs: dict[str, Any] = {"agent": self._agent, "model": model}
        if signal_id:
            base_attrs["grafanagent.signal_id"] = signal_id

        with _tracer.start_as_current_span(f"anthropic.{operation}") as span:
            span.set_attribute("gen_ai.system", "anthropic")
            span.set_attribute("gen_ai.operation.name", operation)
            span.set_attribute("gen_ai.request.model", model)
            span.set_attribute("gen_ai.request.max_tokens", max_tokens)
            span.set_attribute("gen_ai.request.temperature", temperature)
            span.set_attribute("grafanagent.agent", self._agent)
            if signal_id:
                span.set_attribute("grafanagent.signal_id", signal_id)
            if tools:
                span.set_attribute("gen_ai.tools", [t.get("name", "") for t in tools])
            if tool_choice:
                span.set_attribute("gen_ai.request.tool_choice", tool_choice.get("name") or tool_choice.get("type", ""))
            span.add_event("gen_ai.prompt", {"messages_json": _safe_json(messages)})

            started = time.perf_counter()
            try:
                message = await self._client.messages.create(**kwargs)
            except Exception as exc:
                elapsed = time.perf_counter() - started
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                _latency_hist.record(elapsed, {**base_attrs, "outcome": "error"})
                _call_counter.add(1, {**base_attrs, "outcome": "error"})
                raise

            elapsed = time.perf_counter() - started
            usage = message.usage
            usage_in = getattr(usage, "input_tokens", 0) or 0
            usage_out = getattr(usage, "output_tokens", 0) or 0
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
            cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0

            breakdown = cost_breakdown(
                model,
                input_tokens=usage_in,
                output_tokens=usage_out,
                cache_creation_tokens=cache_create,
                cache_read_tokens=cache_read,
            )
            total_usd = breakdown.total_usd

            # ---- span attrs (OTel genai semantic conventions) ----
            span.set_attribute("gen_ai.response.id", message.id)
            span.set_attribute("gen_ai.response.model", message.model)
            if message.stop_reason:
                span.set_attribute("gen_ai.response.finish_reasons", [message.stop_reason])
            span.set_attribute("gen_ai.usage.input_tokens", usage_in)
            span.set_attribute("gen_ai.usage.output_tokens", usage_out)
            if cache_read:
                span.set_attribute("gen_ai.usage.cache_read_input_tokens", cache_read)
            if cache_create:
                span.set_attribute("gen_ai.usage.cache_creation_input_tokens", cache_create)
            span.set_attribute("grafanagent.cost_usd", total_usd)
            span.set_attribute("grafanagent.cost_usd.input", breakdown.input_usd)
            span.set_attribute("grafanagent.cost_usd.output", breakdown.output_usd)
            if breakdown.cache_read_usd:
                span.set_attribute("grafanagent.cost_usd.cache_read", breakdown.cache_read_usd)
            if breakdown.cache_write_usd:
                span.set_attribute("grafanagent.cost_usd.cache_write", breakdown.cache_write_usd)
            span.set_attribute("grafanagent.latency_s", elapsed)
            span.add_event("gen_ai.completion", {"content_json": _safe_json(_serialize_content(message))})

            # ---- metrics ----
            _tokens_counter.add(usage_in, {**base_attrs, "direction": "input"})
            _tokens_counter.add(usage_out, {**base_attrs, "direction": "output"})
            if cache_read:
                _tokens_counter.add(cache_read, {**base_attrs, "direction": "cache_read"})
            if cache_create:
                _tokens_counter.add(cache_create, {**base_attrs, "direction": "cache_write"})

            _cost_counter.add(breakdown.input_usd, {**base_attrs, "bucket": "input"})
            _cost_counter.add(breakdown.output_usd, {**base_attrs, "bucket": "output"})
            if breakdown.cache_read_usd:
                _cost_counter.add(breakdown.cache_read_usd, {**base_attrs, "bucket": "cache_read"})
            if breakdown.cache_write_usd:
                _cost_counter.add(breakdown.cache_write_usd, {**base_attrs, "bucket": "cache_write"})

            _latency_hist.record(elapsed, {**base_attrs, "outcome": "ok"})
            _call_counter.add(1, {**base_attrs, "outcome": "ok"})

            if signal_id and total_usd > 0:
                _signal_cost_counter.add(
                    total_usd,
                    {
                        "agent": self._agent,
                        "model": model,
                        "grafanagent.signal_id": signal_id,
                    },
                )

            return message


# ---------- helpers ----------


def _as_cached_system(system: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Wrap a system prompt with cache_control so Anthropic caches it."""
    if isinstance(system, str):
        return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    out = []
    for block in system:
        new = dict(block)
        new.setdefault("cache_control", {"type": "ephemeral"})
        out.append(new)
    return out


def _strip_pydantic_meta(schema: dict[str, Any]) -> dict[str, Any]:
    """Pydantic emits $defs / title fields that Anthropic ignores; keep the schema lean."""
    schema = dict(schema)
    schema.pop("title", None)
    return schema


def _serialize_content(message: Message) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for block in message.content:
        block_type = getattr(block, "type", "unknown")
        if block_type == "text":
            out.append({"type": "text", "text": getattr(block, "text", "")})
        elif block_type == "tool_use":
            out.append(
                {
                    "type": "tool_use",
                    "name": getattr(block, "name", ""),
                    "input": getattr(block, "input", {}),
                }
            )
        else:
            out.append({"type": block_type})
    return out


def _safe_json(value: Any) -> str:
    """Best-effort JSON for span events. Truncates oversized payloads to keep
    Tempo storage sane; full payload still goes to Loki via the structured logger."""
    try:
        s = json.dumps(value, default=str)
    except Exception:  # noqa: BLE001
        s = repr(value)
    limit = int(os.getenv("GRAFANAGENT_SPAN_PAYLOAD_LIMIT", "8000"))
    return s if len(s) <= limit else s[:limit] + "...[truncated]"
