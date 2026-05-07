"""User interaction tools for the chat runtime."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from codeask.agent.chat_runtime.tool_contracts import ToolContext, ToolResult, ToolSpec
from codeask.agent.chat_runtime.tool_registry import ToolRegistry


class AskUserRequired(Exception):
    def __init__(
        self,
        *,
        question: str,
        options: list[dict[str, Any]],
        allow_free_text: bool,
        reason: str | None,
    ) -> None:
        super().__init__(question)
        self.question = question
        self.options = options
        self.allow_free_text = allow_free_text
        self.reason = reason


class AskUserInput(BaseModel):
    question: str
    reason: str | None = None
    options: list[dict[str, Any]] = Field(default_factory=list)
    allow_free_text: bool = True


def register_user_interaction_tools(registry: ToolRegistry) -> None:
    async def ask_user(args: AskUserInput, ctx: ToolContext) -> ToolResult:
        raise AskUserRequired(
            question=args.question,
            options=args.options,
            allow_free_text=args.allow_free_text,
            reason=args.reason,
        )

    registry.register(
        ToolSpec(
            name="ask_user",
            description="向用户提出一个关键澄清问题，并暂停当前 Agent turn。",
            input_model=AskUserInput,
            read_only=True,
            concurrency_safe=False,
            requires_confirmation=False,
            requires_user_interaction=True,
        ),
        ask_user,
    )
