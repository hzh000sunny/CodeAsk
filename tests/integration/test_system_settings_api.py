"""System settings API tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_system_settings_are_admin_only_and_update_attachment_gate(
    client: AsyncClient,
) -> None:
    anonymous = await client.get("/api/system-settings")
    assert anonymous.status_code == 403

    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200, login.text

    initial = await client.get("/api/system-settings")
    assert initial.status_code == 200, initial.text
    assert initial.json() == {"session_attachments_enabled": True}

    updated = await client.patch(
        "/api/system-settings",
        json={"session_attachments_enabled": False},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json() == {"session_attachments_enabled": False}

    reloaded = await client.get("/api/system-settings")
    assert reloaded.status_code == 200, reloaded.text
    assert reloaded.json() == {"session_attachments_enabled": False}
