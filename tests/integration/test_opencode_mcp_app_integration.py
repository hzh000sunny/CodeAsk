from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from codeask.agent.opencode_compat.mcp.auth import make_session_mcp_token
from codeask.agent.opencode_compat.sessions import ExternalAgentSessionCreate
from codeask.agent.opencode_compat.workspace import OpenCodeWorkspaceManager
from codeask.code_index.cloner import RepoCloner
from codeask.db.models import Feature, Repo, Session


@pytest.mark.asyncio
async def test_app_registers_opencode_mcp_server_with_feature_tools(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    async with app.state.session_factory() as session:
        session.add(
            Feature(
                name="AnythingLLM",
                slug="anything-llm",
                description="AnythingLLM 源码分析",
                owner_subject_id="admin",
            )
        )
        await session.commit()

    token = make_session_mcp_token(app.state.settings.data_key, "sess_mcp_app")
    response = await client.post(
        "/api/agent-mcp/sess_mcp_app",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "list_features", "arguments": {}},
        },
    )

    assert response.status_code == 200
    payload = json.loads(response.json()["result"]["content"][0]["text"])
    assert payload["features"][0]["name"] == "AnythingLLM"

    listed = await client.post(
        "/api/agent-mcp/sess_mcp_app",
        headers={"Authorization": f"Bearer {token}"},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    assert listed.status_code == 200
    tool_names = [tool["name"] for tool in listed.json()["result"]["tools"]]
    assert "prepare_worktree" in tool_names
    assert "search_reports" not in tool_names
    assert "read_report" not in tool_names
    assert hasattr(app.state, "opencode_compat")


@pytest.mark.asyncio
async def test_opencode_mcp_tools_list_matches_v104_contract(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    token = make_session_mcp_token(app.state.settings.data_key, "sess_mcp_schema")

    listed = await client.post(
        "/api/agent-mcp/sess_mcp_schema",
        headers={"Authorization": f"Bearer {token}"},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )

    assert listed.status_code == 200
    tools = listed.json()["result"]["tools"]
    assert [tool["name"] for tool in tools] == [
        "list_features",
        "get_feature_info",
        "list_feature_repos",
        "bind_session_features",
        "list_session_attachments",
        "read_session_attachment",
        "prepare_worktree",
    ]
    schemas = {tool["name"]: tool["inputSchema"] for tool in tools}
    assert set(schemas["list_features"]["properties"]) == {"limit", "query"}
    assert set(schemas["get_feature_info"]["properties"]) == {
        "feature_id",
        "slug",
        "name",
    }
    assert set(schemas["list_feature_repos"]["properties"]) == {
        "feature_id",
        "include_unready",
        "query",
        "limit",
    }
    assert schemas["bind_session_features"]["required"] == ["feature_ids"]
    assert schemas["list_session_attachments"]["properties"] == {}
    assert set(schemas["read_session_attachment"]["properties"]) == {
        "attachment_id",
        "max_chars",
    }
    assert set(schemas["prepare_worktree"]["properties"]) == {
        "repo_id",
        "repo_name",
        "ref",
        "reason",
    }
    for schema in schemas.values():
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False


@pytest.mark.asyncio
async def test_opencode_mcp_rejects_cross_session_token_at_app_boundary(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    token = make_session_mcp_token(app.state.settings.data_key, "sess_allowed")

    response = await client.post(
        "/api/agent-mcp/sess_other",
        headers={"Authorization": f"Bearer {token}"},
        json={"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid mcp token"}


@pytest.mark.asyncio
async def test_opencode_mcp_prepare_worktree_supports_plain_local_dir_repo(
    app: FastAPI,
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    source = tmp_path / "plain-local"
    source.mkdir()
    (source / "README.md").write_text("plain local source\n", encoding="utf-8")
    (source / "server").mkdir()
    (source / "server" / "app.py").write_text("print('local-dir')\n", encoding="utf-8")

    repo_root = Path(app.state.settings.data_dir) / "repos"
    repo_id = "repo_plain_local"
    bare = repo_root / repo_id / "bare"
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=Path(app.state.settings.data_dir),
        wiki_workspace_root=Path(app.state.settings.data_dir) / "wiki_workspace" / "current",
    )
    workspace = workspace_manager.prepare_workspace("sess_local_dir")
    async with app.state.session_factory() as session:
        session.add(Session(id="sess_local_dir", title="local", created_by_subject_id="subject-1"))
        session.add(
            Repo(
                id=repo_id,
                name="Plain Local Repo",
                source=Repo.SOURCE_LOCAL_DIR,
                url=None,
                local_path=str(source),
                bare_path=str(bare),
                status=Repo.STATUS_REGISTERED,
            )
        )
        await session.commit()

    cloner = RepoCloner(app.state.session_factory, clone_timeout_seconds=30)
    await asyncio.to_thread(cloner.run_clone, repo_id)
    await app.state.opencode_session_store.upsert(
        ExternalAgentSessionCreate(
            session_id="sess_local_dir",
            external_session_key="ses_local",
            session_dir=str(workspace.session_dir),
            workspace_dir=str(workspace.workspace_dir),
            server_url="http://127.0.0.1:4100",
            port=4100,
            pid=123,
            config_hash="hash",
            config_json={},
        )
    )

    token = make_session_mcp_token(app.state.settings.data_key, "sess_local_dir")
    response = await client.post(
        "/api/agent-mcp/sess_local_dir",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "prepare_worktree",
                "arguments": {"repo_name": "Plain Local Repo", "reason": "local dir E2E"},
            },
        },
    )

    assert response.status_code == 200, response.text
    payload = json.loads(response.json()["result"]["content"][0]["text"])
    assert payload["repository"]["repo_id"] == repo_id
    assert payload["workspace_relative_path"] == "repos/Plain_Local_Repo"
    linked_file = workspace.workspace_dir / payload["workspace_relative_path"] / "server" / "app.py"
    assert linked_file.read_text(encoding="utf-8") == "print('local-dir')\n"
