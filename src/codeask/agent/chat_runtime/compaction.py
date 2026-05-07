"""Context budget and compaction helpers for chat runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from codeask.llm.types import LLMMessage, ToolResultBlock

DEFAULT_CONTEXT_WINDOW_CHARS = 202_752
DEFAULT_SUMMARY_OUTPUT_RESERVE_CHARS = 20_000
AUTOCOMPACT_BUFFER_CHARS = 13_000
WARNING_THRESHOLD_BUFFER_CHARS = 20_000
ERROR_THRESHOLD_BUFFER_CHARS = 20_000
MANUAL_COMPACT_BUFFER_CHARS = 3_000
MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3


@dataclass(frozen=True)
class ContextBudgetPolicy:
    """Claude-Code-inspired context thresholds using serialized-message chars.

    Claude Code uses token accounting. CodeAsk does not yet have provider-neutral
    token usage before each request, so v1.0.2 uses serialized message length as
    the enforcement unit. The buffer names and defaults intentionally mirror the
    Claude Code threshold model.
    """

    context_window_chars: int = DEFAULT_CONTEXT_WINDOW_CHARS
    summary_output_reserve_chars: int = DEFAULT_SUMMARY_OUTPUT_RESERVE_CHARS
    autocompact_buffer_chars: int = AUTOCOMPACT_BUFFER_CHARS
    warning_buffer_chars: int = WARNING_THRESHOLD_BUFFER_CHARS
    error_buffer_chars: int = ERROR_THRESHOLD_BUFFER_CHARS
    manual_compact_buffer_chars: int = MANUAL_COMPACT_BUFFER_CHARS
    keep_recent_tool_results: int = 3

    @property
    def effective_context_window_chars(self) -> int:
        reserve = min(self.summary_output_reserve_chars, self.context_window_chars // 4)
        return max(1, self.context_window_chars - reserve)

    @property
    def auto_compact_threshold_chars(self) -> int:
        return max(1, self.effective_context_window_chars - self.autocompact_buffer_chars)

    @property
    def warning_threshold_chars(self) -> int:
        return max(1, self.auto_compact_threshold_chars - self.warning_buffer_chars)

    @property
    def error_threshold_chars(self) -> int:
        return max(1, self.auto_compact_threshold_chars - self.error_buffer_chars)

    @property
    def blocking_limit_chars(self) -> int:
        return max(1, self.effective_context_window_chars - self.manual_compact_buffer_chars)


@dataclass(frozen=True)
class ContextBudgetState:
    size_chars: int
    threshold_chars: int
    blocking_limit_chars: int
    is_above_warning_threshold: bool
    is_above_error_threshold: bool
    is_above_auto_compact_threshold: bool
    is_at_blocking_limit: bool


@dataclass(frozen=True)
class CompactionResult:
    messages: list[LLMMessage]
    before_chars: int
    after_chars: int
    compacted_tool_results: int
    triggered: bool


def estimate_context_size_chars(messages: list[LLMMessage]) -> int:
    """Estimate provider input size from serialized messages."""

    return sum(len(message.model_dump_json()) for message in messages)


def calculate_context_budget_state(
    messages: list[LLMMessage],
    policy: ContextBudgetPolicy,
) -> ContextBudgetState:
    size = estimate_context_size_chars(messages)
    return ContextBudgetState(
        size_chars=size,
        threshold_chars=policy.auto_compact_threshold_chars,
        blocking_limit_chars=policy.blocking_limit_chars,
        is_above_warning_threshold=size >= policy.warning_threshold_chars,
        is_above_error_threshold=size >= policy.error_threshold_chars,
        is_above_auto_compact_threshold=size >= policy.auto_compact_threshold_chars,
        is_at_blocking_limit=size >= policy.blocking_limit_chars,
    )


def compact_messages_if_needed(
    messages: list[LLMMessage],
    policy: ContextBudgetPolicy,
    *,
    force: bool = False,
) -> CompactionResult:
    """Compact old tool results only when the active context crosses threshold."""

    before = estimate_context_size_chars(messages)
    if not force and before < policy.auto_compact_threshold_chars:
        return CompactionResult(
            messages=messages,
            before_chars=before,
            after_chars=before,
            compacted_tool_results=0,
            triggered=False,
        )

    compacted = [message.model_copy(deep=True) for message in messages]
    tool_message_indexes = [
        index
        for index, message in enumerate(compacted)
        if message.role == "tool" and _has_tool_result_content(message)
    ]
    keep_recent = max(0, policy.keep_recent_tool_results)
    indexes_to_compact = (
        tool_message_indexes[:-keep_recent] if keep_recent else tool_message_indexes
    )

    compacted_count = 0
    for index in indexes_to_compact:
        if _compact_tool_message(compacted[index]):
            compacted_count += 1

    after = estimate_context_size_chars(compacted)
    if after <= policy.blocking_limit_chars:
        return CompactionResult(
            messages=compacted,
            before_chars=before,
            after_chars=after,
            compacted_tool_results=compacted_count,
            triggered=True,
        )

    # If the preserved tail still exceeds the hard budget, compact older items
    # inside the recent window one by one while keeping the newest result intact.
    recent_candidates = tool_message_indexes[-keep_recent:-1] if keep_recent > 1 else []
    for index in recent_candidates:
        if _compact_tool_message(compacted[index]):
            compacted_count += 1
            after = estimate_context_size_chars(compacted)
            if after <= policy.blocking_limit_chars:
                break

    return CompactionResult(
        messages=compacted,
        before_chars=before,
        after_chars=estimate_context_size_chars(compacted),
        compacted_tool_results=compacted_count,
        triggered=True,
    )


def _has_tool_result_content(message: LLMMessage) -> bool:
    return any(isinstance(block, ToolResultBlock) for block in message.content)


def _compact_tool_message(message: LLMMessage) -> bool:
    changed = False
    next_content = []
    for block in message.content:
        if isinstance(block, ToolResultBlock):
            next_content.append(
                block.model_copy(update={"content": _compact_tool_result_content(block.content)})
            )
            changed = True
        else:
            next_content.append(block)
    if changed:
        message.content = next_content
    return changed


def _compact_tool_result_content(content: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(content, str):
        return {
            "compacted": True,
            "summary": _truncate(content, 240),
            "items": [],
            "warnings": ["旧工具结果内容已因上下文预算压缩，仅保留摘要。"],
        }

    tool = content.get("tool")
    summary = content.get("summary") or content.get("message") or "旧工具结果已压缩"
    warnings = list(content.get("warnings") or [])
    warnings.append("旧工具结果内容已因上下文预算压缩，仅保留摘要和证据引用。")
    return {
        "compacted": True,
        "ok": content.get("ok"),
        "tool": tool,
        "summary": _truncate(str(summary), 500),
        "evidence_refs": content.get("evidence_refs") or [],
        "warnings": warnings,
        "truncated": True,
        "raw_result_ref": content.get("raw_result_ref"),
        "version_info": content.get("version_info"),
        "error_type": content.get("error_type"),
        "message": _truncate(str(content.get("message")), 500)
        if content.get("message") is not None
        else None,
        "items": [],
    }


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 15)] + "...[truncated]"
