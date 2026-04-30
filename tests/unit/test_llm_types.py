"""Pydantic round-trip + Literal validation for LLM types."""

import pytest
from pydantic import ValidationError

from codeask.llm.types import (
    LLMError,
    LLMEvent,
    LLMMessage,
    LLMRequest,
    TextBlock,
    ToolCallBlock,
    ToolDef,
    ToolResultBlock,
)


def test_text_block() -> None:
    block = TextBlock(type="text", text="hello")
    assert block.text == "hello"


def test_tool_call_block() -> None:
    block = ToolCallBlock(
        type="tool_call",
        id="tc_1",
        name="search_wiki",
        arguments={"q": "x"},
    )
    assert block.name == "search_wiki"


def test_tool_result_block() -> None:
    block = ToolResultBlock(
        type="tool_result",
        tool_call_id="tc_1",
        content={"ok": True},
    )
    assert block.is_error is False


def test_message_with_mixed_blocks() -> None:
    msg = LLMMessage(
        role="assistant",
        content=[
            TextBlock(type="text", text="thinking..."),
            ToolCallBlock(
                type="tool_call",
                id="tc_1",
                name="search_wiki",
                arguments={"query": "ERR_X"},
            ),
        ],
    )
    assert len(msg.content) == 2


def test_request_round_trip() -> None:
    req = LLMRequest(
        config_id=None,
        messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
        tools=[
            ToolDef(
                name="search_wiki",
                description="d",
                input_schema={"type": "object"},
            )
        ],
        tool_choice=None,
        max_tokens=1000,
        temperature=0.2,
    )
    serialized = req.model_dump()
    restored = LLMRequest.model_validate(serialized)
    assert restored.max_tokens == 1000


def test_event_type_validated() -> None:
    LLMEvent(type="text_delta", data={"delta": "hello"})
    with pytest.raises(ValidationError):
        LLMEvent(type="not_a_real_event", data={})  # type: ignore[arg-type]


def test_error_retryable_default() -> None:
    err = LLMError(
        provider="openai",
        error_code="429",
        message="rate limited",
        retryable=True,
    )
    assert err.retryable is True
