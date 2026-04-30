"""SufficiencyJudgement stage A3 hooks."""

import json
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from codeask.agent.prompts import KnowledgeHit, PromptContext
from codeask.agent.stages import Evidence, StageContext, sufficiency_judgement
from codeask.agent.state import AgentState
from codeask.agent.trace import AgentTraceLogger
from codeask.db import Base, create_engine, session_factory
from codeask.db.models import AgentTrace, Session, SessionTurn
from tests.mocks.mock_llm import MockLLMClient, text_message


@pytest_asyncio.fixture()
async def seeded_trace(tmp_path: Path):  # type: ignore[no-untyped-def]
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = session_factory(engine)
    async with factory() as session:
        session.add(Session(id="sess_1", title="t", created_by_subject_id="x", status="active"))
        session.add(
            SessionTurn(
                id="turn_1",
                session_id="sess_1",
                turn_index=0,
                role="user",
                content="q",
                evidence=None,
            )
        )
        await session.commit()
    yield factory, AgentTraceLogger(factory)
    await engine.dispose()


def _ctx(trace_logger: AgentTraceLogger, verdict: str, *, force: bool = False) -> StageContext:
    client = MockLLMClient(
        [
            text_message(
                json.dumps(
                    {
                        "verdict": verdict,
                        "reason": "docs are not enough",
                        "next": "code_investigation",
                    }
                )
            )
        ]
    )
    return StageContext(
        session_id="sess_1",
        turn_id="turn_1",
        prompt_context=PromptContext(
            user_question="订单超时怎么处理？",
            pre_retrieval_hits=[KnowledgeHit(source="doc", title="订单文档", summary="部分说明")],
        ),
        llm_client=client,
        trace_logger=trace_logger,
        collected_evidence=[
            Evidence(id="ev1", type="wiki_doc", summary="部分说明", relevance="medium")
        ],
        force_code_investigation=force,
    )


@pytest.mark.asyncio
async def test_insufficient_goes_to_code_investigation(seeded_trace) -> None:  # type: ignore[no-untyped-def]
    factory, trace_logger = seeded_trace
    result = await sufficiency_judgement.run(_ctx(trace_logger, "insufficient"))

    assert result.next_state == AgentState.CodeInvestigation
    assert [event.type for event in result.events] == ["sufficiency_judgement"]
    async with factory() as session:
        trace = (
            await session.execute(
                select(AgentTrace).where(AgentTrace.event_type == "sufficiency_decision")
            )
        ).scalar_one()
        assert trace.payload["output"]["verdict"] == "insufficient"


@pytest.mark.asyncio
async def test_enough_goes_to_answer_finalization(seeded_trace) -> None:  # type: ignore[no-untyped-def]
    _, trace_logger = seeded_trace
    result = await sufficiency_judgement.run(_ctx(trace_logger, "enough"))
    assert result.next_state == AgentState.AnswerFinalization


@pytest.mark.asyncio
async def test_force_code_investigation_overrides_enough(seeded_trace) -> None:  # type: ignore[no-untyped-def]
    _, trace_logger = seeded_trace
    result = await sufficiency_judgement.run(_ctx(trace_logger, "enough", force=True))
    assert result.next_state == AgentState.CodeInvestigation
