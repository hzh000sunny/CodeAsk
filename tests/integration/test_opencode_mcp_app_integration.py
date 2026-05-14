from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from codeask.agent.opencode_compat.mcp.auth import make_session_mcp_token
from codeask.db.models import Feature


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
