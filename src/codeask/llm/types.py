"""Provider-neutral LLM types."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

StopReason = Literal[
    "end_turn",
    "tool_call",
    "max_tokens",
    "stop_sequence",
    "content_filter",
    "error",
    "unknown",
]

EventType = Literal[
    "message_start",
    "text_delta",
    "tool_call_start",
    "tool_call_delta",
    "tool_call_done",
    "message_stop",
    "usage",
    "error",
]

ProviderProtocol = Literal["openai", "openai_compatible", "anthropic"]


def _empty_tools() -> list[ToolDef]:
    return []


def _empty_metadata() -> dict[str, Any]:
    return {}


class TextBlock(BaseModel):
    type: Literal["text"]
    text: str


class ToolCallBlock(BaseModel):
    type: Literal["tool_call"]
    id: str
    name: str
    arguments: dict[str, Any]


class ToolResultBlock(BaseModel):
    type: Literal["tool_result"]
    tool_call_id: str
    content: str | dict[str, Any]
    is_error: bool = False


ContentBlock = TextBlock | ToolCallBlock | ToolResultBlock


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: list[ContentBlock]
    tool_call_id: str | None = None


class ToolDef(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class ToolChoice(BaseModel):
    type: Literal["auto", "any", "tool", "none"] = "auto"
    name: str | None = None


class LLMRequest(BaseModel):
    config_id: str | None = None
    messages: list[LLMMessage]
    tools: list[ToolDef] = Field(default_factory=_empty_tools)
    tool_choice: ToolChoice | None = None
    max_tokens: int
    temperature: float
    metadata: dict[str, Any] = Field(default_factory=_empty_metadata)


class LLMEvent(BaseModel):
    type: EventType
    data: dict[str, Any] = Field(default_factory=_empty_metadata)


class LLMError(BaseModel):
    provider: str
    error_code: str
    message: str
    retryable: bool
    raw: dict[str, Any] | None = None
