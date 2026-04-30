"""SSE event formatting for agent runtime events."""

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

EventName = Literal[
    "stage_transition",
    "text_delta",
    "tool_call",
    "tool_result",
    "evidence",
    "scope_detection",
    "sufficiency_judgement",
    "ask_user",
    "done",
    "error",
]


class AgentEvent(BaseModel):
    type: EventName
    data: dict[str, Any] = Field(default_factory=dict)


class SSEMultiplexer:
    def format(self, event: AgentEvent) -> bytes:
        payload = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
        return f"event: {event.type}\ndata: {payload}\n\n".encode()
