"""Pydantic v2 models for /api/repos and /api/code/* endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RepoSource = Literal["git", "local_dir"]
RepoStatus = Literal["registered", "cloning", "ready", "failed"]


class RepoCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    source: RepoSource
    url: str | None = Field(default=None, max_length=1024)
    local_path: str | None = Field(default=None, max_length=1024)

    def assert_consistent(self) -> None:
        if self.source == "git" and not self.url:
            raise ValueError("source=git requires url")
        if self.source == "local_dir" and not self.local_path:
            raise ValueError("source=local_dir requires local_path")


class RepoUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    source: RepoSource | None = None
    url: str | None = Field(default=None, max_length=1024)
    local_path: str | None = Field(default=None, max_length=1024)

    def assert_consistent(self, current_source: RepoSource) -> None:
        source = self.source or current_source
        if source == "git" and self.url == "":
            raise ValueError("source=git requires url")
        if source == "local_dir" and self.local_path == "":
            raise ValueError("source=local_dir requires local_path")


class RepoOut(BaseModel):
    id: str
    name: str
    source: RepoSource
    url: str | None
    local_path: str | None
    bare_path: str
    status: RepoStatus
    error_message: str | None
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RepoListOut(BaseModel):
    repos: list[RepoOut]


class CodeGrepIn(BaseModel):
    repo_id: str = Field(..., min_length=1, max_length=64)
    commit: str | None = Field(default=None, max_length=256)
    session_id: str = Field(..., min_length=1, max_length=128)
    pattern: str = Field(..., min_length=1, max_length=1024)
    paths: list[str] | None = Field(default=None)
    max_count: int = Field(default=50, ge=1, le=1000)


class CodeGrepHitOut(BaseModel):
    path: str
    line_number: int
    line_text: str


class CodeGrepOut(BaseModel):
    ok: bool
    repo_id: str
    commit: str
    hits: list[CodeGrepHitOut]
    truncated: bool


class CodeReadIn(BaseModel):
    repo_id: str = Field(..., min_length=1, max_length=64)
    commit: str | None = Field(default=None, max_length=256)
    session_id: str = Field(..., min_length=1, max_length=128)
    path: str = Field(..., min_length=1, max_length=2048)
    line_range: tuple[int, int]


class CodeReadOut(BaseModel):
    ok: bool
    repo_id: str
    commit: str
    path: str
    start_line: int
    end_line: int
    text: str
    truncated: bool


class CodeSymbolsIn(BaseModel):
    repo_id: str = Field(..., min_length=1, max_length=64)
    commit: str | None = Field(default=None, max_length=256)
    session_id: str = Field(..., min_length=1, max_length=128)
    symbol: str = Field(..., min_length=1, max_length=256)


class CodeSymbolHitOut(BaseModel):
    name: str
    path: str
    line: int
    kind: str


class CodeSymbolsOut(BaseModel):
    ok: bool
    repo_id: str
    commit: str
    symbols: list[CodeSymbolHitOut]


class ApiError(BaseModel):
    ok: bool = False
    error_code: str
    message: str
    recoverable: bool = True
