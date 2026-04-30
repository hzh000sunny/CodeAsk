"""Tests for audit writer stub."""

import json

from codeask.logging_config import configure_logging
from codeask.wiki.audit import AuditWriter


def test_audit_writer_emits_event(capsys) -> None:  # type: ignore[no-untyped-def]
    configure_logging("INFO")
    writer = AuditWriter()
    writer.write("report.verified", {"report_id": 42}, subject_id="alice@dev-1")
    output = capsys.readouterr().out.strip()
    record = json.loads(output)
    assert record["event"] == "audit_log"
    assert record["audit_event"] == "report.verified"
    assert record["report_id"] == 42
    assert record["subject_id"] == "alice@dev-1"
