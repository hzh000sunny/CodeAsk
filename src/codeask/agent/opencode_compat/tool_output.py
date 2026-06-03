"""Helpers for interpreting opencode tool output."""

from __future__ import annotations

import json
from typing import cast


def tool_uses_structured_error(tool_name: str) -> bool:
    """Return whether top-level ``error`` is a tool-failure contract."""

    return tool_name.startswith(("codeask_", "openviking_"))


def structured_output(output: object) -> dict[str, object]:
    if isinstance(output, dict):
        return cast(dict[str, object], output)
    if not isinstance(output, str) or not output:
        return {}
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return cast(dict[str, object], parsed)
    return {}


def output_summary(output: object) -> str | None:
    output_data = structured_output(output)
    summary = output_data.get("summary") or output_data.get("message")
    if isinstance(summary, str) and summary:
        return summary
    if isinstance(output, str):
        return output
    return None


def output_error(output: object, *, tool_name: str) -> str | None:
    if not tool_uses_structured_error(tool_name):
        return None
    output_data = structured_output(output)
    error = output_data.get("error")
    if isinstance(error, str) and error:
        return error
    return None
