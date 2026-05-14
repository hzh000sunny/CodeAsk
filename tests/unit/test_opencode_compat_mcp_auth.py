from __future__ import annotations

from codeask.agent.opencode_compat.mcp.auth import make_session_mcp_token


def test_session_mcp_token_is_stable_and_session_scoped() -> None:
    first = make_session_mcp_token("data-key", "sess_1")
    second = make_session_mcp_token("data-key", "sess_1")
    other_session = make_session_mcp_token("data-key", "sess_2")
    other_key = make_session_mcp_token("other-key", "sess_1")

    assert first == second
    assert first != other_session
    assert first != other_key
    assert first.startswith("mcp_")
    assert len(first) >= 40
