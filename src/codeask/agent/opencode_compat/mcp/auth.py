"""Session-scoped MCP token helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac


def make_session_mcp_token(data_key: str, session_id: str) -> str:
    digest = hmac.new(
        data_key.encode("utf-8"),
        f"opencode-mcp:{session_id}".encode(),
        hashlib.sha256,
    ).digest()
    token = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"mcp_{token}"
