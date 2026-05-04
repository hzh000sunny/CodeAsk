"""Read services for native wiki spaces and tree nodes."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import Feature, WikiDocument, WikiNode, WikiSpace
from codeask.wiki.actor import WikiActor
from codeask.wiki.paths import is_descendant_path, join_node_path
from codeask.wiki.permissions import can_admin_feature, can_write_feature
from codeask.wiki.spaces import WikiSpaceBootstrapService
from codeask.wiki.sync import LegacyWikiSyncService


class WikiTreeService:
    async def ensure_current_space_for_feature(
        self,
        session: AsyncSession,
        *,
        feature: Feature,
    ) -> WikiSpace:
        space = (
            await session.execute(
                select(WikiSpace).where(
                    WikiSpace.feature_id == feature.id,
                    WikiSpace.scope == "current",
                )
            )
        ).scalar_one_or_none()
        if space is None:
            space = await WikiSpaceBootstrapService().ensure_feature_space(
                session,
                feature_id=feature.id,
                feature_slug=feature.slug,
            )
        await LegacyWikiSyncService().backfill_feature_content(session, feature_id=feature.id)
        await session.flush()
        return space

    async def get_current_space_for_feature(
        self,
        session: AsyncSession,
        *,
        feature_id: int,
    ) -> WikiSpace:
        space = (
            await session.execute(
                select(WikiSpace).where(
                    WikiSpace.feature_id == feature_id,
                    WikiSpace.scope == "current",
                )
            )
        ).scalar_one_or_none()
        if space is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="wiki space not found",
            )
        return space

    async def list_root_nodes(
        self,
        session: AsyncSession,
        *,
        space_id: int,
    ) -> list[WikiNode]:
        return (
            await session.execute(
                select(WikiNode)
                .where(
                    WikiNode.space_id == space_id,
                    WikiNode.parent_id.is_(None),
                    WikiNode.deleted_at.is_(None),
                )
                .order_by(WikiNode.sort_order.asc(), WikiNode.name.asc(), WikiNode.id.asc())
            )
        ).scalars().all()

    async def list_active_nodes(
        self,
        session: AsyncSession,
        *,
        space_id: int,
    ) -> list[WikiNode]:
        return (
            await session.execute(
                select(WikiNode)
                .where(
                    WikiNode.space_id == space_id,
                    WikiNode.deleted_at.is_(None),
                )
                .order_by(
                    WikiNode.path.asc(),
                    WikiNode.sort_order.asc(),
                    WikiNode.name.asc(),
                    WikiNode.id.asc(),
                )
            )
        ).scalars().all()

    async def get_node_detail(
        self,
        session: AsyncSession,
        *,
        node: WikiNode,
        actor: WikiActor,
    ) -> tuple[Feature, dict[str, bool]]:
        if node.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="wiki node not found")
        feature = await self._load_feature_for_space(session, space_id=node.space_id)
        return feature, {
            "read": True,
            "write": can_write_feature(actor, feature),
            "admin": can_admin_feature(actor, feature),
        }

    async def create_node(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        space: WikiSpace,
        parent: WikiNode | None,
        node_type: str,
        name: str,
    ) -> WikiNode:
        feature = await self._load_feature_for_space(session, space_id=space.id)
        self._require_write(actor, feature)
        if node_type not in {"folder", "document"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="node type must be folder or document",
            )
        if parent is not None:
            self._require_active_node(parent)
            if parent.space_id != space.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="parent node belongs to a different wiki space",
                )
        path = join_node_path(parent.path if parent is not None else None, name)
        await self._assert_path_available(session, space_id=space.id, path=path)
        node = WikiNode(
            space_id=space.id,
            parent_id=parent.id if parent is not None else None,
            type=node_type,
            name=name,
            path=path,
            system_role=None,
            sort_order=0,
        )
        session.add(node)
        await session.flush()
        if node_type == "document":
            session.add(
                WikiDocument(
                    node_id=node.id,
                    legacy_document_id=None,
                    title=name,
                    current_version_id=None,
                    summary=None,
                    index_status="pending",
                    broken_refs_json={"links": []},
                    provenance_json={"source": "manual_create"},
                )
            )
            await session.flush()
        return node

    async def update_node(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        node: WikiNode,
        parent_provided: bool,
        parent: WikiNode | None,
        name: str | None,
        sort_order: int | None,
    ) -> WikiNode:
        self._require_active_node(node)
        self._require_mutable_node(node)
        feature = await self._load_feature_for_space(session, space_id=node.space_id)
        self._require_write(actor, feature)

        current_name = node.name
        current_parent_id = node.parent_id
        next_name = name if name is not None else current_name
        if parent_provided:
            next_parent_id = parent.id if parent is not None else None
            next_parent_path = parent.path if parent is not None else None
        else:
            next_parent_id = current_parent_id
            next_parent_path = await self._parent_path(session, node)

        if parent is not None:
            self._require_active_node(parent)
            if parent.space_id != node.space_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="target parent belongs to a different wiki space",
                )
            if parent.id == node.id or is_descendant_path(parent.path, node.path):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="cannot move a node into itself or its descendants",
                )

        if sort_order is not None:
            node.sort_order = sort_order

        if next_name == current_name and next_parent_id == current_parent_id:
            return node

        old_path = node.path
        new_path = join_node_path(next_parent_path, next_name)
        descendants = (
            await session.execute(
                select(WikiNode)
                .where(
                    WikiNode.space_id == node.space_id,
                    WikiNode.deleted_at.is_(None),
                )
                .order_by(WikiNode.path.asc())
            )
        ).scalars().all()
        subtree = [row for row in descendants if row.id == node.id or is_descendant_path(row.path, old_path)]
        subtree_ids = {row.id for row in subtree}

        for row in subtree:
            candidate_path = new_path if row.id == node.id else f"{new_path}/{row.path[len(old_path) + 1:]}"
            await self._assert_path_available(
                session,
                space_id=node.space_id,
                path=candidate_path,
                exclude_ids=subtree_ids,
            )

        node.name = next_name
        node.parent_id = next_parent_id
        node.path = new_path
        for row in subtree:
            if row.id == node.id:
                continue
            suffix = row.path[len(old_path) + 1 :]
            row.path = f"{new_path}/{suffix}"
        return node

    async def delete_node(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        node: WikiNode,
    ) -> None:
        self._require_active_node(node)
        self._require_mutable_node(node)
        feature = await self._load_feature_for_space(session, space_id=node.space_id)
        self._require_write(actor, feature)
        now = datetime.now(UTC)
        descendants = (
            await session.execute(
                select(WikiNode).where(
                    WikiNode.space_id == node.space_id,
                    WikiNode.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        for row in descendants:
            if row.id == node.id or is_descendant_path(row.path, node.path):
                row.deleted_at = now
                row.deleted_by_subject_id = actor.subject_id

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
        exclude_ids = exclude_ids or set()
        if any(row_id not in exclude_ids for row_id in rows):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"wiki node path conflict: {path}",
            )

    def _require_write(self, actor: WikiActor, feature: Feature) -> None:
        if not can_write_feature(actor, feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="write access denied for this wiki feature",
            )

    def _require_active_node(self, node: WikiNode) -> None:
        if node.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="wiki node not found")

    def _require_mutable_node(self, node: WikiNode) -> None:
        if node.system_role is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="system wiki nodes cannot be modified",
            )

    async def _parent_path(self, session: AsyncSession, node: WikiNode) -> str | None:
        if node.parent_id is None:
            return None
        parent = await session.get(WikiNode, node.parent_id)
        return parent.path if parent is not None else None
