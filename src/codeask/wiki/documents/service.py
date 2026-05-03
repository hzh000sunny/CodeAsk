"""Services for native wiki document reads, drafts, publish, and versions."""

from __future__ import annotations

from difflib import unified_diff

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import Feature, WikiDocument, WikiDocumentDraft, WikiDocumentVersion, WikiNode, WikiSpace
from codeask.wiki.actor import WikiActor
from codeask.wiki.permissions import can_admin_feature, can_write_feature


class WikiDocumentService:
    async def load_document_by_node(
        self,
        session: AsyncSession,
        *,
        node_id: int,
    ) -> tuple[WikiNode, WikiDocument]:
        node = (await session.execute(select(WikiNode).where(WikiNode.id == node_id))).scalar_one_or_none()
        if node is None or node.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="wiki document not found")
        document = (
            await session.execute(select(WikiDocument).where(WikiDocument.node_id == node_id))
        ).scalar_one_or_none()
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="wiki document not found")
        return node, document

    async def get_document_detail(
        self,
        session: AsyncSession,
        *,
        node_id: int,
        actor: WikiActor,
    ) -> dict[str, object]:
        node, document = await self.load_document_by_node(session, node_id=node_id)
        feature = await self._load_feature_for_space(session, space_id=node.space_id)
        current_version = await self._current_version(session, document=document)
        draft = await self._draft_for_subject(session, document_id=document.id, subject_id=actor.subject_id)
        return {
            "document_id": document.id,
            "node_id": node.id,
            "title": document.title,
            "current_version_id": document.current_version_id,
            "current_body_markdown": current_version.body_markdown if current_version is not None else None,
            "draft_body_markdown": draft.body_markdown if draft is not None else None,
            "index_status": document.index_status,
            "broken_refs_json": document.broken_refs_json,
            "provenance_json": document.provenance_json,
            "permissions": {
                "read": True,
                "write": can_write_feature(actor, feature),
                "admin": can_admin_feature(actor, feature),
            },
        }

    async def save_draft(
        self,
        session: AsyncSession,
        *,
        node_id: int,
        actor: WikiActor,
        body_markdown: str,
    ) -> dict[str, object]:
        _node, document = await self.load_document_by_node(session, node_id=node_id)
        feature = await self._load_feature_for_document(session, document=document)
        self._require_write(actor, feature)
        draft = await self._draft_for_subject(session, document_id=document.id, subject_id=actor.subject_id)
        if draft is None:
            draft = WikiDocumentDraft(
                document_id=document.id,
                subject_id=actor.subject_id,
                body_markdown=body_markdown,
            )
            session.add(draft)
        else:
            draft.body_markdown = body_markdown
        await session.flush()
        return await self.get_document_detail(session, node_id=node_id, actor=actor)

    async def delete_draft(
        self,
        session: AsyncSession,
        *,
        node_id: int,
        actor: WikiActor,
    ) -> None:
        _node, document = await self.load_document_by_node(session, node_id=node_id)
        feature = await self._load_feature_for_document(session, document=document)
        self._require_write(actor, feature)
        draft = await self._draft_for_subject(session, document_id=document.id, subject_id=actor.subject_id)
        if draft is not None:
            await session.delete(draft)

    async def publish_document(
        self,
        session: AsyncSession,
        *,
        node_id: int,
        actor: WikiActor,
        body_markdown: str | None,
    ) -> dict[str, object]:
        _node, document = await self.load_document_by_node(session, node_id=node_id)
        feature = await self._load_feature_for_document(session, document=document)
        self._require_write(actor, feature)

        draft = await self._draft_for_subject(session, document_id=document.id, subject_id=actor.subject_id)
        final_body = body_markdown if body_markdown is not None else draft.body_markdown if draft is not None else None
        if final_body is None or not final_body.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="publish requires body_markdown or an existing draft",
            )

        next_version_no = await self._next_version_no(session, document_id=document.id)
        version = WikiDocumentVersion(
            document_id=document.id,
            version_no=next_version_no,
            body_markdown=final_body,
            created_by_subject_id=actor.subject_id,
        )
        session.add(version)
        await session.flush()
        document.current_version_id = version.id
        document.index_status = "ready"
        if draft is not None:
            await session.delete(draft)
        await session.flush()
        return await self.get_document_detail(session, node_id=node_id, actor=actor)

    async def list_versions(
        self,
        session: AsyncSession,
        *,
        node_id: int,
        actor: WikiActor,
    ) -> list[WikiDocumentVersion]:
        _node, document = await self.load_document_by_node(session, node_id=node_id)
        await self._load_feature_for_document(session, document=document)
        return (
            await session.execute(
                select(WikiDocumentVersion)
                .where(WikiDocumentVersion.document_id == document.id)
                .order_by(WikiDocumentVersion.version_no.desc(), WikiDocumentVersion.id.desc())
            )
        ).scalars().all()

    async def get_version(
        self,
        session: AsyncSession,
        *,
        node_id: int,
        version_id: int,
        actor: WikiActor,
    ) -> WikiDocumentVersion:
        _node, document = await self.load_document_by_node(session, node_id=node_id)
        await self._load_feature_for_document(session, document=document)
        return await self._load_version(session, document_id=document.id, version_id=version_id)

    async def diff_versions(
        self,
        session: AsyncSession,
        *,
        node_id: int,
        from_version_id: int,
        to_version_id: int,
        actor: WikiActor,
    ) -> dict[str, object]:
        _node, document = await self.load_document_by_node(session, node_id=node_id)
        await self._load_feature_for_document(session, document=document)
        from_version = await self._load_version(
            session,
            document_id=document.id,
            version_id=from_version_id,
        )
        to_version = await self._load_version(
            session,
            document_id=document.id,
            version_id=to_version_id,
        )
        patch = "\n".join(
            unified_diff(
                from_version.body_markdown.splitlines(),
                to_version.body_markdown.splitlines(),
                fromfile=f"v{from_version.version_no}",
                tofile=f"v{to_version.version_no}",
                lineterm="",
            )
        )
        return {
            "from_version_id": from_version.id,
            "from_version_no": from_version.version_no,
            "to_version_id": to_version.id,
            "to_version_no": to_version.version_no,
            "patch": patch,
        }

    async def rollback_to_version(
        self,
        session: AsyncSession,
        *,
        node_id: int,
        version_id: int,
        actor: WikiActor,
    ) -> dict[str, object]:
        _node, document = await self.load_document_by_node(session, node_id=node_id)
        feature = await self._load_feature_for_document(session, document=document)
        self._require_write(actor, feature)
        version = await self._load_version(session, document_id=document.id, version_id=version_id)
        next_version_no = await self._next_version_no(session, document_id=document.id)
        new_version = WikiDocumentVersion(
            document_id=document.id,
            version_no=next_version_no,
            body_markdown=version.body_markdown,
            created_by_subject_id=actor.subject_id,
        )
        session.add(new_version)
        await session.flush()
        document.current_version_id = new_version.id
        document.index_status = "ready"
        await session.flush()
        return await self.get_document_detail(session, node_id=node_id, actor=actor)

    async def _current_version(
        self,
        session: AsyncSession,
        *,
        document: WikiDocument,
    ) -> WikiDocumentVersion | None:
        if document.current_version_id is None:
            return None
        return (
            await session.execute(
                select(WikiDocumentVersion).where(WikiDocumentVersion.id == document.current_version_id)
            )
        ).scalar_one_or_none()

    async def _draft_for_subject(
        self,
        session: AsyncSession,
        *,
        document_id: int,
        subject_id: str,
    ) -> WikiDocumentDraft | None:
        return (
            await session.execute(
                select(WikiDocumentDraft).where(
                    WikiDocumentDraft.document_id == document_id,
                    WikiDocumentDraft.subject_id == subject_id,
                )
            )
        ).scalar_one_or_none()

    async def _next_version_no(self, session: AsyncSession, *, document_id: int) -> int:
        current = (
            await session.execute(
                select(func.max(WikiDocumentVersion.version_no)).where(
                    WikiDocumentVersion.document_id == document_id
                )
            )
        ).scalar_one()
        return int(current or 0) + 1

    async def _load_version(
        self,
        session: AsyncSession,
        *,
        document_id: int,
        version_id: int,
    ) -> WikiDocumentVersion:
        version = (
            await session.execute(
                select(WikiDocumentVersion).where(
                    WikiDocumentVersion.id == version_id,
                    WikiDocumentVersion.document_id == document_id,
                )
            )
        ).scalar_one_or_none()
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="wiki document version not found",
            )
        return version

    async def _load_feature_for_document(
        self,
        session: AsyncSession,
        *,
        document: WikiDocument,
    ) -> Feature:
        node = await session.get(WikiNode, document.node_id)
        if node is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="wiki document not found")
        return await self._load_feature_for_space(session, space_id=node.space_id)

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
