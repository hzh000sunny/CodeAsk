"""Redact host paths from agent events before they leave the backend."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

_AGENT_SESSION_PATH_RE = re.compile(
    r"(?:[A-Za-z]:)?/[^\s\"'`<>|)]*/agent_sessions/[^\s\"'`<>|)]+/"
    r"(?:sessions/)?(?P<session>sess_[A-Za-z0-9_-]+)(?P<relative>/[^\s\"'`<>|)]*)?"
)
_WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"\b[A-Za-z]:\\[^\s\"'`<>|)]+")
_POSIX_ABSOLUTE_PATH_RE = re.compile(
    r"(^|[\s\"'`\(\[\{:=,])"
    r"((?:/(?:home|Users|var|tmp|opt|private|mnt|srv|root|etc|usr|run|data|Volumes|workspace)"
    r"\b[^\s\"'`<>|)]*))"
)

HIDDEN_ABSOLUTE_PATH = "[外部绝对路径已隐藏]"


def redact_trace_payload_for_frontend(payload: Any, *, session_id: str) -> Any:
    """Return a redacted copy for UI/API output without mutating runtime payloads."""

    return _redact_value(deepcopy(payload), session_id=session_id)


def _redact_value(value: Any, *, session_id: str) -> Any:
    if isinstance(value, str):
        return _redact_text(value, session_id=session_id)
    if isinstance(value, list):
        return [_redact_value(item, session_id=session_id) for item in value]
    if isinstance(value, dict):
        return {key: _redact_value(child, session_id=session_id) for key, child in value.items()}
    return value


def _redact_text(value: str, *, session_id: str) -> str:
    text = _AGENT_SESSION_PATH_RE.sub(
        lambda match: _agent_session_replacement(match, session_id=session_id),
        value,
    )
    text = _WINDOWS_ABSOLUTE_PATH_RE.sub(HIDDEN_ABSOLUTE_PATH, text)
    return _POSIX_ABSOLUTE_PATH_RE.sub(
        lambda match: f"{match.group(1)}{HIDDEN_ABSOLUTE_PATH}",
        text,
    )


def _agent_session_replacement(match: re.Match[str], *, session_id: str) -> str:
    if match.group("session") != session_id:
        return HIDDEN_ABSOLUTE_PATH
    relative = (match.group("relative") or "").lstrip("/")
    return relative or "."
