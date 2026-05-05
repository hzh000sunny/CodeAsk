"""Queue-based wiki import session services."""

from __future__ import annotations

import mimetypes
import shutil
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from secrets import token_hex

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import (
    Feature,
    WikiAsset,
    WikiDocument,
    WikiImportSession,
    WikiImportSessionItem,
    WikiNode,
    WikiSpace,
)
from codeask.wiki.actor import WikiActor
from codeask.wiki.documents.service import WikiDocumentService
from codeask.wiki.imports.preflight import WikiImportPreflightService
from codeask.wiki.paths import is_descendant_path
from codeask.wiki.permissions import can_write_feature
from codeask.wiki.sources import WikiSourceService
from codeask.wiki.tree import WikiTreeService


class WikiImportSessionService:
    def __init__(self) -> None:
        self._preflight = WikiImportPreflightService()

    async def create_session(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        space: WikiSpace,
        parent: WikiNode | None,
        mode: str,
    ) -> dict[str, object]:
        feature = await self._load_feature_for_space(session, space_id=space.id)
        self._require_write(actor, feature)
        self._preflight._validate_parent(space=space, parent=parent)
        if mode not in {"markdown", "directory"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="mode must be one of: markdown, directory",
            )

        import_session = WikiImportSession(
            space_id=space.id,
            parent_id=parent.id if parent is not None else None,
            mode=mode,
            status="running",
            requested_by_subject_id=actor.subject_id,
            summary_json=self._empty_summary(),
            metadata_json={
                "root_strip_segments": 1 if mode == "directory" else 0,
                "base_path": parent.path if parent is not None else None,
            },
            error_message=None,
        )
        session.add(import_session)
        await session.flush()
        source = await WikiSourceService().create_source(
            session,
            actor=actor,
            space_id=space.id,
            kind="directory_import",
            display_name=f"导入会话 {import_session.id}",
            uri=None,
            metadata_json={
                "import_session_id": import_session.id,
                "requested_by_subject_id": actor.subject_id,
                "mode": mode,
            },
        )
        import_session.metadata_json = {
            **(import_session.metadata_json or {}),
            "source_id": source.id,
        }
        await session.flush()
        return self._serialize_session(import_session)

    async def get_session(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        session_id: int,
    ) -> dict[str, object]:
        import_session = await self._load_session(session, session_id=session_id)
        feature = await self._load_feature_for_space(session, space_id=import_session.space_id)
        self._require_write(actor, feature)
        import_session.summary_json = await self._recalculate_summary(session, import_session.id)
        await session.flush()
        return self._serialize_session(import_session)

    async def scan_session(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        session_id: int,
        items: list[dict[str, object]],
    ) -> dict[str, object]:
        import_session = await self._load_session(session, session_id=session_id)
        feature = await self._load_feature_for_space(session, space_id=import_session.space_id)
        self._require_write(actor, feature)
        await session.execute(
            delete(WikiImportSessionItem).where(WikiImportSessionItem.session_id == import_session.id)
        )

        root_strip_segments = int((import_session.metadata_json or {}).get("root_strip_segments", 0))
        base_path = (import_session.metadata_json or {}).get("base_path")
        if base_path is not None and not isinstance(base_path, str):
            base_path = None

        for index, raw_item in enumerate(items):
            relative_path = self._preflight._normalize_relative_path(
                str(raw_item.get("relative_path") or "")
            )
            included = bool(raw_item.get("included"))
            item_kind = str(raw_item.get("item_kind") or "").strip() or "ignored"
            ignore_reason = raw_item.get("ignore_reason")
            if ignore_reason is not None and not isinstance(ignore_reason, str):
                ignore_reason = str(ignore_reason)

            target_path: str | None = None
            status_value = "ignored"
            progress_percent = 0
            if included:
                if item_kind not in {"document", "asset"}:
                    item_kind = self._preflight._classify_kind(relative_path)
                target_relative_path = self._strip_root_segments(
                    relative_path,
                    strip_count=root_strip_segments,
                )
                target_path = self._preflight._target_path(
                    base_path=base_path,
                    relative_path=target_relative_path,
                    kind=item_kind,
                )
                status_value = "pending"
            session.add(
                WikiImportSessionItem(
                    session_id=import_session.id,
                    sort_order=index,
                    source_path=relative_path,
                    target_node_path=target_path,
                    display_name=PurePosixPath(relative_path).name,
                    item_kind=item_kind,
                    status=status_value,
                    progress_percent=progress_percent,
                    metadata_json={"ignore_reason": ignore_reason} if ignore_reason else None,
                    error_message=None,
                )
            )

        await session.flush()
        import_session.summary_json = await self._recalculate_summary(session, import_session.id)
        await session.flush()
        return self._serialize_session(import_session)

    async def list_items(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        session_id: int,
    ) -> dict[str, object]:
        import_session = await self._load_session(session, session_id=session_id)
        feature = await self._load_feature_for_space(session, space_id=import_session.space_id)
        self._require_write(actor, feature)
        items = await self._load_items(session, session_id=import_session.id)
        return {"items": [self._serialize_item(item) for item in items]}

    async def upload_item(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        settings_data_dir: Path,
        session_id: int,
        item_id: int,
        file: UploadFile,
    ) -> dict[str, object]:
        import_session = await self._load_session(session, session_id=session_id)
        feature = await self._load_feature_for_space(session, space_id=import_session.space_id)
        self._require_write(actor, feature)
        if import_session.status != "running":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"wiki import session is not uploadable from status {import_session.status}",
            )
        item = await self._load_item(session, session_id=import_session.id, item_id=item_id)
        if item.status not in {"pending", "failed"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"wiki import session item is not uploadable from status {item.status}",
            )
        if item.target_node_path is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="wiki import session item has no target path",
            )

        item.status = "uploading"
        await session.flush()

        staging_root = settings_data_dir / "wiki" / "imports" / f"session_{import_session.id}"
        staging_root.mkdir(parents=True, exist_ok=True)
        staged_path = staging_root / item.source_path
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        with staged_path.open("wb") as output:
            shutil.copyfileobj(file.file, output)
        await file.seek(0)

        metadata = dict(item.metadata_json or {})
        metadata["staging_path"] = str(staged_path)
        item.metadata_json = metadata
        item.progress_percent = 100
        item.error_message = None
        if await self._path_conflicts_with_active_node(
            session,
            space_id=import_session.space_id,
            target_path=item.target_node_path,
        ):
            default_conflict_action = self._default_conflict_action(import_session)
            if default_conflict_action == "skip":
                item.status = "skipped"
            elif default_conflict_action == "overwrite":
                await self._soft_delete_conflicting_path(
                    session,
                    actor=actor,
                    space_id=import_session.space_id,
                    target_path=item.target_node_path,
                )
                item.status = "uploaded"
            else:
                item.status = "conflict"
                item.error_message = f"wiki node path conflict: {item.target_node_path}"
        else:
            item.status = "uploaded"
        await session.flush()

        items = await self._load_items(session, session_id=import_session.id)
        if self._ready_to_materialize(items):
            await self._materialize_or_mark_failed(
                session,
                actor=actor,
                settings_data_dir=settings_data_dir,
                import_session=import_session,
                items=items,
                failed_item=item,
            )
        else:
            import_session.status = "running"
        import_session.summary_json = await self._recalculate_summary(session, import_session.id)
        await session.flush()
        return {
            "session": self._serialize_session(import_session),
            "item": self._serialize_item(item),
        }

    async def cancel_session(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        session_id: int,
    ) -> dict[str, object]:
        import_session = await self._load_session(session, session_id=session_id)
        feature = await self._load_feature_for_space(session, space_id=import_session.space_id)
        self._require_write(actor, feature)
        if import_session.status == "completed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="completed wiki import session cannot be cancelled",
            )
        if import_session.status != "cancelled":
            import_session.status = "cancelled"
            import_session.summary_json = await self._recalculate_summary(session, import_session.id)
            await session.flush()
        return self._serialize_session(import_session)

    async def retry_item(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        settings_data_dir: Path,
        session_id: int,
        item_id: int,
    ) -> dict[str, object]:
        import_session = await self._load_session(session, session_id=session_id)
        feature = await self._load_feature_for_space(session, space_id=import_session.space_id)
        self._require_write(actor, feature)
        if import_session.status != "running":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"wiki import session is not retryable from status {import_session.status}",
            )
        item = await self._load_item(session, session_id=import_session.id, item_id=item_id)
        if item.status != "failed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"wiki import session item is not retryable from status {item.status}",
            )
        metadata = dict(item.metadata_json or {})
        staged_path_str = metadata.get("staging_path")
        if not isinstance(staged_path_str, str) or not Path(staged_path_str).is_file():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="wiki import session item has no retryable staged file",
            )
        item.status = "uploaded"
        item.error_message = None
        items = await self._load_items(session, session_id=import_session.id)
        if self._ready_to_materialize(items):
            await self._materialize_or_mark_failed(
                session,
                actor=actor,
                settings_data_dir=settings_data_dir,
                import_session=import_session,
                items=items,
                failed_item=item,
            )
        else:
            import_session.status = "running"
        import_session.summary_json = await self._recalculate_summary(session, import_session.id)
        await session.flush()
        return {
            "session": self._serialize_session(import_session),
            "item": self._serialize_item(item),
        }

    async def retry_failed_items(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        settings_data_dir: Path,
        session_id: int,
    ) -> dict[str, object]:
        import_session = await self._load_session(session, session_id=session_id)
        feature = await self._load_feature_for_space(session, space_id=import_session.space_id)
        self._require_write(actor, feature)
        if import_session.status != "running":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"wiki import session is not retryable from status {import_session.status}",
            )
        items = await self._load_items(session, session_id=import_session.id)
        failed_items = [item for item in items if item.status == "failed"]
        if not failed_items:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="wiki import session has no failed items",
            )
        for item in failed_items:
            metadata = dict(item.metadata_json or {})
            staged_path_str = metadata.get("staging_path")
            if not isinstance(staged_path_str, str) or not Path(staged_path_str).is_file():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"wiki import session item {item.id} has no retryable staged file",
                )
            item.status = "uploaded"
            item.error_message = None
        items = await self._load_items(session, session_id=import_session.id)
        if self._ready_to_materialize(items):
            await self._materialize_or_mark_failed(
                session,
                actor=actor,
                settings_data_dir=settings_data_dir,
                import_session=import_session,
                items=items,
                failed_item=failed_items[0],
            )
        else:
            import_session.status = "running"
        import_session.summary_json = await self._recalculate_summary(session, import_session.id)
        await session.flush()
        return self._serialize_session(import_session)

    async def resolve_item(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        settings_data_dir: Path,
        session_id: int,
        item_id: int,
        action: str,
    ) -> dict[str, object]:
        import_session = await self._load_session(session, session_id=session_id)
        feature = await self._load_feature_for_space(session, space_id=import_session.space_id)
        self._require_write(actor, feature)
        if import_session.status != "running":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"wiki import session is not resolvable from status {import_session.status}",
            )
        item = await self._load_item(session, session_id=import_session.id, item_id=item_id)
        if item.status != "conflict":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"wiki import session item is not resolvable from status {item.status}",
            )
        if action not in {"skip", "overwrite"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="action must be one of: skip, overwrite",
            )

        if action == "skip":
            item.status = "skipped"
            item.error_message = None
        else:
            if item.target_node_path is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="wiki import session item has no target path",
                )
            await self._soft_delete_conflicting_path(
                session,
                actor=actor,
                space_id=import_session.space_id,
                target_path=item.target_node_path,
            )
            item.status = "uploaded"
            item.error_message = None

        items = await self._load_items(session, session_id=import_session.id)
        if self._ready_to_materialize(items):
            await self._materialize_uploaded_items(
                session,
                actor=actor,
                settings_data_dir=settings_data_dir,
                import_session=import_session,
                items=items,
            )
            import_session.status = "completed"
        else:
            import_session.status = "running"
        import_session.summary_json = await self._recalculate_summary(session, import_session.id)
        await session.flush()
        return {
            "session": self._serialize_session(import_session),
            "item": self._serialize_item(item),
        }

    async def bulk_resolve_items(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        settings_data_dir: Path,
        session_id: int,
        action: str,
    ) -> dict[str, object]:
        import_session = await self._load_session(session, session_id=session_id)
        feature = await self._load_feature_for_space(session, space_id=import_session.space_id)
        self._require_write(actor, feature)
        if import_session.status != "running":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"wiki import session is not resolvable from status {import_session.status}",
            )
        if action not in {"skip_all", "overwrite_all"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="action must be one of: skip_all, overwrite_all",
            )

        items = await self._load_items(session, session_id=import_session.id)
        conflict_items = [item for item in items if item.status == "conflict"]
        if not conflict_items:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="wiki import session has no conflict items",
            )

        if action == "overwrite_all":
            self._set_default_conflict_action(import_session, "overwrite")
            target_paths = sorted(
                {item.target_node_path for item in conflict_items if item.target_node_path},
            )
            for target_path in target_paths:
                await self._soft_delete_conflicting_path(
                    session,
                    actor=actor,
                    space_id=import_session.space_id,
                    target_path=target_path,
                )
            for item in conflict_items:
                item.status = "uploaded"
                item.error_message = None
        else:
            self._set_default_conflict_action(import_session, "skip")
            for item in conflict_items:
                item.status = "skipped"
                item.error_message = None

        items = await self._load_items(session, session_id=import_session.id)
        if self._ready_to_materialize(items):
            await self._materialize_uploaded_items(
                session,
                actor=actor,
                settings_data_dir=settings_data_dir,
                import_session=import_session,
                items=items,
            )
            import_session.status = "completed"
        else:
            import_session.status = "running"
        import_session.summary_json = await self._recalculate_summary(session, import_session.id)
        await session.flush()
        return self._serialize_session(import_session)

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

    async def _load_session(
        self,
        session: AsyncSession,
        *,
        session_id: int,
    ) -> WikiImportSession:
        import_session = (
            await session.execute(
                select(WikiImportSession).where(WikiImportSession.id == session_id)
            )
        ).scalar_one_or_none()
        if import_session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="wiki import session not found",
            )
        return import_session

    async def _load_items(
        self,
        session: AsyncSession,
        *,
        session_id: int,
    ) -> list[WikiImportSessionItem]:
        return (
            await session.execute(
                select(WikiImportSessionItem)
                .where(WikiImportSessionItem.session_id == session_id)
                .order_by(
                    WikiImportSessionItem.sort_order.asc(),
                    WikiImportSessionItem.id.asc(),
                )
            )
        ).scalars().all()

    async def _load_item(
        self,
        session: AsyncSession,
        *,
        session_id: int,
        item_id: int,
    ) -> WikiImportSessionItem:
        item = (
            await session.execute(
                select(WikiImportSessionItem).where(
                    WikiImportSessionItem.session_id == session_id,
                    WikiImportSessionItem.id == item_id,
                )
            )
        ).scalar_one_or_none()
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="wiki import session item not found",
            )
        return item

    async def _recalculate_summary(
        self,
        session: AsyncSession,
        session_id: int,
    ) -> dict[str, int]:
        items = await self._load_items(session, session_id=session_id)
        summary = self._empty_summary()
        summary["total_files"] = len(items)
        for item in items:
            if item.status == "pending":
                summary["pending_count"] += 1
            elif item.status == "uploading":
                summary["uploading_count"] += 1
            elif item.status == "uploaded":
                summary["uploaded_count"] += 1
            elif item.status == "conflict":
                summary["conflict_count"] += 1
            elif item.status == "failed":
                summary["failed_count"] += 1
            elif item.status == "ignored":
                summary["ignored_count"] += 1
            elif item.status == "skipped":
                summary["skipped_count"] += 1
        return summary

    def _empty_summary(self) -> dict[str, int]:
        return {
            "total_files": 0,
            "pending_count": 0,
            "uploading_count": 0,
            "uploaded_count": 0,
            "conflict_count": 0,
            "failed_count": 0,
            "ignored_count": 0,
            "skipped_count": 0,
        }

    def _default_conflict_action(self, import_session: WikiImportSession) -> str | None:
        value = (import_session.metadata_json or {}).get("default_conflict_action")
        if value in {"skip", "overwrite"}:
            return value
        return None

    def _set_default_conflict_action(
        self,
        import_session: WikiImportSession,
        action: str | None,
    ) -> None:
        metadata = dict(import_session.metadata_json or {})
        if action is None:
            metadata.pop("default_conflict_action", None)
        else:
            metadata["default_conflict_action"] = action
        import_session.metadata_json = metadata

    def _strip_root_segments(self, relative_path: str, *, strip_count: int) -> str:
        if strip_count <= 0:
            return relative_path
        parts = PurePosixPath(relative_path).parts
        if len(parts) <= strip_count:
            return relative_path
        return "/".join(parts[strip_count:])

    def _serialize_session(self, import_session: WikiImportSession) -> dict[str, object]:
        return {
            "id": import_session.id,
            "space_id": import_session.space_id,
            "parent_id": import_session.parent_id,
            "mode": import_session.mode,
            "status": import_session.status,
            "requested_by_subject_id": import_session.requested_by_subject_id,
            "created_at": import_session.created_at,
            "updated_at": import_session.updated_at,
            "summary": dict(import_session.summary_json or self._empty_summary()),
        }

    def _serialize_item(self, item: WikiImportSessionItem) -> dict[str, object]:
        metadata = dict(item.metadata_json or {})
        return {
            "id": item.id,
            "source_path": item.source_path,
            "target_path": item.target_node_path,
            "item_kind": item.item_kind,
            "status": item.status,
            "progress_percent": item.progress_percent,
            "ignore_reason": metadata.get("ignore_reason"),
            "staging_path": metadata.get("staging_path"),
            "result_node_id": metadata.get("result_node_id"),
            "error_message": item.error_message,
        }

    def _ready_to_materialize(self, items: list[WikiImportSessionItem]) -> bool:
        blocking_statuses = {"pending", "uploading", "conflict", "failed"}
        return not any(item.status in blocking_statuses for item in items)

    async def _materialize_uploaded_items(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        settings_data_dir: Path,
        import_session: WikiImportSession,
        items: list[WikiImportSessionItem],
    ) -> None:
        nodes_by_path = await self._load_existing_nodes(session, space_id=import_session.space_id)
        document_items: list[tuple[WikiImportSessionItem, WikiNode, Path]] = []
        space = await self._load_space(session, space_id=import_session.space_id)

        for item in items:
            if item.status != "uploaded":
                continue
            metadata = dict(item.metadata_json or {})
            staged_path_str = metadata.get("staging_path")
            if not isinstance(staged_path_str, str):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"wiki import session item {item.id} missing staging_path",
                )
            staged_path = Path(staged_path_str)
            if not staged_path.is_file():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"staged import file missing: {item.source_path}",
                )
            if not item.target_node_path:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"wiki import session item {item.id} missing target path",
                )
            if item.target_node_path in nodes_by_path:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"wiki node path conflict: {item.target_node_path}",
                )
            parent_node = await self._ensure_parent_folders(
                session,
                actor=actor,
                space=space,
                nodes_by_path=nodes_by_path,
                source_path=item.source_path,
                target_path=item.target_node_path,
            )
            if item.item_kind == "asset":
                source_id = (import_session.metadata_json or {}).get("source_id")
                node = await self._create_asset_from_staged(
                    session,
                    settings_data_dir=settings_data_dir,
                    space=space,
                    parent=parent_node,
                    source_path=item.source_path,
                    target_path=item.target_node_path,
                    staged_path=staged_path,
                    import_session_id=import_session.id,
                    source_id=source_id if isinstance(source_id, int) else None,
                )
                nodes_by_path[node.path] = node
                metadata["result_node_id"] = node.id
                item.metadata_json = metadata
                continue

            node = await WikiTreeService().create_node(
                session,
                actor=actor,
                space=space,
                parent=parent_node,
                node_type="document",
                name=Path(item.source_path).stem,
            )
            nodes_by_path[node.path] = node
            document = (
                await session.execute(select(WikiDocument).where(WikiDocument.node_id == node.id))
            ).scalar_one()
            source_id = (import_session.metadata_json or {}).get("source_id")
            document.provenance_json = {
                "source": "directory_import",
                "source_id": source_id,
                "import_session_id": import_session.id,
                "source_path": item.source_path,
            }
            document.title = Path(item.source_path).stem
            document_items.append((item, node, staged_path))

        for item, node, staged_path in document_items:
            await WikiDocumentService().publish_document(
                session,
                node_id=node.id,
                actor=actor,
                body_markdown=staged_path.read_text(encoding="utf-8"),
            )
            metadata = dict(item.metadata_json or {})
            metadata["result_node_id"] = node.id
            item.metadata_json = metadata
        await session.flush()

    async def _load_existing_nodes(
        self,
        session: AsyncSession,
        *,
        space_id: int,
    ) -> dict[str, WikiNode]:
        rows = (
            await session.execute(
                select(WikiNode).where(
                    WikiNode.space_id == space_id,
                    WikiNode.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        return {row.path: row for row in rows}

    async def _materialize_or_mark_failed(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        settings_data_dir: Path,
        import_session: WikiImportSession,
        items: list[WikiImportSessionItem],
        failed_item: WikiImportSessionItem,
    ) -> None:
        try:
            await self._materialize_uploaded_items(
                session,
                actor=actor,
                settings_data_dir=settings_data_dir,
                import_session=import_session,
                items=items,
            )
            import_session.status = "completed"
        except HTTPException as exc:
            failed_item.status = "failed"
            failed_item.error_message = str(exc.detail)
            import_session.status = "running"
        except Exception as exc:  # pragma: no cover - defensive fallback
            failed_item.status = "failed"
            failed_item.error_message = str(exc)
            import_session.status = "running"

    async def _path_conflicts_with_active_node(
        self,
        session: AsyncSession,
        *,
        space_id: int,
        target_path: str,
    ) -> bool:
        return (
            await session.execute(
                select(WikiNode.id).where(
                    WikiNode.space_id == space_id,
                    WikiNode.path == target_path,
                    WikiNode.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none() is not None

    async def _load_space(self, session: AsyncSession, *, space_id: int) -> WikiSpace:
        space = (
            await session.execute(select(WikiSpace).where(WikiSpace.id == space_id))
        ).scalar_one_or_none()
        if space is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="wiki space not found")
        return space

    async def _ensure_parent_folders(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        space: WikiSpace,
        nodes_by_path: dict[str, WikiNode],
        source_path: str,
        target_path: str,
    ) -> WikiNode | None:
        source_parts = Path(source_path).parts[:-1]
        target_parts = target_path.split("/")[:-1]
        parent: WikiNode | None = None
        for index, folder_path in enumerate(target_parts):
            cumulative_path = "/".join(target_parts[: index + 1])
            existing = nodes_by_path.get(cumulative_path)
            if existing is not None:
                parent = existing
                continue
            display_name = source_parts[index] if index < len(source_parts) else folder_path
            parent = await WikiTreeService().create_node(
                session,
                actor=actor,
                space=space,
                parent=parent,
                node_type="folder",
                name=display_name,
            )
            nodes_by_path[parent.path] = parent
        return parent

    async def _create_asset_from_staged(
        self,
        session: AsyncSession,
        *,
        settings_data_dir: Path,
        space: WikiSpace,
        parent: WikiNode | None,
        source_path: str,
        target_path: str,
        staged_path: Path,
        import_session_id: int,
        source_id: int | None,
    ) -> WikiNode:
        node = WikiNode(
            space_id=space.id,
            parent_id=parent.id if parent is not None else None,
            type="asset",
            name=Path(source_path).name,
            path=target_path,
            system_role=None,
            sort_order=0,
        )
        session.add(node)
        await session.flush()
        asset_dir = settings_data_dir / "wiki" / "assets" / f"space_{space.id}"
        asset_dir.mkdir(parents=True, exist_ok=True)
        storage_name = f"{token_hex(8)}_{Path(source_path).name}"
        stored_path = asset_dir / storage_name
        shutil.copyfile(staged_path, stored_path)
        session.add(
            WikiAsset(
                node_id=node.id,
                original_name=Path(source_path).name,
                file_name=storage_name,
                storage_path=str(stored_path),
                mime_type=mimetypes.guess_type(Path(source_path).name)[0] or "application/octet-stream",
                size_bytes=stored_path.stat().st_size,
                provenance_json={
                    "source": "directory_import",
                    "source_id": source_id,
                    "import_session_id": import_session_id,
                    "source_path": source_path,
                },
            )
        )
        await session.flush()
        return node

    async def _soft_delete_conflicting_path(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        space_id: int,
        target_path: str,
    ) -> None:
        rows = (
            await session.execute(
                select(WikiNode).where(
                    WikiNode.space_id == space_id,
                    WikiNode.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        now = datetime.now(UTC)
        for row in rows:
            if row.path == target_path or is_descendant_path(row.path, target_path):
                row.deleted_at = now
                row.deleted_by_subject_id = actor.subject_id

    def _require_write(self, actor: WikiActor, feature: Feature) -> None:
        if not can_write_feature(actor, feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="write access denied for this wiki feature",
            )
