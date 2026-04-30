"""Agent SSE event formatting."""

import json

import pytest
from pydantic import ValidationError

from codeask.agent.sse import AgentEvent, SSEMultiplexer


def test_format_outputs_sse_frame() -> None:
    event = AgentEvent(
        type="stage_transition",
        data={"from": "initialize", "to": "input_analysis", "message": None},
    )
    frame = SSEMultiplexer().format(event)
    assert frame.startswith(b"event: stage_transition\n")
    assert frame.endswith(b"\n\n")


def test_format_data_is_json() -> None:
    event = AgentEvent(type="text_delta", data={"delta": "你好"})
    frame = SSEMultiplexer().format(event).decode("utf-8")
    data_line = [line for line in frame.splitlines() if line.startswith("data: ")][0]
    assert json.loads(data_line.removeprefix("data: ")) == {"delta": "你好"}


def test_event_type_is_validated() -> None:
    with pytest.raises(ValidationError):
        AgentEvent(type="not_real", data={})  # type: ignore[arg-type]
