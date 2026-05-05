"""Promote session attachments into formal wiki nodes."""

from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path
from secrets import token_hex

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import (
    Feature,
    Session,
    SessionAttachment,
    WikiAsset,
    WikiDocument,
    WikiNode,
    WikiSource,
    WikiSpace,
)
from codeask.metrics.audit import record_audit_log
from codeask.wiki.audit import AuditWriter
from codeask.wiki.actor import WikiActor
from codeask.wiki.documents import WikiDocumentService
from codeask.wiki.paths import normalize_asset_name
from codeask.wiki.permissions import can_write_feature
from codeask.wiki.tree import WikiTreeService

_TEXT_SUFFIXES = {".md", ".txt", ".log"}


class WikiPromotionService:
    def __init__(self, audit: AuditWriter | None = None) -> None:
        self._audit = audit or AuditWriter()

    async def promote_session_attachment(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        settings_data_dir: Path,
        session_id: str,
        attachment_id: str,
        space_id: int,
        parent_id: int | None,
        target_kind: str,
        name: str | None,
    ) -> dict[str, object]:
        source_session = await self._load_session(session, session_id=session_id, actor=actor)
        attachment = await self._load_attachment(
            session,
            session_id=source_session.id,
            attachment_id=attachment_id,
        )
        space = await self._load_space(session, space_id=space_id)
        parent = await self._load_parent(session, space=space, parent_id=parent_id)
        feature = await self._load_feature_for_space(session, space_id=space.id)
        self._require_write(actor, feature)

        source = WikiSource(
            space_id=space.id,
            kind="session_promotion",
            display_name=attachment.display_name,
            uri=None,
            metadata_json={
                "session_id": source_session.id,
                "attachment_id": attachment.id,
                "original_filename": attachment.original_filename,
            },
            status="active",
        )
        session.add(source)
        await session.flush()

        if target_kind == "document":
            result = await self._promote_document(
                session,
                actor=actor,
                attachment=attachment,
                parent=parent,
                space=space,
                source=source,
                title=name or Path(attachment.display_name).stem,
            )
        elif target_kind == "asset":
            result = await self._promote_asset(
                session,
                settings_data_dir=settings_data_dir,
                attachment=attachment,
                parent=parent,
                space=space,
                source=source,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="unsupported wiki promotion target kind",
            )
        await record_audit_log(
            session,
            entity_type="wiki_promotion",
            entity_id=str(source.id),
            action="session_attachment_promote",
            subject_id=actor.subject_id,
            to_status=target_kind,
        )
        self._audit.write(
            "wiki_promotion.session_attachment_promoted",
            {
                "source_id": int(source.id),
                "space_id": int(space.id),
                "session_id": source_session.id,
                "attachment_id": attachment.id,
                "target_kind": target_kind,
            },
            subject_id=actor.subject_id,
        )
        return result

    async def _promote_document(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        attachment: SessionAttachment,
        parent: WikiNode | None,
        space: WikiSpace,
        source: WikiSource,
        title: str,
    ) -> dict[str, object]:
        suffix = Path(attachment.original_filename).suffix.lower()
        if suffix not in _TEXT_SUFFIXES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="session attachment cannot be promoted as a wiki document",
            )
        body_markdown = Path(attachment.file_path).read_text(encoding="utf-8")
        node = await WikiTreeService().create_node(
            session,
            actor=actor,
            space=space,
            parent=parent,
            node_type="document",
            name=title,
        )
        document = (
            await session.execute(select(WikiDocument).where(WikiDocument.node_id == node.id))
        ).scalar_one()
        document.title = title
        document.provenance_json = {
            "source": "session_promotion",
            "source_id": source.id,
            "session_id": attachment.session_id,
            "attachment_id": attachment.id,
            "source_path": attachment.display_name,
        }
        await session.flush()
        detail = await WikiDocumentService().publish_document(
            session,
            node_id=node.id,
            actor=actor,
            body_markdown=body_markdown,
        )
        return {
            "node": {
                "id": node.id,
                "space_id": node.space_id,
                "feature_id": space.feature_id,
                "parent_id": node.parent_id,
                "type": node.type,
                "name": node.name,
                "path": node.path,
                "system_role": node.system_role,
                "sort_order": node.sort_order,
                "created_at": node.created_at,
                "updated_at": node.updated_at,
            },
            "document_id": detail["document_id"],
            "source_id": source.id,
        }

    async def _promote_asset(
        self,
        session: AsyncSession,
        *,
        settings_data_dir: Path,
        attachment: SessionAttachment,
        parent: WikiNode | None,
        space: WikiSpace,
        source: WikiSource,
    ) -> dict[str, object]:
        display_name = Path(attachment.display_name).name
        leaf = await self._unique_asset_leaf(
            session,
            space_id=space.id,
            parent_path=parent.path if parent is not None else None,
            preferred_name=display_name,
        )
        path = leaf if parent is None else f"{parent.path}/{leaf}"
        node = WikiNode(
            space_id=space.id,
            parent_id=parent.id if parent is not None else None,
            type="asset",
            name=display_name,
            path=path,
            system_role=None,
            sort_order=0,
        )
        session.add(node)
        await session.flush()

        source_path = Path(attachment.file_path)
        asset_dir = settings_data_dir / "wiki" / "assets" / f"space_{space.id}"
        asset_dir.mkdir(parents=True, exist_ok=True)
        storage_name = f"{token_hex(8)}_{display_name}"
        target = asset_dir / storage_name
        shutil.copyfile(source_path, target)
        session.add(
            WikiAsset(
                node_id=node.id,
                original_name=display_name,
                file_name=storage_name,
                storage_path=str(target),
                mime_type=attachment.mime_type
                or mimetypes.guess_type(display_name)[0]
                or "application/octet-stream",
                size_bytes=target.stat().st_size,
                provenance_json={
                    "source": "session_promotion",
                    "source_id": source.id,
                    "session_id": attachment.session_id,
                    "attachment_id": attachment.id,
                    "source_path": attachment.display_name,
                },
            )
        )
        await session.flush()
        return {
            "node": {
                "id": node.id,
                "space_id": node.space_id,
                "feature_id": space.feature_id,
                "parent_id": node.parent_id,
                "type": node.type,
                "name": node.name,
                "path": node.path,
                "system_role": node.system_role,
                "sort_order": node.sort_order,
                "created_at": node.created_at,
                "updated_at": node.updated_at,
            },
            "document_id": None,
            "source_id": source.id,
        }

    async def _load_session(
        self,
        session: AsyncSession,
        *,
        session_id: str,
        actor: WikiActor,
    ) -> Session:
        row = (
            await session.execute(
                select(Session).where(
                    Session.id == session_id,
                    Session.created_by_subject_id == actor.subject_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
        return row

    async def _load_attachment(
        self,
        session: AsyncSession,
        *,
        session_id: str,
        attachment_id: str,
    ) -> SessionAttachment:
        row = (
            await session.execute(
                select(SessionAttachment).where(
                    SessionAttachment.id == attachment_id,
                    SessionAttachment.session_id == session_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="attachment not found")
        return row

    async def _load_space(self, session: AsyncSession, *, space_id: int) -> WikiSpace:
        space = (
            await session.execute(select(WikiSpace).where(WikiSpace.id == space_id))
        ).scalar_one_or_none()
        if space is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="wiki space not found")
        return space

    async def _load_parent(
        self,
        session: AsyncSession,
        *,
        space: WikiSpace,
        parent_id: int | None,
    ) -> WikiNode | None:
        if parent_id is None:
            return None
        parent = (
            await session.execute(select(WikiNode).where(WikiNode.id == parent_id))
        ).scalar_one_or_none()
        if parent is None or parent.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="wiki node not found")
        if parent.space_id != space.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="parent node belongs to a different wiki space",
            )
        return parent

    async def _load_feature_for_space(self, session: AsyncSession, *, space_id: int) -> Feature:
        feature = (
            await session.execute(
                select(Feature)
                .join(WikiSpace, WikiSpace.feature_id == Feature.id)
                .where(WikiSpace.id == space_id)
            )
        ).scalar_one_or_none()
        if feature is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feature not found")
        return feature

    async def _unique_asset_leaf(
        self,
        session: AsyncSession,
        *,
        space_id: int,
        parent_path: str | None,
        preferred_name: str,
    ) -> str:
        safe = normalize_asset_name(preferred_name)
        stem = Path(safe).stem
        suffix = Path(safe).suffix
        candidate = safe
        index = 2
        while await self._path_exists(
            session,
            space_id=space_id,
            path=candidate if parent_path is None else f"{parent_path}/{candidate}",
        ):
            candidate = f"{stem}-{index}{suffix}"
            index += 1
        return candidate

    async def _path_exists(self, session: AsyncSession, *, space_id: int, path: str) -> bool:
        return (
            await session.execute(
                select(WikiNode.id).where(
                    WikiNode.space_id == space_id,
                    WikiNode.path == path,
                    WikiNode.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none() is not None

    def _require_write(self, actor: WikiActor, feature: Feature) -> None:
        if not can_write_feature(actor, feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="write access denied for this wiki feature",
            )
