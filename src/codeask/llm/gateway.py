"""LLM gateway protocol dispatch and retry policy."""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from codeask.llm.client import (
    AnthropicClient,
    LLMClient,
    OpenAIClient,
    OpenAICompatibleClient,
)
from codeask.llm.repo import LLMConfigRepo
from codeask.llm.types import LLMEvent, LLMRequest


@dataclass(frozen=True)
class ClientFactory:
    provider_clients: dict[str, Callable[..., LLMClient]]

    @classmethod
    def default(cls) -> "ClientFactory":
        return cls(
            provider_clients={
                "openai": lambda **kwargs: OpenAIClient(**kwargs),
                "openai_compatible": lambda **kwargs: OpenAICompatibleClient(**kwargs),
                "anthropic": lambda **kwargs: AnthropicClient(**kwargs),
            }
        )

    def create(self, protocol: str, **kwargs: object) -> LLMClient:
        if protocol not in self.provider_clients:
            raise ValueError(f"unknown protocol {protocol!r}")
        return self.provider_clients[protocol](**kwargs)


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
