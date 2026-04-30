"""LLM gateway protocol dispatch and retry policy."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from codeask.llm.client import (
    AnthropicClient,
    LLMClient,
    OpenAIClient,
    OpenAICompatibleClient,
)
from codeask.llm.repo import LLMConfigRepo
from codeask.llm.types import LLMEvent, LLMRequest


class ClientBuilder(Protocol):
    def __call__(
        self,
        *,
        api_key: str,
        model_name: str,
        base_url: str | None = None,
    ) -> LLMClient: ...


def _openai_client(
    *,
    api_key: str,
    model_name: str,
    base_url: str | None = None,
) -> LLMClient:
    return OpenAIClient(api_key=api_key, model_name=model_name, base_url=base_url)


def _openai_compatible_client(
    *,
    api_key: str,
    model_name: str,
    base_url: str | None = None,
) -> LLMClient:
    return OpenAICompatibleClient(api_key=api_key, model_name=model_name, base_url=base_url)


def _anthropic_client(
    *,
    api_key: str,
    model_name: str,
    base_url: str | None = None,
) -> LLMClient:
    return AnthropicClient(api_key=api_key, model_name=model_name, base_url=base_url)


@dataclass(frozen=True)
class ClientFactory:
    provider_clients: dict[str, ClientBuilder]

    @classmethod
    def default(cls) -> "ClientFactory":
        return cls(
            provider_clients={
                "openai": _openai_client,
                "openai_compatible": _openai_compatible_client,
                "anthropic": _anthropic_client,
            }
        )

    def create(
        self,
        protocol: str,
        *,
        api_key: str,
        model_name: str,
        base_url: str | None = None,
    ) -> LLMClient:
        if protocol not in self.provider_clients:
            raise ValueError(f"unknown protocol {protocol!r}")
        return self.provider_clients[protocol](
            api_key=api_key,
            model_name=model_name,
            base_url=base_url,
        )


class LLMGateway:
    def __init__(
        self,
        config_repo: LLMConfigRepo,
        client_factory: ClientFactory,
        max_retries: int = 3,
        base_delay: float = 0.5,
    ) -> None:
        self._repo = config_repo
        self._factory = client_factory
        self._max_retries = max_retries
        self._base_delay = base_delay

    @property
    def client_factory(self) -> ClientFactory:
        return self._factory

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        config = await self._repo.get_default_or(request.config_id)
        client = self._factory.create(
            config.protocol,
            api_key=config.api_key,
            model_name=config.model_name,
            base_url=config.base_url,
        )

        attempt = 0
        while True:
            emitted_real_event = False
            last_error: LLMEvent | None = None

            async for event in client.stream(
                messages=request.messages,
                tools=request.tools,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            ):
                if event.type == "error":
                    last_error = event
                    retryable = bool(event.data.get("retryable", False))
                    if not emitted_real_event and retryable and attempt < self._max_retries:
                        break
                    yield event
                    return

                if event.type != "message_start":
                    emitted_real_event = True

                yield event
                if event.type == "message_stop":
                    return

            if last_error is None:
                return
            if emitted_real_event:
                yield last_error
                return

            attempt += 1
            if attempt > self._max_retries:
                yield last_error
                return
            await asyncio.sleep(self._base_delay * (2 ** (attempt - 1)))
