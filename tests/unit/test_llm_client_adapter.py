"""Adapter test: LiteLLM streaming chunks -> LLMEvent."""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest

from codeask.llm.client import OpenAIClient
from codeask.llm.types import LLMMessage, TextBlock, ToolDef


def _chunk(
    content: str | None = None,
    tool_calls: list[Any] | None = None,
    finish_reason: str | None = None,
) -> SimpleNamespace:
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], model="gpt-4o", usage=None)


def _tool_call_chunk(
    idx: int,
    tc_id: str | None,
    name: str | None,
    args_delta: str,
) -> Any:
    fn = SimpleNamespace(name=name, arguments=args_delta)
    return SimpleNamespace(index=idx, id=tc_id, type="function", function=fn)


@pytest.mark.asyncio
async def test_text_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_acompletion(**kwargs):  # type: ignore[no-untyped-def]
        async def gen() -> AsyncIterator[Any]:
            yield _chunk(content="hello ")
            yield _chunk(content="world")
            yield _chunk(finish_reason="stop")

        return gen()

    import codeask.llm.client as mod

    monkeypatch.setattr(mod, "acompletion", fake_acompletion)

    client = OpenAIClient(api_key="x", model_name="gpt-4o")
    events = []
    async for event in client.stream(
        messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
        tools=[],
        max_tokens=100,
        temperature=0.0,
    ):
        events.append(event)

    types = [event.type for event in events]
    assert types[0] == "message_start"
    assert "text_delta" in types
    assert types[-1] == "message_stop"
    assert any(
        event.type == "message_stop" and event.data["stop_reason"] == "end_turn" for event in events
    )


@pytest.mark.asyncio
async def test_tool_call_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_acompletion(**kwargs):  # type: ignore[no-untyped-def]
        async def gen() -> AsyncIterator[Any]:
            yield _chunk(tool_calls=[_tool_call_chunk(0, "tc_a", "search_wiki", "")])
            yield _chunk(tool_calls=[_tool_call_chunk(0, None, None, '{"q":')])
            yield _chunk(tool_calls=[_tool_call_chunk(0, None, None, '"x"}')])
            yield _chunk(finish_reason="tool_calls")

        return gen()

    import codeask.llm.client as mod

    monkeypatch.setattr(mod, "acompletion", fake_acompletion)

    client = OpenAIClient(api_key="x", model_name="gpt-4o")
    events = []
    async for event in client.stream(
        messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
        tools=[ToolDef(name="search_wiki", description="d", input_schema={})],
        max_tokens=100,
        temperature=0.0,
    ):
        events.append(event)

    starts = [event for event in events if event.type == "tool_call_start"]
    dones = [event for event in events if event.type == "tool_call_done"]
    assert starts and starts[0].data["name"] == "search_wiki"
    assert dones and dones[0].data["arguments"] == {"q": "x"}
    stop = [event for event in events if event.type == "message_stop"][0]
    assert stop.data["stop_reason"] == "tool_call"
