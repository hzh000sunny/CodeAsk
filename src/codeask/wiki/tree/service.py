"""Read services for native wiki spaces and tree nodes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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
    async def list_global_tree_nodes(
        self,
        session: AsyncSession,
    ) -> list[dict[str, Any]]:
        features = (
            await session.execute(
                select(Feature).where(Feature.status == "active").order_by(Feature.id.asc())
            )
        ).scalars().all()
        now = datetime.now(UTC)
        nodes: list[dict[str, Any]] = [
            self._virtual_node(
                node_id=-1,
                space_id=0,
                feature_id=None,
                parent_id=None,
                name="当前特性",
                path="当前特性",
                system_role="feature_group_current",
                sort_order=0,
                created_at=now,
                updated_at=now,
            ),
            self._virtual_node(
                node_id=-2,
                space_id=0,
                feature_id=None,
                parent_id=None,
                name="历史特性",
                path="历史特性",
                system_role="feature_group_history",
                sort_order=1,
                created_at=now,
                updated_at=now,
            ),
        ]

        for index, feature in enumerate(features):
            space = await self.ensure_current_space_for_feature(session, feature=feature)
            feature_root_id = -100000 - feature.id
            nodes.append(
                self._virtual_node(
                    node_id=feature_root_id,
                    space_id=space.id,
                    feature_id=feature.id,
                    parent_id=-1,
                    name=feature.name,
                    path=f"当前特性/{feature.slug}",
                    system_role="feature_space_current",
                    sort_order=index,
                    created_at=space.created_at,
                    updated_at=space.updated_at,
                )
            )
            for node in await self.list_active_nodes(session, space_id=space.id):
                payload = self._node_payload(node)
                payload["feature_id"] = feature.id
                if payload["parent_id"] is None:
                    payload["parent_id"] = feature_root_id
                nodes.append(payload)

        history_spaces = (
            await session.execute(
                select(WikiSpace, Feature)
                .join(Feature, Feature.id == WikiSpace.feature_id)
                .where(WikiSpace.scope == "history")
                .order_by(WikiSpace.id.asc())
            )
        ).all()
        for index, (space, feature) in enumerate(history_spaces):
            feature_root_id = -200000 - feature.id
            nodes.append(
                self._virtual_node(
                    node_id=feature_root_id,
                    space_id=space.id,
                    feature_id=feature.id,
                    parent_id=-2,
                    name=feature.name,
                    path=f"历史特性/{feature.slug}",
                    system_role="feature_space_history",
                    sort_order=index,
                    created_at=space.created_at,
                    updated_at=space.updated_at,
                )
            )
            for node in await self.list_active_nodes(session, space_id=space.id):
                payload = self._node_payload(node)
                payload["feature_id"] = feature.id
                if payload["parent_id"] is None:
                    payload["parent_id"] = feature_root_id
                nodes.append(payload)

        return nodes

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

    async def get_preferred_space_for_feature(
        self,
        session: AsyncSession,
        *,
        feature: Feature,
    ) -> WikiSpace:
        if feature.status == "active":
            return await self.ensure_current_space_for_feature(session, feature=feature)
        history_space = (
            await session.execute(
                select(WikiSpace).where(
                    WikiSpace.feature_id == feature.id,
                    WikiSpace.scope == "history",
                )
            )
        ).scalar_one_or_none()
        if history_space is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="wiki space not found",
            )
        return history_space

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

    async def restore_archived_space(
        self,
        session: AsyncSession,
        *,
        space: WikiSpace,
    ) -> WikiSpace:
        if space.scope != "history" or space.status != "archived":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="wiki space is not archived",
            )
        feature = await self._load_feature_for_space(session, space_id=space.id)
        if feature.status != "archived":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="feature is not archived",
            )
        current_space = (
            await session.execute(
                select(WikiSpace).where(
                    WikiSpace.feature_id == feature.id,
                    WikiSpace.scope == "current",
                )
            )
        ).scalar_one_or_none()
        if current_space is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="feature already has a current wiki space",
            )
        feature.status = "active"
        feature.archived_at = None
        feature.archived_by_subject_id = None
        space.scope = "current"
        space.status = "active"
        space.archived_at = None
        space.archived_by_subject_id = None
        await session.flush()
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
        if node.type == "document":
            document = (
                await session.execute(select(WikiDocument).where(WikiDocument.node_id == node.id))
            ).scalar_one_or_none()
            if document is not None:
                document.title = next_name
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

    async def restore_node(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        node: WikiNode,
    ) -> WikiNode:
        if node.deleted_at is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="wiki node is not deleted",
            )
        self._require_mutable_node(node)
        feature = await self._load_feature_for_space(session, space_id=node.space_id)
        self._require_write(actor, feature)

        if node.parent_id is not None:
            parent = await session.get(WikiNode, node.parent_id)
            if parent is None or parent.deleted_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="cannot restore node while parent is unavailable",
                )

        candidates = (
            await session.execute(
                select(WikiNode)
                .where(WikiNode.space_id == node.space_id)
                .order_by(WikiNode.path.asc(), WikiNode.id.asc())
            )
        ).scalars().all()
        subtree = [row for row in candidates if row.id == node.id or is_descendant_path(row.path, node.path)]
        subtree_ids = {row.id for row in subtree}
        for row in subtree:
            await self._assert_path_available(
                session,
                space_id=row.space_id,
                path=row.path,
                exclude_ids=subtree_ids,
            )
        for row in subtree:
            row.deleted_at = None
            row.deleted_by_subject_id = None
        return node

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

    def _node_payload(self, node: WikiNode) -> dict[str, Any]:
        return {
            "id": node.id,
            "space_id": node.space_id,
            "feature_id": None,
            "parent_id": node.parent_id,
            "type": node.type,
            "name": node.name,
            "path": node.path,
            "system_role": node.system_role,
            "sort_order": node.sort_order,
            "created_at": node.created_at,
            "updated_at": node.updated_at,
        }

    def _virtual_node(
        self,
        *,
        node_id: int,
        space_id: int,
        feature_id: int | None,
        parent_id: int | None,
        name: str,
        path: str,
        system_role: str,
        sort_order: int,
        created_at: datetime,
        updated_at: datetime,
    ) -> dict[str, Any]:
        return {
            "id": node_id,
            "space_id": space_id,
            "feature_id": feature_id,
            "parent_id": parent_id,
            "type": "folder",
            "name": name,
            "path": path,
            "system_role": system_role,
            "sort_order": sort_order,
            "created_at": created_at,
            "updated_at": updated_at,
        }
