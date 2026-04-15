"""Shared pytest fixtures for GrafanAgent tests."""
from __future__ import annotations

from typing import Any

import pytest
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

from agents._llm import LLMClient


class FakeAnthropic:
    """Minimal quack-like-AsyncAnthropic stand-in.

    Seed with a list of `Message` objects; each `messages.create` call pops one
    and records the kwargs in `.calls`. Tests inspect `.calls` to assert prompt
    caching, tool selection, etc.
    """

    def __init__(self, responses: list[Message]):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        # The real client exposes `.messages.create`; we are both objects at once.
        self.messages = self

    async def create(self, **kwargs: Any) -> Message:
        if not self._responses:
            raise AssertionError("FakeAnthropic ran out of canned responses")
        self.calls.append(kwargs)
        return self._responses.pop(0)


def tool_use_response(
    *,
    tool_name: str,
    tool_input: dict[str, Any],
    model: str = "claude-haiku-4-5",
    input_tokens: int = 120,
    output_tokens: int = 40,
) -> Message:
    """Build a canned Message containing one tool_use block — what the classifier expects."""
    return Message(
        id="msg_test_" + tool_name,
        type="message",
        role="assistant",
        model=model,
        stop_reason="tool_use",
        stop_sequence=None,
        content=[
            ToolUseBlock(
                id="toolu_test",
                type="tool_use",
                name=tool_name,
                input=tool_input,
            )
        ],
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def text_response(
    text: str,
    *,
    model: str = "claude-haiku-4-5",
    input_tokens: int = 50,
    output_tokens: int = 20,
) -> Message:
    return Message(
        id="msg_test_text",
        type="message",
        role="assistant",
        model=model,
        stop_reason="end_turn",
        stop_sequence=None,
        content=[TextBlock(type="text", text=text)],
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


@pytest.fixture
def fake_anthropic_factory():
    """Returns a callable that builds a `FakeAnthropic` from a list of responses."""
    def _factory(*responses: Message) -> FakeAnthropic:
        return FakeAnthropic(list(responses))
    return _factory


@pytest.fixture
def make_llm(fake_anthropic_factory):
    """Build an `LLMClient` backed by a `FakeAnthropic` with the given canned responses."""
    def _make(*responses: Message, agent: str = "test") -> tuple[LLMClient, FakeAnthropic]:
        fake = fake_anthropic_factory(*responses)
        return LLMClient(client=fake, agent=agent), fake  # type: ignore[arg-type]
    return _make
