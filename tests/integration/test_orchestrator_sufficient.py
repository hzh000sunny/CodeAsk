"""Full happy path: knowledge sufficient, no code investigation."""

from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy import select

from codeask.agent.orchestrator import AgentOrchestrator
from codeask.agent.tools import ToolRegistry
from codeask.agent.trace import AgentTraceLogger
from codeask.crypto import Crypto
from codeask.db import Base, create_engine, session_factory
from codeask.db.models import AgentTrace, Feature, Session, SessionAttachment, SessionTurn
from codeask.llm.gateway import ClientFactory, LLMGateway
from codeask.llm.repo import LLMConfigInput, LLMConfigRepo
from tests.mocks.mock_llm import MockLLMClient, text_message, tool_call_message


@pytest_asyncio.fixture()
async def orchestrator(tmp_path: Path):  # type: ignore[no-untyped-def]
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

    scope = tool_call_message(
        "tc_scope",
        "select_feature",
        {"feature_ids": [1], "confidence": "high", "reason": "order domain"},
    )
    sufficiency = text_message(
        '{"verdict":"enough","reason":"docs cover this","next":"answer_finalization"}'
    )
    answer = text_message("结论：可能用户上下文为空。证据 [ev_knowledge_1].")
    mock = MockLLMClient([scope, sufficiency, answer])
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
            return {"items": []}

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
        session.add(
            SessionAttachment(
                id="att_log",
                session_id="sess_1",
                kind="log",
                display_name="db-node-a.log",
                original_filename="service.log",
                aliases_json=["service.log", "db-node-a.log"],
                description="数据库节点 A 的启动日志",
                file_path=str(tmp_path / "sessions" / "sess_1" / "att_log.log"),
                mime_type="text/plain",
                size_bytes=256,
            )
        )
        await session.commit()

    yield (
        AgentOrchestrator(
            gateway=gateway,
            tool_registry=registry,
            trace_logger=trace_logger,
            session_factory=factory,
            wiki_search_service=wiki_service,
            code_search_service=code_service,
        ),
        factory,
        mock,
    )
    await engine.dispose()


@pytest.mark.asyncio
async def test_full_happy_path(orchestrator) -> None:  # type: ignore[no-untyped-def]
    agent, factory, _mock = orchestrator

    events = [event async for event in agent.run("sess_1", "turn_1", "为什么订单偶发 500")]
    event_types = [event.type for event in events]

    assert "scope_detection" in event_types
    assert "evidence" in event_types
    assert "sufficiency_judgement" in event_types
    assert "text_delta" in event_types
    assert event_types[-1] == "done"
    assert event_types.count("done") == 1

    async with factory() as session:
        traces = (
            (
                await session.execute(
                    select(AgentTrace).order_by(AgentTrace.created_at, AgentTrace.id)
                )
            )
            .scalars()
            .all()
        )

    assert any(trace.event_type == "scope_decision" for trace in traces)
    assert any(trace.event_type == "sufficiency_decision" for trace in traces)
    assert any(
        trace.event_type == "stage_enter" and trace.stage == "answer_finalization"
        for trace in traces
    )


@pytest.mark.asyncio
async def test_orchestrator_includes_attachment_mapping_in_prompt(orchestrator) -> None:  # type: ignore[no-untyped-def]
    agent, _factory, mock = orchestrator

    _events = [
        event
        async for event in agent.run(
            "sess_1", "turn_1", "service.log 是节点 A 的日志，先看启动失败"
        )
    ]

    first_call_text = _call_text(mock.calls[0])
    assert "attachment_summaries" in first_call_text
    assert "att_log" in first_call_text
    assert "db-node-a.log" in first_call_text
    assert "service.log" in first_call_text
    assert "att_log.log" in first_call_text
    assert "数据库节点 A 的启动日志" in first_call_text
    assert "reference_names" in first_call_text


def _call_text(call: dict[str, object]) -> str:
    messages = call["messages"]
    assert isinstance(messages, list)
    text_parts: list[str] = []
    for message in messages:
        assert isinstance(message, dict)
        content = message["content"]
        assert isinstance(content, list)
        for block in content:
            assert isinstance(block, dict)
            if block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
    return "\n".join(text_parts)
