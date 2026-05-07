"""Tool contracts for the chat runtime."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from codeask.agent.chat_runtime.events import EvidenceRef


def _empty_dict() -> dict[str, Any]:
    return {}


class ToolErrorType(StrEnum):
    INVALID_INPUT = "invalid_input"
    NOT_FOUND = "not_found"
    OUT_OF_SCOPE = "out_of_scope"
    PERMISSION_DENIED = "permission_denied"
    NEEDS_CLARIFICATION = "needs_clarification"
    VERSION_UNKNOWN = "version_unknown"
    TOO_LARGE = "too_large"
    TRANSIENT_ERROR = "transient_error"
    INTERNAL_ERROR = "internal_error"


class ToolContext(BaseModel):
    session_id: str
    turn_id: str
    subject_id: str | None = None
    explicit_constraints: dict[str, Any] = Field(default_factory=_empty_dict)
    limits: dict[str, Any] = Field(default_factory=_empty_dict)
    services: dict[str, Any] = Field(default_factory=_empty_dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ToolSpec(BaseModel):
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel] | None = None
    read_only: bool = False
    concurrency_safe: bool = False
    requires_confirmation: bool = True
    requires_user_interaction: bool = False
    max_result_size_chars: int = 12_000
    enabled: bool = True

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def input_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=_empty_dict)


class ToolResult(BaseModel):
    ok: bool
    tool: str
    summary: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    truncated: bool = False
    raw_result_ref: str | None = None
    version_info: dict[str, Any] | None = None
    error_type: ToolErrorType | None = None
    message: str | None = None
    suggested_user_question: str | None = None

    @classmethod
    def error(
        cls,
        *,
        tool: str,
        error_type: ToolErrorType,
        message: str,
        suggested_user_question: str | None = None,
        summary: str | None = None,
    ) -> ToolResult:
        return cls(
            ok=False,
            tool=tool,
            summary=summary or message,
            error_type=error_type,
            message=message,
            suggested_user_question=suggested_user_question,
        )


def _tool_result_ok(
    cls: type[ToolResult],
    *,
    tool: str,
    summary: str,
    items: list[dict[str, Any]] | None = None,
    evidence_refs: list[EvidenceRef] | None = None,
    warnings: list[str] | None = None,
    truncated: bool = False,
    raw_result_ref: str | None = None,
    version_info: dict[str, Any] | None = None,
) -> ToolResult:
    return cls(
        ok=True,
        tool=tool,
        summary=summary,
        items=items or [],
        evidence_refs=evidence_refs or [],
        warnings=warnings or [],
        truncated=truncated,
        raw_result_ref=raw_result_ref,
        version_info=version_info,
    )


ToolResult.ok = classmethod(_tool_result_ok)  # type: ignore[attr-defined, method-assign]

ToolHandler = Callable[[BaseModel, ToolContext], Awaitable[ToolResult]]
