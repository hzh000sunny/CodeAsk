"""Provider-neutral structured reasoning normalization."""

from __future__ import annotations

from typing import Any, Literal

ReasoningEventName = Literal["reasoning_start", "reasoning_delta", "reasoning_stop", "text_delta"]

_THINK_OPEN_TAG = "<think>"
_THINK_CLOSE_TAG = "</think>"
_CONTENT_THINK_FIELD = "content_think_tag"


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


class ThinkTagContentFilter:
    """Last-resort compatibility filter for providers leaking think markup as content.

    Primary reasoning handling is structured provider fields such as
    reasoning_content, thinking_delta, or Anthropic thinking blocks. This filter
    only prevents leaked `<think>...</think>` markup from entering visible text
    and persisted assistant messages when a private gateway returns it inside
    normal content.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._inside = False

    def feed(self, text: str) -> list[tuple[ReasoningEventName, dict[str, Any]]]:
        if not text:
            return []

        self._buffer += text
        events: list[tuple[ReasoningEventName, dict[str, Any]]] = []

        while self._buffer:
            lowered = self._buffer.lower()
            if self._inside:
                close_index = lowered.find(_THINK_CLOSE_TAG)
                if close_index == -1:
                    keep = _suffix_length(lowered, _THINK_CLOSE_TAG)
                    leaked = self._buffer[:-keep] if keep else self._buffer
                    _append_reasoning_delta(events, leaked)
                    self._buffer = self._buffer[-keep:] if keep else ""
                    break

                leaked = self._buffer[:close_index]
                _append_reasoning_delta(events, leaked)
                self._buffer = self._buffer[close_index + len(_THINK_CLOSE_TAG) :]
                self._inside = False
                continue

            open_index = lowered.find(_THINK_OPEN_TAG)
            close_index = lowered.find(_THINK_CLOSE_TAG)
            if close_index != -1 and (open_index == -1 or close_index < open_index):
                _append_text_delta(events, self._buffer[:close_index])
                self._buffer = self._buffer[close_index + len(_THINK_CLOSE_TAG) :]
                continue

            if open_index == -1:
                keep = max(
                    _suffix_length(lowered, _THINK_OPEN_TAG),
                    _suffix_length(lowered, _THINK_CLOSE_TAG),
                )
                visible = self._buffer[:-keep] if keep else self._buffer
                _append_text_delta(events, visible)
                self._buffer = self._buffer[-keep:] if keep else ""
                break

            _append_text_delta(events, self._buffer[:open_index])
            self._buffer = self._buffer[open_index + len(_THINK_OPEN_TAG) :]
            self._inside = True

        return events

    def flush(self) -> list[tuple[ReasoningEventName, dict[str, Any]]]:
        if not self._buffer:
            return []
        pending = self._buffer
        self._buffer = ""
        if self._inside:
            self._inside = False
            return (
                [
                    (
                        "reasoning_delta",
                        {"delta": pending, "field": _CONTENT_THINK_FIELD, "redacted": False},
                    )
                ]
                if pending
                else []
            )
        return [("text_delta", {"delta": pending})]


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


def _append_text_delta(
    events: list[tuple[ReasoningEventName, dict[str, Any]]],
    text: str,
) -> None:
    if text:
        events.append(("text_delta", {"delta": text}))


def _append_reasoning_delta(
    events: list[tuple[ReasoningEventName, dict[str, Any]]],
    text: str,
) -> None:
    if text:
        events.append(
            (
                "reasoning_delta",
                {"delta": text, "field": _CONTENT_THINK_FIELD, "redacted": False},
            )
        )


def _suffix_length(text: str, tag: str) -> int:
    max_length = min(len(text), len(tag) - 1)
    for length in range(max_length, 0, -1):
        if tag.startswith(text[-length:]):
            return length
    return 0


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
