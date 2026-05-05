"""Cleanup jobs for expired soft-deleted wiki content."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.db.models import WikiAsset, WikiNode

log = structlog.get_logger("codeask.wiki.cleanup")


async def purge_expired_soft_deleted_nodes(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    retention_days: int = 30,
) -> dict[str, int]:
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    async with session_factory() as session:
        nodes = (
            await session.execute(
                select(WikiNode)
                .where(
                    WikiNode.deleted_at.is_not(None),
                    WikiNode.deleted_at <= cutoff,
                )
                .order_by(WikiNode.id.asc())
            )
        ).scalars().all()

        removed_assets = 0
        for node in nodes:
            if node.type == "asset":
                asset = (
                    await session.execute(select(WikiAsset).where(WikiAsset.node_id == node.id))
                ).scalar_one_or_none()
                if asset is not None and _remove_asset_file(Path(asset.storage_path)):
                    removed_assets += 1
            await session.delete(node)

        await session.commit()
        removed_nodes = len(nodes)
        if removed_nodes > 0:
            log.info(
                "wiki_soft_delete_cleanup_completed",
                removed_nodes=removed_nodes,
                removed_assets=removed_assets,
                retention_days=retention_days,
            )
        return {
            "removed_nodes": removed_nodes,
            "removed_assets": removed_assets,
        }


def build_wiki_cleanup_job(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    retention_days: int = 30,
) -> Callable[[], None]:
    def _run() -> None:
        try:
            asyncio.run(
                purge_expired_soft_deleted_nodes(
                    session_factory,
                    retention_days=retention_days,
                )
            )
        except Exception as exc:  # pragma: no cover - scheduler guard
            log.warning(
                "wiki_soft_delete_cleanup_failed",
                retention_days=retention_days,
                error=str(exc),
            )

    return _run


def _remove_asset_file(path: Path) -> bool:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return False
    return True
