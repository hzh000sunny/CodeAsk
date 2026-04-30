"""LLMGateway: factory dispatch + retry-before-first-token only."""

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest

from codeask.llm.gateway import ClientFactory, LLMGateway
from codeask.llm.types import LLMEvent, LLMMessage, LLMRequest, TextBlock


class _ScriptedClient:
    def __init__(self, scripts: list[list[LLMEvent]]) -> None:
        self._scripts = scripts
        self._idx = 0

    async def stream(self, **_: object) -> AsyncIterator[LLMEvent]:
        script = self._scripts[self._idx]
        self._idx += 1
        for event in script:
            yield event


class _FakeRepo:
    async def get_default_or(self, _id: str | None) -> object:
        @dataclass(frozen=True)
        class Config:
            id: str = "cfg"
            protocol: str = "openai"
            api_key: str = "x"
            base_url: str | None = None
            model_name: str = "m"
            max_tokens: int = 100
            temperature: float = 0.0

        return Config()


def _request() -> LLMRequest:
    return LLMRequest(
        messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
        max_tokens=100,
        temperature=0.0,
    )


@pytest.mark.asyncio
async def test_retry_when_error_before_first_token() -> None:
    bad = LLMEvent(type="error", data={"retryable": True, "message": "transient"})
    good = [
        LLMEvent(type="message_start", data={}),
        LLMEvent(type="text_delta", data={"delta": "ok"}),
        LLMEvent(type="message_stop", data={"stop_reason": "end_turn"}),
    ]
    client = _ScriptedClient([[bad], good])

    factory = ClientFactory(provider_clients={"openai": lambda **_: client})
    gateway = LLMGateway(_FakeRepo(), factory, base_delay=0.0)  # type: ignore[arg-type]
    out = [event async for event in gateway.stream(_request())]
    assert out[-1].data["stop_reason"] == "end_turn"


@pytest.mark.asyncio
async def test_no_retry_after_first_token() -> None:
    partial = [
        LLMEvent(type="message_start", data={}),
        LLMEvent(type="text_delta", data={"delta": "abc"}),
        LLMEvent(type="error", data={"retryable": True, "message": "stream cut"}),
    ]
    client = _ScriptedClient([partial])

    factory = ClientFactory(provider_clients={"openai": lambda **_: client})
    gateway = LLMGateway(_FakeRepo(), factory, base_delay=0.0)  # type: ignore[arg-type]
    out = [event async for event in gateway.stream(_request())]
    assert out[-1].type == "error"
