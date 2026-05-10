"""Auth and authorization audit API tests."""

from pathlib import Path

import pytest
from httpx import AsyncClient

from codeask.db.models import SystemSetting


async def _login_admin(client: AsyncClient) -> None:
    response = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert response.status_code == 200, response.text


async def _create_member(client: AsyncClient, username: str) -> str:
    response = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "secret1"},
    )
    assert response.status_code == 200, response.text
    user_id = response.json()["subject_id"]
    await client.post("/api/auth/logout")
    return str(user_id)


async def _create_feature(client: AsyncClient, slug: str) -> int:
    await _login_admin(client)
    response = await client.post("/api/features", json={"name": slug, "slug": slug})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


@pytest.mark.asyncio
async def test_audit_log_is_admin_only(client: AsyncClient) -> None:
    anonymous = await client.get("/api/audit-log")
    assert anonymous.status_code == 403

    await _create_member(client, "audit-viewer")
    member_login = await client.post(
        "/api/auth/login",
        json={"username": "audit-viewer", "password": "secret1"},
    )
    assert member_login.status_code == 200, member_login.text
    member = await client.get("/api/audit-log")
    assert member.status_code == 403
    await client.post("/api/auth/logout")

    await _login_admin(client)
    admin = await client.get("/api/audit-log")
    assert admin.status_code == 200, admin.text
    assert admin.json()["entries"] != []


@pytest.mark.asyncio
async def test_login_failure_and_auto_register_write_audit(client: AsyncClient) -> None:
    registered = await client.post(
        "/api/auth/login",
        json={"username": "audit-login-user", "password": "secret1"},
    )
    assert registered.status_code == 200, registered.text
    await client.post("/api/auth/logout")

    failed = await client.post(
        "/api/auth/login",
        json={"username": "audit-login-user", "password": "wrongpw"},
    )
    assert failed.status_code == 401

    await _login_admin(client)
    response = await client.get("/api/audit-log", params={"action": "auth.login"})
    assert response.status_code == 200, response.text
    entries = response.json()["entries"]
    assert any(entry["entity_id"] == "audit-login-user" for entry in entries)
    assert any(
        entry["entity_id"] == "audit-login-user" and entry["to_status"] == "failed"
        for entry in entries
    )

    registered_entries = await client.get("/api/audit-log", params={"action": "auth.register"})
    assert registered_entries.status_code == 200, registered_entries.text
    assert any(
        entry["entity_id"] == "audit-login-user" for entry in registered_entries.json()["entries"]
    )


@pytest.mark.asyncio
async def test_add_feature_admin_writes_audit(client: AsyncClient) -> None:
    feature_id = await _create_feature(client, "audit-feature-admin")
    await client.post("/api/auth/logout")
    user_id = await _create_member(client, "audit-feature-user")

    await _login_admin(client)
    response = await client.post(f"/api/features/{feature_id}/admins", json={"user_id": user_id})
    assert response.status_code == 201, response.text

    audit = await client.get("/api/audit-log", params={"action": "feature_admin.add"})
    assert audit.status_code == 200, audit.text
    assert any(entry["entity_id"] == f"{feature_id}:{user_id}" for entry in audit.json()["entries"])


@pytest.mark.asyncio
async def test_attachment_disabled_upload_rejection_writes_audit(
    client: AsyncClient,
    app,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    created = await client.post(
        "/api/sessions",
        json={"title": "audit attachment"},
        headers={"X-Subject-Id": "client_audit_attach"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    async with app.state.session_factory() as session:
        session.add(
            SystemSetting(
                key="session_attachments_enabled",
                value=False,
            )
        )
        await session.commit()

    upload_path = tmp_path / "audit.log"
    upload_path.write_text("ERR_AUDIT", encoding="utf-8")
    with upload_path.open("rb") as file:
        denied = await client.post(
            f"/api/sessions/{session_id}/attachments",
            data={"kind": "log"},
            files={"file": ("audit.log", file, "text/plain")},
            headers={"X-Subject-Id": "client_audit_attach"},
        )
    assert denied.status_code == 403

    await _login_admin(client)
    audit = await client.get(
        "/api/audit-log",
        params={"action": "session_attachment.upload_denied", "entity_id": session_id},
    )
    assert audit.status_code == 200, audit.text
    assert audit.json()["entries"][0]["subject_id"] == "client_audit_attach"
