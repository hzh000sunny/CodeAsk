"""Schemas for session APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def _empty_feature_ids() -> list[int]:
    return []


def _empty_repo_bindings() -> list[RepoBindingIn]:
    return []


class SessionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_by_subject_id: str
    status: str
    created_at: datetime
    updated_at: datetime


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
    kind: Literal["log", "image", "doc", "other"]
    file_path: str
    mime_type: str
