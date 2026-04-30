"""Orchestrator paths that require code investigation."""

from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from codeask.agent.orchestrator import AgentOrchestrator
from codeask.agent.tools import ToolRegistry, ToolResult
from codeask.agent.trace import AgentTraceLogger
from codeask.crypto import Crypto
from codeask.db import Base, create_engine, session_factory
from codeask.db.models import AgentTrace, Feature, Session, SessionTurn
from codeask.llm.gateway import ClientFactory, LLMGateway
from codeask.llm.repo import LLMConfigInput, LLMConfigRepo
from codeask.llm.types import LLMEvent
from tests.mocks.mock_llm import MockLLMClient, text_message, tool_call_message


async def _build_agent(tmp_path: Path, scripts: list[list[LLMEvent]]):  # type: ignore[no-untyped-def]
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = session_factory(engine)
    crypto = Crypto(Fernet.generate_key().decode())
    config_repo = LLMConfigRepo(factory, crypto)
    await config_repo.create(
        LLMConfigInput(
            name="default",
            protocol="openai",
            base_url=None,
            api_key="x",
            model_name="m",
            max_tokens=100,
            temperature=0.0,
            is_default=True,
        )
    )

    mock = MockLLMClient(scripts)
    gateway = LLMGateway(
        config_repo,
        ClientFactory(provider_clients={"openai": lambda **_: mock}),
        base_delay=0.0,
    )
    trace_logger = AgentTraceLogger(factory)

    class FakeWikiService:
        async def search(self, query, feature_ids, top_k=10):  # type: ignore[no-untyped-def]
            return [
                {
                    "id": "doc_1",
                    "source": "doc",
                    "title": "OrderService timeout",
                    "summary": "OrderService timeout doc",
                    "score": 0.9,
                }
            ]

    class FakeCodeService:
        async def grep_code(self, args, ctx):  # type: ignore[no-untyped-def]
            return ToolResult(
                ok=True,
                summary="OrderService code path",
                data={"path": "src/orders/service.py", "line": 42},
            )

    wiki_service = FakeWikiService()
    code_service = FakeCodeService()
    registry = ToolRegistry.bootstrap(
        wiki_search_service=wiki_service,
        code_search_service=code_service,
        attachment_repo=None,
    )

    async with factory() as session:
        session.add(
            Feature(
                id=1,
                name="订单域",
                slug="orders",
                description="订单问题知识库",
                owner_subject_id="alice@dev-1",
                summary_text="订单域知识",
            )
        )
        session.add(
            Session(
                id="sess_1",
                title="t",
                created_by_subject_id="alice@dev-1",
                status="active",
            )
        )
        session.add(
            SessionTurn(
                id="turn_1",
                session_id="sess_1",
                turn_index=0,
                role="user",
                content="为什么订单偶发 500",
                evidence=None,
            )
        )
        await session.commit()

    agent = AgentOrchestrator(
        gateway=gateway,
        tool_registry=registry,
        trace_logger=trace_logger,
        session_factory=factory,
        wiki_search_service=wiki_service,
        code_search_service=code_service,
    )
    return agent, factory, engine


def _scope_high() -> list[LLMEvent]:
    return tool_call_message(
        "tc_scope",
        "select_feature",
        {"feature_ids": [1], "confidence": "high", "reason": "order domain"},
    )


def _code_tool_call() -> list[LLMEvent]:
    return tool_call_message(
        "tc_code",
        "grep_code",
        {
            "repo_id": "repo_1",
            "commit_sha": "abc1234",
            "query": "OrderService",
            "path_glob": None,
        },
    )


@pytest.mark.asyncio
async def test_insufficient_path_runs_code_investigation(tmp_path: Path) -> None:
    agent, factory, engine = await _build_agent(
        tmp_path,
        [
            _scope_high(),
            text_message(
                '{"verdict":"insufficient","reason":"need code","next":"code_investigation"}'
            ),
            _code_tool_call(),
            text_message(""),
            text_message("结论：代码路径显示 OrderService 可能返回 500。"),
        ],
    )

    events = [event async for event in agent.run("sess_1", "turn_1", "为什么订单偶发 500")]
    event_types = [event.type for event in events]

    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "evidence" in event_types
    assert event_types[-1] == "done"

    async with factory() as session:
        traces = (await session.execute(select(AgentTrace))).scalars().all()
        turn = (
            await session.execute(select(SessionTurn).where(SessionTurn.id == "turn_1"))
        ).scalar_one()

    assert any(
        trace.event_type == "stage_enter" and trace.stage == "code_investigation"
        for trace in traces
    )
    assert turn.evidence is not None
    evidence_types = [item["type"] for item in turn.evidence["items"]]
    assert evidence_types == ["wiki_doc", "code"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_force_code_investigation_overrides_enough(tmp_path: Path) -> None:
    agent, factory, engine = await _build_agent(
        tmp_path,
        [
            _scope_high(),
            text_message(
                '{"verdict":"enough","reason":"docs cover it","next":"answer_finalization"}'
            ),
            _code_tool_call(),
            text_message(""),
            text_message("结论：强制深查后仍返回代码证据。"),
        ],
    )

    events = [
        event
        async for event in agent.run(
            "sess_1",
            "turn_1",
            "为什么订单偶发 500",
            force_code_investigation=True,
        )
    ]
    event_types = [event.type for event in events]

    assert "tool_call" in event_types
    async with factory() as session:
        traces = (await session.execute(select(AgentTrace))).scalars().all()
    assert any(
        trace.event_type == "stage_enter" and trace.stage == "code_investigation"
        for trace in traces
    )
    await engine.dispose()
