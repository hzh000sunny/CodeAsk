"""Scriptable LLM client for integration tests."""

from collections.abc import AsyncIterator
from typing import Any

from codeask.llm.types import LLMEvent, LLMMessage, ToolDef


class MockLLMClient:
    """Replay a fixed list of LLMEvent sequences, one per stream() call."""

    def __init__(self, scripts: list[list[LLMEvent]]) -> None:
        self._scripts = list(scripts)
        self._idx = 0
        self._calls: list[dict[str, Any]] = []

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self._calls

    async def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[LLMEvent]:
        self._calls.append(
            {
                "messages": [message.model_dump() for message in messages],
                "tools": [tool.model_dump() for tool in tools],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        if self._idx >= len(self._scripts):
            raise AssertionError(f"MockLLMClient: ran out of scripts (call #{self._idx + 1})")
        script = self._scripts[self._idx]
        self._idx += 1
        for event in script:
            yield event


def text_message(text: str) -> list[LLMEvent]:
    return [
        LLMEvent(type="message_start", data={}),
        LLMEvent(type="text_delta", data={"delta": text}),
        LLMEvent(type="message_stop", data={"stop_reason": "end_turn"}),
    ]


def tool_call_message(call_id: str, name: str, arguments: dict[str, Any]) -> list[LLMEvent]:
    return [
        LLMEvent(type="message_start", data={}),
        LLMEvent(type="tool_call_start", data={"id": call_id, "name": name}),
        LLMEvent(
            type="tool_call_done",
            data={"id": call_id, "name": name, "arguments": arguments},
        ),
        LLMEvent(type="message_stop", data={"stop_reason": "tool_call"}),
    ]
