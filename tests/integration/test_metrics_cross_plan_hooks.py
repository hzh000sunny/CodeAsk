"""Cross-plan audit hooks write audit_log rows for report lifecycle events."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import AuditLog


@pytest.mark.asyncio
async def test_report_verify_creates_audit_row(
    client: AsyncClient,
    app,
    seeded_report_draft: int,
) -> None:
    response = await client.post(
        f"/api/reports/{seeded_report_draft}/verify",
        headers={"X-Subject-Id": "alice@dev"},
    )

    assert response.status_code == 200, response.text

    async with app.state.session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.entity_type == "report",
                        AuditLog.entity_id == str(seeded_report_draft),
                        AuditLog.action == "verify",
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(rows) == 1
    assert rows[0].from_status == "draft"
    assert rows[0].to_status == "verified"
    assert rows[0].subject_id == "alice@dev"


@pytest.mark.asyncio
async def test_report_unverify_creates_audit_row(
    client: AsyncClient,
    app,
    seeded_report_verified: int,
) -> None:
    response = await client.post(
        f"/api/reports/{seeded_report_verified}/unverify",
        headers={"X-Subject-Id": "bob@dev"},
    )

    assert response.status_code == 200, response.text

    async with app.state.session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.entity_type == "report",
                        AuditLog.entity_id == str(seeded_report_verified),
                        AuditLog.action == "unverify",
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(rows) == 1
    assert rows[0].from_status == "verified"
    assert rows[0].to_status == "draft"
    assert rows[0].subject_id == "bob@dev"


def report_gate_metadata() -> dict[str, Any]:
    return {
        "evidence": [{"type": "log", "summary": "traceback shows ERR_ORDER_EMPTY"}],
        "applicability": "orders created after checkout",
        "recommended_fix": "guard empty order context",
    }
