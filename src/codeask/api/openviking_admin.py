"""Admin OpenViking embedding configuration endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select

from codeask.identity import require_admin
from codeask.rag.openviking.models import OpenVikingEmbeddingSetting

router = APIRouter()


@router.get("/admin/openviking/embedding")
async def get_openviking_embedding(request: Request) -> dict[str, Any]:
    require_admin(request)
    setting = await ensure_default_embedding_setting(request)
    return _embedding_to_dict(setting)


async def ensure_default_embedding_setting(request: Request) -> OpenVikingEmbeddingSetting:
    factory = request.app.state.session_factory
    settings = request.app.state.settings
    async with factory() as session:
        setting = (
            await session.execute(
                select(OpenVikingEmbeddingSetting).order_by(
                    OpenVikingEmbeddingSetting.activated_at.desc(),
                    OpenVikingEmbeddingSetting.id.desc(),
                )
            )
        ).scalar_one_or_none()
        if setting is not None:
            return setting
        setting = OpenVikingEmbeddingSetting(
            provider="ollama",
            base_url=settings.openviking_ollama_base_url,
            model=settings.openviking_embedding_model,
            dimension=settings.openviking_embedding_dimension,
            max_concurrent=settings.openviking_embedding_max_concurrent,
            activated_at=datetime.now(UTC),
            activated_by=None,
            rebuild_status="idle",
        )
        session.add(setting)
        await session.commit()
        await session.refresh(setting)
        return setting


def _embedding_to_dict(setting: OpenVikingEmbeddingSetting) -> dict[str, Any]:
    return {
        "id": setting.id,
        "provider": setting.provider,
        "base_url": setting.base_url,
        "model": setting.model,
        "dimension": setting.dimension,
        "max_concurrent": setting.max_concurrent,
        "activated_at": setting.activated_at.isoformat(),
        "activated_by": setting.activated_by,
        "previous_setting_id": setting.previous_setting_id,
        "rebuild_status": setting.rebuild_status,
        "rebuild_progress": setting.rebuild_progress,
    }
