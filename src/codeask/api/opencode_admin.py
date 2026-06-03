"""Admin OpenCode tool-permission configuration endpoints.

Exposes the admin-editable allow/deny matrix for opencode agent tools, plus the
bash tri-state (allow / deny / whitelist). The resolved value is stored in the
shared ``system_settings`` key-value table under :data:`PERMISSIONS_KEY` and read
back at session-init time through :func:`load_opencode_tool_permissions`.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.agent.opencode_compat.permissions import (
    BASH_WHITELIST_SUGGESTIONS,
    GOVERNED_TOOLS,
    OPENVIKING_WRITE_TOOLS,
    InvalidBashPatterns,
    OpencodeToolPermissions,
    validate_bash_patterns,
)
from codeask.audit import write_audit
from codeask.db.models import SystemSetting
from codeask.identity import require_admin

router = APIRouter()

AdminDep = Annotated[None, Depends(require_admin)]

PERMISSIONS_KEY = "opencode_tool_permissions"

# UI-facing catalog metadata: display label, one-line purpose, group, OV flag.
_TOOL_CATALOG: dict[str, tuple[str, str, str]] = {
    "read": ("读取文件", "读取工作区与仓库内的文件内容", "read"),
    "grep": ("内容检索", "按正则在文件内容中搜索", "search"),
    "glob": ("文件查找", "按通配符匹配文件路径", "search"),
    "webfetch": ("网络抓取", "抓取外部 URL 内容（出网）", "network"),
    "edit": ("编辑文件", "修改工作区内已存在的文件", "write"),
    "write": ("写入文件", "在工作区创建或覆盖文件", "write"),
    "openviking_remember": ("OpenViking 记忆", "向 RAG 写入记忆条目", "openviking"),
    "openviking_add_resource": ("OpenViking 资源", "向 RAG 索引添加资源", "openviking"),
    "openviking_forget": ("OpenViking 遗忘", "从 RAG 删除记忆条目", "openviking"),
}


async def load_opencode_tool_permissions(
    session_factory: async_sessionmaker[AsyncSession],
) -> OpencodeToolPermissions:
    """Read the stored permission config; always returns a usable value."""

    async with session_factory() as session:
        row = await session.get(SystemSetting, PERMISSIONS_KEY)
    if row is None:
        return OpencodeToolPermissions.default()
    return OpencodeToolPermissions.from_stored(row.value)


class BashPermission(BaseModel):
    mode: Literal["allow", "deny", "whitelist"] = "deny"
    patterns: list[str] = Field(default_factory=list)


class PermissionsUpdateRequest(BaseModel):
    tools: dict[str, Literal["allow", "deny"]] = Field(default_factory=dict)
    bash: BashPermission = Field(default_factory=BashPermission)


def _tool_catalog(openviking_enabled: bool) -> list[dict[str, object]]:
    keys = list(GOVERNED_TOOLS)
    if openviking_enabled:
        keys.extend(OPENVIKING_WRITE_TOOLS)
    catalog: list[dict[str, object]] = []
    for key in keys:
        label, purpose, group = _TOOL_CATALOG.get(key, (key, "", "other"))
        catalog.append(
            {
                "key": key,
                "label": label,
                "purpose": purpose,
                "group": group,
                "openviking": key in OPENVIKING_WRITE_TOOLS,
            }
        )
    return catalog


def _serialize(
    permissions: OpencodeToolPermissions,
    *,
    openviking_enabled: bool,
) -> dict[str, object]:
    stored = permissions.to_stored()
    return {
        "tools": stored["tools"],
        "bash": stored["bash"],
        "openviking_enabled": openviking_enabled,
        "catalog": {
            "tools": _tool_catalog(openviking_enabled),
            "bash_suggestions": list(BASH_WHITELIST_SUGGESTIONS),
        },
        "defaults": OpencodeToolPermissions.default().to_stored(),
    }


@router.get("/admin/opencode/permissions")
async def get_opencode_permissions(_: AdminDep, request: Request) -> dict[str, object]:
    openviking_enabled = bool(getattr(request.app.state.settings, "openviking_enabled", False))
    permissions = await load_opencode_tool_permissions(request.app.state.session_factory)
    return _serialize(permissions, openviking_enabled=openviking_enabled)


@router.put("/admin/opencode/permissions")
async def update_opencode_permissions(
    payload: PermissionsUpdateRequest,
    _: AdminDep,
    request: Request,
) -> dict[str, object]:
    openviking_enabled = bool(getattr(request.app.state.settings, "openviking_enabled", False))

    governed = set(GOVERNED_TOOLS) | set(OPENVIKING_WRITE_TOOLS)
    unknown = set(payload.tools) - governed
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown tool keys: {', '.join(sorted(unknown))}",
        )

    try:
        patterns = validate_bash_patterns(payload.bash.patterns)
    except InvalidBashPatterns as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Start from defaults, overlay the admin-supplied values (absent keys keep default).
    merged_tools = dict(OpencodeToolPermissions.default().tools)
    for key, value in payload.tools.items():
        merged_tools[key] = value

    permissions = OpencodeToolPermissions(
        tools=merged_tools,
        bash_mode=payload.bash.mode,
        bash_patterns=tuple(patterns),
    )

    async with request.app.state.session_factory() as session:
        row = await session.get(SystemSetting, PERMISSIONS_KEY)
        stored = permissions.to_stored()
        if row is None:
            session.add(SystemSetting(key=PERMISSIONS_KEY, value=stored))
        else:
            row.value = stored
        await write_audit(
            session,
            entity_type="system_setting",
            entity_id=PERMISSIONS_KEY,
            action="opencode_permissions.update",
            subject_id=request.state.subject_id,
            result=permissions.bash_mode,
        )
        await session.commit()

    return _serialize(permissions, openviking_enabled=openviking_enabled)
