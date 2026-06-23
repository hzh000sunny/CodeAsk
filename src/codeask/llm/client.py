"""LiteLLM-backed adapters for provider-neutral streaming."""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol, cast

import structlog
from litellm import acompletion as _raw_acompletion  # type: ignore[reportUnknownVariableType]

from codeask.llm.reasoning import ThinkTagContentFilter, normalize_openai_delta
from codeask.llm.request_profiles import (
    DEFAULT_REASONING_PROFILE,
    build_reasoning_request_kwargs,
)
from codeask.llm.types import (
    LLMError,
    LLMEvent,
    LLMMessage,
    ReasoningBlock,
    StopReason,
    TextBlock,
    ToolCallBlock,
    ToolDef,
    ToolResultBlock,
)

_OPENAI_TO_INTERNAL_STOP: dict[str, StopReason] = {
    "stop": "end_turn",
    "tool_calls": "tool_call",
    "length": "max_tokens",
    "content_filter": "content_filter",
}
_ACompletion = Callable[..., Awaitable[object]]
acompletion: _ACompletion = cast(_ACompletion, _raw_acompletion)
logger = structlog.get_logger(__name__)


def _with_provider_hint(provider: str, model_name: str) -> str:
    if "/" in model_name:
        return model_name
    return f"{provider}/{model_name}"


def _normalize_stop_reason(reason: str | None) -> StopReason:
    if reason is None:
        return "unknown"
    return _OPENAI_TO_INTERNAL_STOP.get(reason, "unknown")


def _is_retryable_initial_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if isinstance(status_code, int):
        if status_code in {408, 409, 425, 429, 500, 502, 503, 504}:
            return True
        if 400 <= status_code < 500:
            return False

    name = type(exc).__name__.lower()
    message = str(exc).lower()
    non_retryable_markers = (
        "badrequest",
        "authentication",
        "permission",
        "unauthorized",
        "forbidden",
        "invalid",
        "input length",
        "context length",
        "maximum length",
        "max_tokens",
    )
    if any(marker in name or marker in message for marker in non_retryable_markers):
        return False

    retryable_markers = (
        "timeout",
        "ratelimit",
        "rate limit",
        "connection",
        "serviceunavailable",
        "service unavailable",
        "internalserver",
        "internal server",
        "temporarily unavailable",
        "overloaded",
    )
    return any(marker in name or marker in message for marker in retryable_markers)


def _is_tool_schema_compatibility_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "tool" in message and any(
        marker in message
        for marker in (
            "unknown variant",
            "invalid tool",
            "tool schema",
            "tools[",
            "failed to deserialize",
        )
    )


def _messages_to_litellm(
    messages: list[LLMMessage],
    *,
    metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    reasoning_history = _reasoning_history_policy(metadata)
    for message in messages:
        if message.role == "tool":
            for block in message.content:
                if isinstance(block, ToolResultBlock):
                    payload = (
                        block.content
                        if isinstance(block.content, str)
                        else json.dumps(block.content)
                    )
                    converted.append(
                        {
                            "role": "tool",
                            "tool_call_id": block.tool_call_id,
                            "content": payload,
                        }
                    )
            continue

        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in message.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
            elif isinstance(block, ReasoningBlock):
                if message.role == "assistant" and reasoning_history is not None:
                    reasoning_parts.append(block.text)
            elif isinstance(block, ToolCallBlock):
                tool_calls.append(
                    {
                        "id": block.id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(block.arguments),
                        },
                    }
                )

        record: dict[str, Any] = {
            "role": message.role,
            "content": "\n".join(text_parts) if text_parts else None,
        }
        if tool_calls:
            record["tool_calls"] = tool_calls
        if message.role == "assistant" and reasoning_parts and reasoning_history is not None:
            record[reasoning_history["field"]] = "".join(reasoning_parts)
        converted.append(record)
    return converted


def _reasoning_history_policy(
    metadata: dict[str, Any] | None,
) -> dict[str, str] | None:
    value = (metadata or {}).get("reasoning_history")
    if not isinstance(value, dict):
        return None
    policy = cast(dict[str, Any], value)
    if policy.get("mode") != "openai_interleaved":
        return None
    field = policy.get("field")
    if field not in {"reasoning_content", "reasoning_details"}:
        return None
    return {"mode": "openai_interleaved", "field": str(field)}


def _tools_to_litellm(tools: list[ToolDef]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
        for tool in tools
    ]


