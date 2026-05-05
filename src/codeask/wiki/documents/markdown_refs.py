"""Markdown reference parsing and resolution for wiki documents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import posixpath
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import WikiNode
from codeask.wiki.paths import normalize_asset_name, normalize_node_name

_IMG_LINK_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_REL_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)\s#]+)(?:\s+\"[^\"]*\")?\)")
_HTML_IMG_SRC_RE = re.compile(r"<img\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"'][^>]*>", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class MarkdownReference:
    target: str
    kind: str


def parse_markdown_references(raw_text: str) -> list[MarkdownReference]:
    refs: list[MarkdownReference] = []
    seen: set[tuple[str, str]] = set()
    for match in _IMG_LINK_RE.finditer(raw_text):
        target = match.group(1)
        key = (target, "image")
        if key not in seen:
            seen.add(key)
            refs.append(MarkdownReference(target=target, kind="image"))
    for match in _REL_LINK_RE.finditer(raw_text):
        target = match.group(1)
        key = (target, "link")
        if key not in seen:
            seen.add(key)
            refs.append(MarkdownReference(target=target, kind="link"))
    for match in _HTML_IMG_SRC_RE.finditer(raw_text):
        target = match.group(1)
        key = (target, "image")
        if key not in seen:
            seen.add(key)
            refs.append(MarkdownReference(target=target, kind="image"))
    return refs


def resolve_reference_path(source_path: str, target: str) -> str:
    source_dir = PurePosixPath(source_path).parent
    candidate = source_dir.joinpath(PurePosixPath(target))
    normalized = posixpath.normpath(PurePosixPath(str(candidate)).as_posix())
    parts = [part for part in PurePosixPath(normalized).parts if part not in {"", "."}]
    if normalized.endswith(".md"):
        normalized = "/".join(
            [
                *[normalize_node_name(part) for part in parts[:-1]],
                normalize_node_name(PurePosixPath(parts[-1]).stem),
            ]
        )
    elif normalized.endswith(".markdown"):
        normalized = "/".join(
            [
                *[normalize_node_name(part) for part in parts[:-1]],
                normalize_node_name(PurePosixPath(parts[-1]).stem),
            ]
        )
    else:
        normalized = "/".join(
            [
                *[normalize_node_name(part) for part in parts[:-1]],
                normalize_asset_name(parts[-1]),
            ]
        )
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")


async def resolve_markdown_references(
    session: AsyncSession,
    *,
    space_id: int,
    source_node_path: str,
    references: list[MarkdownReference],
) -> dict[str, list[dict[str, object]]]:
    resolved: list[dict[str, object]] = []
    broken_links: list[dict[str, object]] = []
    broken_assets: list[dict[str, object]] = []
    for ref in references:
        resolved_path = resolve_reference_path(source_node_path, ref.target)
        node = (
            await session.execute(
                select(WikiNode).where(
                    WikiNode.space_id == space_id,
                    WikiNode.path == resolved_path,
                    WikiNode.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        item = {
            "target": ref.target,
            "kind": ref.kind,
            "resolved_path": resolved_path,
            "resolved_node_id": node.id if node is not None else None,
            "broken": node is None,
        }
        resolved.append(item)
        if ref.kind == "link" and node is None:
            broken_links.append(item)
        if ref.kind == "image" and node is None:
            broken_assets.append(item)
    return {
        "resolved_refs": resolved,
        "broken_refs": {
            "links": broken_links,
            "assets": broken_assets,
        },
    }
