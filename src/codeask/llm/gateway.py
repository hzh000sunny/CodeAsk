"""LLM gateway protocol dispatch and retry policy."""

import asyncio
import random
import time
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from codeask.llm.client import (
    AnthropicClient,
    LLMClient,
    OpenAIClient,
    OpenAICompatibleClient,
)
from codeask.llm.repo import LLMConfigRepo
from codeask.llm.types import LLMError, LLMEvent, LLMRequest


class ClientBuilder(Protocol):
    def __call__(
        self,
        *,
        api_key: str,
        model_name: str,
        base_url: str | None = None,
        timeout_seconds: int = 600,
        reasoning_request_profile: str | None = None,
        reasoning_request_profile_json: str | None = None,
    ) -> LLMClient: ...


def _openai_client(
    *,
    api_key: str,
    model_name: str,
    base_url: str | None = None,
    timeout_seconds: int = 600,
    reasoning_request_profile: str | None = None,
    reasoning_request_profile_json: str | None = None,
) -> LLMClient:
    return OpenAIClient(
        api_key=api_key,
        model_name=model_name,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        reasoning_request_profile=reasoning_request_profile,
        reasoning_request_profile_json=reasoning_request_profile_json,
    )


def _openai_compatible_client(
    *,
    api_key: str,
    model_name: str,
    base_url: str | None = None,
    timeout_seconds: int = 600,
    reasoning_request_profile: str | None = None,
    reasoning_request_profile_json: str | None = None,
) -> LLMClient:
    return OpenAICompatibleClient(
        api_key=api_key,
        model_name=model_name,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        reasoning_request_profile=reasoning_request_profile,
        reasoning_request_profile_json=reasoning_request_profile_json,
    )


def _anthropic_client(
    *,
    api_key: str,
    model_name: str,
    base_url: str | None = None,
    timeout_seconds: int = 600,
    reasoning_request_profile: str | None = None,
    reasoning_request_profile_json: str | None = None,
) -> LLMClient:
    return AnthropicClient(
        api_key=api_key,
        model_name=model_name,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        reasoning_request_profile=reasoning_request_profile,
        reasoning_request_profile_json=reasoning_request_profile_json,
    )


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
        timeout_seconds: int = 600,
        reasoning_request_profile: str | None = None,
        reasoning_request_profile_json: str | None = None,
    ) -> LLMClient:
        if protocol not in self.provider_clients:
            raise ValueError(f"unknown protocol {protocol!r}")
        return self.provider_clients[protocol](
            api_key=api_key,
            model_name=model_name,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            reasoning_request_profile=reasoning_request_profile,
            reasoning_request_profile_json=reasoning_request_profile_json,
        )


