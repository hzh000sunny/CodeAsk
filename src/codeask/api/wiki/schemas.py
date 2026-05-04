"""Schemas for native wiki APIs."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class WikiSpaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    feature_id: int
    scope: str
    display_name: str
    slug: str
    status: str
    created_at: datetime
    updated_at: datetime


class WikiNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    space_id: int
    parent_id: int | None
    type: str
    name: str
    path: str
    system_role: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime


class WikiNodePermissions(BaseModel):
    read: bool
    write: bool
    admin: bool


class WikiNodeDetailRead(WikiNodeRead):
    permissions: WikiNodePermissions


class WikiNodeCreate(BaseModel):
    space_id: int
    parent_id: int | None = None
    type: str
    name: str


class WikiNodeUpdate(BaseModel):
    parent_id: int | None = None
    name: str | None = None
    sort_order: int | None = None


class WikiTreeRead(BaseModel):
    space: WikiSpaceRead
    nodes: list[WikiNodeRead]


class WikiDocumentDetailRead(BaseModel):
    document_id: int
    node_id: int
    title: str
    current_version_id: int | None
    current_body_markdown: str | None
    draft_body_markdown: str | None
    index_status: str
    broken_refs_json: object | None
    resolved_refs_json: list[dict[str, object]]
    provenance_json: object | None
    permissions: WikiNodePermissions


class WikiDraftWrite(BaseModel):
    body_markdown: str


class WikiPublishRequest(BaseModel):
    body_markdown: str | None = None


class WikiDocumentVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    version_no: int
    body_markdown: str
    created_by_subject_id: str
    created_at: datetime
    updated_at: datetime


class WikiDocumentVersionListRead(BaseModel):
    versions: list[WikiDocumentVersionRead]


class WikiDocumentVersionDetailRead(WikiDocumentVersionRead):
    pass


class WikiDocumentDiffRead(BaseModel):
    from_version_id: int
    from_version_no: int
    to_version_id: int
    to_version_no: int
    patch: str


class WikiAssetRead(BaseModel):
    node_id: int
    path: str
    mime_type: str
    original_name: str
    file_name: str
    size_bytes: int | None


class WikiImportPreflightIssueRead(BaseModel):
    severity: str
    code: str
    message: str
    target: str | None = None
    resolved_path: str | None = None


class WikiImportPreflightItemRead(BaseModel):
    relative_path: str
    kind: str
    target_path: str
    status: str
    issues: list[WikiImportPreflightIssueRead]


class WikiImportPreflightSummaryRead(BaseModel):
    total_files: int
    document_count: int
    asset_count: int
    conflict_count: int
    warning_count: int


class WikiImportPreflightRead(BaseModel):
    ready: bool
    summary: WikiImportPreflightSummaryRead
    items: list[WikiImportPreflightItemRead]


class WikiImportJobRead(BaseModel):
    id: int
    space_id: int
    status: str
    requested_by_subject_id: str
    created_at: datetime
    updated_at: datetime
    summary: WikiImportPreflightSummaryRead


class WikiImportJobItemRead(BaseModel):
    id: int
    source_path: str
    target_path: str | None
    item_kind: str | None
    status: str
    warnings: list[dict[str, Any]]
    staging_path: str | None = None
    result_node_id: int | None = None


class WikiImportJobItemsRead(BaseModel):
    items: list[WikiImportJobItemRead]


class WikiReportProjectionRead(BaseModel):
    node_id: int
    report_id: int
    feature_id: int | None
    title: str
    status: str
    status_group: str
    verified: bool
    verified_by: str | None
    verified_at: datetime | None
    updated_at: datetime


class WikiReportProjectionListRead(BaseModel):
    items: list[WikiReportProjectionRead]


class WikiReportDetailRead(BaseModel):
    node_id: int
    report_id: int
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


class WikiSearchHitRead(BaseModel):
    kind: str
    node_id: int
    title: str
    path: str
    feature_id: int | None
    group_key: str
    group_label: str
    snippet: str
    score: float
    document_id: int | None = None
    report_id: int | None = None


class WikiSearchResultsRead(BaseModel):
    items: list[WikiSearchHitRead]
