"""Tool execution pipeline for the chat runtime."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from pydantic import ValidationError

from codeask.agent.chat_runtime.tool_contracts import (
    ToolContext,
    ToolErrorType,
    ToolResult,
)
from codeask.agent.chat_runtime.tool_registry import ToolRegistry


class ToolExecutor:
    """Validates, guards, and executes chat runtime tools."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def execute(
        self,
        name: str,
        arguments: dict[str, object],
        context: ToolContext,
        *,
        confirmed: bool = False,
    ) -> ToolResult:
        registered = self._registry.get(name)
        if registered is None or not registered.spec.enabled:
            return ToolResult.error(
                tool=name,
                error_type=ToolErrorType.NOT_FOUND,
                message=f"unknown tool {name!r}",
            )

        spec = registered.spec
        try:
            parsed_arguments = spec.input_model.model_validate(arguments)
        except ValidationError as exc:
            return ToolResult.error(
                tool=spec.name,
                error_type=ToolErrorType.INVALID_INPUT,
                message=str(exc),
                summary="工具参数校验失败",
            )

        if spec.requires_confirmation and not confirmed:
            return ToolResult.error(
                tool=spec.name,
                error_type=ToolErrorType.PERMISSION_DENIED,
                message=f"tool {spec.name!r} requires user confirmation",
                summary="工具需要用户确认后才能执行",
            )

        try:
            result = await registered.handler(parsed_arguments, context)
        except Exception as exc:
            return ToolResult.error(
                tool=spec.name,
                error_type=ToolErrorType.INTERNAL_ERROR,
                message=str(exc),
                summary="工具执行失败",
            )

        return self._apply_result_budget(result, spec.max_result_size_chars, context)

    def _apply_result_budget(
        self,
        result: ToolResult,
        max_chars: int,
        context: ToolContext,
    ) -> ToolResult:
        serialized = result.model_dump_json()
        if len(serialized) <= max_chars:
            return result
        raw_ref = result.raw_result_ref or _raw_result_ref(result, context)
        raw_payload = result.model_dump(mode="json")
        budgeted = result.model_copy(
            update={
                "truncated": True,
                "raw_result_ref": raw_ref,
                "audit_raw_result": {
                    "raw_result_ref": raw_ref,
                    "result": raw_payload,
                },
                "warnings": [
                    *result.warnings,
                    f"工具结果超过 {max_chars} 字符，已截断进入模型上下文；"
                    f"完整结果引用：{raw_ref}。",
                ],
            }
        )
        while len(budgeted.model_dump_json()) > max_chars and budgeted.items:
            budgeted = budgeted.model_copy(update={"items": _shrink_items(budgeted.items)})
        if len(budgeted.model_dump_json()) <= max_chars:
            return budgeted
        return budgeted.model_copy(update={"items": []})


def _shrink_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    copied = [dict(item) for item in items]
    longest: tuple[int, str, int] | None = None
    for item_index, item in enumerate(copied):
        for key, value in item.items():
            if isinstance(value, str):
                candidate = (item_index, key, len(value))
                if longest is None or candidate[2] > longest[2]:
                    longest = candidate
    if longest is None:
        return copied[:-1]

    item_index, key, length = longest
    if length <= 80:
        return copied[:-1]
    marker = "...[truncated]"
    keep = max(80, length // 2)
    copied[item_index][key] = copied[item_index][key][: keep - len(marker)] + marker
    return copied


def _raw_result_ref(result: ToolResult, context: ToolContext) -> str:
    digest = sha256(result.model_dump_json().encode("utf-8")).hexdigest()[:16]
    return f"raw_tool_result:{context.session_id}:{context.turn_id}:{result.tool}:{digest}"
