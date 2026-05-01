"""Schemas for metrics API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

FeedbackVerdict = Literal["solved", "partial", "wrong"]

ALLOWED_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "doc_edit_session_started",
        "doc_edit_session_completed",
        "force_deeper_investigation",
        "feature_switch",
        "report_unverify_clicked",
        "feedback_submitted",
        "session_naturally_ended",
        "ask_for_human_clicked",
    }
)


class FeedbackCreate(BaseModel):
    session_turn_id: str = Field(..., min_length=1, max_length=64)
    feedback: FeedbackVerdict
    note: str | None = Field(default=None, max_length=4000)


class FeedbackAck(BaseModel):
    ok: Literal[True] = True


class FrontendEventCreate(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=64)
    session_id: str | None = Field(default=None, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def _check_whitelist(cls, value: str) -> str:
        if value not in ALLOWED_EVENT_TYPES:
            raise ValueError(
                f"event_type '{value}' is not whitelisted; update metrics SDD before sending"
            )
        return value


class FrontendEventAck(BaseModel):
    ok: Literal[True] = True
    id: str


class AuditLogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_type: str
    entity_id: str
    action: str
    from_status: str | None
    to_status: str | None
    subject_id: str
    at: datetime


class AuditLogResponse(BaseModel):
    entries: list[AuditLogEntry]
