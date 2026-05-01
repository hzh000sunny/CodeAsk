"""Authentication and role contract tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_auth_me_defaults_to_self_report_member(client: AsyncClient) -> None:
    response = await client.get("/api/auth/me", headers={"X-Subject-Id": "alice@device"})

    assert response.status_code == 200
    assert response.json() == {
        "subject_id": "alice@device",
        "display_name": "alice@device",
        "role": "member",
        "authenticated": False,
    }


@pytest.mark.asyncio
async def test_admin_login_sets_role_cookie(client: AsyncClient) -> None:
    denied = await client.post("/api/auth/admin/login", json={"password": "wrong"})
    assert denied.status_code == 401

    wrong_user = await client.post(
        "/api/auth/admin/login",
        json={"username": "root", "password": "admin"},
    )
    assert wrong_user.status_code == 401

    logged_in = await client.post(
        "/api/auth/admin/login",
        json={"username": "admin", "password": "admin"},
    )
    assert logged_in.status_code == 200, logged_in.text
    assert logged_in.json()["role"] == "admin"

    me = await client.get("/api/auth/me", headers={"X-Subject-Id": "alice@device"})
    assert me.status_code == 200
    assert me.json()["subject_id"] == "admin"
    assert me.json()["role"] == "admin"
    assert me.json()["authenticated"] is True

    logged_out = await client.post("/api/auth/logout")
    assert logged_out.status_code == 204

    after_logout = await client.get("/api/auth/me", headers={"X-Subject-Id": "alice@device"})
    assert after_logout.json()["role"] == "member"
