from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from codeask.agent.opencode_compat.context import build_dynamic_codeask_context
from codeask.db import session_factory
from codeask.db.base import Base
from codeask.db.models import Feature, FeatureRepo, Repo, Session, SessionAttachment, SessionFeature


@pytest.fixture()
async def db_factory(tmp_path: Path):  # type: ignore[no-untyped-def]
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'context.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = session_factory(engine)
    async with factory() as session:
        feature = Feature(
            name="AnythingLLM Reference",
            slug="anything-llm",
            description="AnythingLLM 上传、切分、向量化和召回流程",
            summary_text="RAG ingestion and retrieval reference",
            owner_subject_id="admin",
        )
        other = Feature(
            name="小米",
            slug="xiaomi",
            description="小米病历和复诊趋势",
            summary_text="肿瘤术后复诊记录",
            owner_subject_id="admin",
        )
        archived = Feature(
            name="Archived",
            slug="archived",
            owner_subject_id="admin",
            status="archived",
        )
        repo = Repo(
            id="repo_anything",
            name="anything-llm",
            source="local_dir",
            local_path="/opt/anything-llm",
            bare_path="/tmp/bare/anything",
            status=Repo.STATUS_READY,
        )
        session.add_all([feature, other, archived, repo])
        await session.flush()
        session.add(FeatureRepo(feature_id=feature.id, repo_id=repo.id))
        session.add(
            Session(
                id="sess_ctx",
                title="AnythingLLM 召回分析",
                created_by_subject_id="admin",
            )
        )
        session.add(SessionFeature(session_id="sess_ctx", feature_id=feature.id, source="auto"))
        session.add(
            SessionAttachment(
                id="att_log",
                session_id="sess_ctx",
                kind="log",
                display_name="客户端日志",
                original_filename="client.log",
                aliases_json=["日志"],
                description="用户上传的 build 失败日志",
                file_path="/tmp/client.log",
                mime_type="text/plain",
                size_bytes=2048,
            )
        )
        await session.commit()
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_dynamic_context_includes_session_features_repos_and_workspace(
    db_factory,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    context = await build_dynamic_codeask_context(
        db_factory,
        session_id="sess_ctx",
        workspace_dir=tmp_path / "workspace",
    )

    assert "<!-- CodeAsk Dynamic Context" in context
    assert "Session ID: sess_ctx" in context
    assert f"Workspace: {tmp_path / 'workspace'}" in context
    assert "anything-llm" in context
    assert "AnythingLLM Reference" in context
    assert "./wiki/anything-llm" in context
    assert "repo_anything" in context
    assert "小米" in context
    assert "Archived" not in context
    assert "客户端日志" in context
    assert "client.log" in context
    assert "att_log" in context
    assert "bind_session_features" in context
    assert "prepare_worktree" in context
