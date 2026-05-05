"""Permission-aware maintenance operations for native wiki."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import Feature, WikiNode, WikiSpace
from codeask.wiki.actor import WikiActor
from codeask.wiki.index import WikiIndexService
from codeask.wiki.permissions import can_maintain_feature


class WikiMaintenanceService:
    def __init__(self, index_service: WikiIndexService | None = None) -> None:
        self._index = index_service or WikiIndexService()

    async def reindex_subtree(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        root_node_id: int,
    ) -> dict[str, int]:
        root_node = (
            await session.execute(
                select(WikiNode).where(
                    WikiNode.id == root_node_id,
                    WikiNode.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if root_node is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="wiki node not found")

        feature = await self._load_feature_for_space(session, space_id=root_node.space_id)
        self._require_maintain(actor, feature)
        count = await self._index.reindex_subtree(
            session,
            root_node=root_node,
        )
        await session.flush()
        return {
            "root_node_id": int(root_node.id),
            "reindexed_documents": count,
        }

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

    def _require_maintain(self, actor: WikiActor, feature: Feature) -> None:
        if not can_maintain_feature(actor, feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="maintenance access denied for this wiki feature",
            )
