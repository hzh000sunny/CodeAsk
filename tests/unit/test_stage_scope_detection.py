"""ScopeDetection stage A2 hooks."""

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from codeask.agent.prompts import FeatureDigest, PromptContext
from codeask.agent.stages import StageContext, scope_detection
from codeask.agent.state import AgentState
from codeask.agent.tools import ToolRegistry
from codeask.agent.trace import AgentTraceLogger
from codeask.db import Base, create_engine, session_factory
from codeask.db.models import AgentTrace, Session, SessionTurn
from tests.mocks.mock_llm import MockLLMClient, tool_call_message


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


def _prompt_context() -> PromptContext:
    return PromptContext(
        user_question="订单超时怎么处理？",
        feature_digests=[FeatureDigest(feature_id=1, summary_text="订单域")],
    )


@pytest.mark.asyncio
async def test_high_confidence_goes_to_knowledge_retrieval(seeded_trace) -> None:  # type: ignore[no-untyped-def]
    factory, trace_logger = seeded_trace
    client = MockLLMClient(
        [
            tool_call_message(
                "tc_1",
                "select_feature",
                {"feature_ids": [1], "confidence": "high", "reason": "order keyword"},
            )
        ]
    )
    ctx = StageContext(
        session_id="sess_1",
        turn_id="turn_1",
        prompt_context=_prompt_context(),
        llm_client=client,
        tool_registry=ToolRegistry.bootstrap(),
        trace_logger=trace_logger,
    )

    result = await scope_detection.run(ctx)

    assert result.next_state == AgentState.KnowledgeRetrieval
    assert [event.type for event in result.events] == ["scope_detection"]
    async with factory() as session:
        trace = (
            await session.execute(
                select(AgentTrace).where(AgentTrace.event_type == "scope_decision")
            )
        ).scalar_one()
        assert trace.payload["output"]["confidence"] == "high"


@pytest.mark.asyncio
async def test_low_confidence_goes_to_ask_user(seeded_trace) -> None:  # type: ignore[no-untyped-def]
    _, trace_logger = seeded_trace
    client = MockLLMClient(
        [
            tool_call_message(
                "tc_1",
                "select_feature",
                {"feature_ids": [], "confidence": "low", "reason": "ambiguous"},
            )
        ]
    )
    ctx = StageContext(
        session_id="sess_1",
        turn_id="turn_1",
        prompt_context=_prompt_context(),
        llm_client=client,
        tool_registry=ToolRegistry.bootstrap(),
        trace_logger=trace_logger,
    )

    result = await scope_detection.run(ctx)

    assert result.next_state == AgentState.AskUser
    assert [event.type for event in result.events] == ["scope_detection", "ask_user"]
