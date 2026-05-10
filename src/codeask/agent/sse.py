"""SSE event formatting for agent runtime events."""

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

EventName = Literal[
    "llm_input",
    "stage_transition",
    "text_delta",
    "reasoning_observed",
    "reasoning_leak_detected",
    "runtime_state",
    "tool_call",
    "tool_result",
    "retrieval_context",
    "assistant_action",
    "needs_clarification",
    "evidence",
    "wiki_scope_resolution",
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
        data = event.data
        if isinstance(data, BaseModel):
            data = data.model_dump(mode="json")
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return f"event: {event.type}\ndata: {payload}\n\n".encode()
