"""Bridge legacy document/report APIs into native wiki structures."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import (
    Document,
    Report,
    WikiDocument,
    WikiDocumentVersion,
    WikiNode,
    WikiReportRef,
    WikiSpace,
)
from codeask.wiki.paths import normalize_node_name


def _slugify_node_name(value: str) -> str:
    return normalize_node_name(value)


class LegacyWikiSyncService:
    async def backfill_feature_content(self, session: AsyncSession, *, feature_id: int) -> None:
        documents = (
            await session.execute(
                select(Document).where(
                    Document.feature_id == feature_id,
                    Document.kind == "markdown",
                    Document.is_deleted.is_(False),
                )
            )
        ).scalars().all()
        for document in documents:
            raw_text = Path(document.raw_file_path).read_text(encoding="utf-8")
            await self.sync_legacy_markdown_document(
                session,
                feature_id=feature_id,
                legacy_document_id=int(document.id),
                safe_name=document.path,
                title=document.title,
                body_markdown=raw_text,
                subject_id=document.uploaded_by_subject_id,
            )

        reports = (
            await session.execute(select(Report).where(Report.feature_id == feature_id))
        ).scalars().all()
        for report in reports:
            await self.sync_report_ref(
                session,
                report_id=int(report.id),
                feature_id=report.feature_id,
                title=report.title,
            )

    async def sync_legacy_markdown_document(
        self,
        session: AsyncSession,
        *,
        feature_id: int,
        legacy_document_id: int,
        safe_name: str,
        title: str,
        body_markdown: str,
        subject_id: str,
    ) -> None:
        existing = (
            await session.execute(
                select(WikiDocument).where(WikiDocument.legacy_document_id == legacy_document_id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return

        space = await self._require_current_space(session, feature_id=feature_id)
        root = await self._require_system_root(session, space_id=space.id, role="knowledge_base")
        leaf = await self._unique_child_leaf(
            session,
            space_id=space.id,
            parent_path=root.path,
            preferred_leaf=_slugify_node_name(Path(safe_name).stem),
        )
        node = WikiNode(
            space_id=space.id,
            parent_id=root.id,
            type="document",
            name=Path(safe_name).stem or title,
            path=f"{root.path}/{leaf}",
            system_role=None,
            sort_order=0,
        )
        session.add(node)
        await session.flush()

        document = WikiDocument(
            node_id=node.id,
            legacy_document_id=legacy_document_id,
            title=title,
            current_version_id=None,
            summary=None,
            index_status="ready",
            broken_refs_json={"links": []},
            provenance_json={
                "source": "manual_upload",
                "legacy_document_id": legacy_document_id,
            },
        )
        session.add(document)
        await session.flush()

        version = WikiDocumentVersion(
            document_id=document.id,
            version_no=1,
            body_markdown=body_markdown,
            created_by_subject_id=subject_id,
        )
        session.add(version)
        await session.flush()
        document.current_version_id = version.id

    async def soft_delete_legacy_document(
        self,
        session: AsyncSession,
        *,
        legacy_document_id: int,
        subject_id: str,
    ) -> None:
        document = (
            await session.execute(
                select(WikiDocument).where(WikiDocument.legacy_document_id == legacy_document_id)
            )
        ).scalar_one_or_none()
        if document is None:
            return
        node = await session.get(WikiNode, document.node_id)
        if node is None or node.deleted_at is not None:
            return
        node.deleted_at = datetime.now(UTC)
        node.deleted_by_subject_id = subject_id

    async def sync_report_ref(
        self,
        session: AsyncSession,
        *,
        report_id: int,
        feature_id: int | None,
        title: str,
    ) -> None:
        if feature_id is None:
            return

        existing = (
            await session.execute(select(WikiReportRef).where(WikiReportRef.report_id == report_id))
        ).scalar_one_or_none()
        space = await self._require_current_space(session, feature_id=feature_id)
        root = await self._require_system_root(session, space_id=space.id, role="reports")
        if existing is not None:
            node = await session.get(WikiNode, existing.node_id)
            if node is not None:
                next_path = await self._unique_report_ref_path(
                    session,
                    space_id=space.id,
                    root_path=root.path,
                    title=title,
                    current_node_id=int(node.id),
                )
                node.name = title
                node.path = next_path
                return

        leaf = await self._unique_child_leaf(
            session,
            space_id=space.id,
            parent_path=root.path,
            preferred_leaf=_slugify_node_name(title),
        )
        node = WikiNode(
            space_id=space.id,
            parent_id=root.id,
            type="report_ref",
            name=title,
            path=f"{root.path}/{leaf}",
            system_role=None,
            sort_order=0,
        )
        session.add(node)
        await session.flush()

        session.add(WikiReportRef(node_id=node.id, report_id=report_id))
        await session.flush()

    async def delete_report_ref(self, session: AsyncSession, *, report_id: int) -> None:
        report_ref = (
            await session.execute(select(WikiReportRef).where(WikiReportRef.report_id == report_id))
        ).scalar_one_or_none()
        if report_ref is None:
            return
        node = await session.get(WikiNode, report_ref.node_id)
        await session.delete(report_ref)
        if node is not None:
            await session.delete(node)

    async def _unique_report_ref_path(
        self,
        session: AsyncSession,
        *,
        space_id: int,
        root_path: str,
        title: str,
        current_node_id: int,
    ) -> str:
        leaf = _slugify_node_name(title)
        candidate = leaf or "item"
        suffix = 2
        while True:
            path = f"{root_path}/{candidate}"
            owner_id = (
                await session.execute(
                    select(WikiNode.id).where(
                        WikiNode.space_id == space_id,
                        WikiNode.path == path,
                    )
                )
            ).scalar_one_or_none()
            if owner_id is None or int(owner_id) == current_node_id:
                return path
            candidate = f"{leaf or 'item'}-{suffix}"
            suffix += 1

    async def _require_current_space(self, session: AsyncSession, *, feature_id: int) -> WikiSpace:
        return (
            await session.execute(
                select(WikiSpace).where(
                    WikiSpace.feature_id == feature_id,
                    WikiSpace.scope == "current",
                )
            )
        ).scalar_one()

    async def _require_system_root(
        self,
        session: AsyncSession,
        *,
        space_id: int,
        role: str,
    ) -> WikiNode:
        return (
            await session.execute(
                select(WikiNode).where(
                    WikiNode.space_id == space_id,
                    WikiNode.system_role == role,
                    WikiNode.parent_id.is_(None),
                )
            )
        ).scalar_one()

    async def _unique_child_leaf(
        self,
        session: AsyncSession,
        *,
        space_id: int,
        parent_path: str,
        preferred_leaf: str,
    ) -> str:
        leaf = preferred_leaf or "item"
        candidate = leaf
        suffix = 2
        while await self._path_exists(session, space_id=space_id, path=f"{parent_path}/{candidate}"):
            candidate = f"{leaf}-{suffix}"
            suffix += 1
        return candidate

    async def _path_exists(self, session: AsyncSession, *, space_id: int, path: str) -> bool:
        return (
            await session.execute(
                select(WikiNode.id).where(
                    WikiNode.space_id == space_id,
                    WikiNode.path == path,
                )
            )
        ).scalar_one_or_none() is not None
