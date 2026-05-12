"""Structured events emitted by the chat runtime."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


def _empty_dict() -> dict[str, Any]:
    return {}


def _empty_list() -> list[Any]:
    return []


class EvidenceRef(BaseModel):
    type: Literal["wiki", "report", "attachment", "code", "feature", "policy"]
    title: str | None = None
    path: str | None = None
    node_id: int | None = None
    report_id: int | None = None
    attachment_id: str | None = None
    repo_id: str | None = None
    ref: str | None = None
    commit: str | None = None
    line: int | None = None
    metadata: dict[str, Any] = Field(default_factory=_empty_dict)


class RetrievalContextEventData(BaseModel):
    feature_catalog: list[dict[str, Any]] = Field(default_factory=_empty_list)
    feature_knowledge_index: list[dict[str, Any]] = Field(default_factory=_empty_list)
    feature_candidates: list[dict[str, Any]] = Field(default_factory=_empty_list)
    wiki_hits: list[dict[str, Any]] = Field(default_factory=_empty_list)
    report_hits: list[dict[str, Any]] = Field(default_factory=_empty_list)
    attachment_candidates: list[dict[str, Any]] = Field(default_factory=_empty_list)
    repo_candidates: list[dict[str, Any]] = Field(default_factory=_empty_list)


class RuntimeStateEventData(BaseModel):
    config_id: str | None = None
    config_name: str | None = None
    model_name: str
    protocol: str | None = None
    scope: str | None = None
    is_global_pool: bool = False
    update_reason: str = "snapshot"
    context_size_chars: int
    context_window_chars: int
    usage_ratio: float
    usage_label: str


class ToolCallEventData(BaseModel):
    tool_call_id: str
    tool_name: str
    arguments_summary: dict[str, Any] = Field(default_factory=_empty_dict)
    reason: str | None = None
    arguments_parse_error: str | None = None
    raw_arguments: str | None = None


class ToolResultEventData(BaseModel):
    tool_call_id: str
    tool_name: str
    ok: bool
    summary: str
    items_count: int = 0
    items_preview: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    truncated: bool = False
    raw_result_ref: str | None = None
    audit_raw_result: dict[str, Any] | None = Field(default=None, exclude=True)
    version_info: dict[str, Any] | None = None
    error_type: str | None = None
    message: str | None = None
    suggested_user_question: str | None = None


class EvidenceEventData(BaseModel):
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class ClarificationEventData(BaseModel):
    question: str
    reason: str | None = None
    options: list[dict[str, Any]] = Field(default_factory=list)
    allow_free_text: bool = True


class AssistantActionEventData(BaseModel):
    action: str
    summary: str
    required_confirmation: bool = False
    metadata: dict[str, Any] = Field(default_factory=_empty_dict)


RuntimeEventType = Literal[
    "llm_input",
    "text_delta",
    "reasoning_observed",
    "reasoning_leak_detected",
    "runtime_state",
    "retrieval_context",
    "tool_call",
    "tool_result",
    "evidence",
    "assistant_action",
    "needs_clarification",
    "done",
    "error",
]


RuntimeEventData = (
    RuntimeStateEventData
    | RetrievalContextEventData
    | ToolCallEventData
    | ToolResultEventData
    | EvidenceEventData
    | ClarificationEventData
    | AssistantActionEventData
    | dict[str, Any]
)


class ChatRuntimeEvent(BaseModel):
    type: RuntimeEventType
    data: Any = Field(default_factory=_empty_dict)
