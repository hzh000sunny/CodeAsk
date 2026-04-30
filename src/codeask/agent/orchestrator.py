"""Agent runtime orchestrator."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.agent.prompts import FeatureDigest, PromptContext, RepoBinding
from codeask.agent.sse import AgentEvent
from codeask.agent.stages import (
    StageContext,
    StageResult,
    answer_finalization,
    ask_user,
    code_investigation,
    evidence_synthesis,
    input_analysis,
    knowledge_retrieval,
    report_drafting,
    scope_detection,
    sufficiency_judgement,
    version_confirmation,
)
from codeask.agent.state import AgentState, is_valid_transition
from codeask.agent.tools import ToolRegistry
from codeask.agent.trace import AgentTraceLogger
from codeask.db.models import (
    Feature,
    SessionRepoBinding,
    SessionTurn,
)
from codeask.db.models import (
    Session as SessionModel,
)
from codeask.llm.gateway import LLMGateway
from codeask.llm.types import LLMEvent, LLMMessage, LLMRequest, TextBlock, ToolDef

StageFn = Callable[[StageContext], Awaitable[StageResult]]


@dataclass(frozen=True)
class _GatewayStageClient:
    gateway: LLMGateway
    config_id: str | None = None

    def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[LLMEvent]:
        return self.gateway.stream(
            LLMRequest(
                config_id=self.config_id,
                messages=messages,
                tools=tools,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        )


class AgentOrchestrator:
    def __init__(
        self,
        *,
        gateway: LLMGateway,
        tool_registry: ToolRegistry,
        trace_logger: AgentTraceLogger,
        session_factory: async_sessionmaker[AsyncSession],
        wiki_search_service: object | None = None,
        code_search_service: object | None = None,
        attachment_repo: object | None = None,
    ) -> None:
        self._gateway = gateway
        self._tool_registry = tool_registry
        self._trace = trace_logger
        self._session_factory = session_factory
        self._wiki_search_service = wiki_search_service
        self._code_search_service = code_search_service
        self._attachment_repo = attachment_repo
        self._stage_dispatch: dict[AgentState, StageFn] = {
            AgentState.Initialize: self._initialize,
            AgentState.InputAnalysis: input_analysis.run,
            AgentState.ScopeDetection: scope_detection.run,
            AgentState.KnowledgeRetrieval: knowledge_retrieval.run,
            AgentState.SufficiencyJudgement: sufficiency_judgement.run,
            AgentState.CodeInvestigation: code_investigation.run,
            AgentState.VersionConfirmation: version_confirmation.run,
            AgentState.AnswerFinalization: answer_finalization.run,
            AgentState.EvidenceSynthesis: evidence_synthesis.run,
            AgentState.ReportDrafting: report_drafting.run,
            AgentState.AskUser: ask_user.run,
        }

    async def run(
        self,
        session_id: str,
        turn_id: str,
        user_message: str,
        force_code_investigation: bool = False,
    ) -> AsyncIterator[AgentEvent]:
        state = AgentState.Initialize
        ctx = await self._build_context(
            session_id,
            turn_id,
            user_message,
            force_code_investigation,
        )

        while state != AgentState.Terminate:
            await self._trace.log_stage_enter(
                session_id,
                turn_id,
                state.value,
                {"question": user_message, "evidence_count": len(ctx.collected_evidence)},
            )
            stage_fn = self._stage_dispatch[state]
            try:
                result = await stage_fn(ctx)
            except Exception as exc:
                await self._trace.log_stage_exit(
                    session_id,
                    turn_id,
                    state.value,
                    {"error": type(exc).__name__},
                )
                yield AgentEvent(
                    type="error",
                    data={
                        "code": "STAGE_FAILED",
                        "stage": state.value,
                        "message": str(exc),
                    },
                )
                return

            for event in result.events:
                yield event

            ctx = self._merge(ctx, result)
            await self._trace.log_stage_exit(
                session_id,
                turn_id,
                state.value,
                {"next": result.next_state.value},
            )
            if not is_valid_transition(state, result.next_state):
                yield AgentEvent(
                    type="error",
                    data={
                        "code": "INVALID_TRANSITION",
                        "message": f"{state.value}->{result.next_state.value}",
                    },
                )
                return

            previous = state
            state = result.next_state
            yield AgentEvent(
                type="stage_transition",
                data={"from": previous.value, "to": state.value, "message": None},
            )
            if state == AgentState.AskUser:
                return

        yield AgentEvent(type="done", data={"turn_id": turn_id})

    async def _build_context(
        self,
        session_id: str,
        turn_id: str,
        user_message: str,
        force_code_investigation: bool,
    ) -> StageContext:
        async with self._session_factory() as session:
            session_row = (
                await session.execute(select(SessionModel).where(SessionModel.id == session_id))
            ).scalar_one()
            feature_rows = (await session.execute(select(Feature).order_by(Feature.id))).scalars()
            repo_rows = (
                await session.execute(
                    select(SessionRepoBinding).where(SessionRepoBinding.session_id == session_id)
                )
            ).scalars()
            turn_rows = (
                await session.execute(
                    select(SessionTurn)
                    .where(SessionTurn.session_id == session_id)
                    .order_by(SessionTurn.turn_index, SessionTurn.created_at)
                )
            ).scalars()

            features = list(feature_rows)
            repos = list(repo_rows)
            turns = list(turn_rows)

        prompt_context = PromptContext(
            user_question=user_message,
            feature_digests=[
                FeatureDigest(
                    feature_id=feature.id,
                    summary_text=feature.summary_text or feature.description,
                    navigation_index=(
                        str(feature.navigation_index_json)
                        if feature.navigation_index_json is not None
                        else None
                    ),
                )
                for feature in features
            ],
            repo_bindings=[
                RepoBinding(
                    repo_id=repo.repo_id,
                    commit_sha=repo.commit_sha,
                    paths=[repo.worktree_path],
                )
                for repo in repos
            ],
            turn_history=_turn_history(turns, current_turn_id=turn_id),
        )
        return StageContext(
            session_id=session_id,
            turn_id=turn_id,
            prompt_context=prompt_context,
            llm_client=_GatewayStageClient(self._gateway),
            tool_registry=self._tool_registry,
            trace_logger=self._trace,
            collected_evidence=[],
            force_code_investigation=force_code_investigation,
            subject_id=session_row.created_by_subject_id,
            wiki_search_service=self._wiki_search_service,
            code_search_service=self._code_search_service,
            attachment_repo=self._attachment_repo,
        )

    async def _initialize(self, ctx: StageContext) -> StageResult:
        return StageResult(next_state=AgentState.InputAnalysis)

    def _merge(self, ctx: StageContext, result: StageResult) -> StageContext:
        prompt_context = replace(
            ctx.prompt_context,
            turn_history=[
                *ctx.prompt_context.turn_history,
                *result.messages_appended,
            ],
        )
        return replace(
            ctx,
            prompt_context=prompt_context,
            collected_evidence=[*ctx.collected_evidence, *result.evidence_added],
        )


def _turn_history(
    turns: list[SessionTurn],
    *,
    current_turn_id: str,
) -> list[LLMMessage]:
    messages: list[LLMMessage] = []
    for turn in turns:
        if turn.id == current_turn_id:
            continue
        role: Literal["assistant", "user"] = "assistant" if turn.role == "agent" else "user"
        messages.append(
            LLMMessage(
                role=role,
                content=[TextBlock(type="text", text=turn.content)],
            )
        )
    return messages
