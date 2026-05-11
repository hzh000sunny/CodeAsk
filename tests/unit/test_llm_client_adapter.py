"""Adapter test: LiteLLM streaming chunks -> LLMEvent."""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest

from codeask.llm.client import AnthropicClient, OpenAIClient, OpenAICompatibleClient
from codeask.llm.types import LLMMessage, ReasoningBlock, TextBlock, ToolDef


def _chunk(
    content: str | None = None,
    tool_calls: list[Any] | None = None,
    finish_reason: str | None = None,
) -> SimpleNamespace:
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], model="gpt-4o", usage=None)


def _chunk_with_delta(
    delta_fields: dict[str, Any],
    finish_reason: str | None = None,
) -> SimpleNamespace:
    delta = SimpleNamespace(**delta_fields)
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
async def test_openai_compatible_stream_emits_reasoning_delta_without_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_acompletion(**kwargs):  # type: ignore[no-untyped-def]
        async def gen() -> AsyncIterator[Any]:
            yield _chunk_with_delta({"reasoning_content": "先分析"})
            yield _chunk_with_delta({"content": "正式回答"})
            yield _chunk_with_delta({}, finish_reason="stop")

        return gen()

    import codeask.llm.client as mod

    monkeypatch.setattr(mod, "acompletion", fake_acompletion)

    client = OpenAICompatibleClient(api_key="x", model_name="local-reasoning")
    events = [
        event
        async for event in client.stream(
            messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
            tools=[],
            max_tokens=100,
            temperature=0.0,
        )
    ]

    assert [event.type for event in events] == [
        "message_start",
        "reasoning_delta",
        "text_delta",
        "message_stop",
    ]
    assert events[1].data == {
        "delta": "先分析",
        "field": "reasoning_content",
        "redacted": False,
    }
    assert events[2].data == {"delta": "正式回答"}


@pytest.mark.asyncio
async def test_openai_compatible_stream_emits_reasoning_and_text_from_same_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_acompletion(**kwargs):  # type: ignore[no-untyped-def]
        async def gen() -> AsyncIterator[Any]:
            yield _chunk_with_delta(
                {"reasoning": "内部", "content": "回答"},
                finish_reason="stop",
            )

        return gen()

    import codeask.llm.client as mod

    monkeypatch.setattr(mod, "acompletion", fake_acompletion)

    client = OpenAICompatibleClient(api_key="x", model_name="local-reasoning")
    events = [
        event
        async for event in client.stream(
            messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
            tools=[],
            max_tokens=100,
            temperature=0.0,
        )
    ]

    assert [event.type for event in events] == [
        "message_start",
        "reasoning_delta",
        "text_delta",
        "message_stop",
    ]
    assert events[1].data["field"] == "reasoning"
    assert events[1].data["delta"] == "内部"
    assert events[2].data["delta"] == "回答"


@pytest.mark.asyncio
async def test_openai_compatible_routes_think_tag_content_to_reasoning_delta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_acompletion(**kwargs):  # type: ignore[no-untyped-def]
        async def gen() -> AsyncIterator[Any]:
            yield _chunk(content="<think>内部</think>正式回答")
            yield _chunk(finish_reason="stop")

        return gen()

    import codeask.llm.client as mod

    monkeypatch.setattr(mod, "acompletion", fake_acompletion)

    client = OpenAICompatibleClient(api_key="x", model_name="local-reasoning")
    events = [
        event
        async for event in client.stream(
            messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
            tools=[],
            max_tokens=100,
            temperature=0.0,
        )
    ]

    assert [event.type for event in events] == [
        "message_start",
        "reasoning_delta",
        "text_delta",
        "message_stop",
    ]
    assert events[1].data == {
        "delta": "内部",
        "field": "content_think_tag",
        "redacted": False,
    }
    assert events[2].data == {"delta": "正式回答"}


@pytest.mark.asyncio
async def test_openai_compatible_routes_split_think_tags_without_visible_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_acompletion(**kwargs):  # type: ignore[no-untyped-def]
        async def gen() -> AsyncIterator[Any]:
            yield _chunk(content="前缀<thi")
            yield _chunk(content="nk>内部</th")
            yield _chunk(content="ink>结论")
            yield _chunk(finish_reason="stop")

        return gen()

    import codeask.llm.client as mod

    monkeypatch.setattr(mod, "acompletion", fake_acompletion)

    client = OpenAICompatibleClient(api_key="x", model_name="local-reasoning")
    events = [
        event
        async for event in client.stream(
            messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
            tools=[],
            max_tokens=100,
            temperature=0.0,
        )
    ]

    text = "".join(str(event.data["delta"]) for event in events if event.type == "text_delta")
    reasoning = "".join(
        str(event.data["delta"]) for event in events if event.type == "reasoning_delta"
    )

    assert text == "前缀结论"
    assert reasoning == "内部"


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
    assert "extra_body" not in captured
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
    assert "extra_body" not in captured
    assert captured["timeout"] == 600
    assert [event.type for event in events] == [
        "message_start",
        "text_delta",
        "message_stop",
    ]


