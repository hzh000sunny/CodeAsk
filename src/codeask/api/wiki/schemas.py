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
