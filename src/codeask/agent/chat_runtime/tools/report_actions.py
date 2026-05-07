"""Report action suggestion tools for the chat runtime."""

from __future__ import annotations

from pydantic import BaseModel, Field

from codeask.agent.chat_runtime.tool_contracts import ToolContext, ToolResult, ToolSpec
from codeask.agent.chat_runtime.tool_registry import ToolRegistry


class ProposeReportInput(BaseModel):
    reason: str
    candidate_feature_ids: list[int] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


def register_report_action_tools(registry: ToolRegistry) -> None:
    async def propose_report(args: ProposeReportInput, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(
            tool="propose_report",
            summary="模型建议生成问题定位报告，但尚未创建报告。",
            items=[
                {
                    "reason": args.reason,
                    "candidate_feature_ids": args.candidate_feature_ids,
                    "missing_fields": args.missing_fields,
                    "required_confirmation": True,
                    "generated": False,
                }
            ],
        )

    registry.register(
        ToolSpec(
            name="propose_report",
            description="建议生成问题定位报告，但不直接创建报告。",
            input_model=ProposeReportInput,
            read_only=True,
            concurrency_safe=False,
            requires_confirmation=False,
        ),
        propose_report,
    )