@pytest.mark.asyncio
async def test_openai_compatible_reasoning_request_profile_adds_provider_kwargs(
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

    client = OpenAICompatibleClient(
        api_key="local-secret",
        model_name="local-model",
        base_url="http://llm.local/v1",
        reasoning_request_profile="volcengine_thinking",
    )

    _ = [
        event
        async for event in client.stream(
            messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
            tools=[],
            max_tokens=100,
            temperature=0.0,
        )
    ]

    assert captured["extra_body"] == {"thinking": {"type": "enabled"}}


@pytest.mark.asyncio
async def test_openai_compatible_replays_reasoning_history_only_when_configured(
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

    client = OpenAICompatibleClient(
        api_key="local-secret",
        model_name="local-model",
        base_url="http://llm.local/v1",
    )
    messages = [
        LLMMessage(
            role="assistant",
            content=[
                ReasoningBlock(
                    type="reasoning",
                    text="internal",
                    field="reasoning_content",
                ),
                TextBlock(type="text", text="visible"),
            ],
        ),
        LLMMessage(role="user", content=[TextBlock(type="text", text="again")]),
    ]

    _ = [
        event
        async for event in client.stream(
            messages=messages,
            tools=[],
            max_tokens=100,
            temperature=0.0,
        )
    ]

    assert captured["messages"][0] == {
        "role": "assistant",
        "content": "visible",
    }

    _ = [
        event
        async for event in client.stream(
            messages=messages,
            tools=[],
            max_tokens=100,
            temperature=0.0,
            metadata={
                "reasoning_history": {
                    "mode": "openai_interleaved",
                    "field": "reasoning_content",
                }
            },
        )
    ]

    assert captured["messages"][0] == {
        "role": "assistant",
        "content": "visible",
        "reasoning_content": "internal",
    }


@pytest.mark.asyncio
async def test_client_allows_custom_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_acompletion(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)

        async def gen() -> AsyncIterator[Any]:
            yield _chunk(content="ok")
            yield _chunk(finish_reason="stop")

        return gen()

    import codeask.llm.client as mod

    monkeypatch.setattr(mod, "acompletion", fake_acompletion)

    client = OpenAICompatibleClient(
        api_key="local-secret",
        model_name="local-model",
        base_url="http://llm.local/v1",
        timeout_seconds=900,
    )

    _ = [
        event
        async for event in client.stream(
            messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
            tools=[],
            max_tokens=100,
            temperature=0.0,
        )
    ]

    assert captured["timeout"] == 900


@pytest.mark.asyncio
async def test_initial_litellm_transient_error_is_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ServiceUnavailableError(Exception):
        status_code = 503

    async def fake_acompletion(**_: object) -> object:
        raise ServiceUnavailableError("upstream service unavailable")

    import codeask.llm.client as mod

    monkeypatch.setattr(mod, "acompletion", fake_acompletion)

    client = OpenAICompatibleClient(api_key="x", model_name="m")
    events = [
        event
        async for event in client.stream(
            messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
            tools=[],
            max_tokens=100,
            temperature=0.0,
        )
    ]

    assert events[0].type == "error"
    assert events[0].data["retryable"] is True


@pytest.mark.asyncio
async def test_initial_litellm_bad_request_error_is_not_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BadRequestError(Exception):
        status_code = 400

    async def fake_acompletion(**_: object) -> object:
        raise BadRequestError("Input length exceeds the maximum length")

    import codeask.llm.client as mod

    monkeypatch.setattr(mod, "acompletion", fake_acompletion)

    client = OpenAICompatibleClient(api_key="x", model_name="m")
    events = [
        event
        async for event in client.stream(
            messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
            tools=[],
            max_tokens=100,
            temperature=0.0,
        )
    ]

    assert events[0].type == "error"
    assert events[0].data["retryable"] is False


@pytest.mark.asyncio
async def test_initial_tool_schema_error_retries_once_without_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    class BadRequestError(Exception):
        status_code = 400

    async def fake_acompletion(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        if len(calls) == 1:
            raise BadRequestError(
                "Failed to deserialize the JSON body into the target type: "
                "tools[0]: unknown variant custom"
            )

        async def gen() -> AsyncIterator[Any]:
            yield _chunk(content="fallback ok")
            yield _chunk(finish_reason="stop")

        return gen()

    import codeask.llm.client as mod

    monkeypatch.setattr(mod, "acompletion", fake_acompletion)

    client = AnthropicClient(api_key="x", model_name="deepseek-v4-flash")
    events = [
        event
        async for event in client.stream(
            messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
            tools=[ToolDef(name="search_wiki", description="d", input_schema={})],
            max_tokens=100,
            temperature=0.0,
        )
    ]

    assert "tools" in calls[0]
    assert "tools" not in calls[1]
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
