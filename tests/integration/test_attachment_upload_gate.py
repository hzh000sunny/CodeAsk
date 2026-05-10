"""Attachment upload global gate tests."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from codeask.db.models import SystemSetting


async def _create_session(client: AsyncClient, subject: str = "guest-attachment") -> str:
    response = await client.post(
        "/api/sessions",
        json={"title": "attachment gate"},
        headers={"X-Subject-Id": subject},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _set_attachment_gate(app: FastAPI, enabled: bool) -> None:
    async with app.state.session_factory() as session:
        row = await session.get(SystemSetting, "session_attachments_enabled")
        if row is None:
            row = SystemSetting(key="session_attachments_enabled", value=enabled)
            session.add(row)
        else:
            row.value = enabled
        await session.commit()


async def _upload_log(client: AsyncClient, session_id: str, subject: str = "guest-attachment"):
    return await client.post(
        f"/api/sessions/{session_id}/attachments",
        files={"file": ("app.log", b"ERROR order failed", "text/plain")},
        data={"kind": "log"},
        headers={"X-Subject-Id": subject},
    )


@pytest.mark.asyncio
async def test_attachment_upload_enabled_by_default_for_anonymous_user(
    client: AsyncClient,
) -> None:
    session_id = await _create_session(client)

    response = await _upload_log(client, session_id)

    assert response.status_code == 201, response.text
    assert response.json()["display_name"] == "app.log"


@pytest.mark.asyncio
async def test_attachment_upload_disabled_blocks_anonymous_and_logged_in_users(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    await _set_attachment_gate(app, False)
    anonymous_session_id = await _create_session(client, "anonymous-attachment")

    anonymous = await _upload_log(client, anonymous_session_id, "anonymous-attachment")
    assert anonymous.status_code == 403
    assert anonymous.json()["detail"] == "该功能已被禁用"

    login = await client.post(
        "/api/auth/login",
        json={"username": "attachment-user", "password": "secret1"},
    )
    assert login.status_code == 200, login.text
    user_session = await client.post("/api/sessions", json={"title": "attachment user"})
    assert user_session.status_code == 201, user_session.text

    logged_in = await client.post(
        f"/api/sessions/{user_session.json()['id']}/attachments",
        files={"file": ("user.log", b"ERROR user failed", "text/plain")},
        data={"kind": "log"},
    )
    assert logged_in.status_code == 403
    assert logged_in.json()["detail"] == "该功能已被禁用"


@pytest.mark.asyncio
async def test_attachment_gate_does_not_block_existing_attachment_updates(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    session_id = await _create_session(client)
    uploaded = await _upload_log(client, session_id)
    assert uploaded.status_code == 201, uploaded.text
    attachment_id = uploaded.json()["id"]

    await _set_attachment_gate(app, False)

    renamed = await client.patch(
        f"/api/sessions/{session_id}/attachments/{attachment_id}",
        json={"display_name": "renamed.log"},
        headers={"X-Subject-Id": "guest-attachment"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["display_name"] == "renamed.log"

    deleted = await client.delete(
        f"/api/sessions/{session_id}/attachments/{attachment_id}",
        headers={"X-Subject-Id": "guest-attachment"},
    )
    assert deleted.status_code == 204
