"""Shared contracts for agent runtime stages."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from codeask.agent.prompts import PromptContext
from codeask.agent.sse import AgentEvent
from codeask.agent.state import AgentState
from codeask.agent.tools import ToolRegistry
from codeask.agent.trace import AgentTraceLogger
from codeask.llm.types import LLMEvent, LLMMessage, ToolDef


def _empty_data() -> dict[str, Any]:
    return {}


def _empty_events() -> list[AgentEvent]:
    return []


def _empty_evidence() -> list[Evidence]:
    return []


def _empty_messages() -> list[LLMMessage]:
    return []


class LLMStreamer(Protocol):
    def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[LLMEvent]: ...


@dataclass(frozen=True)
class Evidence:
    id: str
    type: str
    summary: str
    relevance: str
    confidence: str = "medium"
    data: dict[str, Any] = field(default_factory=_empty_data)


@dataclass(frozen=True)
class StageResult:
    next_state: AgentState
    events: list[AgentEvent] = field(default_factory=_empty_events)
    evidence_added: list[Evidence] = field(default_factory=_empty_evidence)
    messages_appended: list[LLMMessage] = field(default_factory=_empty_messages)
    metadata_updates: dict[str, Any] = field(default_factory=_empty_data)


@dataclass(frozen=True)
class StageContext:
    session_id: str
    turn_id: str
    prompt_context: PromptContext
    llm_client: LLMStreamer | None = None
    tool_registry: ToolRegistry | None = None
    trace_logger: AgentTraceLogger | None = None
    collected_evidence: list[Evidence] = field(default_factory=_empty_evidence)
    force_code_investigation: bool = False
    subject_id: str = "system"
    limits: dict[str, Any] = field(default_factory=_empty_data)
    wiki_search_service: object | None = None
    code_search_service: object | None = None
    attachment_repo: object | None = None
    metadata: dict[str, Any] = field(default_factory=_empty_data)
