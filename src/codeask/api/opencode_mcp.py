"""OpenCode remote MCP endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status

from codeask.agent.opencode_compat.mcp.server import MCPAuthError, OpenCodeMCPServer

router = APIRouter(prefix="/agent-mcp")


@router.post("/{session_id}", response_model=None)
async def handle_opencode_mcp(session_id: str, request: Request) -> Response | dict[str, Any]:
    server = getattr(request.app.state, "opencode_mcp_server", None)
    if not isinstance(server, OpenCodeMCPServer):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="opencode MCP server is not available",
        )

    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="JSON-RPC payload must be an object",
        )

    try:
        result = await server.handle_json_rpc(
            session_id=session_id,
            authorization=request.headers.get("authorization"),
            payload=payload,
        )
    except MCPAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    if result is None:
        return Response(status_code=status.HTTP_202_ACCEPTED)
    return result
