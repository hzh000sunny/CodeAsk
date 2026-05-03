"""Bootstrap services for native wiki spaces."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import WikiNode, WikiSpace


class WikiSpaceBootstrapService:
    """Create the minimal system space and folders for a feature."""

    async def ensure_feature_space(
        self,
        session: AsyncSession,
        *,
        feature_id: int,
        feature_slug: str,
    ) -> WikiSpace:
        existing = (
            await session.execute(
                select(WikiSpace).where(
                    WikiSpace.feature_id == feature_id,
                    WikiSpace.scope == "current",
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        space = WikiSpace(
            feature_id=feature_id,
            scope="current",
            display_name=feature_slug,
            slug=feature_slug,
            status="active",
        )
        session.add(space)
        await session.flush()

        session.add_all(
            [
                WikiNode(
                    space_id=space.id,
                    parent_id=None,
                    type="folder",
                    name="知识库",
                    path="knowledge-base",
                    system_role="knowledge_base",
                    sort_order=100,
                ),
                WikiNode(
                    space_id=space.id,
                    parent_id=None,
                    type="folder",
                    name="问题定位报告",
                    path="reports",
                    system_role="reports",
                    sort_order=200,
                ),
            ]
        )
        await session.flush()
        return space
