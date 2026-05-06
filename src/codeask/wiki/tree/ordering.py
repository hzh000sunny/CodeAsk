"""Ordering and move operations for native wiki tree nodes."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import Feature, WikiNode, WikiSpace
from codeask.wiki.actor import WikiActor
from codeask.wiki.paths import is_descendant_path, join_node_path
from codeask.wiki.permissions import can_write_feature


class WikiTreeOrderingService:
    async def move_node(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        node: WikiNode,
        target_parent: WikiNode | None,
        target_index: int,
    ) -> WikiNode:
        self._require_active_node(node)
        self._require_movable_node(node)
        feature = await self._load_feature_for_space(session, space_id=node.space_id)
        self._require_write(actor, feature)

        current_parent_id = node.parent_id
        old_siblings = await self._list_active_children(
            session,
            space_id=node.space_id,
            parent_id=current_parent_id,
        )

        target_parent_id, target_parent_path = await self._validate_target_parent(
            session,
            node=node,
            target_parent=target_parent,
        )
        target_siblings = (
            old_siblings
            if target_parent_id == current_parent_id
            else await self._list_active_children(
                session,
                space_id=node.space_id,
                parent_id=target_parent_id,
            )
        )

        if target_parent_id != current_parent_id:
            await self._move_subtree(
                session,
                node=node,
                target_parent_id=target_parent_id,
                target_parent_path=target_parent_path,
            )

        if target_parent_id == current_parent_id:
            reordered = [sibling for sibling in old_siblings if sibling.id != node.id]
            reordered.insert(self._clamp_index(target_index, len(reordered)), node)
            self._resequence(reordered)
            return node

        old_remaining = [sibling for sibling in old_siblings if sibling.id != node.id]
        target_reordered = [sibling for sibling in target_siblings if sibling.id != node.id]
        target_reordered.insert(
            self._clamp_index(target_index, len(target_reordered)),
            node,
        )
        self._resequence(old_remaining)
        self._resequence(target_reordered)
        return node

    async def _validate_target_parent(
        self,
        session: AsyncSession,
        *,
        node: WikiNode,
        target_parent: WikiNode | None,
    ) -> tuple[int | None, str | None]:
        if target_parent is None:
            return None, None

        self._require_active_node(target_parent)
        if target_parent.space_id != node.space_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="target parent belongs to a different wiki space",
            )
        if target_parent.type != "folder":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="target parent must be a folder",
            )
        if target_parent.system_role == "reports":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="cannot move nodes under reports root",
            )
        if target_parent.id == node.id or is_descendant_path(target_parent.path, node.path):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="cannot move a node into itself or its descendants",
            )
        return target_parent.id, target_parent.path

    async def _move_subtree(
        self,
        session: AsyncSession,
        *,
        node: WikiNode,
        target_parent_id: int | None,
        target_parent_path: str | None,
    ) -> None:
        old_path = node.path
        new_path = join_node_path(target_parent_path, node.name)
        descendants = (
            await session.execute(
                select(WikiNode)
                .where(
                    WikiNode.space_id == node.space_id,
                    WikiNode.deleted_at.is_(None),
                )
                .order_by(WikiNode.path.asc(), WikiNode.id.asc())
            )
        ).scalars().all()
        subtree = [
            row
            for row in descendants
            if row.id == node.id or is_descendant_path(row.path, old_path)
        ]
        subtree_ids = {row.id for row in subtree}
        for row in subtree:
            candidate_path = (
                new_path if row.id == node.id else f"{new_path}/{row.path[len(old_path) + 1 :]}"
            )
            await self._assert_path_available(
                session,
                space_id=node.space_id,
                path=candidate_path,
                exclude_ids=subtree_ids,
            )

        node.parent_id = target_parent_id
        node.path = new_path
        for row in subtree:
            if row.id == node.id:
                continue
            suffix = row.path[len(old_path) + 1 :]
            row.path = f"{new_path}/{suffix}"

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

    async def _list_active_children(
        self,
        session: AsyncSession,
        *,
        space_id: int,
        parent_id: int | None,
    ) -> list[WikiNode]:
        return (
            await session.execute(
                select(WikiNode)
                .where(
                    WikiNode.space_id == space_id,
                    WikiNode.parent_id.is_(parent_id),
                    WikiNode.deleted_at.is_(None),
                )
                .order_by(WikiNode.sort_order.asc(), WikiNode.name.asc(), WikiNode.id.asc())
            )
        ).scalars().all()

    async def _assert_path_available(
        self,
        session: AsyncSession,
        *,
        space_id: int,
        path: str,
        exclude_ids: set[int] | None = None,
    ) -> None:
        rows = (
            await session.execute(
                select(WikiNode.id).where(
                    WikiNode.space_id == space_id,
                    WikiNode.path == path,
                    WikiNode.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        excluded = exclude_ids or set()
        if any(row_id not in excluded for row_id in rows):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"wiki node path conflict: {path}",
            )

    def _resequence(self, nodes: list[WikiNode]) -> None:
        for index, sibling in enumerate(nodes):
            sibling.sort_order = index

    def _clamp_index(self, index: int, size: int) -> int:
        if index < 0:
            return 0
        if index > size:
            return size
        return index

    def _require_write(self, actor: WikiActor, feature: Feature) -> None:
        if not can_write_feature(actor, feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="write access denied for this wiki feature",
            )

    def _require_active_node(self, node: WikiNode) -> None:
        if node.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="wiki node not found")

    def _require_movable_node(self, node: WikiNode) -> None:
        if node.system_role is not None or node.type not in {"folder", "document"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="wiki node cannot be moved",
            )
