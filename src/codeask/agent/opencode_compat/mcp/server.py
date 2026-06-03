"""Minimal StreamableHTTP MCP JSON-RPC handler for opencode."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast


class MCPAuthError(PermissionError):
    """Raised when a MCP request has an invalid session token."""


TokenResolver = Callable[[str], str | None]


@dataclass(frozen=True)
class MCPRequestContext:
    session_id: str


ToolHandler = Callable[[dict[str, Any], MCPRequestContext], Awaitable[str | dict[str, Any]]]


@dataclass(frozen=True)
class MCPTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler

    def to_descriptor(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


class OpenCodeMCPServer:
    """JSON-RPC method handler used by the FastAPI MCP route."""

    def __init__(self, *, token_resolver: TokenResolver, tools: list[MCPTool]) -> None:
        self._token_resolver = token_resolver
        self._tools = {tool.name: tool for tool in tools}

    async def handle_json_rpc(
        self,
        *,
        session_id: str,
        authorization: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        self._verify_token(session_id, authorization)
        method = payload.get("method")
        request_id = payload.get("id")

        if method == "notifications/initialized":
            return None
        if method == "initialize":
            return _result(
                request_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "CodeAsk", "version": "v1.0.4"},
                },
            )
        if method == "tools/list":
            return _result(
                request_id,
                {"tools": [tool.to_descriptor() for tool in self._tools.values()]},
            )
        if method == "tools/call":
            return await self._call_tool(
                request_id,
                payload.get("params"),
                MCPRequestContext(session_id=session_id),
            )
        return _error(request_id, -32601, f"method not found: {method}")

    async def _call_tool(
        self,
        request_id: object,
        params: object,
        ctx: MCPRequestContext,
    ) -> dict[str, Any]:
        if not isinstance(params, dict):
            return _error(request_id, -32602, "tools/call params must be an object")
        params_data = cast(dict[str, object], params)
        name = params_data.get("name")
        arguments = params_data.get("arguments")
        if not isinstance(name, str) or name not in self._tools:
            return _error(request_id, -32602, f"unknown tool: {name}")
        if not isinstance(arguments, dict):
            return _error(request_id, -32602, "tool arguments must be a JSON object")

        try:
            output = await self._tools[name].handler(cast(dict[str, Any], arguments), ctx)
        except Exception as exc:  # pragma: no cover - defensive conversion
            return _error(request_id, -32000, str(exc))

        text = (
            json.dumps(output, ensure_ascii=False, separators=(",", ":"))
            if isinstance(output, dict)
            else output
        )
        result: dict[str, Any] = {"content": [{"type": "text", "text": str(text)}]}
        if _is_tool_error_output(output):
            result["isError"] = True
        return _result(request_id, result)

    def _verify_token(self, session_id: str, authorization: str | None) -> None:
        expected = self._token_resolver(session_id)
        if not expected:
            raise MCPAuthError("mcp token not found")
        if authorization != f"Bearer {expected}":
            raise MCPAuthError("invalid mcp token")


def _result(request_id: object, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _is_tool_error_output(output: object) -> bool:
    if not isinstance(output, dict):
        return False
    output_data = cast(dict[str, Any], output)
    error = output_data.get("error")
    return isinstance(error, str) and bool(error)


def _error(request_id: object, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
