"""GET /api/audit-log filters audit rows by entity and returns newest first."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from codeask.metrics.audit import record_audit_log


@pytest.mark.asyncio
async def test_audit_log_filters_and_orders(client: AsyncClient, app) -> None:
    base = datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC)
    async with app.state.session_factory() as session:
        await record_audit_log(
            session,
            entity_type="report",
            entity_id="42",
            action="verify",
            from_status="draft",
            to_status="verified",
            subject_id="alice@dev",
            at=base,
        )
        await record_audit_log(
            session,
            entity_type="report",
            entity_id="42",
            action="unverify",
            from_status="verified",
            to_status="draft",
            subject_id="bob@dev",
            at=base + timedelta(hours=2),
        )
        await record_audit_log(
            session,
            entity_type="report",
            entity_id="99",
            action="verify",
            subject_id="alice@dev",
            at=base + timedelta(hours=3),
        )
        await session.commit()

    response = await client.get(
        "/api/audit-log",
        params={"entity_type": "report", "entity_id": "42"},
    )

    assert response.status_code == 200, response.text
    entries = response.json()["entries"]
    assert [entry["action"] for entry in entries] == ["unverify", "verify"]
    assert entries[0]["from_status"] == "verified"
    assert entries[0]["to_status"] == "draft"


@pytest.mark.asyncio
async def test_audit_log_requires_filters(client: AsyncClient) -> None:
    response = await client.get("/api/audit-log")
    assert response.status_code == 422
