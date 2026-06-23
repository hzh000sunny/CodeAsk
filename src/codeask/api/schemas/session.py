"""Schemas for session APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from codeask.llm.types import LLMConfigMode


def _empty_feature_ids() -> list[int]:
    return []


def _empty_repo_bindings() -> list[RepoBindingIn]:
    return []


def _empty_attachment_names() -> list[str]:
    return []


class SessionCreate(BaseModel):
    title: str = Field(default="新的研发会话", min_length=1, max_length=256)


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_by_subject_id: str
    status: str
    pinned: bool
    title_source: Literal["default", "auto", "manual"]
    title_generated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SessionTurnResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    turn_index: int
    role: Literal["user", "agent"]
    content: str
    evidence: Any | None
    stopped_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AgentTraceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    turn_id: str
    stage: str
    event_type: str
    payload: Any
    created_at: datetime
    updated_at: datetime


class SessionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=256)
    pinned: bool | None = None


class SessionBulkDelete(BaseModel):
    session_ids: list[str] = Field(..., min_length=1)


class SessionBulkDeleteResponse(BaseModel):
    deleted_ids: list[str]


class SessionReportCreate(BaseModel):
    feature_id: int | None = None
    title: str = Field(..., min_length=1, max_length=500)
    body_markdown: str = Field(..., min_length=1)


class SessionReportPrepareRequest(BaseModel):
    feature_id: int | None = None


class SessionReportPrepared(BaseModel):
    existing_report_id: int | None = None
    feature_id: int | None = None
    inferred_feature_ids: list[int] = Field(default_factory=_empty_feature_ids)
    title: str = Field(..., min_length=1, max_length=500)
    body_markdown: str = Field(..., min_length=1)


class SessionReportPrepareStatus(BaseModel):
    request_id: str
    status: Literal["running", "succeeded", "failed"]
    draft: SessionReportPrepared | None = None
    error: str | None = None


class RepoBindingIn(BaseModel):
    repo_id: str
    ref: str


class GuestLLMConfigIn(BaseModel):
    name: str = Field(default="访客 LLM", min_length=1, max_length=128)
    mode: LLMConfigMode = "catalog"
    provider_id: str = Field(..., min_length=1, max_length=128)
    base_url: str | None = Field(default=None, max_length=2000)
    api_key: str = Field(..., min_length=1, max_length=4096)
    headers: dict[str, str] | None = None
    model_name: str = Field(..., min_length=1, max_length=256)
    reasoning_profile: str = Field(default="none", max_length=128)
    reasoning_profile_json: str | None = Field(default=None, max_length=20000)


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1)
    client_turn_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^turn_[A-Za-z0-9_-]+$",
    )
    feature_ids: list[int] = Field(default_factory=_empty_feature_ids)
    repo_bindings: list[RepoBindingIn] = Field(default_factory=_empty_repo_bindings)
    reply_to: str | None = None
    guest_llm_config: GuestLLMConfigIn | None = None


class AttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    kind: Literal["log", "image", "doc", "other"]
    display_name: str
    original_filename: str
    aliases: list[str] = Field(default_factory=_empty_attachment_names)
    reference_names: list[str] = Field(default_factory=_empty_attachment_names)
    description: str | None = None
    file_path: str
    mime_type: str
    size_bytes: int | None
    created_at: datetime
    updated_at: datetime


class AttachmentUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=2000)
