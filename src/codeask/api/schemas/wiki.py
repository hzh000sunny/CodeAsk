"""Schemas for wiki feature, document, report, and search APIs."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FeatureCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    description: str | None = None


class FeatureUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class FeatureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None
    owner_subject_id: str
    summary_text: str | None
    created_at: datetime
    updated_at: datetime


class DocumentUpload(BaseModel):
    feature_id: int
    title: str | None = None
    tags: list[str] | None = None


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    feature_id: int
    kind: str
    title: str
    path: str
    tags_json: list[str] | None
    summary: str | None
    is_deleted: bool
    uploaded_by_subject_id: str
    created_at: datetime
    updated_at: datetime


class DocumentSearchHit(BaseModel):
    chunk_id: int
    document_id: int
    document_title: str
    document_path: str
    feature_id: int
    heading_path: str
    snippet: str
    score: float
    source_channel: str


class ReportCreate(BaseModel):
    feature_id: int | None = None
    title: str = Field(..., min_length=1, max_length=500)
    body_markdown: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReportUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    body_markdown: str | None = None
    metadata: dict[str, Any] | None = None


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    feature_id: int | None
    title: str
    body_markdown: str
    metadata_json: dict[str, Any]
    status: str
    verified: bool
    verified_by: str | None
    verified_at: datetime | None
    created_by_subject_id: str
    created_at: datetime
    updated_at: datetime


class ReportSearchHit(BaseModel):
    report_id: int
    title: str
    feature_id: int | None
    verified_by: str | None
    verified_at: datetime | None
    commit_sha: str | None
    snippet: str
    score: float


class SearchResults(BaseModel):
    documents: list[DocumentSearchHit] = Field(default_factory=list)
    reports: list[ReportSearchHit] = Field(default_factory=list)
