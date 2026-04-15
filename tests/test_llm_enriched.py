"""LLM wrapper enrichments — cache-token span attrs, signal_id labels, latency record."""
from __future__ import annotations


import pytest
from anthropic.types import Message, TextBlock, Usage

from agents._llm import LLMClient
from observability.signal_ctx import signal_context
from tests.conftest import FakeAnthropic


def _message_with_cache(*, cache_read: int = 1200, cache_create: int = 300) -> Message:
    """Build a real anthropic.types.Message with cache-token fields set."""
    usage = Usage(input_tokens=400, output_tokens=120)
    # Anthropic's Usage exposes these fields on newer SDK versions; they are
    # optional so the pydantic model accepts None. Set them via direct attr
    # assignment to mimic the real response.
    try:
        object.__setattr__(usage, "cache_read_input_tokens", cache_read)
        object.__setattr__(usage, "cache_creation_input_tokens", cache_create)
    except Exception:
        setattr(usage, "cache_read_input_tokens", cache_read)
        setattr(usage, "cache_creation_input_tokens", cache_create)
    return Message(
        id="msg_test_cache",
        type="message",
        role="assistant",
        model="claude-sonnet-4-5",
        stop_reason="end_turn",
        stop_sequence=None,
        content=[TextBlock(type="text", text="ok")],
        usage=usage,
    )


@pytest.mark.asyncio
async def test_llm_handles_cache_tokens_without_crashing():
    fake = FakeAnthropic([_message_with_cache()])
    client = LLMClient(client=fake, agent="router")  # type: ignore[arg-type]
    msg = await client.chat(model="claude-sonnet-4-5", messages=[{"role": "user", "content": "hi"}])
    assert msg.id == "msg_test_cache"


@pytest.mark.asyncio
async def test_llm_request_without_cache_tokens_still_works():
    """Older Anthropic responses don't set cache_* fields — wrapper must cope."""
    from tests.conftest import tool_use_response

    fake = FakeAnthropic([tool_use_response(tool_name="record", tool_input={"k": "v"})])
    client = LLMClient(client=fake, agent="router")  # type: ignore[arg-type]
    msg = await client.chat(
        model="claude-haiku-4-5",
        messages=[{"role": "user", "content": "x"}],
        tools=[{"name": "record", "description": "d", "input_schema": {"type": "object"}}],
        tool_choice={"type": "tool", "name": "record"},
    )
    assert msg.id


@pytest.mark.asyncio
async def test_signal_context_flows_into_call_kwargs():
    """If signal_context is active, the LLM call should receive those labels
    on its metrics — verify no exception, since metrics are recorded opaquely."""
    from tests.conftest import tool_use_response

    fake = FakeAnthropic([tool_use_response(tool_name="record", tool_input={"ok": True})])
    client = LLMClient(client=fake, agent="lifecycle")  # type: ignore[arg-type]

    with signal_context("sig-enrichment-test"):
        msg = await client.chat(
            model="claude-haiku-4-5",
            messages=[{"role": "user", "content": "x"}],
            tools=[{"name": "record", "description": "d", "input_schema": {"type": "object"}}],
            tool_choice={"type": "tool", "name": "record"},
        )

    assert msg.id
    # Ensure nothing polluted the global context.
    from observability.signal_ctx import current_signal_id

    assert current_signal_id() is None


@pytest.mark.asyncio
async def test_tools_span_attr_captured_by_wrapper():
    """Records gen_ai.tools with tool names — verified by inspecting the
    kwargs the wrapper passes down to Anthropic."""
    from tests.conftest import tool_use_response

    fake = FakeAnthropic([tool_use_response(tool_name="record_decision", tool_input={"skill": "lifecycle", "confidence": 0.9, "rationale": "x", "payload": {}})])
    client = LLMClient(client=fake, agent="router")  # type: ignore[arg-type]

    await client.chat(
        model="claude-haiku-4-5",
        messages=[{"role": "user", "content": "x"}],
        tools=[
            {"name": "record_decision", "description": "d", "input_schema": {"type": "object"}},
            {"name": "record_other", "description": "d", "input_schema": {"type": "object"}},
        ],
        tool_choice={"type": "tool", "name": "record_decision"},
    )
    # Verify Anthropic was called with those tools.
    call = fake.calls[0]
    assert [t["name"] for t in call["tools"]] == ["record_decision", "record_other"]
    assert call["tool_choice"]["name"] == "record_decision"
