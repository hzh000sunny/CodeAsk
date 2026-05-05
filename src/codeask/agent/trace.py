"""Append-only writer for agent trace rows."""

from secrets import token_hex
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.db.models import AgentTrace
from codeask.llm.types import LLMEvent


class AgentTraceLogger:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def log(
        self,
        session_id: str,
        turn_id: str,
        stage: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        async with self._session_factory() as session:
            session.add(
                AgentTrace(
                    id=f"tr_{token_hex(8)}",
                    session_id=session_id,
                    turn_id=turn_id,
                    stage=stage,
                    event_type=event_type,
                    payload=payload,
                )
            )
            await session.commit()

    async def log_stage_enter(
        self,
        session_id: str,
        turn_id: str,
        stage: str,
        context: dict[str, Any],
    ) -> None:
        await self.log(session_id, turn_id, stage, "stage_enter", {"context": context})

    async def log_stage_exit(
        self,
        session_id: str,
        turn_id: str,
        stage: str,
        result: dict[str, Any],
    ) -> None:
        await self.log(session_id, turn_id, stage, "stage_exit", {"result": result})

    async def log_llm_input(
        self,
        session_id: str,
        turn_id: str,
        stage: str,
        prompt_summary: dict[str, Any],
    ) -> None:
        await self.log(session_id, turn_id, stage, "llm_input", prompt_summary)

    async def log_llm_event(
        self,
        session_id: str,
        turn_id: str,
        stage: str,
        event: LLMEvent,
    ) -> None:
        await self.log(session_id, turn_id, stage, "llm_event", event.model_dump())

    async def log_tool_call(
        self,
        session_id: str,
        turn_id: str,
        stage: str,
        name: str,
        args: dict[str, Any],
        call_id: str,
    ) -> None:
        await self.log(
            session_id,
            turn_id,
            stage,
            "tool_call",
            {"id": call_id, "name": name, "arguments": args},
        )

    async def log_tool_result(
        self,
        session_id: str,
        turn_id: str,
        stage: str,
        call_id: str,
        result: dict[str, Any],
    ) -> None:
        await self.log(
            session_id,
            turn_id,
            stage,
            "tool_result",
            {"id": call_id, "result": result},
        )

    async def log_scope_decision(
        self,
        session_id: str,
        turn_id: str,
        input_ctx: dict[str, Any],
        output: dict[str, Any],
    ) -> None:
        await self.log(
            session_id,
            turn_id,
            "scope_detection",
            "scope_decision",
            {"input": input_ctx, "output": output},
        )

    async def log_sufficiency_decision(
        self,
        session_id: str,
        turn_id: str,
        input_ctx: dict[str, Any],
        output: dict[str, Any],
    ) -> None:
        await self.log(
            session_id,
            turn_id,
            "sufficiency_judgement",
            "sufficiency_decision",
            {"input": input_ctx, "output": output},
        )

    async def log_wiki_scope_resolution(
        self,
        session_id: str,
        turn_id: str,
        payload: dict[str, Any],
    ) -> None:
        await self.log(
            session_id,
            turn_id,
            "knowledge_retrieval",
            "wiki_scope_resolution",
            payload,
        )

    async def log_user_feedback(
        self,
        session_id: str,
        turn_id: str,
        feedback: dict[str, Any],
    ) -> None:
        await self.log(session_id, turn_id, "terminate", "user_feedback", feedback)
