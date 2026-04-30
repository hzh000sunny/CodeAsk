"""LiteLLM-backed adapters for provider-neutral streaming."""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol, cast

from litellm import acompletion as _raw_acompletion  # type: ignore[reportUnknownVariableType]

from codeask.llm.types import (
    LLMError,
    LLMEvent,
    LLMMessage,
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


def _normalize_stop_reason(reason: str | None) -> StopReason:
    if reason is None:
        return "unknown"
    return _OPENAI_TO_INTERNAL_STOP.get(reason, "unknown")


def _messages_to_litellm(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
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
        tool_calls: list[dict[str, Any]] = []
        for block in message.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
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
        converted.append(record)
    return converted


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


class LLMClient(Protocol):
    def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[LLMEvent]: ...


class _BaseClient:
    _provider_name: str = "openai"

    def __init__(self, api_key: str, model_name: str, base_url: str | None = None) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._base_url = base_url

    def _model(self) -> str:
        return self._model_name

    def _extra_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"api_key": self._api_key}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        return kwargs

    async def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[LLMEvent]:
        kwargs: dict[str, Any] = {
            "model": self._model(),
            "messages": _messages_to_litellm(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            **self._extra_kwargs(),
        }
        if tools:
            kwargs["tools"] = _tools_to_litellm(tools)

        try:
            stream = cast(AsyncIterator[Any], await acompletion(**kwargs))
        except Exception as exc:
            yield LLMEvent(type="error", data=self._error_payload(exc, retryable=False))
            return

        emitted_start = False
        tool_accumulators: dict[str, dict[str, str]] = {}
        active_tool_call_id: str | None = None

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

                content = getattr(delta, "content", None)
                if content:
                    yield LLMEvent(type="text_delta", data={"delta": content})

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
                    for tool_call_id, acc in tool_accumulators.items():
                        arguments: dict[str, Any] = {}
                        try:
                            loaded: object = json.loads(acc["args_str"]) if acc["args_str"] else {}
                        except json.JSONDecodeError:
                            loaded = {}
                        if isinstance(loaded, dict):
                            arguments = cast(dict[str, Any], loaded)
                        yield LLMEvent(
                            type="tool_call_done",
                            data={
                                "id": tool_call_id,
                                "name": acc["name"],
                                "arguments": arguments,
                            },
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


class OpenAIClient(_BaseClient):
    _provider_name = "openai"


class OpenAICompatibleClient(_BaseClient):
    _provider_name = "openai_compatible"

    def _model(self) -> str:
        return f"openai/{self._model_name}"


class AnthropicClient(_BaseClient):
    _provider_name = "anthropic"

    def _model(self) -> str:
        return f"anthropic/{self._model_name}"
