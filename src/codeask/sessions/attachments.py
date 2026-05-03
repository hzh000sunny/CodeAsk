"""Attachment storage and manifest helpers for sessions."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import structlog
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import SessionAttachment

log = structlog.get_logger("codeask.sessions.attachments")


def attachment_display_name(value: str) -> str:
    return Path(value.strip()).name.strip()


def attachment_description(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def append_attachment_alias(current: list[str] | None, value: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in [*(current or []), value]:
        cleaned = str(item or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


async def collect_session_storage_dirs(
    session: AsyncSession,
    data_dir: Path,
    session_ids: list[str],
) -> list[Path]:
    unique_session_ids = list(dict.fromkeys(session_ids))
    dirs: dict[str, Path] = {}
    for session_id in unique_session_ids:
        storage_dir = data_dir / "sessions" / session_id
        dirs[str(storage_dir)] = storage_dir

    if not unique_session_ids:
        return list(dirs.values())

    rows = (
        await session.execute(
            select(SessionAttachment.session_id, SessionAttachment.file_path).where(
                SessionAttachment.session_id.in_(unique_session_ids)
            )
        )
    ).all()
    for row in rows:
        attachment_storage_dir = _session_storage_dir_from_attachment_path(
            row.file_path,
            row.session_id,
        )
        if attachment_storage_dir is not None:
            dirs[str(attachment_storage_dir)] = attachment_storage_dir
    return list(dirs.values())


def remove_session_storage_dirs(storage_dirs: list[Path]) -> None:
    for storage_dir in storage_dirs:
        try:
            shutil.rmtree(storage_dir)
        except FileNotFoundError:
            continue
        except OSError as exc:
            log.warning(
                "session_storage_cleanup_failed",
                path=str(storage_dir),
                error=str(exc),
            )


async def write_session_manifest(request: Request, session_id: str) -> None:
    storage_dir = request.app.state.settings.data_dir / "sessions" / session_id
    storage_dir.mkdir(parents=True, exist_ok=True)
    factory = request.app.state.session_factory
    async with factory() as session:
        rows = (
            (
                await session.execute(
                    select(SessionAttachment)
                    .where(SessionAttachment.session_id == session_id)
                    .order_by(SessionAttachment.created_at, SessionAttachment.id)
                )
            )
            .scalars()
            .all()
        )
    manifest = {
        "session_id": session_id,
        "storage_dir": str(storage_dir),
        "attachments": [_attachment_manifest_entry(row) for row in rows],
    }
    manifest_path = storage_dir / "manifest.json"
    temp_path = storage_dir / "manifest.json.tmp"
    temp_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(manifest_path)


def _session_storage_dir_from_attachment_path(file_path: str, session_id: str) -> Path | None:
    path = Path(file_path)
    for candidate in path.parents:
        if candidate.name == session_id and candidate.parent.name == "sessions":
            return candidate
    return None


def _attachment_manifest_entry(row: SessionAttachment) -> dict[str, Any]:
    return {
        "id": row.id,
        "kind": row.kind,
        "display_name": row.display_name,
        "original_filename": row.original_filename,
        "aliases": row.aliases,
        "reference_names": row.reference_names,
        "description": row.description,
        "stored_filename": Path(row.file_path).name,
        "file_path": row.file_path,
        "mime_type": row.mime_type,
        "size_bytes": row.size_bytes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
