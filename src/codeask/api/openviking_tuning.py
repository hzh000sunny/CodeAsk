"""Admin OpenViking tuning endpoints."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select

from codeask.identity import require_admin
from codeask.rag.openviking.models import OpenVikingTuningSetting

router = APIRouter()


_DEFAULT_TUNING = {
    ("openviking", "embedding.max_concurrent"): "1",
    ("codeask", "sync_workers"): "2",
    ("codeask", "progress_sweep_interval_seconds"): "5",
    ("codeask", "scheduled_refresh_hours"): "24",
    ("ollama_recommend", "num_parallel"): "1",
    ("ollama_recommend", "num_thread"): str(max(1, (os.cpu_count() or 4) // 2)),
}


@router.get("/admin/openviking/tuning")
async def get_openviking_tuning(request: Request) -> dict[str, Any]:
    require_admin(request)
    rows = await ensure_default_tuning_settings(request)
    scopes: dict[str, list[dict[str, Any]]] = {
        "openviking": [],
        "ollama_recommend": [],
        "codeask": [],
    }
    for row in rows:
        scopes.setdefault(row.scope, []).append(
            {
                "key": row.key,
                "value": row.value,
                "activated_at": row.activated_at.isoformat(),
                "activated_by": row.activated_by,
                "previous_value": row.previous_value,
                "notes": row.notes,
            }
        )
    return {"scopes": scopes, "preset": _detect_preset()}


async def ensure_default_tuning_settings(request: Request) -> list[OpenVikingTuningSetting]:
    factory = request.app.state.session_factory
    async with factory() as session:
        existing = (await session.execute(select(OpenVikingTuningSetting))).scalars().all()
        if existing:
            return list(existing)
        now = datetime.now(UTC)
        rows = [
            OpenVikingTuningSetting(
                scope=scope,
                key=key,
                value=value,
                activated_at=now,
                notes="default",
            )
            for (scope, key), value in _DEFAULT_TUNING.items()
        ]
        session.add_all(rows)
        await session.commit()
        return rows


def _detect_preset() -> str:
    cpu_count = os.cpu_count() or 4
    if cpu_count >= 64:
        return "large_server"
    if cpu_count >= 32:
        return "medium_server"
    if cpu_count >= 16:
        return "small_server"
    return "small_machine"
