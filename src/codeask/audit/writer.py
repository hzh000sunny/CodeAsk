"""Safe audit-log writer for auth and authorization events."""

from sqlalchemy.ext.asyncio import AsyncSession

from codeask.metrics.audit import record_audit_log


async def write_audit(
    session: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    subject_id: str,
    result: str = "success",
    reason: str | None = None,
) -> str:
    """Write one sanitized audit row.

    The current audit table stores status transitions. For auth/authz events,
    ``from_status`` carries a short reason and ``to_status`` carries result.
    Do not pass secrets, raw user input content, API keys, or passwords here.
    """

    return await record_audit_log(
        session,
        entity_type=entity_type[:64],
        entity_id=entity_id[:64],
        action=action[:64],
        subject_id=subject_id[:128],
        from_status=reason[:32] if reason else None,
        to_status=result[:32] if result else None,
    )
