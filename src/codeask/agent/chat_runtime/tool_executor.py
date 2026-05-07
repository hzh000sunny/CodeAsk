"""Tool execution pipeline for the chat runtime."""

from __future__ import annotations

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

        return self._apply_result_budget(result, spec.max_result_size_chars)

    def _apply_result_budget(self, result: ToolResult, max_chars: int) -> ToolResult:
        serialized = result.model_dump_json()
        if len(serialized) <= max_chars:
            return result
        return result.model_copy(
            update={
                "truncated": True,
                "warnings": [
                    *result.warnings,
                    f"工具结果超过 {max_chars} 字符，已截断进入模型上下文。",
                ],
            }
        )
