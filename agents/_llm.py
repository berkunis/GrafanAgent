"""Shared Anthropic client wrapper.

Every LLM call in GrafanAgent goes through here so it inherits:

- OTel spans following the genai semantic conventions (gen_ai.* attrs)
- Token + dollar cost recorded as both span attrs and a Mimir counter metric
- Optional structured output via Anthropic tool-forcing
- Optional prompt caching on system messages (`cache_system=True`)
- Tenacity retries on transient API errors

The wrapper is intentionally thin — it does not hide the Anthropic SDK; agents
still see real `Message` objects. We only wrap the things every call needs.
"""
from __future__ import annotations

import json
import os
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

from observability.cost import cost_usd

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

        with _tracer.start_as_current_span(f"anthropic.{operation}") as span:
            span.set_attribute("gen_ai.system", "anthropic")
            span.set_attribute("gen_ai.operation.name", operation)
            span.set_attribute("gen_ai.request.model", model)
            span.set_attribute("gen_ai.request.max_tokens", max_tokens)
            span.set_attribute("gen_ai.request.temperature", temperature)
            span.set_attribute("grafanagent.agent", self._agent)
            span.add_event("gen_ai.prompt", {"messages_json": _safe_json(messages)})

            try:
                message = await self._client.messages.create(**kwargs)
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                _call_counter.add(1, {"agent": self._agent, "model": model, "outcome": "error"})
                raise

            usage_in = getattr(message.usage, "input_tokens", 0) or 0
            usage_out = getattr(message.usage, "output_tokens", 0) or 0
            usd = cost_usd(model, usage_in, usage_out)

            span.set_attribute("gen_ai.response.id", message.id)
            span.set_attribute("gen_ai.response.model", message.model)
            if message.stop_reason:
                span.set_attribute("gen_ai.response.finish_reasons", [message.stop_reason])
            span.set_attribute("gen_ai.usage.input_tokens", usage_in)
            span.set_attribute("gen_ai.usage.output_tokens", usage_out)
            span.set_attribute("grafanagent.cost_usd", usd)
            span.add_event("gen_ai.completion", {"content_json": _safe_json(_serialize_content(message))})

            attrs = {"agent": self._agent, "model": model}
            _tokens_counter.add(usage_in, {**attrs, "direction": "input"})
            _tokens_counter.add(usage_out, {**attrs, "direction": "output"})
            _cost_counter.add(usd, attrs)
            _call_counter.add(1, {**attrs, "outcome": "ok"})

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
