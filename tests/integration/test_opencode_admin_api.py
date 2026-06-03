"""Integration tests for the OpenCode tool-permission admin API."""

import pytest

from codeask.api.opencode_admin import (
    PERMISSIONS_KEY,
    load_opencode_tool_permissions,
)
from codeask.db.models import SystemSetting


async def _login_admin(client) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_opencode_permissions_requires_admin(client) -> None:
    response = await client.get("/api/admin/opencode/permissions")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_opencode_permissions_get_defaults(client) -> None:
    await _login_admin(client)

    response = await client.get("/api/admin/opencode/permissions")
    assert response.status_code == 200
    body = response.json()

    assert body["bash"] == {"mode": "deny", "patterns": []}
    assert body["tools"]["read"] == "allow"
    assert "bash" not in body["tools"]
    assert body["tools"]["edit"] == "deny"
    assert "openviking_enabled" in body
    # Catalog drives the UI rows and bash suggestions.
    catalog_keys = {item["key"] for item in body["catalog"]["tools"]}
    assert {"read", "grep", "glob", "webfetch", "edit", "write"}.issubset(catalog_keys)
    assert "git status" in body["catalog"]["bash_suggestions"]
    assert body["defaults"]["bash"]["mode"] == "deny"


@pytest.mark.asyncio
async def test_opencode_permissions_put_persists(client, app) -> None:
    await _login_admin(client)

    payload = {
        "tools": {"read": "allow", "edit": "allow", "write": "deny", "webfetch": "allow"},
        "bash": {"mode": "deny", "patterns": []},
    }
    response = await client.put("/api/admin/opencode/permissions", json=payload)
    assert response.status_code == 200
    assert response.json()["tools"]["edit"] == "allow"

    # Re-read reflects the persisted value.
    again = await client.get("/api/admin/opencode/permissions")
    assert again.json()["tools"]["edit"] == "allow"
    assert again.json()["tools"]["webfetch"] == "allow"

    # The session-init loader sees the same configuration.
    perms = await load_opencode_tool_permissions(app.state.session_factory)
    assert perms.tools["edit"] == "allow"
    block = perms.to_permission_block(openviking_enabled=False)
    assert block["edit"] == "allow"
    assert block["webfetch"] == "allow"


@pytest.mark.asyncio
async def test_opencode_permissions_put_bash_whitelist(client, app) -> None:
    await _login_admin(client)

    payload = {
        "tools": {},
        "bash": {"mode": "whitelist", "patterns": ["  git * ", "git *", "ls *"]},
    }
    response = await client.put("/api/admin/opencode/permissions", json=payload)
    assert response.status_code == 200
    body = response.json()
    # De-duplicated and trimmed.
    assert body["bash"] == {"mode": "whitelist", "patterns": ["git *", "ls *"]}

    perms = await load_opencode_tool_permissions(app.state.session_factory)
    assert perms.to_permission_block(openviking_enabled=False)["bash"] == {
        "*": "deny",
        "git *": "allow",
        "ls *": "allow",
    }


@pytest.mark.asyncio
async def test_opencode_permissions_put_rejects_too_many_patterns(client) -> None:
    await _login_admin(client)

    payload = {
        "tools": {},
        "bash": {"mode": "whitelist", "patterns": [f"cmd-{i} *" for i in range(65)]},
    }
    response = await client.put("/api/admin/opencode/permissions", json=payload)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_opencode_permissions_put_rejects_unknown_tool(client) -> None:
    await _login_admin(client)

    payload = {
        "tools": {"definitely_not_a_tool": "allow"},
        "bash": {"mode": "deny", "patterns": []},
    }
    response = await client.put("/api/admin/opencode/permissions", json=payload)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_opencode_permissions_put_writes_audit(client, app) -> None:
    await _login_admin(client)

    payload = {"tools": {}, "bash": {"mode": "allow", "patterns": []}}
    response = await client.put("/api/admin/opencode/permissions", json=payload)
    assert response.status_code == 200

    async with app.state.session_factory() as session:
        row = await session.get(SystemSetting, PERMISSIONS_KEY)
    assert row is not None
    assert row.value["bash"]["mode"] == "allow"
