"""Import job staging and persistence services for native wiki imports."""

from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path
from secrets import token_hex

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import Feature, WikiAsset, WikiDocument, WikiImportItem, WikiImportJob, WikiNode, WikiSpace
from codeask.metrics.audit import record_audit_log
from codeask.wiki.audit import AuditWriter
from codeask.wiki.actor import WikiActor
from codeask.wiki.documents.service import WikiDocumentService
from codeask.wiki.imports.preflight import WikiImportPreflightService
from codeask.wiki.permissions import can_write_feature
from codeask.wiki.sources import WikiSourceService
from codeask.wiki.tree import WikiTreeService


class WikiImportJobService:
    def __init__(self, audit: AuditWriter | None = None) -> None:
        self._audit = audit or AuditWriter()

    async def create_job(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        settings_data_dir: Path,
        space: WikiSpace,
        parent: WikiNode | None,
        files: list[UploadFile],
    ) -> dict[str, object]:
        feature = await self._load_feature_for_space(session, space_id=space.id)
        self._require_write(actor, feature)
        items, summary, ready = await WikiImportPreflightService().analyze_import(
            session,
            actor=actor,
            space=space,
            parent=parent,
            files=files,
        )
        if not ready:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="import preflight has conflicts",
            )

        job = WikiImportJob(
            space_id=space.id,
            source_id=None,
            status="queued",
            requested_by_subject_id=actor.subject_id,
            error_message=None,
        )
        session.add(job)
        await session.flush()
        source = await WikiSourceService().create_source(
            session,
            actor=actor,
            space_id=space.id,
            kind="directory_import",
            display_name=f"导入任务 {job.id}",
            uri=None,
            metadata_json={
                "import_job_id": job.id,
                "requested_by_subject_id": actor.subject_id,
            },
        )
        job.source_id = source.id

        staging_root = settings_data_dir / "wiki" / "imports" / f"job_{job.id}"
        staging_root.mkdir(parents=True, exist_ok=True)
        items_by_path = {item.relative_path: item for item in items}
        for file in files:
            relative_path = WikiImportPreflightService()._normalize_relative_path(file.filename)
            preflight_item = items_by_path[relative_path]
            staged_path = staging_root / relative_path
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            with staged_path.open("wb") as output:
                shutil.copyfileobj(file.file, output)
            await file.seek(0)
            session.add(
                WikiImportItem(
                    job_id=job.id,
                    source_path=relative_path,
                    target_node_path=preflight_item.target_path,
                    display_name=Path(relative_path).name,
                    status="pending",
                    metadata_json={
                        "item_kind": preflight_item.kind,
                        "warnings": [
                            issue.as_dict()
                            for issue in preflight_item.issues
                            if issue.severity == "warning"
                        ],
                        "staging_path": str(staged_path),
                    },
                    error_message=None,
                )
            )
        await session.flush()
        await record_audit_log(
            session,
            entity_type="wiki_import_job",
            entity_id=str(job.id),
            action="create",
            subject_id=actor.subject_id,
            to_status=job.status,
        )
        self._audit.write(
            "wiki_import_job.created",
            {"job_id": int(job.id), "space_id": int(job.space_id), "source_id": int(source.id)},
            subject_id=actor.subject_id,
        )
        return {
            "id": job.id,
            "space_id": job.space_id,
            "status": job.status,
            "requested_by_subject_id": job.requested_by_subject_id,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "summary": summary,
        }

    async def get_job(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        job_id: int,
    ) -> dict[str, object]:
        job = await self._load_job(session, job_id=job_id)
        feature = await self._load_feature_for_space(session, space_id=job.space_id)
        self._require_write(actor, feature)
        items = await self._load_items(session, job_id=job.id)
        return {
            "id": job.id,
            "space_id": job.space_id,
            "status": job.status,
            "requested_by_subject_id": job.requested_by_subject_id,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "summary": self._summarize_items(items),
        }

    async def list_items(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        job_id: int,
    ) -> dict[str, object]:
        job = await self._load_job(session, job_id=job_id)
        feature = await self._load_feature_for_space(session, space_id=job.space_id)
        self._require_write(actor, feature)
        items = await self._load_items(session, job_id=job.id)
        return {
            "items": [
                {
                    "id": item.id,
                    "source_path": item.source_path,
                    "target_path": item.target_node_path,
                    "item_kind": (item.metadata_json or {}).get("item_kind"),
                    "status": item.status,
                    "warnings": (item.metadata_json or {}).get("warnings", []),
                    "staging_path": (item.metadata_json or {}).get("staging_path"),
                    "result_node_id": (item.metadata_json or {}).get("result_node_id"),
                }
                for item in items
            ]
        }

    async def apply_job(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        settings_data_dir: Path,
        job_id: int,
    ) -> dict[str, object]:
        job = await self._load_job(session, job_id=job_id)
        feature = await self._load_feature_for_space(session, space_id=job.space_id)
        self._require_write(actor, feature)
        if job.status != "queued":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"wiki import job is not applyable from status {job.status}",
            )

        previous_status = job.status
        items = await self._load_items(session, job_id=job.id)
        nodes_by_path = await self._load_existing_nodes(session, space_id=job.space_id)
        document_items: list[tuple[WikiImportItem, WikiNode, Path]] = []
        job.status = "running"

        for item in items:
            metadata = dict(item.metadata_json or {})
            staged_path_str = metadata.get("staging_path")
            if not isinstance(staged_path_str, str):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"wiki import item {item.id} missing staging_path",
                )
            staged_path = Path(staged_path_str)
            if not staged_path.is_file():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"staged import file missing: {item.source_path}",
                )
            target_path = item.target_node_path
            if not target_path:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"wiki import item {item.id} missing target path",
                )
            if target_path in nodes_by_path:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"wiki node path conflict: {target_path}",
                )

            parent_node = await self._ensure_parent_folders(
                session,
                actor=actor,
                space=await self._load_space(session, space_id=job.space_id),
                nodes_by_path=nodes_by_path,
                source_path=item.source_path,
                target_path=target_path,
            )

            if metadata.get("item_kind") == "asset":
                node = await self._create_asset_from_staged(
                    session,
                    settings_data_dir=settings_data_dir,
                    space=await self._load_space(session, space_id=job.space_id),
                    parent=parent_node,
                    source_path=item.source_path,
                    target_path=target_path,
                    staged_path=staged_path,
                    job_id=job.id,
                    source_id=job.source_id,
                )
                nodes_by_path[node.path] = node
                item.status = "imported"
                metadata["result_node_id"] = node.id
                item.metadata_json = metadata
                continue

            node = await WikiTreeService().create_node(
                session,
                actor=actor,
                space=await self._load_space(session, space_id=job.space_id),
                parent=parent_node,
                node_type="document",
                name=Path(item.source_path).stem,
            )
            nodes_by_path[node.path] = node
            document = (
                await session.execute(select(WikiDocument).where(WikiDocument.node_id == node.id))
            ).scalar_one()
            document.provenance_json = {
                "source": "directory_import",
                "source_id": job.source_id,
                "import_job_id": job.id,
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
            item.status = "imported"

        job.status = "succeeded"
        await session.flush()
        await record_audit_log(
            session,
            entity_type="wiki_import_job",
            entity_id=str(job.id),
            action="apply",
            subject_id=actor.subject_id,
            from_status=previous_status,
            to_status=job.status,
        )
        self._audit.write(
            "wiki_import_job.applied",
            {"job_id": int(job.id), "space_id": int(job.space_id), "source_id": int(job.source_id or 0)},
            subject_id=actor.subject_id,
        )
        return await self.get_job(session, actor=actor, job_id=job.id)

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

    async def _load_job(self, session: AsyncSession, *, job_id: int) -> WikiImportJob:
        job = (
            await session.execute(select(WikiImportJob).where(WikiImportJob.id == job_id))
        ).scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="wiki import job not found")
        return job

    async def _load_items(self, session: AsyncSession, *, job_id: int) -> list[WikiImportItem]:
        return (
            await session.execute(
                select(WikiImportItem)
                .where(WikiImportItem.job_id == job_id)
                .order_by(WikiImportItem.id.asc())
            )
        ).scalars().all()

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
        job_id: int,
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
                    "import_job_id": job_id,
                    "source_path": source_path,
                },
            )
        )
        await session.flush()
        return node

    def _summarize_items(self, items: list[WikiImportItem]) -> dict[str, int]:
        warnings = sum(len((item.metadata_json or {}).get("warnings", [])) for item in items)
        return {
            "total_files": len(items),
            "document_count": sum(
                1 for item in items if (item.metadata_json or {}).get("item_kind") == "document"
            ),
            "asset_count": sum(
                1 for item in items if (item.metadata_json or {}).get("item_kind") == "asset"
            ),
            "conflict_count": sum(1 for item in items if item.status == "conflict"),
            "warning_count": warnings,
        }

    def _require_write(self, actor: WikiActor, feature: Feature) -> None:
        if not can_write_feature(actor, feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="write access denied for this wiki feature",
            )
