"""Map opencode raw events into CodeAsk runtime events."""

from __future__ import annotations

from typing import Any, cast

from codeask.agent.chat_runtime.events import ChatRuntimeEvent
from codeask.agent.opencode_compat.tool_output import (
    output_error as tool_output_error,
)
from codeask.agent.opencode_compat.tool_output import (
    output_summary,
)


def _object_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return {}


def map_global_event(
    event: dict[str, Any],
    *,
    directory: str,
    session_id: str,
) -> ChatRuntimeEvent | None:
    """Map one `/global/event` envelope into a CodeAsk event.

    Events for other workspaces or sessions are ignored. Raw reasoning is never
    returned to the frontend; only redacted metadata is exposed.
    """

    if event.get("directory") != directory:
        return None

    payload = _object_dict(event.get("payload"))
    if not payload:
        return None

    event_type = payload.get("type")
    properties = _object_dict(payload.get("properties"))

    if event_type == "sync":
        return None

    prop_session_id = properties.get("sessionID")
    if isinstance(prop_session_id, str) and prop_session_id != session_id:
        return None

    if event_type == "message.part.delta":
        delta = properties.get("delta")
        if isinstance(delta, str) and delta:
            return ChatRuntimeEvent(type="text_delta", data={"delta": delta})
        return None

    if event_type == "session.status":
        status = _object_dict(properties.get("status"))
        status_type = status.get("type")
        if status_type == "idle":
            return ChatRuntimeEvent(type="done", data={"backend": "opencode"})
        if isinstance(status_type, str) and status_type in {"busy", "retry"}:
            return ChatRuntimeEvent(
                type="assistant_action",
                data={
                    "action": f"opencode_{status_type}",
                    "summary": _status_summary(status_type, status),
                    "metadata": {"status": status},
                },
            )
        return None

    if event_type == "message.part.updated":
        part = _object_dict(properties.get("part"))
        if not part:
            return None
        return _map_part_updated(part)

    if event_type == "session.error":
        error = properties.get("error")
        data: dict[str, object] = {"backend": "opencode", "error": error}
        for key in ("no_progress_seconds", "absolute_wait_seconds"):
            value = properties.get(key)
            if isinstance(value, int):
                data[key] = value
        return ChatRuntimeEvent(type="error", data=data)

    return None


def _status_summary(status_type: str, status: object) -> str:
    status_data = _object_dict(status)
    if not status_data:
        return f"opencode session status: {status_type}"

    if status_type == "retry":
        attempt = status_data.get("attempt")
        message = status_data.get("message")
        attempt_label = f" #{attempt}" if isinstance(attempt, int) and attempt > 0 else ""
        if isinstance(message, str) and message:
            return f"opencode retry{attempt_label}: {message}"
        return f"opencode retry{attempt_label}"

    return f"opencode session status: {status_type}"


def _map_part_updated(part: dict[str, object]) -> ChatRuntimeEvent | None:
    part_type = part.get("type")
    if part_type == "tool":
        state = _object_dict(part.get("state"))
        status = state.get("status")
        tool_name = str(part.get("tool") or "unknown")
        part_id = str(part.get("id") or "")
        if status == "running":
            input_data = _object_dict(state.get("input"))
            return ChatRuntimeEvent(
                type="tool_call",
                data={
                    "tool_call_id": part_id,
                    "tool_name": tool_name,
                    "arguments_summary": input_data,
                },
            )
        if status in {"completed", "error"}:
            output = state.get("output")
            output_error = tool_output_error(output, tool_name=tool_name)
            ok = status == "completed" and output_error is None
            return ChatRuntimeEvent(
                type="tool_result",
                data={
                    "tool_call_id": part_id,
                    "tool_name": tool_name,
                    "ok": ok,
                    "summary": str(state.get("title") or output_summary(output) or status),
                    "message": output_error
                    or (str(state["error"]) if state.get("error") else None),
                    **(
                        {"result": output}
                        if isinstance(output, (dict, list))
                        else {"raw_output": output}
                        if isinstance(output, str) and output
                        else {}
                    ),
                },
            )
        return None

    if part_type == "reasoning":
        text = part.get("text") or part.get("thinking") or part.get("content") or ""
        content_length = len(text) if isinstance(text, str) else 0
        return ChatRuntimeEvent(
            type="reasoning_observed",
            data={
                "source": "opencode",
                "part_id": str(part.get("id") or ""),
                "content_length": content_length,
                "redacted": True,
            },
        )

    return None