def _delta_to_dict(delta: object) -> dict[str, object]:
    model_dump = getattr(delta, "model_dump", None)
    dict_dump = getattr(delta, "dict", None)
    if callable(model_dump):
        dumped = cast(Any, model_dump)(exclude_none=True)
        return (
            {str(key): value for key, value in cast(dict[object, object], dumped).items()}
            if isinstance(dumped, dict)
            else {}
        )
    elif callable(dict_dump):
        dumped = cast(Any, dict_dump)(exclude_none=True)
        return (
            {str(key): value for key, value in cast(dict[object, object], dumped).items()}
            if isinstance(dumped, dict)
            else {}
        )
    elif hasattr(delta, "__dict__"):
        return {
            key: value
            for key, value in vars(delta).items()
            if value is not None and not key.startswith("_")
        }
    return {}


def _metadata_string(metadata: dict[str, Any] | None, key: str) -> str | None:
    if metadata is None:
        return None
    value = metadata.get(key)
    return value if isinstance(value, str) and value else None


def _delta_debug_payload(delta: object) -> dict[str, object]:
    raw = _delta_to_dict(delta)
    payload: dict[str, object] = {"fields": sorted(raw)}
    for key in (
        "content",
        "reasoning_content",
        "reasoning",
        "thinking",
    ):
        if key in raw:
            value = raw[key]
            payload[f"{key}_present"] = True
            payload[f"{key}_length"] = len(value) if isinstance(value, str) else None

    tool_calls = raw.get("tool_calls")
    if isinstance(tool_calls, list):
        payload["tool_calls_count"] = len(cast(list[object], tool_calls))
    return payload


class LLMClient(Protocol):
    def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[LLMEvent]: ...


