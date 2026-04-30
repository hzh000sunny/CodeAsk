"""Audit log writer stub for wiki actions."""

from typing import Any

import structlog


class AuditWriter:
    """Stub writer that emits structured audit events to logs."""

    def __init__(self) -> None:
        self._log = structlog.get_logger("codeask.audit")

    def write(self, event: str, payload: dict[str, Any], *, subject_id: str) -> None:
        self._log.info("audit_log", audit_event=event, subject_id=subject_id, **payload)
