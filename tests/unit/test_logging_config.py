"""Tests for structlog configuration."""

import json
import logging
from typing import Any

import structlog

from codeask.logging_config import configure_logging


def test_logger_outputs_json(capsys: Any) -> None:
    configure_logging("INFO")
    log = structlog.get_logger("test")
    log.info("hello", foo="bar", n=42)
    out = capsys.readouterr().out.strip()
    assert out, "expected log line on stdout"
    record = json.loads(out)
    assert record["event"] == "hello"
    assert record["foo"] == "bar"
    assert record["n"] == 42
    assert record["level"] == "info"


def test_reconfigure_does_not_corrupt_output(capsys: Any) -> None:
    configure_logging("DEBUG")
    configure_logging("DEBUG")
    log = structlog.get_logger("test")
    log.info("second")
    out = capsys.readouterr().out.strip()
    record = json.loads(out)
    assert record["event"] == "second"


def test_respects_stdlib_level() -> None:
    configure_logging("WARNING")
    assert logging.getLogger().level == logging.WARNING
