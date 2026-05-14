from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from codeask.agent.opencode_compat.mcp.server import MCPRequestContext
from codeask.agent.opencode_compat.mcp.tools.features import (
    build_feature_tools,
    get_feature_info_tool,
    list_feature_repos_tool,
    list_features_tool,
)
from codeask.db import session_factory
from codeask.db.base import Base
from codeask.db.models import Feature, FeatureRepo, Repo, WikiNode, WikiSpace

_CTX = MCPRequestContext(session_id="sess_tools")


@pytest.fixture()
async def db_factory(tmp_path: Path):  # type: ignore[no-untyped-def]
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'tools.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = session_factory(engine)
    async with factory() as session:
        feature = Feature(
            name="小米",
            slug="xiaomi",
            description="小米病历和治疗记录",
            summary_text="肿瘤切除后的复诊趋势",
            owner_subject_id="admin",
        )
        archived = Feature(
            name="归档特性",
            slug="archived",
            description="不应默认给模型",
            owner_subject_id="admin",
            status="archived",
        )
        session.add_all([feature, archived])
        await session.flush()

        space = WikiSpace(
            feature_id=feature.id,
            scope="current",
            display_name="当前特性",
            slug="xiaomi-current",
        )
        session.add(space)
        await session.flush()
        session.add_all(
            [
                WikiNode(
                    space_id=space.id,
                    parent_id=None,
                    type="folder",
                    name="知识库",
                    path="knowledge-base",
                    system_role="knowledge_base",
                    sort_order=0,
                ),
                WikiNode(
                    space_id=space.id,
                    parent_id=None,
                    type="document",
                    name="小米病历",
                    path="knowledge-base/小米病历",
                    sort_order=1,
                ),
            ]
        )
        ready_repo = Repo(
            id="repo_ready",
            name="anything-llm",
            source="local_dir",
            local_path="/tmp/anything",
            bare_path="/tmp/bare/anything",
            status=Repo.STATUS_READY,
        )
        failed_repo = Repo(
            id="repo_failed",
            name="failed",
            source="local_dir",
            local_path="/tmp/failed",
            bare_path="/tmp/bare/failed",
            status=Repo.STATUS_FAILED,
        )
        session.add_all([ready_repo, failed_repo])
        session.add_all(
            [
                FeatureRepo(feature_id=feature.id, repo_id=ready_repo.id),
                FeatureRepo(feature_id=feature.id, repo_id=failed_repo.id),
            ]
        )
        await session.commit()
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_features_tool_returns_active_feature_catalog(db_factory) -> None:  # type: ignore[no-untyped-def]
    result = await list_features_tool(db_factory).handler({"limit": 20}, _CTX)

    assert result["summary"] == "返回 1 个活跃特性"
    assert result["features"] == [
        {
            "feature_id": 1,
            "name": "小米",
            "slug": "xiaomi",
            "description": "小米病历和治疗记录",
            "summary": "肿瘤切除后的复诊趋势",
            "wiki_path": "./wiki/xiaomi",
            "ready_repo_count": 1,
            "binding_required_before_use": (
                "If you decide this feature is relevant and will use its wiki, "
                "reports, repositories, or metadata to answer the conversation, "
                "call codeask_bind_session_features with this feature_id first."
            ),
        }
    ]
    assert "codeask_bind_session_features" in result["session_binding_policy"]


@pytest.mark.asyncio
async def test_get_feature_info_tool_returns_wiki_entries_and_repos(db_factory) -> None:  # type: ignore[no-untyped-def]
    result = await get_feature_info_tool(db_factory).handler({"feature_id": 1}, _CTX)

    assert result["feature"]["name"] == "小米"
    assert result["wiki"]["workspace_path"] == "./wiki/xiaomi"
    assert result["wiki"]["entries"] == [
        {
            "node_id": 1,
            "type": "folder",
            "name": "知识库",
            "path": "knowledge-base",
            "system_role": "knowledge_base",
        },
        {
            "node_id": 2,
            "type": "document",
            "name": "小米病历",
            "path": "knowledge-base/小米病历",
            "system_role": None,
        },
    ]
    assert result["repositories"] == [
        {
            "repo_id": "repo_ready",
            "name": "anything-llm",
            "status": "ready",
            "source": "local_dir",
        }
    ]


@pytest.mark.asyncio
async def test_list_feature_repos_can_include_unready_repos(db_factory) -> None:  # type: ignore[no-untyped-def]
    result = await list_feature_repos_tool(db_factory).handler(
        {"feature_id": 1, "include_unready": True},
        _CTX,
    )

    assert [repo["repo_id"] for repo in result["repositories"]] == [
        "repo_ready",
        "repo_failed",
    ]
    assert result["repositories"][1]["status"] == "failed"


def test_build_feature_tools_has_simple_json_schemas(db_factory) -> None:  # type: ignore[no-untyped-def]
    tools = build_feature_tools(db_factory)

    assert [tool.name for tool in tools] == [
        "list_features",
        "get_feature_info",
        "list_feature_repos",
    ]
    assert tools[0].input_schema["type"] == "object"
