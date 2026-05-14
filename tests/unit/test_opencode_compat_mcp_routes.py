from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeask.agent.opencode_compat.mcp.server import MCPRequestContext, MCPTool, OpenCodeMCPServer
from codeask.api.opencode_mcp import router as opencode_mcp_router


async def _echo(arguments: dict[str, object], ctx: MCPRequestContext) -> str:
    assert ctx.session_id == "sess_1"
    return f"ECHO:{arguments['text']}"


def _client() -> TestClient:
    app = FastAPI()
    app.state.opencode_mcp_server = OpenCodeMCPServer(
        token_resolver=lambda session_id: f"token-{session_id}",
        tools=[
            MCPTool(
                name="echo_tool",
                description="Echo text",
                input_schema={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
                handler=_echo,
            )
        ],
    )
    app.include_router(opencode_mcp_router, prefix="/api")
    return TestClient(app)


def test_opencode_mcp_route_exposes_json_rpc_tools() -> None:
    client = _client()

    initialize = client.post(
        "/api/agent-mcp/sess_1",
        headers={"Authorization": "Bearer token-sess_1"},
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    tools = client.post(
        "/api/agent-mcp/sess_1",
        headers={"Authorization": "Bearer token-sess_1"},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    called = client.post(
        "/api/agent-mcp/sess_1",
        headers={"Authorization": "Bearer token-sess_1"},
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "echo_tool", "arguments": {"text": "hello"}},
        },
    )

    assert initialize.status_code == 200
    assert initialize.json()["result"]["serverInfo"]["name"] == "CodeAsk"
    assert tools.status_code == 200
    assert tools.json()["result"]["tools"][0]["name"] == "echo_tool"
    assert called.status_code == 200
    assert called.json()["result"]["content"][0]["text"] == "ECHO:hello"


def test_opencode_mcp_route_rejects_cross_session_token() -> None:
    response = _client().post(
        "/api/agent-mcp/sess_1",
        headers={"Authorization": "Bearer token-sess_2"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid mcp token"}


def test_opencode_mcp_route_accepts_initialized_notification() -> None:
    response = _client().post(
        "/api/agent-mcp/sess_1",
        headers={"Authorization": "Bearer token-sess_1"},
        json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
    )

    assert response.status_code == 202
    assert response.content == b""
