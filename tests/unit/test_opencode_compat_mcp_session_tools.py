from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from codeask.agent.opencode_compat.mcp.server import MCPRequestContext
from codeask.agent.opencode_compat.mcp.tools.sessions import (
    bind_session_features_tool,
    list_session_attachments_tool,
    read_session_attachment_tool,
)
from codeask.db import session_factory
from codeask.db.base import Base
from codeask.db.models import Feature, Session, SessionAttachment, SessionFeature

_CTX = MCPRequestContext(session_id="sess_tools")


@pytest.fixture()
async def db_factory(tmp_path: Path):  # type: ignore[no-untyped-def]
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'session-tools.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = session_factory(engine)
    attachment_path = tmp_path / "client.log"
    attachment_path.write_text("line1\nline2\n", encoding="utf-8")
    async with factory() as session:
        feature = Feature(
            name="小米",
            slug="xiaomi",
            description="小米病历",
            owner_subject_id="admin",
        )
        archived = Feature(
            name="归档",
            slug="archived",
            owner_subject_id="admin",
            status="archived",
        )
        session.add_all([feature, archived])
        session.add(
            Session(
                id="sess_tools",
                title="工具会话",
                created_by_subject_id="admin",
                status="active",
            )
        )
        await session.flush()
        session.add(
            SessionAttachment(
                id="att_1",
                session_id="sess_tools",
                kind="log",
                display_name="客户端日志",
                original_filename="client.log",
                aliases_json=["启动日志"],
                description="客户端失败日志",
                file_path=str(attachment_path),
                mime_type="text/plain",
                size_bytes=attachment_path.stat().st_size,
            )
        )
        await session.commit()
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_bind_session_features_tool_binds_active_features(db_factory) -> None:  # type: ignore[no-untyped-def]
    result = await bind_session_features_tool(db_factory).handler({"feature_ids": [1, 2]}, _CTX)

    assert result["summary"] == "已绑定 1 个特性到当前会话"
    assert result["bound_feature_ids"] == [1]
    assert result["skipped"] == [{"feature_id": 2, "reason": "not_found_or_inactive"}]
    async with db_factory() as session:
        rows = (
            await session.execute(
                select(SessionFeature).where(SessionFeature.session_id == "sess_tools")
            )
        ).scalars()
        assert [(row.feature_id, row.source) for row in rows] == [(1, "auto")]


@pytest.mark.asyncio
async def test_list_and_read_session_attachment_tools(db_factory) -> None:  # type: ignore[no-untyped-def]
    listed = await list_session_attachments_tool(db_factory).handler({}, _CTX)
    read = await read_session_attachment_tool(db_factory).handler(
        {"attachment_id": "att_1", "max_chars": 20},
        _CTX,
    )

    assert listed["attachments"][0]["attachment_id"] == "att_1"
    assert listed["attachments"][0]["reference_names"] == [
        "att_1",
        "客户端日志",
        "启动日志",
        "client.log",
    ]
    assert read["attachment"]["display_name"] == "客户端日志"
    assert read["content"] == "line1\nline2\n"
