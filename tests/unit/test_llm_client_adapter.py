"""Adapter test: LiteLLM streaming chunks -> LLMEvent."""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest

from codeask.llm.client import AnthropicClient, OpenAIClient, OpenAICompatibleClient
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

    client = AnthropicClient(api_key="x", model_name="claude-test")
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

    client = AnthropicClient(api_key="x", model_name="claude-test")
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


@pytest.mark.asyncio
async def test_openai_protocol_uses_litellm_with_internal_provider_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_acompletion(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)

        async def gen() -> AsyncIterator[Any]:
            yield _chunk(content="你好")
            yield _chunk(finish_reason="stop")

        return gen()

    import codeask.llm.client as mod

    monkeypatch.setattr(mod, "acompletion", fake_acompletion)

    client = OpenAIClient(
        api_key="ark-test",
        model_name="GLM-5.1",
        base_url="https://ark.example.test/api/coding/v3",
    )

    events = [
        event
        async for event in client.stream(
            messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
            tools=[],
            max_tokens=100,
            temperature=0.0,
        )
    ]

    assert captured["model"] == "openai/GLM-5.1"
    assert captured["api_key"] == "ark-test"
    assert captured["base_url"] == "https://ark.example.test/api/coding/v3"
    assert [event.type for event in events] == [
        "message_start",
        "text_delta",
        "message_stop",
    ]


@pytest.mark.asyncio
async def test_openai_compatible_protocol_uses_litellm_with_internal_provider_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_acompletion(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)

        async def gen() -> AsyncIterator[Any]:
            yield _chunk(content="local ok")
            yield _chunk(finish_reason="stop")

        return gen()

    import codeask.llm.client as mod

    monkeypatch.setattr(mod, "acompletion", fake_acompletion)

    client = OpenAICompatibleClient(
        api_key="local-secret",
        model_name="local-model",
        base_url="http://llm.local/v1",
    )

    events = [
        event
        async for event in client.stream(
            messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
            tools=[],
            max_tokens=100,
            temperature=0.0,
        )
    ]

    assert captured["model"] == "openai/local-model"
    assert captured["api_key"] == "local-secret"
    assert captured["base_url"] == "http://llm.local/v1"
    assert [event.type for event in events] == [
        "message_start",
        "text_delta",
        "message_stop",
    ]


@pytest.mark.asyncio
async def test_openai_provider_hint_preserves_explicit_litellm_model_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_acompletion(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)

        async def gen() -> AsyncIterator[Any]:
            yield _chunk(content="ok")
            yield _chunk(finish_reason="stop")

        return gen()

    import codeask.llm.client as mod

    monkeypatch.setattr(mod, "acompletion", fake_acompletion)

    client = OpenAIClient(api_key="x", model_name="openai/gpt-4o")
    events = [
        event
        async for event in client.stream(
            messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
            tools=[],
            max_tokens=100,
            temperature=0.0,
        )
    ]

    assert captured["model"] == "openai/gpt-4o"
    assert events[-1].type == "message_stop"
