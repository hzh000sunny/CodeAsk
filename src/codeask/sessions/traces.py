"""Trace filtering helpers for session history APIs."""

from __future__ import annotations

from typing import Any, cast

from codeask.db.models import AgentTrace


def is_visible_trace(row: AgentTrace) -> bool:
    if row.event_type != "llm_event":
        return True
    payload = agent_trace_payload(row)
    return payload.get("type") in {"message_start", "tool_call_done", "error"}


def trace_event_priority(row: AgentTrace) -> int:
    priorities = {
        "stage_enter": 0,
        "llm_input": 1,
        "scope_decision": 2,
        "sufficiency_decision": 2,
        "tool_call": 3,
        "tool_result": 4,
        "stage_exit": 9,
    }
    if row.event_type == "llm_event":
        payload = agent_trace_payload(row)
        llm_type = payload.get("type")
        if llm_type == "message_start":
            return 1
        if llm_type == "tool_call_done":
            return 3
        if llm_type == "error":
            return 8
    return priorities.get(row.event_type, 5)


def agent_trace_payload(row: AgentTrace) -> dict[str, Any]:
    payload: Any = row.payload
    if isinstance(payload, dict):
        return cast(dict[str, Any], payload)
    return {}
