"""Public audit-log writer. Idempotent at second resolution."""

import hashlib
from datetime import UTC, datetime

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models.audit_log import AuditLog


def _stable_id(
    entity_type: str,
    entity_id: str,
    action: str,
    at: datetime,
    subject_id: str,
) -> str:
    digest = hashlib.sha1(
        f"{entity_type}|{entity_id}|{action}|{at.isoformat(timespec='seconds')}|{subject_id}".encode()
    ).hexdigest()
    return f"al_{digest[:24]}"


async def record_audit_log(
    session: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    subject_id: str,
    from_status: str | None = None,
    to_status: str | None = None,
    at: datetime | None = None,
) -> str:
    """Write one audit row and return its stable id.

    Same entity/action/actor at the same second yields the same id. SQLite
    ``ON CONFLICT DO NOTHING`` keeps duplicate writes from raising.
    """

    when = (at or datetime.now(UTC)).replace(microsecond=0)
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    row_id = _stable_id(entity_type, entity_id, action, when, subject_id)
    stmt = (
        sqlite_insert(AuditLog)
        .values(
            id=row_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            subject_id=subject_id,
            at=when,
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )
    await session.execute(stmt)
    return row_id
