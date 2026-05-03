"""Support helpers for wiki API route handlers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.api.schemas.code_index import RepoOut
from codeask.db.models import Feature, Repo

_KIND_BY_EXT: dict[str, str] = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".text": "text",
    ".pdf": "pdf",
    ".docx": "docx",
}
_IMG_LINK_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_REL_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)\s#]+)(?:\s+\"[^\"]*\")?\)")


def repo_to_out(repo: Repo) -> RepoOut:
    return RepoOut(
        id=repo.id,
        name=repo.name,
        source=repo.source,  # type: ignore[arg-type]
        url=repo.url,
        local_path=repo.local_path,
        bare_path=repo.bare_path,
        status=repo.status,  # type: ignore[arg-type]
        error_message=repo.error_message,
        last_synced_at=repo.last_synced_at,
        created_at=repo.created_at,
        updated_at=repo.updated_at,
    )


def slugify_feature_name(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return normalized[:120].strip("-") or "feature"


async def unique_feature_slug(name: str, session: AsyncSession) -> str:
    base = slugify_feature_name(name)
    slug = base
    suffix = 2
    while (
        await session.execute(select(Feature.id).where(Feature.slug == slug))
    ).scalar_one_or_none() is not None:
        tail = f"-{suffix}"
        slug = f"{base[: 120 - len(tail)]}{tail}"
        suffix += 1
    return slug


def kind_from_filename(name: str) -> str:
    extension = Path(name).suffix.lower()
    if extension not in _KIND_BY_EXT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported file extension: {extension}",
        )
    return _KIND_BY_EXT[extension]


def wiki_storage_dir(request: Request) -> Path:
    settings = request.app.state.settings
    path = settings.data_dir / "wiki"
    path.mkdir(parents=True, exist_ok=True)
    return path


def parse_tags(tags: str | None) -> list[str] | None:
    parsed = [tag.strip() for tag in (tags or "").split(",") if tag.strip()]
    return parsed or None


def markdown_references(raw_text: str) -> list[tuple[str, Literal["image", "link"]]]:
    references: list[tuple[str, Literal["image", "link"]]] = []
    seen_refs: set[tuple[str, Literal["image", "link"]]] = set()
    for match in _IMG_LINK_RE.finditer(raw_text):
        key = (match.group(1), "image")
        if key not in seen_refs:
            seen_refs.add(key)
            references.append(key)
    for match in _REL_LINK_RE.finditer(raw_text):
        key = (match.group(1), "link")
        if key not in seen_refs:
            seen_refs.add(key)
            references.append(key)
    return references
