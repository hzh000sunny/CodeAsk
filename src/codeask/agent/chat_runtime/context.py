"""Context assembly for chat runtime turns."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


def _empty_dict() -> dict[str, Any]:
    return {}


class SessionMessage(BaseModel):
    role: Literal["user", "assistant", "tool", "system"]
    content: str


class ChatTurnContext(BaseModel):
    current_user_message: str
    recent_history: list[SessionMessage] = Field(default_factory=list)
    retrieval_context: dict[str, Any] = Field(default_factory=_empty_dict)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    explicit_constraints: dict[str, Any] = Field(default_factory=_empty_dict)


class ContextAssembler:
    def __init__(self, *, max_history_messages: int = 12) -> None:
        self._max_history_messages = max_history_messages

    def assemble(
        self,
        *,
        user_message: str,
        history: list[SessionMessage],
        retrieval_context: dict[str, Any],
        attachments: list[dict[str, Any]],
        explicit_constraints: dict[str, Any],
    ) -> ChatTurnContext:
        recent_history = history[-self._max_history_messages :]
        return ChatTurnContext(
            current_user_message=user_message,
            recent_history=recent_history,
            retrieval_context=retrieval_context,
            attachments=attachments,
            explicit_constraints=explicit_constraints,
        )
