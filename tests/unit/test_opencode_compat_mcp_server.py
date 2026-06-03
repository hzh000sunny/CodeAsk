from __future__ import annotations

import pytest

from codeask.agent.opencode_compat.mcp.server import (
    MCPAuthError,
    MCPRequestContext,
    MCPTool,
    OpenCodeMCPServer,
)


async def _echo(arguments: dict[str, object], ctx: MCPRequestContext) -> str:
    assert ctx.session_id == "sess_1"
    return f"ECHO:{arguments['text']}"


async def _structured(arguments: dict[str, object], ctx: MCPRequestContext) -> dict[str, object]:
    return {"summary": "ok", "session_id": ctx.session_id, "data": {"value": arguments["value"]}}


@pytest.mark.asyncio
async def test_mcp_server_handles_initialize_tools_list_and_call() -> None:
    server = OpenCodeMCPServer(
        token_resolver=lambda session_id: "token-1",
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

    initialized = await server.handle_json_rpc(
        session_id="sess_1",
        authorization="Bearer token-1",
        payload={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    tools = await server.handle_json_rpc(
        session_id="sess_1",
        authorization="Bearer token-1",
        payload={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    called = await server.handle_json_rpc(
        session_id="sess_1",
        authorization="Bearer token-1",
        payload={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "echo_tool", "arguments": {"text": "hello"}},
        },
    )

    assert initialized is not None
    assert tools is not None
    assert called is not None
    assert initialized["result"]["serverInfo"] == {"name": "CodeAsk", "version": "v1.0.4"}
    assert tools["result"]["tools"][0]["name"] == "echo_tool"
    assert called == {
        "jsonrpc": "2.0",
        "id": 3,
        "result": {"content": [{"type": "text", "text": "ECHO:hello"}]},
    }


@pytest.mark.asyncio
async def test_mcp_server_rejects_cross_session_token() -> None:
    server = OpenCodeMCPServer(token_resolver=lambda session_id: "token-1", tools=[])

    with pytest.raises(MCPAuthError):
        await server.handle_json_rpc(
            session_id="sess_1",
            authorization="Bearer wrong",
            payload={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )


@pytest.mark.asyncio
async def test_mcp_server_returns_structured_tool_output_as_json_text() -> None:
    server = OpenCodeMCPServer(
        token_resolver=lambda session_id: "token-1",
        tools=[
            MCPTool(
                name="structured_tool",
                description="Return structured data",
                input_schema={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
                handler=_structured,
            )
        ],
    )

    called = await server.handle_json_rpc(
        session_id="sess_1",
        authorization="Bearer token-1",
        payload={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "structured_tool", "arguments": {"value": "hello"}},
        },
    )

    assert called is not None
    assert called["result"]["content"][0]["text"] == (
        '{"summary":"ok","session_id":"sess_1","data":{"value":"hello"}}'
    )
