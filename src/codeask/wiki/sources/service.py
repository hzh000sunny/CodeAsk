"""Service layer for the minimal wiki source registry."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import Feature, WikiSource, WikiSpace
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
        return (
            await session.execute(
                select(WikiSource)
                .where(WikiSource.space_id == space_id)
                .order_by(WikiSource.id.asc())
            )
        ).scalars().all()

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
