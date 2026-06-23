"""Scriptable LLM client for integration tests."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from codeask.llm.types import LLMEvent, LLMMessage, ToolDef


class _StubClientFactory:
    """Test seam: always hand back a single pre-built client.

    The production ``ClientFactory`` builds one LiteLLM client per call keyed on
    the resolved provider; integration tests just want their scripted client
    returned regardless of provider/model arguments.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    def create(self, **_kwargs: Any) -> Any:
        return self._client


def install_mock_llm_client(app: Any, client: Any) -> None:
    """Route the app's LLM gateway through ``client`` for the rest of the test."""

    # ``client_factory`` is a read-only property; swap the backing field so the
    # gateway builds our scripted client instead of a real LiteLLM one.
    app.state.llm_gateway._factory = _StubClientFactory(client)


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
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[LLMEvent]:
        self._calls.append(
            {
                "messages": [message.model_dump() for message in messages],
                "tools": [tool.model_dump() for tool in tools],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "metadata": dict(metadata or {}),
            }
        )
        if self._idx >= len(self._scripts):
            raise AssertionError(f"MockLLMClient: ran out of scripts (call #{self._idx + 1})")
        script = self._scripts[self._idx]
        self._idx += 1
        for event in script:
            yield event


class ScriptedLLM:
    """Replay high-level chat runtime script steps."""

    def __init__(self, steps: list[dict[str, Any]]) -> None:
        if not steps:
            raise ValueError("ScriptedLLM requires at least one step")
        self._steps = list(steps)
        self._cursor = 0
        self.calls: list[dict[str, Any]] = []

    async def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[LLMEvent]:
        self.calls.append(
            {
                "messages": [message.model_dump() for message in messages],
                "tools": [tool.model_dump() for tool in tools],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "metadata": dict(metadata or {}),
            }
        )
        if self._cursor >= len(self._steps):
            raise AssertionError(f"ScriptedLLM exhausted at call #{self._cursor + 1}")
        step = self._steps[self._cursor]
        self._cursor += 1
        step_type = step["type"]
        if step_type == "assistant_text":
            yield LLMEvent(type="message_start", data={})
            yield LLMEvent(type="text_delta", data={"delta": str(step["content"])})
            yield LLMEvent(type="message_stop", data={"stop_reason": "end_turn"})
            return
        if step_type == "tool_call":
            yield LLMEvent(type="message_start", data={})
            yield LLMEvent(
                type="tool_call_start",
                data={"id": str(step["id"]), "name": str(step["name"])},
            )
            yield LLMEvent(
                type="tool_call_done",
                data={
                    "id": str(step["id"]),
                    "name": str(step["name"]),
                    "arguments": step["input"],
                },
            )
            yield LLMEvent(type="message_stop", data={"stop_reason": "tool_call"})
            return
        raise AssertionError(f"unknown ScriptedLLM step type {step_type!r}")


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


@dataclass(frozen=True)
class ScriptStep:
    """A single eval replay step. Either text, a tool call, or a finish marker."""

    text: str | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] | None = None
    finish: bool = False


class ScriptedMockLLMClient:
    """Replay fixed ScriptStep values for eval harnesses."""

    def __init__(self, steps: list[ScriptStep]) -> None:
        if not steps:
            raise ValueError("ScriptedMockLLMClient requires at least one step")
        self._steps = list(steps)
        self._cursor = 0

    def reset(self) -> None:
        self._cursor = 0

    async def next_step(self) -> ScriptStep:
        if self._cursor >= len(self._steps):
            raise IndexError("ScriptedMockLLMClient exhausted")
        step = self._steps[self._cursor]
        self._cursor += 1
        return step
