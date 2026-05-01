"""Schemas for session APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def _empty_feature_ids() -> list[int]:
    return []


def _empty_repo_bindings() -> list[RepoBindingIn]:
    return []


def _empty_attachment_names() -> list[str]:
    return []


class SessionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_by_subject_id: str
    status: str
    pinned: bool
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
    feature_id: int
    title: str = Field(..., min_length=1, max_length=500)


class RepoBindingIn(BaseModel):
    repo_id: str
    ref: str


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1)
    feature_ids: list[int] = Field(default_factory=_empty_feature_ids)
    repo_bindings: list[RepoBindingIn] = Field(default_factory=_empty_repo_bindings)
    force_code_investigation: bool = False
    reply_to: str | None = None


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
