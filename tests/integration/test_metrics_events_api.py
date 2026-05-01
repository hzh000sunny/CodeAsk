"""POST /api/events persists whitelisted frontend events."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import FrontendEvent


@pytest.mark.asyncio
async def test_event_writes_payload(client: AsyncClient, app) -> None:
    response = await client.post(
        "/api/events",
        json={
            "event_type": "force_deeper_investigation",
            "session_id": "sess_1",
            "payload": {"sufficiency_verdict": "sufficient", "user_overrode": True},
        },
        headers={"X-Subject-Id": "bob@dev"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["id"].startswith("ev_")

    async with app.state.session_factory() as session:
        row = (await session.execute(select(FrontendEvent))).scalar_one()

    assert row.event_type == "force_deeper_investigation"
    assert row.session_id == "sess_1"
    assert row.subject_id == "bob@dev"
    assert row.payload["user_overrode"] is True


@pytest.mark.asyncio
async def test_event_rejects_off_whitelist(client: AsyncClient) -> None:
    response = await client.post(
        "/api/events",
        json={"event_type": "totally_unknown_event", "payload": {}},
    )
    assert response.status_code == 422
