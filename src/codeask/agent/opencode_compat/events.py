"""Map opencode raw events into CodeAsk runtime events."""

from __future__ import annotations

from typing import Any

from codeask.agent.chat_runtime.events import ChatRuntimeEvent


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

    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None

    event_type = payload.get("type")
    properties = payload.get("properties")
    if not isinstance(properties, dict):
        properties = {}

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
        status = properties.get("status")
        status_type = status.get("type") if isinstance(status, dict) else None
        if status_type == "idle":
            return ChatRuntimeEvent(type="done", data={"backend": "opencode"})
        if status_type in {"busy", "retry"}:
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
        part = properties.get("part")
        if not isinstance(part, dict):
            return None
        return _map_part_updated(part)

    if event_type == "session.error":
        error = properties.get("error")
        return ChatRuntimeEvent(type="error", data={"backend": "opencode", "error": error})

    return None


def _status_summary(status_type: str, status: object) -> str:
    if not isinstance(status, dict):
        return f"opencode session status: {status_type}"

    if status_type == "retry":
        attempt = status.get("attempt")
        message = status.get("message")
        attempt_label = f" #{attempt}" if isinstance(attempt, int) and attempt > 0 else ""
        if isinstance(message, str) and message:
            return f"opencode retry{attempt_label}: {message}"
        return f"opencode retry{attempt_label}"

    return f"opencode session status: {status_type}"


def _map_part_updated(part: dict[str, Any]) -> ChatRuntimeEvent | None:
    part_type = part.get("type")
    if part_type == "tool":
        state = part.get("state")
        state = state if isinstance(state, dict) else {}
        status = state.get("status")
        tool_name = str(part.get("tool") or "unknown")
        part_id = str(part.get("id") or "")
        if status == "running":
            input_data = state.get("input")
            return ChatRuntimeEvent(
                type="tool_call",
                data={
                    "tool_call_id": part_id,
                    "tool_name": tool_name,
                    "arguments_summary": input_data if isinstance(input_data, dict) else {},
                },
            )
        if status in {"completed", "error"}:
            output = state.get("output")
            return ChatRuntimeEvent(
                type="tool_result",
                data={
                    "tool_call_id": part_id,
                    "tool_name": tool_name,
                    "ok": status == "completed",
                    "summary": str(state.get("title") or _output_summary(output) or status),
                    "message": str(state.get("error")) if state.get("error") else None,
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


def _output_summary(output: object) -> str | None:
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        summary = output.get("summary") or output.get("message")
        if isinstance(summary, str) and summary:
            return summary
    return None
