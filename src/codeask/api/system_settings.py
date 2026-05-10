"""System settings endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from codeask.audit import write_audit
from codeask.db.models import SystemSetting
from codeask.identity import require_admin

router = APIRouter()

AdminDep = Annotated[None, Depends(require_admin)]

_SESSION_ATTACHMENTS_ENABLED_KEY = "session_attachments_enabled"


class SystemSettingsResponse(BaseModel):
    session_attachments_enabled: bool = True


class SystemSettingsUpdate(BaseModel):
    session_attachments_enabled: bool | None = None


@router.get("/system-settings", response_model=SystemSettingsResponse)
async def get_system_settings(_: AdminDep, request: Request) -> SystemSettingsResponse:
    async with request.app.state.session_factory() as session:
        row = await session.get(SystemSetting, _SESSION_ATTACHMENTS_ENABLED_KEY)
    return SystemSettingsResponse(
        session_attachments_enabled=_setting_bool(row, default=True),
    )


@router.patch("/system-settings", response_model=SystemSettingsResponse)
async def update_system_settings(
    payload: SystemSettingsUpdate,
    _: AdminDep,
    request: Request,
) -> SystemSettingsResponse:
    async with request.app.state.session_factory() as session:
        if payload.session_attachments_enabled is not None:
            row = await session.get(SystemSetting, _SESSION_ATTACHMENTS_ENABLED_KEY)
            if row is None:
                row = SystemSetting(
                    key=_SESSION_ATTACHMENTS_ENABLED_KEY,
                    value=payload.session_attachments_enabled,
                )
                session.add(row)
            else:
                row.value = payload.session_attachments_enabled
            await write_audit(
                session,
                entity_type="system_setting",
                entity_id=_SESSION_ATTACHMENTS_ENABLED_KEY,
                action="system_setting.update",
                subject_id=request.state.subject_id,
                result=str(payload.session_attachments_enabled).lower(),
            )
        await session.commit()
        row = await session.get(SystemSetting, _SESSION_ATTACHMENTS_ENABLED_KEY)
    return SystemSettingsResponse(
        session_attachments_enabled=_setting_bool(row, default=True),
    )


def _setting_bool(row: SystemSetting | None, *, default: bool) -> bool:
    if row is None:
        return default
    return bool(row.value)
