"""Schema validation for feedback verdicts and frontend event whitelist."""

import pytest
from pydantic import ValidationError

from codeask.api.schemas.metrics import ALLOWED_EVENT_TYPES, FeedbackCreate, FrontendEventCreate


def test_feedback_accepts_valid_verdicts() -> None:
    for verdict in ("solved", "partial", "wrong"):
        payload = FeedbackCreate(session_turn_id="turn_1", feedback=verdict)  # type: ignore[arg-type]
        assert payload.feedback == verdict


def test_feedback_rejects_unknown_verdict() -> None:
    with pytest.raises(ValidationError):
        FeedbackCreate(session_turn_id="turn_1", feedback="maybe")  # type: ignore[arg-type]


def test_event_accepts_whitelisted_type() -> None:
    payload = FrontendEventCreate(
        event_type="force_deeper_investigation",
        session_id="sess_1",
        payload={"sufficiency_verdict": "sufficient"},
    )
    assert payload.event_type == "force_deeper_investigation"


def test_event_rejects_off_whitelist_type() -> None:
    with pytest.raises(ValidationError):
        FrontendEventCreate(event_type="random_thing")


def test_whitelist_contains_critical_metrics_events() -> None:
    required = {
        "doc_edit_session_started",
        "doc_edit_session_completed",
        "force_deeper_investigation",
        "feature_switch",
        "feedback_submitted",
    }
    assert required <= ALLOWED_EVENT_TYPES
