"""SufficiencyJudgement stage A3 hooks."""

import json
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from codeask.agent.prompts import KnowledgeHit, PromptContext, RepoBinding
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


def _ctx(
    trace_logger: AgentTraceLogger,
    verdict: str,
    *,
    force: bool = False,
    with_repo_binding: bool = False,
) -> StageContext:
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
            repo_bindings=(
                [RepoBinding(repo_id="repo_1", commit_sha="abc123", paths=["src/orders"])]
                if with_repo_binding
                else []
            ),
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
    result = await sufficiency_judgement.run(
        _ctx(trace_logger, "insufficient", with_repo_binding=True)
    )

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


def test_parse_decision_falls_back_to_enough_for_plain_text_sufficiency_summary() -> None:
    raw = """
当前信息充分性判断

已获取到小米的病历信息，可以从现有记录中初步识别病情变化趋势。
当前信息足以支持回答。
""".strip()

    parsed = sufficiency_judgement._parse_decision(raw)

    assert parsed["verdict"] == "enough"
    assert parsed["reason"] == "inferred enough from plain-text sufficiency response"


def test_parse_decision_falls_back_to_partial_for_plain_text_partial_summary() -> None:
    raw = """
## 充分性判断

判断结果：⚠️ 部分充分

可以基于现有证据给出有限的趋势分析，但无法完整回答病情变化趋势。
""".strip()

    parsed = sufficiency_judgement._parse_decision(raw)

    assert parsed["verdict"] == "partial"
    assert parsed["reason"] == "inferred partial from plain-text sufficiency response"


@pytest.mark.asyncio
async def test_partial_without_repo_bindings_goes_to_answer_finalization(
    seeded_trace,
) -> None:  # type: ignore[no-untyped-def]
    _, trace_logger = seeded_trace
    result = await sufficiency_judgement.run(_ctx(trace_logger, "partial"))
    assert result.next_state == AgentState.AnswerFinalization


@pytest.mark.asyncio
async def test_insufficient_without_repo_bindings_but_with_evidence_goes_to_answer_finalization(
    seeded_trace,
) -> None:  # type: ignore[no-untyped-def]
    _, trace_logger = seeded_trace
    result = await sufficiency_judgement.run(_ctx(trace_logger, "insufficient"))
    assert result.next_state == AgentState.AnswerFinalization
