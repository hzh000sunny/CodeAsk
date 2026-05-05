"""Schemas for native wiki APIs."""

from datetime import datetime
from typing import Literal
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
    feature_id: int | None = None
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
    space: WikiSpaceRead | None = None
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
    provenance_summary: object | None = None
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


class WikiImportSessionCreate(BaseModel):
    space_id: int
    parent_id: int | None = None
    mode: str


class WikiImportSessionScanItemWrite(BaseModel):
    relative_path: str
    item_kind: str
    included: bool
    ignore_reason: str | None = None


class WikiImportSessionScanWrite(BaseModel):
    items: list[WikiImportSessionScanItemWrite]


class WikiImportSessionSummaryRead(BaseModel):
    total_files: int
    pending_count: int
    uploading_count: int
    uploaded_count: int
    conflict_count: int
    failed_count: int
    ignored_count: int
    skipped_count: int


class WikiImportSessionRead(BaseModel):
    id: int
    space_id: int
    parent_id: int | None
    mode: str
    status: str
    requested_by_subject_id: str
    created_at: datetime
    updated_at: datetime
    summary: WikiImportSessionSummaryRead


class WikiMaintenanceReindexRead(BaseModel):
    root_node_id: int
    reindexed_documents: int


class WikiImportSessionItemRead(BaseModel):
    id: int
    source_path: str
    target_path: str | None
    item_kind: str
    status: str
    progress_percent: int
    ignore_reason: str | None = None
    staging_path: str | None = None
    result_node_id: int | None = None
    error_message: str | None = None


class WikiImportSessionItemsRead(BaseModel):
    items: list[WikiImportSessionItemRead]


class WikiImportSessionUploadRead(BaseModel):
    session: WikiImportSessionRead
    item: WikiImportSessionItemRead


WikiSourceKind = Literal["manual_upload", "directory_import", "session_promotion"]
WikiSourceStatus = Literal["active", "failed", "archived"]


class WikiSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    space_id: int
    kind: WikiSourceKind
    display_name: str
    uri: str | None
    metadata_json: object | None
    status: WikiSourceStatus
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WikiSourceListRead(BaseModel):
    items: list[WikiSourceRead]


class WikiSourceCreate(BaseModel):
    space_id: int
    kind: WikiSourceKind
    display_name: str
    uri: str | None = None
    metadata_json: object | None = None


class WikiSourceUpdate(BaseModel):
    display_name: str | None = None
    uri: str | None = None
    metadata_json: object | None = None
    status: WikiSourceStatus | None = None


WikiPromotionTargetKind = Literal["document", "asset"]


class WikiSessionAttachmentPromotionCreate(BaseModel):
    session_id: str
    attachment_id: str
    space_id: int
    parent_id: int | None = None
    target_kind: WikiPromotionTargetKind
    name: str | None = None


class WikiPromotionRead(BaseModel):
    node: WikiNodeRead
    document_id: int | None
    source_id: int | None


class WikiImportSessionResolveWrite(BaseModel):
    action: str


class WikiImportSessionBulkResolveWrite(BaseModel):
    action: str


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
    heading_path: str | None = None
    document_id: int | None = None
    report_id: int | None = None


class WikiSearchResultsRead(BaseModel):
    items: list[WikiSearchHitRead]


class WikiPathResolveHitRead(BaseModel):
    node_id: int
    space_id: int
    feature_id: int
    node_type: str
    name: str
    path: str
    system_role: str | None
    score: float
    match_reason: str
    matched_phrase: str


class WikiPathResolveResultsRead(BaseModel):
    items: list[WikiPathResolveHitRead]
