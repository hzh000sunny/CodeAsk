"""Refresh derived state for native wiki documents."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import WikiDocument, WikiDocumentVersion, WikiNode
from codeask.wiki.documents.markdown_refs import parse_markdown_references, resolve_markdown_references
from codeask.wiki.paths import is_descendant_path


class WikiIndexService:
    async def refresh_document_by_node_id(
        self,
        session: AsyncSession,
        *,
        node_id: int,
    ) -> WikiDocument:
        row = (
            await session.execute(
                select(WikiNode, WikiDocument)
                .join(WikiDocument, WikiDocument.node_id == WikiNode.id)
                .where(
                    WikiNode.id == node_id,
                    WikiNode.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="wiki document not found")
        node, document = row
        return await self.refresh_document(
            session,
            node=node,
            document=document,
        )

    async def refresh_document(
        self,
        session: AsyncSession,
        *,
        node: WikiNode,
        document: WikiDocument,
    ) -> WikiDocument:
        if document.current_version_id is None:
            document.index_status = "pending"
            document.broken_refs_json = {"links": [], "assets": []}
            await session.flush()
            return document

        version = (
            await session.execute(
                select(WikiDocumentVersion).where(WikiDocumentVersion.id == document.current_version_id)
            )
        ).scalar_one_or_none()
        if version is None:
            document.index_status = "failed"
            document.broken_refs_json = {"links": [], "assets": []}
            await session.flush()
            return document

        refs = await self._reference_state(
            session,
            space_id=node.space_id,
            source_node_path=node.path,
            body_markdown=version.body_markdown,
        )
        document.index_status = "ready"
        document.broken_refs_json = refs["broken_refs"]
        await session.flush()
        return document

    async def reindex_subtree(
        self,
        session: AsyncSession,
        *,
        root_node: WikiNode,
    ) -> int:
        rows = (
            await session.execute(
                select(WikiNode, WikiDocument)
                .join(WikiDocument, WikiDocument.node_id == WikiNode.id)
                .where(
                    WikiNode.space_id == root_node.space_id,
                    WikiNode.deleted_at.is_(None),
                )
                .order_by(WikiNode.path.asc(), WikiNode.id.asc())
            )
        ).all()
        count = 0
        for node, document in rows:
            if node.path == root_node.path or is_descendant_path(node.path, root_node.path):
                await self.refresh_document(
                    session,
                    node=node,
                    document=document,
                )
                count += 1
        return count

    async def _reference_state(
        self,
        session: AsyncSession,
        *,
        space_id: int,
        source_node_path: str,
        body_markdown: str,
    ) -> dict[str, object]:
        refs = parse_markdown_references(body_markdown)
        return await resolve_markdown_references(
            session,
            space_id=space_id,
            source_node_path=source_node_path,
            references=refs,
        )