class LLMGateway:
    def __init__(
        self,
        config_repo: LLMConfigRepo,
        client_factory: ClientFactory,
        timeout_seconds: int = 600,
        max_retries: int = 3,
        base_delay: float = 0.5,
        global_max_sessions: int = 3,
        global_usage_window_seconds: float = 60.0,
        global_session_sticky_seconds: float = 300.0,
        unhealthy_failure_threshold: int = 3,
        unhealthy_window_seconds: float = 300.0,
        unhealthy_cooldown_seconds: float = 600.0,
        monotonic: Callable[[], float] = time.monotonic,
        random_choice: Callable[[Sequence[Any]], Any] = random.choice,
    ) -> None:
        self._repo = config_repo
        self._factory = client_factory
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._global_usage = GlobalLLMUsageWindow(
            max_sessions=global_max_sessions,
            usage_window_seconds=global_usage_window_seconds,
            session_sticky_seconds=global_session_sticky_seconds,
            failure_threshold=unhealthy_failure_threshold,
            failure_window_seconds=unhealthy_window_seconds,
            failure_cooldown_seconds=unhealthy_cooldown_seconds,
            monotonic=monotonic,
        )
        self._random_choice = random_choice

    @property
    def client_factory(self) -> ClientFactory:
        return self._factory

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        subject_id = request.metadata.get("subject_id")
        session_id = request.metadata.get("session_id")
        normalized_subject_id = subject_id if isinstance(subject_id, str) else None
        normalized_session_id = session_id if isinstance(session_id, str) else None
        excluded_global_config_ids: set[str] = set()
        selected = await self._select_config(
            request.config_id,
            subject_id=normalized_subject_id,
            session_id=normalized_session_id,
            excluded_global_config_ids=excluded_global_config_ids,
        )
        if selected is None:
            yield _resource_busy_event()
            return
        config, pooled_global = selected
        client = self._factory.create(
            config.protocol,
            api_key=config.api_key,
            model_name=config.model_name,
            base_url=config.base_url,
            timeout_seconds=self._timeout_seconds,
            reasoning_request_profile=config.reasoning_profile,
            reasoning_request_profile_json=config.reasoning_profile_json,
        )

        attempt = 0
        while True:
            yield LLMEvent(
                type="message_start",
                data={
                    "selected_config": _selected_config_summary(
                        config,
                        pooled_global=pooled_global,
                    )
                },
            )
            emitted_real_event = False
            last_error: LLMEvent | None = None
            retry_with_selected_config = False

            async for event in client.stream(
                messages=request.messages,
                tools=request.tools,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            ):
                if event.type == "error":
                    last_error = event
                    retryable = bool(event.data.get("retryable", False))
                    if not _counts_against_config_health(event.data):
                        yield event
                        return
                    if not emitted_real_event and pooled_global:
                        self._global_usage.record_failure(config.id)
                        if normalized_session_id is not None:
                            self._global_usage.clear_sticky_session(
                                normalized_session_id,
                                config.id,
                            )
                        excluded_global_config_ids.add(config.id)
                        selected = await self._select_config(
                            request.config_id,
                            subject_id=normalized_subject_id,
                            session_id=normalized_session_id,
                            excluded_global_config_ids=excluded_global_config_ids,
                        )
                        if selected is not None and attempt < self._max_retries:
                            attempt += 1
                            config, pooled_global = selected
                            client = self._factory.create(
                                config.protocol,
                                api_key=config.api_key,
                                model_name=config.model_name,
                                base_url=config.base_url,
                                timeout_seconds=self._timeout_seconds,
                                reasoning_request_profile=config.reasoning_profile,
                                reasoning_request_profile_json=config.reasoning_profile_json,
                            )
                            retry_with_selected_config = True
                            break
                        if selected is None and retryable and attempt < self._max_retries:
                            break
                        yield last_error
                        return
                    if not emitted_real_event and retryable and attempt < self._max_retries:
                        break
                    if pooled_global:
                        self._global_usage.record_failure(config.id)
                    yield event
                    return

                if event.type != "message_start":
                    emitted_real_event = True

                if event.type == "message_stop" and pooled_global:
                    self._global_usage.record_success(config.id)
                yield event
                if event.type == "message_stop":
                    return

            if last_error is None:
                return
            if retry_with_selected_config:
                continue
            if emitted_real_event:
                if pooled_global:
                    self._global_usage.record_failure(config.id)
                yield last_error
                return

            attempt += 1
            if attempt > self._max_retries:
                if pooled_global:
                    self._global_usage.record_failure(config.id)
                yield last_error
                return
            await asyncio.sleep(self._base_delay * (2 ** (attempt - 1)))

    async def _select_config(
        self,
        config_id: str | None,
        *,
        subject_id: str | None,
        session_id: str | None,
        excluded_global_config_ids: set[str] | None = None,
    ) -> tuple[Any, bool] | None:
        if config_id is not None:
            return await self._repo.get_default_or(config_id, subject_id=subject_id), False

        if subject_id:
            user_configs = await self._repo.list_runtime_user_configs(subject_id)
            if user_configs:
                return user_configs[0], False

        excluded_global_config_ids = excluded_global_config_ids or set()
        global_configs = await self._repo.list_runtime_global_configs()
        if not global_configs:
            return None

        by_id = {config.id: config for config in global_configs}
        if session_id:
            sticky_config_id = self._global_usage.sticky_config_id(session_id)
            if sticky_config_id is not None and sticky_config_id not in excluded_global_config_ids:
                sticky = by_id.get(sticky_config_id)
                if sticky is not None and not self._global_usage.is_unhealthy(sticky.id):
                    self._global_usage.record_session(sticky.id, session_id)
                    return sticky, True

        candidates = [
            config
            for config in global_configs
            if config.id not in excluded_global_config_ids
            and not self._global_usage.is_unhealthy(config.id)
            and self._global_usage.session_count(config.id) < self._global_usage.max_sessions
        ]
        if not candidates:
            return None
        selected = self._random_choice(candidates)
        if session_id:
            self._global_usage.record_session(selected.id, session_id)
        return selected, True


