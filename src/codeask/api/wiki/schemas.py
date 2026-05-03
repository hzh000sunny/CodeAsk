"""Schemas for native wiki APIs."""

from datetime import datetime

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
