"""Orchestrator ask-user early stop path."""

from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from codeask.agent.orchestrator import AgentOrchestrator
from codeask.agent.tools import ToolRegistry
from codeask.agent.trace import AgentTraceLogger
from codeask.crypto import Crypto
from codeask.db import Base, create_engine, session_factory
from codeask.db.models import AgentTrace, Feature, Session, SessionTurn
from codeask.llm.gateway import ClientFactory, LLMGateway
from codeask.llm.repo import LLMConfigInput, LLMConfigRepo
from tests.mocks.mock_llm import MockLLMClient, tool_call_message


@pytest.mark.asyncio
async def test_low_confidence_scope_detection_asks_user(tmp_path: Path) -> None:
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

    mock = MockLLMClient(
        [
            tool_call_message(
                "tc_scope",
                "select_feature",
                {"feature_ids": [], "confidence": "low", "reason": "ambiguous"},
            )
        ]
    )
    gateway = LLMGateway(
        config_repo,
        ClientFactory(provider_clients={"openai": lambda **_: mock}),
        base_delay=0.0,
    )
    trace_logger = AgentTraceLogger(factory)
    registry = ToolRegistry.bootstrap()

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
                content="这个 500 是哪个功能？",
                evidence=None,
            )
        )
        await session.commit()

    agent = AgentOrchestrator(
        gateway=gateway,
        tool_registry=registry,
        trace_logger=trace_logger,
        session_factory=factory,
    )

    events = [event async for event in agent.run("sess_1", "turn_1", "这个 500 是哪个功能？")]
    event_types = [event.type for event in events]

    assert "ask_user" in event_types
    assert event_types[-1] == "ask_user"
    assert "done" not in event_types

    async with factory() as session:
        traces = (await session.execute(select(AgentTrace))).scalars().all()

    assert any(trace.event_type == "scope_decision" for trace in traces)
    assert not any(trace.event_type == "sufficiency_decision" for trace in traces)
    await engine.dispose()