def _resource_busy_event() -> LLMEvent:
    return LLMEvent(
        type="error",
        data=LLMError(
            provider="codeask",
            error_code="resource_busy",
            message="当前资源繁忙，请稍后再试",
            retryable=True,
        ).model_dump(),
    )


def _selected_config_summary(config: Any, *, pooled_global: bool) -> dict[str, Any]:
    return {
        "config_id": getattr(config, "id", None),
        "config_name": getattr(config, "name", None),
        "model_name": getattr(config, "model_name", "unknown"),
        "protocol": getattr(config, "protocol", None),
        "scope": getattr(config, "scope", None),
        "is_global_pool": pooled_global,
    }


def _counts_against_config_health(data: dict[str, Any]) -> bool:
    text = " ".join(
        str(data.get(key, ""))
        for key in ("error_code", "message", "provider")
        if data.get(key) is not None
    ).lower()
    request_error_markers = (
        "input length",
        "context length",
        "maximum length",
        "max_tokens",
        "max tokens",
        "prompt too long",
        "too many tokens",
        "token limit",
        "tool schema",
        "invalid tool",
        "schema",
        "request body",
        "invalid request body",
    )
    return not any(marker in text for marker in request_error_markers)


class GlobalLLMUsageWindow:
    def __init__(
        self,
        *,
        max_sessions: int,
        usage_window_seconds: float,
        session_sticky_seconds: float,
        failure_threshold: int,
        failure_window_seconds: float,
        failure_cooldown_seconds: float,
        monotonic: Callable[[], float],
    ) -> None:
        self.max_sessions = max_sessions
        self._usage_window_seconds = usage_window_seconds
        self._session_sticky_seconds = session_sticky_seconds
        self._failure_threshold = failure_threshold
        self._failure_window_seconds = failure_window_seconds
        self._failure_cooldown_seconds = failure_cooldown_seconds
        self._monotonic = monotonic
        self._usage: dict[str, dict[str, float]] = {}
        self._sticky_sessions: dict[str, tuple[str, float]] = {}
        self._failures: dict[str, list[float]] = {}
        self._unhealthy_until: dict[str, float] = {}

    def record_session(self, config_id: str, session_id: str) -> None:
        now = self._monotonic()
        self._prune_usage(config_id, now)
        self._usage.setdefault(config_id, {})[session_id] = now
        self._sticky_sessions[session_id] = (config_id, now)

    def sticky_config_id(self, session_id: str) -> str | None:
        now = self._monotonic()
        record = self._sticky_sessions.get(session_id)
        if record is None:
            return None
        config_id, last_seen = record
        if now - last_seen > self._session_sticky_seconds:
            self._sticky_sessions.pop(session_id, None)
            return None
        return config_id

    def clear_sticky_session(self, session_id: str, config_id: str) -> None:
        record = self._sticky_sessions.get(session_id)
        if record is not None and record[0] == config_id:
            self._sticky_sessions.pop(session_id, None)

    def session_count(self, config_id: str) -> int:
        now = self._monotonic()
        self._prune_usage(config_id, now)
        return len(self._usage.get(config_id, {}))

    def is_unhealthy(self, config_id: str) -> bool:
        now = self._monotonic()
        until = self._unhealthy_until.get(config_id)
        if until is None:
            return False
        if now >= until:
            self._unhealthy_until.pop(config_id, None)
            self._failures.pop(config_id, None)
            return False
        return True

    def record_failure(self, config_id: str) -> None:
        now = self._monotonic()
        failures = [
            at
            for at in self._failures.get(config_id, [])
            if now - at <= self._failure_window_seconds
        ]
        failures.append(now)
        self._failures[config_id] = failures
        if len(failures) >= self._failure_threshold:
            self._unhealthy_until[config_id] = now + self._failure_cooldown_seconds

    def record_success(self, config_id: str) -> None:
        self._failures.pop(config_id, None)
        self._unhealthy_until.pop(config_id, None)

    def _prune_usage(self, config_id: str, now: float) -> None:
        sessions = self._usage.get(config_id)
        if not sessions:
            return
        stale = [
            session_id
            for session_id, last_seen in sessions.items()
            if now - last_seen > self._usage_window_seconds
        ]
        for session_id in stale:
            sessions.pop(session_id, None)
        if not sessions:
            self._usage.pop(config_id, None)
