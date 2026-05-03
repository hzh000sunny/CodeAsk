"""Shared models and exceptions for agent tool execution."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft7Validator
from pydantic import BaseModel, Field

from codeask.agent.state import AgentState


def _empty_evidence() -> list[dict[str, Any]]:
    return []


class ToolResult(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None
    summary: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=_empty_evidence)
    truncated: bool = False
    hint: str | None = None
    error_code: str | None = None
    message: str | None = None
    recoverable: bool = True


@dataclass(frozen=True)
class ToolContext:
    session_id: str
    turn_id: str
    feature_ids: list[int]
    repo_bindings: list[dict[str, Any]]
    subject_id: str
    phase: AgentState
    limits: dict[str, Any]


class AskUserSignal(Exception):
    def __init__(
        self,
        question: str,
        options: list[str] | None,
        ask_id: str,
    ) -> None:
        super().__init__(question)
        self.question = question
        self.options = options
        self.ask_id = ask_id


class RepoNotReadyError(Exception):
    """Raised by code tools when a repo is not ready for investigation."""


ToolFn = Callable[[dict[str, Any], ToolContext], Awaitable[ToolResult]]


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    description: str
    schema: dict[str, Any]
    validator: Draft7Validator
    allowed_phases: set[AgentState]
    fn: ToolFn
