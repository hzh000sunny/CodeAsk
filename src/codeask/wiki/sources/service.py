"""Service layer for the minimal wiki source registry."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import Feature, WikiAsset, WikiDocument, WikiImportSession, WikiNode, WikiSource, WikiSpace
from codeask.metrics.audit import record_audit_log
from codeask.wiki.audit import AuditWriter
from codeask.wiki.actor import WikiActor
from codeask.wiki.permissions import can_write_feature


class WikiSourceService:
    def __init__(self, audit: AuditWriter | None = None) -> None:
        self._audit = audit or AuditWriter()

    async def list_sources(
        self,
        session: AsyncSession,
        *,
        space_id: int,
    ) -> list[WikiSource]:
        await self._load_feature_for_space(session, space_id=space_id)
        rows = (
            await session.execute(
                select(WikiSource)
                .where(WikiSource.space_id == space_id)
                .order_by(WikiSource.id.asc())
            )
        ).scalars().all()
        visible: list[WikiSource] = []
        for source in rows:
            if await self._should_hide_legacy_placeholder(session, source):
                continue
            override_name = await self._legacy_display_name_override(session, source)
            if override_name:
                source.display_name = override_name
            visible.append(source)
        return visible

    async def create_source(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        space_id: int,
        kind: str,
        display_name: str,
        uri: str | None,
        metadata_json: object | None,
    ) -> WikiSource:
        feature = await self._load_feature_for_space(session, space_id=space_id)
        self._require_write(actor, feature)
        source = WikiSource(
            space_id=space_id,
            kind=kind,
            display_name=display_name.strip(),
            uri=uri.strip() if isinstance(uri, str) and uri.strip() else None,
            metadata_json=metadata_json,
            status="active",
        )
        session.add(source)
        await session.flush()
        return source

    async def update_source(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        source: WikiSource,
        display_name: str | None,
        uri: str | None,
        metadata_json: object | None,
        status_value: str | None,
    ) -> WikiSource:
        feature = await self._load_feature_for_space(session, space_id=source.space_id)
        self._require_write(actor, feature)
        if display_name is not None:
            source.display_name = display_name.strip()
        if uri is not None:
            source.uri = uri.strip() or None
        if metadata_json is not None:
            source.metadata_json = metadata_json
        if status_value is not None:
            source.status = status_value
        await session.flush()
        return source

    async def sync_source(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        source: WikiSource,
    ) -> WikiSource:
        feature = await self._load_feature_for_space(session, space_id=source.space_id)
        self._require_write(actor, feature)
        if source.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="archived wiki source cannot be synced",
            )
        previous_status = source.status
        source.status = "active"
        source.last_synced_at = datetime.now(UTC)
        await session.flush()
        await record_audit_log(
            session,
            entity_type="wiki_source",
            entity_id=str(source.id),
            action="sync",
            subject_id=actor.subject_id,
            from_status=previous_status,
            to_status=source.status,
        )
        self._audit.write(
            "wiki_source.synced",
            {"source_id": int(source.id), "space_id": int(source.space_id)},
            subject_id=actor.subject_id,
        )
        return source

    async def load_source(
        self,
        session: AsyncSession,
        *,
        source_id: int,
    ) -> WikiSource:
        source = (
            await session.execute(select(WikiSource).where(WikiSource.id == source_id))
        ).scalar_one_or_none()
        if source is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="wiki source not found")
        return source

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

    def _require_write(self, actor: WikiActor, feature: Feature) -> None:
        if not can_write_feature(actor, feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="write access denied for this wiki feature",
            )

    async def _should_hide_legacy_placeholder(
        self,
        session: AsyncSession,
        source: WikiSource,
    ) -> bool:
        if source.kind != "directory_import":
            return False
        if source.uri is not None or source.last_synced_at is not None:
            return False
        if not source.display_name.startswith("导入会话 "):
            return False
        metadata = source.metadata_json if isinstance(source.metadata_json, dict) else {}
        import_session_id = metadata.get("import_session_id")
        if not isinstance(import_session_id, int):
            return False
        import_session = await session.get(WikiImportSession, import_session_id)
        if import_session is None:
            return True
        if import_session.status != "completed":
            return True
        return not await self._has_active_references(session, source_id=int(source.id))

    async def _has_active_references(
        self,
        session: AsyncSession,
        source_id: int,
    ) -> bool:
        return bool(await self._active_reference_paths(session, source_id=source_id))

    async def _legacy_display_name_override(
        self,
        session: AsyncSession,
        source: WikiSource,
    ) -> str | None:
        if source.kind != "directory_import":
            return None
        if not source.display_name.startswith("导入会话 "):
            return None
        metadata = source.metadata_json if isinstance(source.metadata_json, dict) else {}
        root_label = metadata.get("root_label")
        if isinstance(root_label, str) and root_label.strip():
            return root_label.strip()
        paths = await self._active_reference_paths(session, source_id=int(source.id))
        return self._derive_display_name_from_paths(paths)

    async def _active_reference_paths(
        self,
        session: AsyncSession,
        *,
        source_id: int,
    ) -> list[str]:
        paths: list[str] = []
        document_rows = (
            await session.execute(
                select(WikiDocument.provenance_json, WikiNode.deleted_at)
                .join(WikiNode, WikiNode.id == WikiDocument.node_id)
            )
        ).all()
        for provenance_json, deleted_at in document_rows:
            if deleted_at is not None:
                continue
            if isinstance(provenance_json, dict) and provenance_json.get("source_id") == source_id:
                source_path = provenance_json.get("source_path")
                if isinstance(source_path, str) and source_path.strip():
                    paths.append(source_path.strip())

        asset_rows = (
            await session.execute(
                select(WikiAsset.provenance_json, WikiNode.deleted_at)
                .join(WikiNode, WikiNode.id == WikiAsset.node_id)
            )
        ).all()
        for provenance_json, deleted_at in asset_rows:
            if deleted_at is not None:
                continue
            if isinstance(provenance_json, dict) and provenance_json.get("source_id") == source_id:
                source_path = provenance_json.get("source_path")
                if isinstance(source_path, str) and source_path.strip():
                    paths.append(source_path.strip())
        return paths

    def _derive_display_name_from_paths(self, paths: list[str]) -> str | None:
        if not paths:
            return None
        first_segments = {path.split("/", 1)[0].strip() for path in paths if path.strip()}
        first_segments.discard("")
        if len(first_segments) == 1:
            return next(iter(first_segments))
        if len(paths) == 1:
            leaf = paths[0].rsplit("/", 1)[-1].strip()
            if "." in leaf:
                leaf = leaf.rsplit(".", 1)[0]
            return leaf or None
        return None
