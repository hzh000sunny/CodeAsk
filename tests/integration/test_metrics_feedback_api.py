"""POST /api/feedback persists explicit user feedback."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import Feedback


@pytest.mark.asyncio
async def test_post_feedback_creates_row(
    client: AsyncClient,
    app,
    seeded_session_turn: str,
) -> None:
    response = await client.post(
        "/api/feedback",
        json={
            "session_turn_id": seeded_session_turn,
            "feedback": "solved",
            "note": "helped",
        },
        headers={"X-Subject-Id": "alice@dev"},
    )

    assert response.status_code == 201, response.text
    assert response.json() == {"ok": True}

    async with app.state.session_factory() as session:
        rows = (await session.execute(select(Feedback))).scalars().all()

    assert len(rows) == 1
    assert rows[0].session_turn_id == seeded_session_turn
    assert rows[0].feedback == "solved"
    assert rows[0].note == "helped"
    assert rows[0].subject_id == "alice@dev"


@pytest.mark.asyncio
async def test_post_feedback_rejects_unknown_verdict(client: AsyncClient) -> None:
    response = await client.post(
        "/api/feedback",
        json={"session_turn_id": "turn_missing", "feedback": "ok-ish"},
    )
    assert response.status_code == 422
