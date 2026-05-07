"""Analysis policy tools for the chat runtime."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from codeask.agent.chat_runtime.events import EvidenceRef
from codeask.agent.chat_runtime.tool_contracts import (
    ToolContext,
    ToolErrorType,
    ToolResult,
    ToolSpec,
)
from codeask.agent.chat_runtime.tool_registry import ToolRegistry


class LoadAnalysisPolicyInput(BaseModel):
    policy_id: int
    scope: str


def register_policy_tools(
    registry: ToolRegistry,
    *,
    fake_policies: list[dict[str, Any]] | None = None,
) -> None:
    policies = fake_policies or []

    async def load_analysis_policy(
        args: LoadAnalysisPolicyInput,
        ctx: ToolContext,
    ) -> ToolResult:
        policy = next(
            (
                item
                for item in policies
                if item.get("policy_id") == args.policy_id
                and item.get("scope") == args.scope
                and item.get("enabled", True)
            ),
            None,
        )
        if policy is None:
            return ToolResult.error(
                tool="load_analysis_policy",
                error_type=ToolErrorType.NOT_FOUND,
                message=f"analysis policy not found: {args.policy_id}",
            )
        return ToolResult.ok(
            tool="load_analysis_policy",
            summary=f"读取分析策略：{policy.get('name', args.policy_id)}",
            items=[policy],
            evidence_refs=[
                EvidenceRef(
                    type="policy",
                    title=str(policy.get("name")) if policy.get("name") else None,
                    metadata={"policy_id": args.policy_id, "scope": args.scope},
                )
            ],
        )

    registry.register(
        ToolSpec(
            name="load_analysis_policy",
            description="按需读取全局或特性分析策略全文。策略是指导，不是固定流程。",
            input_model=LoadAnalysisPolicyInput,
            read_only=True,
            concurrency_safe=True,
            requires_confirmation=False,
        ),
        load_analysis_policy,
    )
