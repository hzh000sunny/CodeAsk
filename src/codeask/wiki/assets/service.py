"""Services for native wiki asset uploads and content reads."""

from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path
from secrets import token_hex

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import Feature, WikiAsset, WikiNode, WikiSpace
from codeask.wiki.actor import WikiActor
from codeask.wiki.paths import normalize_asset_name
from codeask.wiki.permissions import can_write_feature
from codeask.wiki.sources import WikiSourceService


class WikiAssetService:
    async def upload_asset(
        self,
        session: AsyncSession,
        *,
        actor: WikiActor,
        settings_data_dir: Path,
        space: WikiSpace,
        parent: WikiNode | None,
        file: UploadFile,
    ) -> dict[str, object]:
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="asset upload requires a filename",
            )
        feature = await self._load_feature_for_space(session, space_id=space.id)
        self._require_write(actor, feature)
        if parent is not None:
            if parent.deleted_at is not None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="wiki node not found")
            if parent.space_id != space.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="parent node belongs to a different wiki space",
                )

        display_name = Path(file.filename).name
        leaf = await self._unique_asset_leaf(
            session,
            space_id=space.id,
            parent_path=parent.path if parent is not None else None,
            preferred_name=display_name,
        )
        path = leaf if parent is None else f"{parent.path}/{leaf}"

        node = WikiNode(
            space_id=space.id,
            parent_id=parent.id if parent is not None else None,
            type="asset",
            name=display_name,
            path=path,
            system_role=None,
            sort_order=0,
        )
        session.add(node)
        await session.flush()

        asset_dir = settings_data_dir / "wiki" / "assets" / f"space_{space.id}"
        asset_dir.mkdir(parents=True, exist_ok=True)
        storage_name = f"{token_hex(8)}_{display_name}"
        target = asset_dir / storage_name
        with target.open("wb") as output:
            shutil.copyfileobj(file.file, output)

        mime_type = file.content_type or mimetypes.guess_type(display_name)[0] or "application/octet-stream"
        source = await WikiSourceService().create_source(
            session,
            actor=actor,
            space_id=space.id,
            kind="manual_upload",
            display_name=display_name,
            uri=None,
            metadata_json={
                "node_id": node.id,
                "original_name": display_name,
            },
        )
        asset = WikiAsset(
            node_id=node.id,
            original_name=display_name,
            file_name=storage_name,
            storage_path=str(target),
            mime_type=mime_type,
            size_bytes=target.stat().st_size,
            provenance_json={
                "source": "manual_upload",
                "source_id": source.id,
            },
        )
        session.add(asset)
        await session.flush()
        return {
            "node_id": node.id,
            "path": node.path,
            "mime_type": asset.mime_type,
            "original_name": asset.original_name,
            "file_name": asset.file_name,
            "size_bytes": asset.size_bytes,
        }

    async def load_asset_content(
        self,
        session: AsyncSession,
        *,
        node_id: int,
    ) -> tuple[Path, str]:
        node = (await session.execute(select(WikiNode).where(WikiNode.id == node_id))).scalar_one_or_none()
        if node is None or node.deleted_at is not None or node.type != "asset":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="wiki asset not found")
        asset = (
            await session.execute(select(WikiAsset).where(WikiAsset.node_id == node_id))
        ).scalar_one_or_none()
        if asset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="wiki asset not found")
        path = Path(asset.storage_path)
        if not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="wiki asset content missing")
        return path, asset.mime_type or "application/octet-stream"

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

    async def _unique_asset_leaf(
        self,
        session: AsyncSession,
        *,
        space_id: int,
        parent_path: str | None,
        preferred_name: str,
    ) -> str:
        safe = normalize_asset_name(preferred_name)
        stem = Path(safe).stem
        suffix = Path(safe).suffix
        candidate = safe
        index = 2
        while await self._path_exists(
            session,
            space_id=space_id,
            path=candidate if parent_path is None else f"{parent_path}/{candidate}",
        ):
            candidate = f"{stem}-{index}{suffix}"
            index += 1
        return candidate

    async def _path_exists(self, session: AsyncSession, *, space_id: int, path: str) -> bool:
        return (
            await session.execute(
                select(WikiNode.id).where(
                    WikiNode.space_id == space_id,
                    WikiNode.path == path,
                    WikiNode.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none() is not None

    def _require_write(self, actor: WikiActor, feature: Feature) -> None:
        if not can_write_feature(actor, feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="write access denied for this wiki feature",
            )