class LiteLLMClient:
    """Single LiteLLM-backed client keyed on a resolved litellm provider prefix.

    ``litellm_provider`` is the prefix used to build the ``provider/model`` string
    (e.g. ``openai``, ``deepseek``, ``gemini``, ``anthropic``). Custom providers
    resolve to ``openai`` upstream and carry a ``base_url`` + ``extra_headers``.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str,
        base_url: str | None = None,
        timeout_seconds: int = 600,
        reasoning_request_profile: str | None = None,
        reasoning_request_profile_json: str | None = None,
        litellm_provider: str = "openai",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._reasoning_request_profile = reasoning_request_profile or DEFAULT_REASONING_PROFILE
        self._reasoning_request_profile_json = reasoning_request_profile_json
        self._litellm_provider = litellm_provider or "openai"
        self._extra_headers = extra_headers or {}

    @property
    def _provider_name(self) -> str:
        return self._litellm_provider

    def _is_anthropic(self) -> bool:
        return self._litellm_provider == "anthropic"

    def _model(self) -> str:
        return _with_provider_hint(self._litellm_provider, self._model_name)

    def _extra_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"api_key": self._api_key}
        base_url = self._base_url
        if base_url and self._is_anthropic():
            normalized = base_url.rstrip("/")
            if not normalized.endswith("/v1/messages"):
                normalized = f"{normalized}/v1/messages"
            base_url = normalized
        if base_url:
            kwargs["base_url"] = base_url
        if self._extra_headers:
            kwargs["extra_headers"] = dict(self._extra_headers)
        kwargs.update(
            build_reasoning_request_kwargs(
                self._reasoning_request_profile,
                custom_json=self._reasoning_request_profile_json,
                protocol="anthropic" if self._is_anthropic() else "openai",
            )
        )
        return kwargs

    async def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[LLMEvent]:
        kwargs: dict[str, Any] = {
            "model": self._model(),
            "messages": _messages_to_litellm(messages, metadata=metadata),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "timeout": self._timeout_seconds,
            **self._extra_kwargs(),
        }
        if tools:
            kwargs["tools"] = _tools_to_litellm(tools)

        logger.info(
            "llm_request_debug",
            provider=self._provider_name,
            model=kwargs.get("model"),
            base_url_configured=bool(self._base_url),
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
            tools_count=len(tools),
            reasoning_request_profile=self._reasoning_request_profile,
            extra_body_present="extra_body" in kwargs,
            thinking_present="thinking" in kwargs,
            request_purpose=_metadata_string(metadata, "request_purpose"),
            session_id=_metadata_string(metadata, "session_id"),
            request_id=_metadata_string(metadata, "request_id"),
        )

        try:
            stream = cast(AsyncIterator[Any], await acompletion(**kwargs))
        except Exception as exc:
            if tools and _is_tool_schema_compatibility_error(exc):
                fallback_kwargs = dict(kwargs)
                fallback_kwargs.pop("tools", None)
                logger.warning(
                    "llm_tool_schema_fallback_without_tools",
                    provider=self._provider_name,
                    model=kwargs.get("model"),
                    error_type=type(exc).__name__,
                )
                try:
                    stream = cast(AsyncIterator[Any], await acompletion(**fallback_kwargs))
                except Exception as fallback_exc:
                    yield LLMEvent(
                        type="error",
                        data=self._error_payload(
                            fallback_exc,
                            retryable=_is_retryable_initial_error(fallback_exc),
                        ),
                    )
                    return
            else:
                yield LLMEvent(
                    type="error",
                    data=self._error_payload(exc, retryable=_is_retryable_initial_error(exc)),
                )
                return

        emitted_start = False
        tool_accumulators: dict[str, dict[str, str]] = {}
        active_tool_call_id: str | None = None
        think_tag_filter = ThinkTagContentFilter()

        try:
            async for chunk in stream:
                if not emitted_start:
                    yield LLMEvent(
                        type="message_start",
                        data={"model": getattr(chunk, "model", self._model_name)},
                    )
                    emitted_start = True

                choices: Any = getattr(chunk, "choices", None)
                choice = choices[0] if choices else None
                if choice is None:
                    continue
                delta = getattr(choice, "delta", None)
                if delta is None:
                    continue
                logger.debug("llm_stream_delta_debug", **_delta_debug_payload(delta))

                for event_type, event_data in normalize_openai_delta(
                    cast(dict[str, Any], _delta_to_dict(delta))
                ):
                    if event_type == "text_delta":
                        text = event_data.get("delta")
                        if isinstance(text, str):
                            for filtered_type, filtered_data in think_tag_filter.feed(text):
                                yield LLMEvent(type=filtered_type, data=filtered_data)
                        continue
                    yield LLMEvent(type=event_type, data=event_data)

                tool_calls = cast(list[Any], getattr(delta, "tool_calls", None) or [])
                for tool_call in tool_calls:
                    fn = getattr(tool_call, "function", None)
                    raw_name = getattr(fn, "name", None) if fn else None
                    name = raw_name if isinstance(raw_name, str) else None
                    raw_args_delta = getattr(fn, "arguments", "") if fn else ""
                    args_delta = raw_args_delta if isinstance(raw_args_delta, str) else ""
                    raw_tool_call_id = getattr(tool_call, "id", None)
                    tool_call_id = (
                        raw_tool_call_id
                        if isinstance(raw_tool_call_id, str)
                        else active_tool_call_id
                    )

                    if tool_call_id and tool_call_id not in tool_accumulators:
                        tool_accumulators[tool_call_id] = {
                            "name": name or "",
                            "args_str": "",
                        }
                        active_tool_call_id = tool_call_id
                        yield LLMEvent(
                            type="tool_call_start",
                            data={"id": tool_call_id, "name": name or ""},
                        )
                    elif tool_call_id is None and active_tool_call_id is not None:
                        tool_call_id = active_tool_call_id

                    if tool_call_id is None:
                        continue

                    if name and not tool_accumulators[tool_call_id]["name"]:
                        tool_accumulators[tool_call_id]["name"] = name
                    if args_delta:
                        tool_accumulators[tool_call_id]["args_str"] += args_delta
                        yield LLMEvent(
                            type="tool_call_delta",
                            data={"id": tool_call_id, "arguments_delta": args_delta},
                        )

                finish_reason = getattr(choice, "finish_reason", None)
                if finish_reason is not None:
                    for filtered_type, filtered_data in think_tag_filter.flush():
                        yield LLMEvent(type=filtered_type, data=filtered_data)
                    for tool_call_id, acc in tool_accumulators.items():
                        arguments: dict[str, Any] = {}
                        parse_error: str | None = None
                        try:
                            loaded: object = json.loads(acc["args_str"]) if acc["args_str"] else {}
                        except json.JSONDecodeError as exc:
                            parse_error = str(exc)
                            loaded = {}
                        if isinstance(loaded, dict):
                            arguments = cast(dict[str, Any], loaded)
                        data: dict[str, Any] = {
                            "id": tool_call_id,
                            "name": acc["name"],
                            "arguments": arguments,
                        }
                        if parse_error is not None:
                            data["arguments_parse_error"] = parse_error
                            data["raw_arguments"] = acc["args_str"]
                        yield LLMEvent(
                            type="tool_call_done",
                            data=data,
                        )

                    yield LLMEvent(
                        type="message_stop",
                        data={
                            "stop_reason": _normalize_stop_reason(
                                finish_reason if isinstance(finish_reason, str) else None
                            )
                        },
                    )
                    usage = getattr(chunk, "usage", None)
                    if usage is not None:
                        yield LLMEvent(
                            type="usage",
                            data={
                                "input_tokens": getattr(usage, "prompt_tokens", 0),
                                "output_tokens": getattr(usage, "completion_tokens", 0),
                            },
                        )
                    return
        except Exception as exc:
            yield LLMEvent(type="error", data=self._error_payload(exc, retryable=True))

    def _error_payload(self, exc: Exception, retryable: bool) -> dict[str, Any]:
        return LLMError(
            provider=self._provider_name,
            error_code=type(exc).__name__,
            message=str(exc),
            retryable=retryable,
        ).model_dump()
