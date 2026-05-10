"""Provider-neutral structured reasoning normalization."""

from __future__ import annotations

from typing import Any, Literal

ReasoningEventName = Literal["reasoning_start", "reasoning_delta", "reasoning_stop", "text_delta"]


def normalize_openai_delta(
    delta: dict[str, Any],
) -> list[tuple[ReasoningEventName, dict[str, Any]]]:
    """Normalize OpenAI-compatible delta fields without parsing visible content."""

    events: list[tuple[ReasoningEventName, dict[str, Any]]] = []
    for field in ("reasoning", "reasoning_content", "thinking"):
        value = delta.get(field)
        text = _reasoning_text(value)
        if text:
            events.append(
                (
                    "reasoning_delta",
                    {"delta": text, "field": field, "redacted": False},
                )
            )

    content = delta.get("content")
    if isinstance(content, str) and content:
        events.append(("text_delta", {"delta": content}))
    return events


def normalize_anthropic_stream_event(
    event: dict[str, Any],
) -> list[tuple[ReasoningEventName, dict[str, Any]]]:
    """Normalize Anthropic-style stream events into provider-neutral events."""

    event_type = str(event.get("type") or "")
    out: list[tuple[ReasoningEventName, dict[str, Any]]] = []
    if event_type == "content_block_start":
        block = _dict_value(event.get("content_block"))
        block_type = str(block.get("type") or "")
        if block_type == "thinking":
            out.append(("reasoning_start", {"field": "thinking", "redacted": False}))
        elif block_type == "redacted_thinking":
            data = block.get("data")
            if isinstance(data, str) and data:
                out.append(
                    (
                        "reasoning_delta",
                        {
                            "delta": data,
                            "field": "redacted_thinking",
                            "redacted": True,
                        },
                    )
                )
    elif event_type == "content_block_delta":
        delta = _dict_value(event.get("delta"))
        delta_type = str(delta.get("type") or "")
        if delta_type == "thinking_delta":
            text = delta.get("thinking")
            if isinstance(text, str) and text:
                out.append(
                    (
                        "reasoning_delta",
                        {"delta": text, "field": "thinking_delta", "redacted": False},
                    )
                )
        elif delta_type == "text_delta":
            text = delta.get("text")
            if isinstance(text, str) and text:
                out.append(("text_delta", {"delta": text}))
        elif delta_type == "signature_delta":
            return []
    elif event_type == "content_block_stop":
        out.append(("reasoning_stop", {"field": "thinking"}))
    return out


def reasoning_diagnostic(data: dict[str, Any]) -> dict[str, Any]:
    delta = data.get("delta")
    return {
        "field": str(data.get("field") or "unknown"),
        "length": len(delta) if isinstance(delta, str) else 0,
        "chunks": 1 if isinstance(delta, str) and delta else 0,
        "redacted": bool(data.get("redacted", False)),
        "raw_reasoning_used": False,
    }


class ReasoningDiagnosticAccumulator:
    """Aggregates structured reasoning chunks into one safe diagnostic event."""

    def __init__(self) -> None:
        self._fields: set[str] = set()
        self._length = 0
        self._chunks = 0
        self._redacted = False

    def observe(self, data: dict[str, Any]) -> None:
        delta = data.get("delta")
        if isinstance(delta, str) and delta:
            self._length += len(delta)
            self._chunks += 1
        field = data.get("field")
        if isinstance(field, str) and field:
            self._fields.add(field)
        if data.get("redacted") is True:
            self._redacted = True

    def diagnostic(self) -> dict[str, Any] | None:
        if self._chunks == 0 and not self._fields:
            return None
        return {
            "field": ", ".join(sorted(self._fields)) if self._fields else "unknown",
            "length": self._length,
            "chunks": self._chunks,
            "redacted": self._redacted,
            "raw_reasoning_used": False,
        }


def _reasoning_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("text", "thinking", "content", "reasoning"):
            item = value.get(key)
            if isinstance(item, str) and item:
                return item
    return ""


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
