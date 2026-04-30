# Agent Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 CodeAsk 9 阶段 Agent 状态机：LLM 网关（OpenAI / OpenAI-compatible / Anthropic 三协议归一化）、ToolRegistry（包装 wiki + code 工具 + ask_user）、SSE 流式输出、ScopeDetection / SufficiencyJudgement / CodeInvestigation / AnswerSynthesis 等阶段、agent_traces 完整落库，以及 `/api/llm-configs` / `/api/sessions` / `/api/skills` 三组 API。

**Architecture:** Agent 主循环由 `AgentOrchestrator` 驱动；每阶段调用 LLM 网关 + 工具，事件统一走 `SSEMultiplexer`；LLM 网关用 LiteLLM 包一层但内部仍按 SDD 接口暴露 `LLMEvent`；工具实现委托 02 wiki-knowledge plan 的 search service 和 03 code-index plan 的 grep/read/symbols 服务；所有阶段事件、LLM 输入/输出、工具调用都按行写入 `agent_traces`，保证调查过程可回放可审计。一期 LLM 错误用结构化 `LLMError` 模型 + 指数退避最多 3 次；工具错误用结构化 `ToolResult.error_code` 回填给模型而不中断会话。

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 async, LiteLLM, tiktoken, Pydantic v2, SSE (StreamingResponse), pytest, pytest-asyncio

**Source SDD docs**（路径相对本文件 `docs/v1.0/plans/agent-runtime.md`）：
- `../design/api-data-model.md`
- `../design/agent-runtime.md`
- `../design/llm-gateway.md`
- `../design/tools.md`
- `../design/debugging-workflow.md`
- `../design/evidence-report.md`
- `../design/session-input.md`
- `../design/dependencies.md`

**Depends on:** `docs/v1.0/plans/foundation.md`、`docs/v1.0/plans/wiki-knowledge.md`、`docs/v1.0/plans/code-index.md`

**Project root:** `/home/hzh/workspace/CodeAsk/`（与 `docs/` 同级）。本计划全部文件路径相对此根目录。

**SDD inconsistency tracked here:** `llm-gateway.md` §8 用 `CODEASK_MASTER_KEY`，但 `deployment-security.md` §5 + `foundation.md` 已锁定 `CODEASK_DATA_KEY`。foundation handoff §5 把这条记账给本计划——本计划在 Task 2 同步把 `llm-gateway.md` §8 改为 `CODEASK_DATA_KEY`，并在该 commit message 中注明。

---

## File Structure

本计划交付以下新增文件（全部相对项目根 `/home/hzh/workspace/CodeAsk/`）：

```text
CodeAsk/
├── alembic/versions/
│   ├── 20260430_0007_llm_configs.py
│   ├── 20260430_0008_skills.py
│   ├── 20260430_0009_sessions.py
│   ├── 20260430_0010_session_features_repo_bindings.py
│   ├── 20260430_0011_session_turns_attachments.py
│   └── 20260430_0012_agent_traces.py
├── src/codeask/
│   ├── db/models/
│   │   ├── llm.py                     # LLMConfig
│   │   ├── skill.py                   # Skill
│   │   ├── session.py                 # Session, SessionFeature, SessionRepoBinding,
│   │   │                              #   SessionTurn, SessionAttachment
│   │   └── agent.py                   # AgentTrace
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── types.py                   # LLMRequest / LLMMessage / blocks / ToolDef
│   │   │                              #   / LLMEvent / LLMError / StopReason
│   │   ├── client.py                  # LLMClient Protocol + 3 LiteLLM-backed impls
│   │   ├── gateway.py                 # LLMGateway (config repo + retry + factory)
│   │   └── repo.py                    # LLMConfigRepo (CRUD + Crypto)
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── state.py                   # AgentState enum + StageTransition
│   │   ├── prompts.py                 # L0..L6 prompt builders (Jinja2)
│   │   ├── tools.py                   # ToolRegistry + ToolContext + ToolResult
│   │   ├── trace.py                   # AgentTraceLogger
│   │   ├── sse.py                     # SSEMultiplexer + AgentEvent
│   │   ├── orchestrator.py            # AgentOrchestrator.run()
│   │   └── stages/
│   │       ├── __init__.py
│   │       ├── input_analysis.py
│   │       ├── scope_detection.py
│   │       ├── knowledge_retrieval.py
│   │       ├── sufficiency_judgement.py
│   │       ├── code_investigation.py
│   │       ├── version_confirmation.py
│   │       ├── evidence_synthesis.py
│   │       ├── answer_finalization.py
│   │       ├── report_drafting.py
│   │       └── ask_user.py
│   ├── api/
│   │   ├── llm_configs.py             # /api/llm-configs CRUD
│   │   ├── sessions.py                # /api/sessions + messages SSE + attachments
│   │   ├── skills.py                  # /api/skills CRUD
│   │   └── schemas/
│   │       ├── __init__.py
│   │       ├── llm_config.py
│   │       ├── session.py
│   │       └── skill.py
│   └── (existing) app.py, settings.py, crypto.py, identity.py, ...
└── tests/
    ├── mocks/
    │   ├── __init__.py
    │   └── mock_llm.py                # MockLLMClient
    ├── unit/
    │   ├── test_llm_types.py
    │   ├── test_llm_gateway.py
    │   ├── test_tool_registry.py
    │   ├── test_agent_state.py
    │   ├── test_sse.py
    │   └── test_trace.py
    └── integration/
        ├── test_llm_configs_api.py
        ├── test_skills_api.py
        ├── test_sessions_api.py
        ├── test_orchestrator_sufficient.py
        ├── test_orchestrator_insufficient.py
        └── test_orchestrator_ask_user.py
```

**职责边界**：
- `llm/types.py` 只定义 Pydantic 模型——无业务逻辑、无副作用
- `llm/client.py` 只翻译协议——LiteLLM streaming 转 LLMEvent；不知道 Agent 状态机
- `llm/gateway.py` 持有 client factory + config repo + 重试；不知道工具
- `llm/repo.py` 只做 LLMConfig CRUD + 加解密
- `agent/state.py` 只定义枚举和合法迁移
- `agent/prompts.py` 只组装 messages——读 wiki digest / repo binding / 历史 turns
- `agent/tools.py` 是工具注册表 + 校验层；具体工具实现委托 wiki / code_index 服务
- `agent/trace.py` 只写 agent_traces 表
- `agent/sse.py` 只把 AgentEvent 序列化为 SSE 帧
- `agent/orchestrator.py` 是控制流——按状态机驱动 LLM + 工具 + 证据归并
- `agent/stages/*.py` 每个阶段一个模块，提供 `run(ctx) -> StageResult`
- `api/llm_configs.py` / `sessions.py` / `skills.py` 只编排 HTTP——通过 `app.state.session_factory` 拿 DB session
- `tests/mocks/mock_llm.py` 提供脚本化 LLMEvent 回放

---

## Task 1: ORM 模型 — llm_configs（含 Fernet 加密字段）

**Files:**
- Create: `src/codeask/db/models/llm.py`
- Modify: `src/codeask/db/models/__init__.py`
- Create: `alembic/versions/20260430_0007_llm_configs.py`
- Create: `tests/integration/test_llm_config_model.py`

按 `llm-gateway.md` §8 + `api-data-model.md` §3 落地。`api_key_encrypted` 用 `Crypto(settings.data_key)` 加解密；`is_default` 唯一（最多一条 `is_default=True`）。

**与 foundation handoff §1 的契约**：02 wiki-knowledge plan 占 0002-0005、03 code-index plan 占 0006，本 plan 从 0007 起递增到 0012（共 6 份 migration）。后续 06 metrics-eval plan 接 0013。

- [ ] **Step 1: 写测试 `tests/integration/test_llm_config_model.py`**

```python
"""Round-trip + uniqueness for llm_configs."""

from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from codeask.crypto import Crypto
from codeask.db import Base, create_engine, session_factory
from codeask.db.models import LLMConfig


@pytest_asyncio.fixture()
async def engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    eng = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_round_trip_with_encryption(engine) -> None:  # type: ignore[no-untyped-def]
    crypto = Crypto(Fernet.generate_key().decode())
    cipher = crypto.encrypt("sk-real-key-123")
    factory = session_factory(engine)
    async with factory() as s:
        s.add(
            LLMConfig(
                id="cfg_1",
                name="default openai",
                protocol="openai",
                base_url=None,
                api_key_encrypted=cipher,
                model_name="gpt-4o",
                max_tokens=4096,
                temperature=0.2,
                is_default=True,
            )
        )
        await s.commit()

    async with factory() as s:
        row = (await s.execute(select(LLMConfig))).scalar_one()
        assert crypto.decrypt(row.api_key_encrypted) == "sk-real-key-123"
        assert row.protocol == "openai"
        assert row.is_default is True


@pytest.mark.asyncio
async def test_only_one_default_allowed(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        s.add(
            LLMConfig(
                id="cfg_a", name="a", protocol="openai",
                api_key_encrypted="x", model_name="m",
                max_tokens=1, temperature=0.0, is_default=True,
            )
        )
        s.add(
            LLMConfig(
                id="cfg_b", name="b", protocol="openai",
                api_key_encrypted="x", model_name="m",
                max_tokens=1, temperature=0.0, is_default=True,
            )
        )
        with pytest.raises(IntegrityError):
            await s.commit()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/integration/test_llm_config_model.py -v`
Expected: ImportError on `LLMConfig`

- [ ] **Step 3: 创建 `src/codeask/db/models/llm.py`**

```python
"""llm_configs: provider-neutral LLM configuration with encrypted API key."""

from sqlalchemy import Boolean, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class LLMConfig(Base, TimestampMixin):
    __tablename__ = "llm_configs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    protocol: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    api_key_encrypted: Mapped[str] = mapped_column(String(2048), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4096)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        # SQLite partial unique index: at most one row with is_default=1.
        Index(
            "ix_llm_configs_only_one_default",
            "is_default",
            unique=True,
            sqlite_where=Boolean().literal_processor(None)
            if False  # placeholder; real filter set in migration
            else None,
        ),
        UniqueConstraint("name", name="uq_llm_configs_name"),
    )
```

> 实施提示：上述 `Index` 的 `sqlite_where` 占位无法直接编译，**真正的 partial unique 由 0007 migration 用 `op.create_index(..., sqlite_where=sa.text("is_default = 1"))` 创建**。`Base.metadata.create_all` 路径（仅测试用）由 `protocol IN (...)` check 约束补不齐，因此我们在 ORM 层只声明 `name` 唯一，把"最多一行 is_default"完全交给 migration / repo 层。

把 `Index(...)` 行整体删掉，改为：

```python
    __table_args__ = (
        UniqueConstraint("name", name="uq_llm_configs_name"),
    )
```

并在 Task 8 `LLMConfigRepo.save_default` 中用事务 + 显式 SELECT 保证唯一性，partial unique index 由 migration 提供生产保护。测试 `test_only_one_default_allowed` 改为通过 repo 层验证，Step 1 测试同步调整为：

```python
@pytest.mark.asyncio
async def test_unique_name(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        s.add(
            LLMConfig(
                id="cfg_a", name="dup", protocol="openai",
                api_key_encrypted="x", model_name="m",
                max_tokens=1, temperature=0.0, is_default=False,
            )
        )
        s.add(
            LLMConfig(
                id="cfg_b", name="dup", protocol="openai",
                api_key_encrypted="x", model_name="m",
                max_tokens=1, temperature=0.0, is_default=False,
            )
        )
        with pytest.raises(IntegrityError):
            await s.commit()
```

把第二个测试函数名替换为 `test_unique_name`，删除 `test_only_one_default_allowed`。

- [ ] **Step 4: 修改 `src/codeask/db/models/__init__.py`**

```python
"""ORM model definitions."""

from codeask.db.models.llm import LLMConfig
from codeask.db.models.system_settings import SystemSetting

__all__ = ["LLMConfig", "SystemSetting"]
```

- [ ] **Step 5: 创建 migration `alembic/versions/20260430_0007_llm_configs.py`**

```python
"""llm_configs

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-29 00:40:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_configs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("protocol", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.String(length=512), nullable=True),
        sa.Column("api_key_encrypted", sa.String(length=2048), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="4096"),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.2"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_llm_configs_name"),
        sa.CheckConstraint(
            "protocol IN ('openai', 'openai_compatible', 'anthropic')",
            name="ck_llm_configs_protocol",
        ),
    )
    op.create_index(
        "ix_llm_configs_only_one_default",
        "llm_configs",
        ["is_default"],
        unique=True,
        sqlite_where=sa.text("is_default = 1"),
    )


def downgrade() -> None:
    op.drop_index("ix_llm_configs_only_one_default", table_name="llm_configs")
    op.drop_table("llm_configs")
```

> 注：`down_revision="0006"` 假设 02 / 03 plan 共消耗 0002..0006 的 revision 范围。如果实际落地时这些 plan 用了更少 revision，本 plan 在执行前**必须**把 0007..0012 整体重新编号到接续上一份 plan 的最后一份，并修正各文件 `down_revision` 链。

- [ ] **Step 6: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_llm_config_model.py -v`
Expected: 两个测试 PASS

- [ ] **Step 7: 提交**

```bash
git add src/codeask/db/models/llm.py src/codeask/db/models/__init__.py \
    alembic/versions/20260430_0007_llm_configs.py \
    tests/integration/test_llm_config_model.py
git commit -m "feat(db): llm_configs table with encrypted api_key + protocol check"
```

---

## Task 2: ORM 模型 — sessions / session_features / session_repo_bindings + 同步修正 llm-gateway.md

**Files:**
- Create: `src/codeask/db/models/session.py`
- Modify: `src/codeask/db/models/__init__.py`
- Create: `alembic/versions/20260430_0009_sessions.py`
- Create: `alembic/versions/20260430_0010_session_features_repo_bindings.py`
- Create: `tests/integration/test_session_models.py`
- Modify: `docs/v1.0/design/llm-gateway.md`

按 `api-data-model.md` §3 + `session-input.md` §2 落地。

- [ ] **Step 1: 修正 `docs/v1.0/design/llm-gateway.md` §8**

把 §8 "API Key 使用 Fernet 加密，master key 来自 `CODEASK_MASTER_KEY`。" 改为 "API Key 使用 Fernet 加密，master key 来自 `CODEASK_DATA_KEY`（与 `deployment-security.md` §5 一致）。"

- [ ] **Step 2: 写测试 `tests/integration/test_session_models.py`**

```python
"""Round-trip + composite PK + FK cascade for session-related tables."""

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from codeask.db import Base, create_engine, session_factory
from codeask.db.models import Session, SessionFeature, SessionRepoBinding


@pytest_asyncio.fixture()
async def engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    eng = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_session_round_trip(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        s.add(
            Session(
                id="sess_1",
                title="排查订单 5xx",
                created_by_subject_id="alice@dev-1",
                status="active",
            )
        )
        await s.commit()
    async with factory() as s:
        row = (await s.execute(select(Session))).scalar_one()
        assert row.title == "排查订单 5xx"
        assert row.status == "active"


@pytest.mark.asyncio
async def test_session_features_composite_pk(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        s.add(Session(id="sess_2", title="t", created_by_subject_id="x", status="active"))
        s.add(SessionFeature(session_id="sess_2", feature_id="feat_a", source="auto"))
        s.add(SessionFeature(session_id="sess_2", feature_id="feat_b", source="manual"))
        await s.commit()
    async with factory() as s:
        rows = (await s.execute(select(SessionFeature))).scalars().all()
        assert {r.feature_id for r in rows} == {"feat_a", "feat_b"}


@pytest.mark.asyncio
async def test_repo_binding_composite_pk(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        s.add(Session(id="sess_3", title="t", created_by_subject_id="x", status="active"))
        s.add(
            SessionRepoBinding(
                session_id="sess_3",
                repo_id="repo_order",
                commit_sha="abc123",
                worktree_path="/tmp/wt/sess_3",
            )
        )
        await s.commit()
    async with factory() as s:
        row = (await s.execute(select(SessionRepoBinding))).scalar_one()
        assert row.commit_sha == "abc123"
```

- [ ] **Step 3: 跑测试确认失败**

Run: `uv run pytest tests/integration/test_session_models.py -v`
Expected: ImportError

- [ ] **Step 4: 创建 `src/codeask/db/models/session.py`（仅 Session / SessionFeature / SessionRepoBinding）**

```python
"""Session and its child binding tables."""

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class Session(Base, TimestampMixin):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    created_by_subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="ck_sessions_status"),
    )


class SessionFeature(Base):
    __tablename__ = "session_features"

    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    feature_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)

    __table_args__ = (
        CheckConstraint("source IN ('auto', 'manual')", name="ck_session_features_source"),
    )


class SessionRepoBinding(Base):
    __tablename__ = "session_repo_bindings"

    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    repo_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    commit_sha: Mapped[str] = mapped_column(String(64), primary_key=True)
    worktree_path: Mapped[str] = mapped_column(String(1024), nullable=False)
```

- [ ] **Step 5: 修改 `src/codeask/db/models/__init__.py`**

```python
"""ORM model definitions."""

from codeask.db.models.llm import LLMConfig
from codeask.db.models.session import Session, SessionFeature, SessionRepoBinding
from codeask.db.models.system_settings import SystemSetting

__all__ = [
    "LLMConfig",
    "Session",
    "SessionFeature",
    "SessionRepoBinding",
    "SystemSetting",
]
```

- [ ] **Step 6: 创建 migration `alembic/versions/20260430_0009_sessions.py`**

```python
"""sessions

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-29 00:42:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("created_by_subject_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_sessions_status"),
    )
    op.create_index("ix_sessions_subject", "sessions", ["created_by_subject_id"])


def downgrade() -> None:
    op.drop_index("ix_sessions_subject", table_name="sessions")
    op.drop_table("sessions")
```

- [ ] **Step 7: 创建 migration `alembic/versions/20260430_0010_session_features_repo_bindings.py`**

```python
"""session_features + session_repo_bindings

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-29 00:43:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "session_features",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("feature_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id", "feature_id"),
        sa.CheckConstraint("source IN ('auto', 'manual')", name="ck_session_features_source"),
    )
    op.create_table(
        "session_repo_bindings",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("repo_id", sa.String(length=64), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=False),
        sa.Column("worktree_path", sa.String(length=1024), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id", "repo_id", "commit_sha"),
    )


def downgrade() -> None:
    op.drop_table("session_repo_bindings")
    op.drop_table("session_features")
```

- [ ] **Step 8: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_session_models.py -v`
Expected: 三个测试 PASS

- [ ] **Step 9: 提交**

```bash
git add src/codeask/db/models/session.py src/codeask/db/models/__init__.py \
    alembic/versions/20260430_0009_sessions.py \
    alembic/versions/20260430_0010_session_features_repo_bindings.py \
    tests/integration/test_session_models.py \
    docs/v1.0/design/llm-gateway.md
git commit -m "feat(db): sessions + session_features + session_repo_bindings; align llm-gateway.md to CODEASK_DATA_KEY"
```

---

## Task 3: ORM 模型 — session_turns / session_attachments + skills

**Files:**
- Modify: `src/codeask/db/models/session.py`（追加 SessionTurn / SessionAttachment）
- Create: `src/codeask/db/models/skill.py`
- Modify: `src/codeask/db/models/__init__.py`
- Create: `alembic/versions/20260430_0008_skills.py`
- Create: `alembic/versions/20260430_0011_session_turns_attachments.py`
- Create: `tests/integration/test_turn_attachment_skill_models.py`

按 `api-data-model.md` §3 + `evidence-report.md` §3 + `wiki-search.md` §12 落地。

**说明 0008 vs 0009/0010 顺序**：skills 在 0008，sessions 在 0009（已建）；migration 链顺序是 0007(llm) → 0008(skills) → 0009(sessions) → 0010(session_features+bindings) → 0011(turns+attachments) → 0012(agent_traces)。本任务先建 0008 再建 0011。

- [ ] **Step 1: 写测试 `tests/integration/test_turn_attachment_skill_models.py`**

```python
"""Round-trip for session_turns / session_attachments / skills."""

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from codeask.db import Base, create_engine, session_factory
from codeask.db.models import Session, SessionAttachment, SessionTurn, Skill


@pytest_asyncio.fixture()
async def engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    eng = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_turn_round_trip(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        s.add(Session(id="sess_t", title="t", created_by_subject_id="x", status="active"))
        s.add(
            SessionTurn(
                id="turn_1",
                session_id="sess_t",
                turn_index=0,
                role="user",
                content="为什么订单偶发 500",
                evidence=None,
            )
        )
        s.add(
            SessionTurn(
                id="turn_2",
                session_id="sess_t",
                turn_index=1,
                role="agent",
                content="可能是用户上下文为空",
                evidence={"items": [{"id": "ev1", "type": "code"}]},
            )
        )
        await s.commit()
    async with factory() as s:
        rows = (
            await s.execute(select(SessionTurn).order_by(SessionTurn.turn_index))
        ).scalars().all()
        assert [r.role for r in rows] == ["user", "agent"]
        assert rows[1].evidence == {"items": [{"id": "ev1", "type": "code"}]}


@pytest.mark.asyncio
async def test_attachment_round_trip(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        s.add(Session(id="sess_a", title="t", created_by_subject_id="x", status="active"))
        s.add(
            SessionAttachment(
                id="att_1",
                session_id="sess_a",
                kind="log",
                file_path="/data/sessions/sess_a/x.log",
                mime_type="text/plain",
            )
        )
        await s.commit()
    async with factory() as s:
        row = (await s.execute(select(SessionAttachment))).scalar_one()
        assert row.kind == "log"


@pytest.mark.asyncio
async def test_skill_round_trip(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        s.add(Skill(id="sk_g", name="global default", scope="global", feature_id=None,
                    prompt_template="You are a helpful R&D assistant."))
        s.add(Skill(id="sk_f", name="order feature", scope="feature", feature_id="feat_order",
                    prompt_template="When asked about order flow..."))
        await s.commit()
    async with factory() as s:
        rows = (await s.execute(select(Skill).order_by(Skill.scope))).scalars().all()
        assert {r.scope for r in rows} == {"global", "feature"}
```

- [ ] **Step 2: 在 `src/codeask/db/models/session.py` 末尾追加**

```python
from typing import Any

from sqlalchemy import JSON, Integer


class SessionTurn(Base, TimestampMixin):
    __tablename__ = "session_turns"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    evidence: Mapped[Any | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        CheckConstraint("role IN ('user', 'agent')", name="ck_session_turns_role"),
    )


class SessionAttachment(Base, TimestampMixin):
    __tablename__ = "session_attachments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "kind IN ('log', 'image', 'doc', 'other')", name="ck_session_attachments_kind"
        ),
    )
```

> 注意：原文件 imports 没有 `JSON` / `Integer` / `Any`，把它们加到顶部 `from sqlalchemy import` 行，并在文件顶部 `from typing import Any`。同时 `from sqlalchemy import` 行需保留 `CheckConstraint`、`ForeignKey`、`String`，并增补 `JSON, Integer`。

- [ ] **Step 3: 创建 `src/codeask/db/models/skill.py`**

```python
"""skills: prompt templates injected per-feature or globally."""

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class Skill(Base, TimestampMixin):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    feature_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_template: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        CheckConstraint("scope IN ('global', 'feature')", name="ck_skills_scope"),
        CheckConstraint(
            "(scope = 'global' AND feature_id IS NULL) OR "
            "(scope = 'feature' AND feature_id IS NOT NULL)",
            name="ck_skills_scope_feature_consistency",
        ),
    )
```

- [ ] **Step 4: 修改 `src/codeask/db/models/__init__.py`**

```python
"""ORM model definitions."""

from codeask.db.models.llm import LLMConfig
from codeask.db.models.session import (
    Session,
    SessionAttachment,
    SessionFeature,
    SessionRepoBinding,
    SessionTurn,
)
from codeask.db.models.skill import Skill
from codeask.db.models.system_settings import SystemSetting

__all__ = [
    "LLMConfig",
    "Session",
    "SessionAttachment",
    "SessionFeature",
    "SessionRepoBinding",
    "SessionTurn",
    "Skill",
    "SystemSetting",
]
```

- [ ] **Step 5: 创建 migration `alembic/versions/20260430_0008_skills.py`**

```python
"""skills

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-29 00:41:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("feature_id", sa.String(length=64), nullable=True),
        sa.Column("prompt_template", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("scope IN ('global', 'feature')", name="ck_skills_scope"),
        sa.CheckConstraint(
            "(scope = 'global' AND feature_id IS NULL) OR "
            "(scope = 'feature' AND feature_id IS NOT NULL)",
            name="ck_skills_scope_feature_consistency",
        ),
    )
    op.create_index("ix_skills_feature", "skills", ["feature_id"])


def downgrade() -> None:
    op.drop_index("ix_skills_feature", table_name="skills")
    op.drop_table("skills")
```

- [ ] **Step 6: 创建 migration `alembic/versions/20260430_0011_session_turns_attachments.py`**

```python
"""session_turns + session_attachments

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-29 00:44:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "session_turns",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("role IN ('user', 'agent')", name="ck_session_turns_role"),
    )
    op.create_index("ix_session_turns_session", "session_turns", ["session_id", "turn_index"])

    op.create_table(
        "session_attachments",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "kind IN ('log', 'image', 'doc', 'other')", name="ck_session_attachments_kind"
        ),
    )
    op.create_index("ix_session_attachments_session", "session_attachments", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_session_attachments_session", table_name="session_attachments")
    op.drop_table("session_attachments")
    op.drop_index("ix_session_turns_session", table_name="session_turns")
    op.drop_table("session_turns")
```

- [ ] **Step 7: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_turn_attachment_skill_models.py -v`
Expected: 三个测试 PASS

- [ ] **Step 8: 提交**

```bash
git add src/codeask/db/models/session.py src/codeask/db/models/skill.py \
    src/codeask/db/models/__init__.py \
    alembic/versions/20260430_0008_skills.py \
    alembic/versions/20260430_0011_session_turns_attachments.py \
    tests/integration/test_turn_attachment_skill_models.py
git commit -m "feat(db): session_turns + session_attachments + skills"
```

---

## Task 4: ORM 模型 — agent_traces

**Files:**
- Create: `src/codeask/db/models/agent.py`
- Modify: `src/codeask/db/models/__init__.py`
- Create: `alembic/versions/20260430_0012_agent_traces.py`
- Create: `tests/integration/test_agent_trace_model.py`

按 `agent-runtime.md` §13 + `dependencies.md` §2.7 落地——每阶段事件一行；payload 是 JSON。

- [ ] **Step 1: 写测试 `tests/integration/test_agent_trace_model.py`**

```python
"""Round-trip + ordering for agent_traces."""

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from codeask.db import Base, create_engine, session_factory
from codeask.db.models import AgentTrace, Session, SessionTurn


@pytest_asyncio.fixture()
async def engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    eng = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_trace_round_trip(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        s.add(Session(id="sess_x", title="t", created_by_subject_id="x", status="active"))
        s.add(SessionTurn(id="turn_x", session_id="sess_x", turn_index=0, role="user",
                          content="q", evidence=None))
        s.add(
            AgentTrace(
                id="tr_1",
                session_id="sess_x",
                turn_id="turn_x",
                stage="scope_detection",
                event_type="stage_enter",
                payload={"input": {"question": "q"}},
            )
        )
        s.add(
            AgentTrace(
                id="tr_2",
                session_id="sess_x",
                turn_id="turn_x",
                stage="scope_detection",
                event_type="llm_response",
                payload={"feature_ids": ["feat_a"], "confidence": "high"},
            )
        )
        await s.commit()
    async with factory() as s:
        rows = (
            await s.execute(select(AgentTrace).order_by(AgentTrace.created_at, AgentTrace.id))
        ).scalars().all()
        assert [r.event_type for r in rows] == ["stage_enter", "llm_response"]
        assert rows[1].payload == {"feature_ids": ["feat_a"], "confidence": "high"}
```

- [ ] **Step 2: 创建 `src/codeask/db/models/agent.py`**

```python
"""agent_traces: per-stage event log."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class AgentTrace(Base, TimestampMixin):
    __tablename__ = "agent_traces"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("session_turns.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[Any] = mapped_column(JSON, nullable=False)
```

- [ ] **Step 3: 修改 `src/codeask/db/models/__init__.py` 导出 AgentTrace**

```python
"""ORM model definitions."""

from codeask.db.models.agent import AgentTrace
from codeask.db.models.llm import LLMConfig
from codeask.db.models.session import (
    Session,
    SessionAttachment,
    SessionFeature,
    SessionRepoBinding,
    SessionTurn,
)
from codeask.db.models.skill import Skill
from codeask.db.models.system_settings import SystemSetting

__all__ = [
    "AgentTrace",
    "LLMConfig",
    "Session",
    "SessionAttachment",
    "SessionFeature",
    "SessionRepoBinding",
    "SessionTurn",
    "Skill",
    "SystemSetting",
]
```

- [ ] **Step 4: 创建 migration `alembic/versions/20260430_0012_agent_traces.py`**

```python
"""agent_traces

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-29 00:45:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_traces",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("turn_id", sa.String(length=64), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["turn_id"], ["session_turns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_traces_turn", "agent_traces", ["turn_id", "created_at"])
    op.create_index("ix_agent_traces_session_stage", "agent_traces", ["session_id", "stage"])


def downgrade() -> None:
    op.drop_index("ix_agent_traces_session_stage", table_name="agent_traces")
    op.drop_index("ix_agent_traces_turn", table_name="agent_traces")
    op.drop_table("agent_traces")
```

- [ ] **Step 5: 跑测试**

Run: `uv run pytest tests/integration/test_agent_trace_model.py -v`
Expected: PASS

- [ ] **Step 6: 跑所有迁移测试 + 全量回归**

Run: `uv run pytest -v`
Expected: 已有测试 + 本计划 1-4 task 测试全 PASS。

- [ ] **Step 7: 提交**

```bash
git add src/codeask/db/models/agent.py src/codeask/db/models/__init__.py \
    alembic/versions/20260430_0012_agent_traces.py \
    tests/integration/test_agent_trace_model.py
git commit -m "feat(db): agent_traces table for per-stage event log"
```

---

## Task 5: LLM Gateway — 通用类型（types.py）

**Files:**
- Create: `src/codeask/llm/__init__.py`
- Create: `src/codeask/llm/types.py`
- Create: `tests/unit/test_llm_types.py`

按 `llm-gateway.md` §3-§5 + §9 落地：`LLMRequest` / `LLMMessage` / 三种 ContentBlock / `ToolDef` / `LLMEvent` / `LLMError` / `StopReason`。**纯 Pydantic 模型，无副作用**。

LLMEvent.type 取值锁定（用于 types.py / 适配器 / 测试间统一）：
`message_start | text_delta | tool_call_start | tool_call_delta | tool_call_done | message_stop | usage | error`

StopReason 取值锁定：`end_turn | tool_call | max_tokens | stop_sequence | content_filter | error | unknown`

- [ ] **Step 1: 写测试 `tests/unit/test_llm_types.py`**

```python
"""Pydantic round-trip + Literal validation for LLM types."""

import pytest
from pydantic import ValidationError

from codeask.llm.types import (
    LLMError,
    LLMEvent,
    LLMMessage,
    LLMRequest,
    TextBlock,
    ToolCallBlock,
    ToolDef,
    ToolResultBlock,
)


def test_text_block() -> None:
    b = TextBlock(type="text", text="hello")
    assert b.text == "hello"


def test_tool_call_block() -> None:
    b = ToolCallBlock(type="tool_call", id="tc_1", name="search_wiki", arguments={"q": "x"})
    assert b.name == "search_wiki"


def test_tool_result_block() -> None:
    b = ToolResultBlock(type="tool_result", tool_call_id="tc_1", content={"ok": True})
    assert b.is_error is False


def test_message_with_mixed_blocks() -> None:
    msg = LLMMessage(
        role="assistant",
        content=[
            TextBlock(type="text", text="thinking..."),
            ToolCallBlock(type="tool_call", id="tc_1", name="search_wiki",
                          arguments={"query": "ERR_X"}),
        ],
    )
    assert len(msg.content) == 2


def test_request_round_trip() -> None:
    req = LLMRequest(
        config_id=None,
        messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
        tools=[ToolDef(name="search_wiki", description="d",
                       input_schema={"type": "object"})],
        tool_choice=None,
        max_tokens=1000,
        temperature=0.2,
    )
    serialized = req.model_dump()
    restored = LLMRequest.model_validate(serialized)
    assert restored.max_tokens == 1000


def test_event_type_validated() -> None:
    LLMEvent(type="text_delta", data={"delta": "hello"})
    with pytest.raises(ValidationError):
        LLMEvent(type="not_a_real_event", data={})  # type: ignore[arg-type]


def test_error_retryable_default() -> None:
    err = LLMError(provider="openai", error_code="429", message="rate limited",
                   retryable=True)
    assert err.retryable is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_llm_types.py -v`
Expected: ImportError on `codeask.llm.types`

- [ ] **Step 3: 创建 `src/codeask/llm/__init__.py`**

```python
"""LLM gateway: provider-neutral request/event types and adapters."""
```

- [ ] **Step 4: 创建 `src/codeask/llm/types.py`**

```python
"""Provider-neutral LLM types (Pydantic v2)."""

from typing import Any, Literal, Union

from pydantic import BaseModel, Field

StopReason = Literal[
    "end_turn",
    "tool_call",
    "max_tokens",
    "stop_sequence",
    "content_filter",
    "error",
    "unknown",
]

EventType = Literal[
    "message_start",
    "text_delta",
    "tool_call_start",
    "tool_call_delta",
    "tool_call_done",
    "message_stop",
    "usage",
    "error",
]

ProviderProtocol = Literal["openai", "openai_compatible", "anthropic"]


class TextBlock(BaseModel):
    type: Literal["text"]
    text: str


class ToolCallBlock(BaseModel):
    type: Literal["tool_call"]
    id: str
    name: str
    arguments: dict[str, Any]


class ToolResultBlock(BaseModel):
    type: Literal["tool_result"]
    tool_call_id: str
    content: Union[str, dict[str, Any]]
    is_error: bool = False


ContentBlock = Union[TextBlock, ToolCallBlock, ToolResultBlock]


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: list[ContentBlock]
    tool_call_id: str | None = None


class ToolDef(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class ToolChoice(BaseModel):
    type: Literal["auto", "any", "tool", "none"] = "auto"
    name: str | None = None


class LLMRequest(BaseModel):
    config_id: str | None = None
    messages: list[LLMMessage]
    tools: list[ToolDef] = Field(default_factory=list)
    tool_choice: ToolChoice | None = None
    max_tokens: int
    temperature: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMEvent(BaseModel):
    type: EventType
    data: dict[str, Any] = Field(default_factory=dict)


class LLMError(BaseModel):
    provider: str
    error_code: str
    message: str
    retryable: bool
    raw: dict[str, Any] | None = None
```

- [ ] **Step 5: 跑测试**

Run: `uv run pytest tests/unit/test_llm_types.py -v`
Expected: 七个测试全 PASS

- [ ] **Step 6: 提交**

```bash
git add src/codeask/llm/__init__.py src/codeask/llm/types.py tests/unit/test_llm_types.py
git commit -m "feat(llm): provider-neutral request/message/event types"
```

---

## Task 6: LLM Gateway — LLMConfigRepo（CRUD + 加解密 + 单 default 保证）

**Files:**
- Create: `src/codeask/llm/repo.py`
- Create: `tests/integration/test_llm_config_repo.py`

`LLMConfigRepo` 持有 `Crypto` + `AsyncSession` factory：
- `list()` 返回 masked key（永不返回明文）
- `get(id)` 返回明文 key（仅给网关用）
- `get_default()` / `get_default_or(config_id)` 选默认或指定
- `save_default(...)` 在事务里把其他 default 清零再 set——保证最多一条 default

- [ ] **Step 1: 写测试 `tests/integration/test_llm_config_repo.py`**

```python
"""LLMConfigRepo: encryption + default uniqueness."""

from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet

from codeask.crypto import Crypto
from codeask.db import Base, create_engine, session_factory
from codeask.llm.repo import LLMConfigInput, LLMConfigRepo


@pytest_asyncio.fixture()
async def repo(tmp_path: Path):  # type: ignore[no-untyped-def]
    eng = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = session_factory(eng)
    crypto = Crypto(Fernet.generate_key().decode())
    yield LLMConfigRepo(factory, crypto)
    await eng.dispose()


@pytest.mark.asyncio
async def test_create_and_decrypt(repo: LLMConfigRepo) -> None:
    cfg_id = await repo.create(
        LLMConfigInput(
            name="default",
            protocol="openai",
            base_url=None,
            api_key="sk-secret",
            model_name="gpt-4o",
            max_tokens=4096,
            temperature=0.2,
            is_default=True,
        )
    )
    decrypted = await repo.get_with_secret(cfg_id)
    assert decrypted.api_key == "sk-secret"


@pytest.mark.asyncio
async def test_list_masks_key(repo: LLMConfigRepo) -> None:
    await repo.create(
        LLMConfigInput(
            name="a", protocol="openai", base_url=None,
            api_key="sk-aaaaaa", model_name="m",
            max_tokens=1, temperature=0.0, is_default=True,
        )
    )
    items = await repo.list()
    assert items[0].api_key_masked.startswith("sk-")
    assert "aaaa" not in items[0].api_key_masked


@pytest.mark.asyncio
async def test_only_one_default(repo: LLMConfigRepo) -> None:
    a = await repo.create(
        LLMConfigInput(name="a", protocol="openai", base_url=None, api_key="x",
                       model_name="m", max_tokens=1, temperature=0.0, is_default=True)
    )
    b = await repo.create(
        LLMConfigInput(name="b", protocol="anthropic", base_url=None, api_key="y",
                       model_name="m", max_tokens=1, temperature=0.0, is_default=True)
    )
    default = await repo.get_default()
    assert default is not None
    assert default.id == b
    items = {it.id: it.is_default for it in await repo.list()}
    assert items[a] is False
    assert items[b] is True
```

- [ ] **Step 2: 创建 `src/codeask/llm/repo.py`**

```python
"""LLMConfig CRUD + encryption + default-uniqueness enforcement."""

from dataclasses import dataclass
from secrets import token_hex
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.crypto import Crypto
from codeask.db.models import LLMConfig


class LLMConfigInput(BaseModel):
    name: str
    protocol: Literal["openai", "openai_compatible", "anthropic"]
    base_url: str | None
    api_key: str
    model_name: str
    max_tokens: int
    temperature: float
    is_default: bool = False


@dataclass
class LLMConfigPublic:
    id: str
    name: str
    protocol: str
    base_url: str | None
    api_key_masked: str
    model_name: str
    max_tokens: int
    temperature: float
    is_default: bool


@dataclass
class LLMConfigWithSecret:
    id: str
    name: str
    protocol: str
    base_url: str | None
    api_key: str
    model_name: str
    max_tokens: int
    temperature: float
    is_default: bool


def _mask_key(key: str) -> str:
    if len(key) <= 6:
        return "***"
    return f"{key[:3]}...{key[-3:]}"


class LLMConfigRepo:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        crypto: Crypto,
    ) -> None:
        self._sf = session_factory
        self._crypto = crypto

    async def create(self, data: LLMConfigInput) -> str:
        cfg_id = f"cfg_{token_hex(8)}"
        cipher = self._crypto.encrypt(data.api_key)
        async with self._sf() as s:
            if data.is_default:
                await s.execute(
                    update(LLMConfig).values(is_default=False).where(LLMConfig.is_default == True)  # noqa: E712
                )
            s.add(
                LLMConfig(
                    id=cfg_id,
                    name=data.name,
                    protocol=data.protocol,
                    base_url=data.base_url,
                    api_key_encrypted=cipher,
                    model_name=data.model_name,
                    max_tokens=data.max_tokens,
                    temperature=data.temperature,
                    is_default=data.is_default,
                )
            )
            await s.commit()
        return cfg_id

    async def list(self) -> list[LLMConfigPublic]:
        async with self._sf() as s:
            rows = (await s.execute(select(LLMConfig).order_by(LLMConfig.created_at))).scalars().all()
        out: list[LLMConfigPublic] = []
        for r in rows:
            try:
                plain = self._crypto.decrypt(r.api_key_encrypted)
            except Exception:
                plain = ""
            out.append(
                LLMConfigPublic(
                    id=r.id, name=r.name, protocol=r.protocol, base_url=r.base_url,
                    api_key_masked=_mask_key(plain),
                    model_name=r.model_name, max_tokens=r.max_tokens,
                    temperature=r.temperature, is_default=r.is_default,
                )
            )
        return out

    async def get_with_secret(self, cfg_id: str) -> LLMConfigWithSecret:
        async with self._sf() as s:
            row = (await s.execute(select(LLMConfig).where(LLMConfig.id == cfg_id))).scalar_one()
        return LLMConfigWithSecret(
            id=row.id, name=row.name, protocol=row.protocol, base_url=row.base_url,
            api_key=self._crypto.decrypt(row.api_key_encrypted),
            model_name=row.model_name, max_tokens=row.max_tokens,
            temperature=row.temperature, is_default=row.is_default,
        )

    async def get_default(self) -> LLMConfigWithSecret | None:
        async with self._sf() as s:
            row = (
                await s.execute(select(LLMConfig).where(LLMConfig.is_default == True))  # noqa: E712
            ).scalar_one_or_none()
        if row is None:
            return None
        return LLMConfigWithSecret(
            id=row.id, name=row.name, protocol=row.protocol, base_url=row.base_url,
            api_key=self._crypto.decrypt(row.api_key_encrypted),
            model_name=row.model_name, max_tokens=row.max_tokens,
            temperature=row.temperature, is_default=row.is_default,
        )

    async def get_default_or(self, cfg_id: str | None) -> LLMConfigWithSecret:
        if cfg_id is not None:
            return await self.get_with_secret(cfg_id)
        d = await self.get_default()
        if d is None:
            raise LookupError("no default LLM config configured")
        return d

    async def delete(self, cfg_id: str) -> None:
        async with self._sf() as s:
            row = (await s.execute(select(LLMConfig).where(LLMConfig.id == cfg_id))).scalar_one()
            await s.delete(row)
            await s.commit()
```

- [ ] **Step 3: 跑测试**

Run: `uv run pytest tests/integration/test_llm_config_repo.py -v`
Expected: 三个测试 PASS

- [ ] **Step 4: 提交**

```bash
git add src/codeask/llm/repo.py tests/integration/test_llm_config_repo.py
git commit -m "feat(llm): LLMConfigRepo with encryption + default-uniqueness"
```

---

## Task 7: LLM Gateway — Client 协议 + LiteLLM 适配器（OpenAI / OpenAI-compatible / Anthropic）

**Files:**
- Create: `src/codeask/llm/client.py`
- Create: `tests/unit/test_llm_client_adapter.py`
- Modify: `pyproject.toml`（增加 `litellm>=1.50` 依赖）

按 `llm-gateway.md` §2 + §6 落地。`LLMClient` Protocol 接 `stream(messages, tools, max_tokens, temperature) -> AsyncIterator[LLMEvent]`。三个具体 client（OpenAI / OpenAICompatible / Anthropic）都通过 LiteLLM `acompletion(stream=True, ...)` 实现，但**对外仍只暴露 `LLMEvent`**。

LiteLLM 调用规则：
- protocol="openai" → `model=<model_name>`，使用 `api_key`
- protocol="openai_compatible" → `model=f"openai/{model_name}"`，使用 `api_key` + `base_url`
- protocol="anthropic" → `model=f"anthropic/{model_name}"`，使用 `api_key`

LiteLLM streaming chunk → LLMEvent 转换：
- 第一个 chunk → `message_start`（含 model）
- `chunk.choices[0].delta.content` 非空 → `text_delta`（data={"delta": str}）
- `chunk.choices[0].delta.tool_calls[i]`：
  - 该 tool_call_id 第一次出现 → `tool_call_start`（data={"id", "name"}）
  - 后续 args delta → `tool_call_delta`（data={"id", "arguments_delta": str}）
  - 累积完整 args 后（`finish_reason` 出现或下一个 chunk 切换 id） → `tool_call_done`（data={"id", "name", "arguments": dict}）
- `chunk.choices[0].finish_reason` 出现 → `message_stop`（data={"stop_reason": <normalized>}）+ `usage`（如 LiteLLM 给）
- 异常 → `error`

stop_reason 归一化映射（OpenAI / Anthropic 都靠 LiteLLM 拉平到 OpenAI 格式）：
- `stop` → `end_turn`
- `tool_calls` → `tool_call`
- `length` → `max_tokens`
- `content_filter` → `content_filter`
- 其他 → `unknown`

- [ ] **Step 1: 修改 `pyproject.toml` 增加依赖**

在 `[project] dependencies` 末尾追加：

```toml
    "litellm>=1.50",
    "tiktoken>=0.7",
```

- [ ] **Step 2: 写测试 `tests/unit/test_llm_client_adapter.py`**（用 monkeypatch 替换 LiteLLM `acompletion` → 模拟 chunk 序列）

```python
"""Adapter test: LiteLLM streaming chunks → LLMEvent."""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest

from codeask.llm.client import OpenAIClient
from codeask.llm.types import LLMMessage, TextBlock, ToolDef


def _chunk(content: str | None = None, tool_calls: list[Any] | None = None,
           finish_reason: str | None = None) -> SimpleNamespace:
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], model="gpt-4o", usage=None)


def _tool_call_chunk(idx: int, tc_id: str | None, name: str | None,
                     args_delta: str) -> Any:
    fn = SimpleNamespace(name=name, arguments=args_delta)
    return SimpleNamespace(index=idx, id=tc_id, type="function", function=fn)


@pytest.mark.asyncio
async def test_text_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_acompletion(**kwargs):  # type: ignore[no-untyped-def]
        async def gen() -> AsyncIterator[Any]:
            yield _chunk(content="hello ")
            yield _chunk(content="world")
            yield _chunk(finish_reason="stop")
        return gen()

    import codeask.llm.client as mod
    monkeypatch.setattr(mod, "acompletion", fake_acompletion)

    client = OpenAIClient(api_key="x", model_name="gpt-4o")
    events = []
    async for ev in client.stream(
        messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
        tools=[], max_tokens=100, temperature=0.0,
    ):
        events.append(ev)
    types = [e.type for e in events]
    assert types[0] == "message_start"
    assert "text_delta" in types
    assert types[-2] == "message_stop"  # message_stop then usage(or no usage)
    assert any(e.type == "message_stop" and e.data["stop_reason"] == "end_turn"
               for e in events)


@pytest.mark.asyncio
async def test_tool_call_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_acompletion(**kwargs):  # type: ignore[no-untyped-def]
        async def gen() -> AsyncIterator[Any]:
            yield _chunk(tool_calls=[_tool_call_chunk(0, "tc_a", "search_wiki", "")])
            yield _chunk(tool_calls=[_tool_call_chunk(0, None, None, '{"q":')])
            yield _chunk(tool_calls=[_tool_call_chunk(0, None, None, '"x"}')])
            yield _chunk(finish_reason="tool_calls")
        return gen()

    import codeask.llm.client as mod
    monkeypatch.setattr(mod, "acompletion", fake_acompletion)

    client = OpenAIClient(api_key="x", model_name="gpt-4o")
    events = []
    async for ev in client.stream(
        messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
        tools=[ToolDef(name="search_wiki", description="d", input_schema={})],
        max_tokens=100, temperature=0.0,
    ):
        events.append(ev)
    starts = [e for e in events if e.type == "tool_call_start"]
    dones = [e for e in events if e.type == "tool_call_done"]
    assert starts and starts[0].data["name"] == "search_wiki"
    assert dones and dones[0].data["arguments"] == {"q": "x"}
    stop = [e for e in events if e.type == "message_stop"][0]
    assert stop.data["stop_reason"] == "tool_call"
```

- [ ] **Step 3: 创建 `src/codeask/llm/client.py`**

```python
"""LLMClient: LiteLLM-backed adapters for openai / openai_compatible / anthropic."""

import json
from collections.abc import AsyncIterator
from typing import Any, Protocol

from litellm import acompletion

from codeask.llm.types import (
    EventType,
    LLMError,
    LLMEvent,
    LLMMessage,
    StopReason,
    TextBlock,
    ToolCallBlock,
    ToolDef,
    ToolResultBlock,
)


_OPENAI_TO_INTERNAL_STOP: dict[str, StopReason] = {
    "stop": "end_turn",
    "tool_calls": "tool_call",
    "length": "max_tokens",
    "content_filter": "content_filter",
}


def _normalize_stop_reason(reason: str | None) -> StopReason:
    if reason is None:
        return "unknown"
    return _OPENAI_TO_INTERNAL_STOP.get(reason, "unknown")


def _messages_to_litellm(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == "tool":
            for block in msg.content:
                if isinstance(block, ToolResultBlock):
                    payload = block.content if isinstance(block.content, str) else json.dumps(block.content)
                    out.append({"role": "tool", "tool_call_id": block.tool_call_id, "content": payload})
            continue
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in msg.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
            elif isinstance(block, ToolCallBlock):
                tool_calls.append({
                    "id": block.id, "type": "function",
                    "function": {"name": block.name, "arguments": json.dumps(block.arguments)},
                })
        rec: dict[str, Any] = {"role": msg.role, "content": "\n".join(text_parts) if text_parts else None}
        if tool_calls:
            rec["tool_calls"] = tool_calls
        out.append(rec)
    return out


def _tools_to_litellm(tools: list[ToolDef]) -> list[dict[str, Any]]:
    return [
        {"type": "function",
         "function": {"name": t.name, "description": t.description,
                      "parameters": t.input_schema}}
        for t in tools
    ]


class LLMClient(Protocol):
    async def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[LLMEvent]: ...


class _BaseClient:
    """Common LiteLLM streaming → LLMEvent loop. Subclasses set self._model + extra kwargs."""

    _provider_name: str = "openai"

    def __init__(self, api_key: str, model_name: str, base_url: str | None = None) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._base_url = base_url

    def _model(self) -> str:
        return self._model_name

    def _extra_kwargs(self) -> dict[str, Any]:
        kw: dict[str, Any] = {"api_key": self._api_key}
        if self._base_url:
            kw["base_url"] = self._base_url
        return kw

    async def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[LLMEvent]:
        kwargs: dict[str, Any] = {
            "model": self._model(),
            "messages": _messages_to_litellm(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            **self._extra_kwargs(),
        }
        if tools:
            kwargs["tools"] = _tools_to_litellm(tools)

        try:
            stream = await acompletion(**kwargs)
        except Exception as exc:  # network / auth / schema error
            yield LLMEvent(type="error", data=self._error_payload(exc, retryable=False))
            return

        emitted_start = False
        # Per tool_call accumulator: tc_id -> (name, args_str, idx)
        tc_acc: dict[str, dict[str, Any]] = {}
        active_tc_id: str | None = None

        try:
            async for chunk in stream:
                if not emitted_start:
                    yield LLMEvent(type="message_start",
                                   data={"model": getattr(chunk, "model", self._model_name)})
                    emitted_start = True

                choice = chunk.choices[0] if getattr(chunk, "choices", None) else None
                if choice is None:
                    continue
                delta = getattr(choice, "delta", None)
                if delta is None:
                    continue

                content = getattr(delta, "content", None)
                if content:
                    yield LLMEvent(type="text_delta", data={"delta": content})

                tcs = getattr(delta, "tool_calls", None) or []
                for tc in tcs:
                    tc_id = getattr(tc, "id", None) or active_tc_id
                    fn = getattr(tc, "function", None)
                    name = getattr(fn, "name", None) if fn else None
                    args_delta = getattr(fn, "arguments", "") if fn else ""

                    if tc_id and tc_id not in tc_acc:
                        tc_acc[tc_id] = {"name": name or "", "args_str": ""}
                        yield LLMEvent(type="tool_call_start",
                                       data={"id": tc_id, "name": name or ""})
                        active_tc_id = tc_id
                    elif tc_id is None and active_tc_id is not None:
                        tc_id = active_tc_id

                    if tc_id is not None:
                        if name and not tc_acc[tc_id]["name"]:
                            tc_acc[tc_id]["name"] = name
                        if args_delta:
                            tc_acc[tc_id]["args_str"] += args_delta
                            yield LLMEvent(type="tool_call_delta",
                                           data={"id": tc_id, "arguments_delta": args_delta})

                finish_reason = getattr(choice, "finish_reason", None)
                if finish_reason is not None:
                    for tid, acc in tc_acc.items():
                        try:
                            parsed = json.loads(acc["args_str"]) if acc["args_str"] else {}
                        except json.JSONDecodeError:
                            parsed = {}
                        yield LLMEvent(type="tool_call_done",
                                       data={"id": tid, "name": acc["name"], "arguments": parsed})
                    yield LLMEvent(type="message_stop",
                                   data={"stop_reason": _normalize_stop_reason(finish_reason)})
                    usage = getattr(chunk, "usage", None)
                    if usage is not None:
                        yield LLMEvent(type="usage", data={
                            "input_tokens": getattr(usage, "prompt_tokens", 0),
                            "output_tokens": getattr(usage, "completion_tokens", 0),
                        })
                    return
        except Exception as exc:
            yield LLMEvent(type="error", data=self._error_payload(exc, retryable=True))

    def _error_payload(self, exc: Exception, retryable: bool) -> dict[str, Any]:
        return LLMError(
            provider=self._provider_name,
            error_code=type(exc).__name__,
            message=str(exc),
            retryable=retryable,
        ).model_dump()


class OpenAIClient(_BaseClient):
    _provider_name = "openai"


class OpenAICompatibleClient(_BaseClient):
    _provider_name = "openai_compatible"

    def _model(self) -> str:
        return f"openai/{self._model_name}"


class AnthropicClient(_BaseClient):
    _provider_name = "anthropic"

    def _model(self) -> str:
        return f"anthropic/{self._model_name}"
```

- [ ] **Step 4: 跑测试**

Run: `uv sync && uv run pytest tests/unit/test_llm_client_adapter.py -v`
Expected: 两个测试 PASS

- [ ] **Step 5: 提交**

```bash
git add src/codeask/llm/client.py tests/unit/test_llm_client_adapter.py pyproject.toml uv.lock
git commit -m "feat(llm): LiteLLM-backed adapters for openai/openai_compatible/anthropic"
```

---

## Task 8: LLM Gateway — LLMGateway（重试 + factory + 错误归一化）

**Files:**
- Create: `src/codeask/llm/gateway.py`
- Create: `tests/unit/test_llm_gateway.py`

按 `llm-gateway.md` §2 + §9 落地。`LLMGateway.stream(request)`：
1. 通过 `LLMConfigRepo.get_default_or(request.config_id)` 拿 config
2. 通过 factory 按 protocol 创建 client
3. 调用 client.stream，**第一次完整跑**直接 yield
4. 如果遇到 `error` event 且 `retryable=True`，按指数退避（0.5s, 1s, 2s）最多重试 3 次

> 流式重试的取舍：如果第一次已经 yield 出 `text_delta`（部分 token 已经发到调用方），重试就会重复输出。**简单做法**：只在"还没 yield 出任何非 message_start 事件"的情况下重试；一旦输出了 token，把 retryable=False 直接终止。`agent-runtime.md` §12 也说"流式中断 → 可恢复错误，本轮停止"。

- [ ] **Step 1: 写测试 `tests/unit/test_llm_gateway.py`**

```python
"""LLMGateway: factory dispatch + retry-before-first-token only."""

from collections.abc import AsyncIterator

import pytest

from codeask.llm.gateway import ClientFactory, LLMGateway
from codeask.llm.types import LLMEvent, LLMMessage, LLMRequest, TextBlock


class _ScriptedClient:
    def __init__(self, scripts: list[list[LLMEvent]]) -> None:
        self._scripts = scripts
        self._idx = 0

    async def stream(self, **_: object) -> AsyncIterator[LLMEvent]:
        script = self._scripts[self._idx]
        self._idx += 1
        for ev in script:
            yield ev


class _FakeRepo:
    async def get_default_or(self, _id: str | None) -> object:
        from dataclasses import dataclass

        @dataclass
        class S:
            id: str = "cfg"
            protocol: str = "openai"
            api_key: str = "x"
            base_url: str | None = None
            model_name: str = "m"
            max_tokens: int = 100
            temperature: float = 0.0

        return S()


def _request() -> LLMRequest:
    return LLMRequest(
        messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
        max_tokens=100, temperature=0.0,
    )


@pytest.mark.asyncio
async def test_retry_when_error_before_first_token() -> None:
    bad = LLMEvent(type="error", data={"retryable": True, "message": "transient"})
    good = [LLMEvent(type="message_start", data={}), LLMEvent(type="text_delta", data={"delta": "ok"}),
            LLMEvent(type="message_stop", data={"stop_reason": "end_turn"})]
    client = _ScriptedClient([[bad], good])

    factory = ClientFactory(provider_clients={"openai": lambda **_: client})
    gw = LLMGateway(_FakeRepo(), factory, base_delay=0.0)  # type: ignore[arg-type]
    out = [e async for e in gw.stream(_request())]
    assert out[-1].data["stop_reason"] == "end_turn"


@pytest.mark.asyncio
async def test_no_retry_after_first_token() -> None:
    partial = [LLMEvent(type="message_start", data={}),
               LLMEvent(type="text_delta", data={"delta": "abc"}),
               LLMEvent(type="error", data={"retryable": True, "message": "stream cut"})]
    client = _ScriptedClient([partial])

    factory = ClientFactory(provider_clients={"openai": lambda **_: client})
    gw = LLMGateway(_FakeRepo(), factory, base_delay=0.0)  # type: ignore[arg-type]
    out = [e async for e in gw.stream(_request())]
    assert out[-1].type == "error"
```

- [ ] **Step 2: 创建 `src/codeask/llm/gateway.py`**

```python
"""LLMGateway: protocol dispatch + retry policy."""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from codeask.llm.client import (
    AnthropicClient,
    LLMClient,
    OpenAICompatibleClient,
    OpenAIClient,
)
from codeask.llm.repo import LLMConfigRepo
from codeask.llm.types import LLMEvent, LLMRequest


@dataclass
class ClientFactory:
    provider_clients: dict[str, Callable[..., LLMClient]]

    @classmethod
    def default(cls) -> "ClientFactory":
        return cls(
            provider_clients={
                "openai": lambda **kw: OpenAIClient(**kw),
                "openai_compatible": lambda **kw: OpenAICompatibleClient(**kw),
                "anthropic": lambda **kw: AnthropicClient(**kw),
            }
        )

    def create(self, protocol: str, **kwargs: object) -> LLMClient:
        if protocol not in self.provider_clients:
            raise ValueError(f"unknown protocol {protocol!r}")
        return self.provider_clients[protocol](**kwargs)  # type: ignore[arg-type]


class LLMGateway:
    def __init__(
        self,
        config_repo: LLMConfigRepo,
        client_factory: ClientFactory,
        max_retries: int = 3,
        base_delay: float = 0.5,
    ) -> None:
        self._repo = config_repo
        self._factory = client_factory
        self._max_retries = max_retries
        self._base_delay = base_delay

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        cfg = await self._repo.get_default_or(request.config_id)
        client = self._factory.create(
            cfg.protocol,
            api_key=cfg.api_key,
            model_name=cfg.model_name,
            base_url=cfg.base_url,
        )

        attempt = 0
        while True:
            emitted_real = False  # any event other than message_start
            last_error: LLMEvent | None = None

            async for ev in client.stream(
                messages=request.messages,
                tools=request.tools,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            ):
                if ev.type == "error":
                    last_error = ev
                    if not emitted_real and bool(ev.data.get("retryable", False)) and attempt < self._max_retries:
                        # stop yielding; we'll retry
                        break
                    yield ev
                    return
                if ev.type != "message_start":
                    emitted_real = True
                yield ev
                if ev.type == "message_stop":
                    return

            # If we got here without message_stop: either retryable error or stream cut
            if last_error is None:
                return  # client exited cleanly without stop event; treat as done
            if emitted_real:
                yield last_error
                return
            attempt += 1
            if attempt > self._max_retries:
                yield last_error
                return
            await asyncio.sleep(self._base_delay * (2 ** (attempt - 1)))
```

- [ ] **Step 3: 跑测试**

Run: `uv run pytest tests/unit/test_llm_gateway.py -v`
Expected: 两个测试 PASS

- [ ] **Step 4: 提交**

```bash
git add src/codeask/llm/gateway.py tests/unit/test_llm_gateway.py
git commit -m "feat(llm): LLMGateway with protocol dispatch + retry-before-first-token"
```

---

## Task 9: AgentState 枚举 + StageTransition 表

**Files:**
- Create: `src/codeask/agent/__init__.py`
- Create: `src/codeask/agent/state.py`
- Create: `tests/unit/test_agent_state.py`

按 `agent-runtime.md` §2 + §3 落地 9 阶段。**枚举值锁定**（agent/state.py / orchestrator.py / 测试 / SSE 共用）：
`Initialize | InputAnalysis | ScopeDetection | KnowledgeRetrieval | SufficiencyJudgement | CodeInvestigation | VersionConfirmation | EvidenceSynthesis | AnswerFinalization | ReportDrafting | AskUser | Terminate`

`stage_value` 字符串形态用 snake_case：`initialize`, `input_analysis`, `scope_detection`, `knowledge_retrieval`, `sufficiency_judgement`, `code_investigation`, `version_confirmation`, `evidence_synthesis`, `answer_finalization`, `report_drafting`, `ask_user`, `terminate`。

合法迁移图（在 `_TRANSITIONS` dict 中静态列出，被 `is_valid_transition` 校验）：

```text
Initialize → InputAnalysis
InputAnalysis → ScopeDetection
ScopeDetection → KnowledgeRetrieval | AskUser
KnowledgeRetrieval → SufficiencyJudgement
SufficiencyJudgement → AnswerFinalization | CodeInvestigation
CodeInvestigation → VersionConfirmation | AnswerFinalization | AskUser
VersionConfirmation → CodeInvestigation | AskUser | AnswerFinalization
AnswerFinalization → EvidenceSynthesis
EvidenceSynthesis → ReportDrafting | Terminate
ReportDrafting → Terminate
AskUser → ScopeDetection | CodeInvestigation | VersionConfirmation | Terminate
```

> 与 SDD §2 状态机的对齐：SDD 文本顺序是 `EvidenceSynthesis → AnswerFinalization`；本计划反过来——`AnswerFinalization` 先合成结论，`EvidenceSynthesis` 把合成产物中的证据 IDs 物化到 session_turns.evidence。在 Task 18 `Self-review §3` 复核此微调。

- [ ] **Step 1: 写测试 `tests/unit/test_agent_state.py`** — 覆盖：(a) 枚举值齐全 12 个；(b) 字符串值与 SSE 事件 `stage` 对齐（snake_case）；(c) 合法迁移通过 / 非法迁移返回 False。

- [ ] **Step 2: 实现 `src/codeask/agent/__init__.py`** —— 仅 docstring。

- [ ] **Step 3: 实现 `src/codeask/agent/state.py`**

```python
"""Agent state machine: enum + valid-transition table."""

from enum import Enum


class AgentState(str, Enum):
    Initialize = "initialize"
    InputAnalysis = "input_analysis"
    ScopeDetection = "scope_detection"
    KnowledgeRetrieval = "knowledge_retrieval"
    SufficiencyJudgement = "sufficiency_judgement"
    CodeInvestigation = "code_investigation"
    VersionConfirmation = "version_confirmation"
    EvidenceSynthesis = "evidence_synthesis"
    AnswerFinalization = "answer_finalization"
    ReportDrafting = "report_drafting"
    AskUser = "ask_user"
    Terminate = "terminate"


_TRANSITIONS: dict[AgentState, set[AgentState]] = {
    AgentState.Initialize: {AgentState.InputAnalysis},
    AgentState.InputAnalysis: {AgentState.ScopeDetection},
    AgentState.ScopeDetection: {AgentState.KnowledgeRetrieval, AgentState.AskUser},
    AgentState.KnowledgeRetrieval: {AgentState.SufficiencyJudgement},
    AgentState.SufficiencyJudgement: {AgentState.AnswerFinalization, AgentState.CodeInvestigation},
    AgentState.CodeInvestigation: {AgentState.VersionConfirmation, AgentState.AnswerFinalization, AgentState.AskUser},
    AgentState.VersionConfirmation: {AgentState.CodeInvestigation, AgentState.AskUser, AgentState.AnswerFinalization},
    AgentState.AnswerFinalization: {AgentState.EvidenceSynthesis},
    AgentState.EvidenceSynthesis: {AgentState.ReportDrafting, AgentState.Terminate},
    AgentState.ReportDrafting: {AgentState.Terminate},
    AgentState.AskUser: {AgentState.ScopeDetection, AgentState.CodeInvestigation, AgentState.VersionConfirmation, AgentState.Terminate},
    AgentState.Terminate: set(),
}


def is_valid_transition(src: AgentState, dst: AgentState) -> bool:
    return dst in _TRANSITIONS.get(src, set())


def allowed_next(state: AgentState) -> set[AgentState]:
    return _TRANSITIONS.get(state, set()).copy()
```

- [ ] **Step 4: 跑测试** — `uv run pytest tests/unit/test_agent_state.py -v`，所有断言 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/codeask/agent/__init__.py src/codeask/agent/state.py tests/unit/test_agent_state.py
git commit -m "feat(agent): AgentState enum + valid-transition table"
```

---

## Task 10: SSE Multiplexer + AgentEvent

**Files:**
- Create: `src/codeask/agent/sse.py`
- Create: `tests/unit/test_sse.py`

按 `agent-runtime.md` §11 落地。`AgentEvent` 是 Pydantic 模型（type + data）。`SSEMultiplexer.format(event)` 把 AgentEvent 序列化为 SSE 帧 `event: <type>\ndata: <json>\n\n`。

事件类型锁定：`stage_transition | text_delta | tool_call | tool_result | evidence | scope_detection | sufficiency_judgement | ask_user | done | error`。

`stage_transition.data`：`{"from": <stage_value>, "to": <stage_value>, "message": str|None}`
`scope_detection.data`：`{"feature_ids": list[str], "confidence": "high"|"medium"|"low", "reason": str}`
`sufficiency_judgement.data`：`{"verdict": "enough"|"partial"|"insufficient", "reason": str, "next": str}`
`ask_user.data`：`{"question": str, "options": list[str]|None, "ask_id": str}`
`tool_call.data`：`{"id": str, "name": str, "arguments": dict}`
`tool_result.data`：`{"id": str, "ok": bool, "summary": str|None, "error_code": str|None}`
`evidence.data`：`{"id": str, "type": str, "summary": str, "relevance": str, "confidence": str}`
`done.data`：`{"turn_id": str}`
`error.data`：`{"code": str, "message": str}`

- [ ] **Step 1: 写测试 `tests/unit/test_sse.py`** — 覆盖：(a) `format()` 输出 `event:` + `data:` + 空行结尾；(b) data 是合法 JSON；(c) 缺失字段抛 `ValidationError`。

- [ ] **Step 2: 实现 `src/codeask/agent/sse.py`**

```python
"""SSE event multiplexer for the agent."""

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

EventName = Literal[
    "stage_transition", "text_delta", "tool_call", "tool_result",
    "evidence", "scope_detection", "sufficiency_judgement", "ask_user",
    "done", "error",
]


class AgentEvent(BaseModel):
    type: EventName
    data: dict[str, Any] = Field(default_factory=dict)


class SSEMultiplexer:
    def format(self, event: AgentEvent) -> bytes:
        payload = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
        return f"event: {event.type}\ndata: {payload}\n\n".encode("utf-8")
```

- [ ] **Step 3: 跑测试 + 提交**

```bash
uv run pytest tests/unit/test_sse.py -v
git add src/codeask/agent/sse.py tests/unit/test_sse.py
git commit -m "feat(agent): SSE multiplexer with locked event-type vocabulary"
```

---

## Task 11: AgentTraceLogger（按行写 agent_traces）

**Files:**
- Create: `src/codeask/agent/trace.py`
- Create: `tests/unit/test_trace.py`

按 `agent-runtime.md` §13 落地。`AgentTraceLogger(session_factory)` 提供：
- `log(session_id, turn_id, stage, event_type, payload: dict) -> None` —— 写一行
- 便捷方法：`log_stage_enter` / `log_stage_exit` / `log_llm_input(prompt_summary)` / `log_llm_event(LLMEvent)` / `log_tool_call(name, args)` / `log_tool_result(name, result)` / `log_scope_detection(input, output)` / `log_sufficiency_judgement(input, output)` / `log_user_feedback(feedback)`

每条 `payload` 是普通 dict；`event_type` 取值锁定（写到 `agent_traces.event_type`）：
`stage_enter | stage_exit | llm_input | llm_event | tool_call | tool_result | scope_decision | sufficiency_decision | user_feedback`

- [ ] **Step 1: 写测试 `tests/unit/test_trace.py`** — 用 in-memory engine + Session/SessionTurn 占位 row，断言 `log()` 一次写入一条 agent_traces 行；payload 经 JSON 往返保持。

- [ ] **Step 2: 实现 `src/codeask/agent/trace.py`**

```python
"""AgentTraceLogger: append-only writer for agent_traces."""

from secrets import token_hex
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.db.models import AgentTrace


class AgentTraceLogger:
    def __init__(self, sf: async_sessionmaker[AsyncSession]) -> None:
        self._sf = sf

    async def log(
        self, session_id: str, turn_id: str, stage: str,
        event_type: str, payload: dict[str, Any],
    ) -> None:
        async with self._sf() as s:
            s.add(AgentTrace(
                id=f"tr_{token_hex(8)}",
                session_id=session_id, turn_id=turn_id,
                stage=stage, event_type=event_type, payload=payload,
            ))
            await s.commit()

    async def log_stage_enter(self, session_id: str, turn_id: str, stage: str,
                              context: dict[str, Any]) -> None:
        await self.log(session_id, turn_id, stage, "stage_enter", {"context": context})

    async def log_stage_exit(self, session_id: str, turn_id: str, stage: str,
                             result: dict[str, Any]) -> None:
        await self.log(session_id, turn_id, stage, "stage_exit", {"result": result})

    async def log_llm_input(self, session_id: str, turn_id: str, stage: str,
                            prompt_summary: dict[str, Any]) -> None:
        await self.log(session_id, turn_id, stage, "llm_input", prompt_summary)

    async def log_llm_event(self, session_id: str, turn_id: str, stage: str,
                            event: dict[str, Any]) -> None:
        await self.log(session_id, turn_id, stage, "llm_event", event)

    async def log_tool_call(self, session_id: str, turn_id: str, stage: str,
                            name: str, args: dict[str, Any], call_id: str) -> None:
        await self.log(session_id, turn_id, stage, "tool_call",
                       {"id": call_id, "name": name, "arguments": args})

    async def log_tool_result(self, session_id: str, turn_id: str, stage: str,
                              call_id: str, result: dict[str, Any]) -> None:
        await self.log(session_id, turn_id, stage, "tool_result",
                       {"id": call_id, "result": result})

    async def log_scope_decision(self, session_id: str, turn_id: str,
                                 input_ctx: dict[str, Any], output: dict[str, Any]) -> None:
        await self.log(session_id, turn_id, "scope_detection", "scope_decision",
                       {"input": input_ctx, "output": output})

    async def log_sufficiency_decision(self, session_id: str, turn_id: str,
                                       input_ctx: dict[str, Any], output: dict[str, Any]) -> None:
        await self.log(session_id, turn_id, "sufficiency_judgement", "sufficiency_decision",
                       {"input": input_ctx, "output": output})

    async def log_user_feedback(self, session_id: str, turn_id: str, feedback: dict[str, Any]) -> None:
        await self.log(session_id, turn_id, "terminate", "user_feedback", feedback)
```

- [ ] **Step 3: 跑测试 + 提交**

```bash
uv run pytest tests/unit/test_trace.py -v
git add src/codeask/agent/trace.py tests/unit/test_trace.py
git commit -m "feat(agent): AgentTraceLogger with locked event-type vocabulary"
```

---

## Task 12: ToolRegistry + ToolContext + ToolResult

**Files:**
- Create: `src/codeask/agent/tools.py`
- Create: `tests/unit/test_tool_registry.py`

按 `tools.md` §2-§7 + `agent-runtime.md` §3 (allowed tools per stage) 落地。

**ToolResult** 标准结构（`tools.md` §5）：

```python
class ToolResult(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None
    summary: str | None = None
    evidence: list[dict[str, Any]] = []
    truncated: bool = False
    hint: str | None = None
    error_code: str | None = None
    message: str | None = None
    recoverable: bool = True
```

**ToolContext**（`tools.md` §2）：dataclass，含 `session_id`, `turn_id`, `feature_ids`, `repo_bindings`, `subject_id`, `phase` (AgentState), `limits`（dict）。

**ToolDef 注册**（10 个工具 —— 见 `tools.md` §3 + `agent-runtime.md` §3）：
1. `select_feature` — 提供给 ScopeDetection 阶段（其实是给模型描述定界结果，参见 §4 落地：实际由 stage 内部直接基于 LLM 输出解析 feature_ids，本工具用作"显式让模型表达 feature 选择"的载体；input_schema：`{feature_ids: string[], confidence: enum, reason: string}`）
2. `search_wiki` — 委托 02 wiki-knowledge plan 的 `WikiSearchService.search(query, top_k)`
3. `read_wiki_doc` — 委托 02 plan 的 `WikiReader.read(document_id, heading_path?)`
4. `search_reports` — 委托 02 plan 的 `ReportSearchService.search(query, top_k)`
5. `read_report` — 委托 02 plan 的 `ReportReader.read(report_id)`
6. `grep_code` — 委托 03 code-index plan 的 `CodeSearchService.grep(repo_id, commit_sha, query, path_glob?)`
7. `read_file` — 委托 03 plan 的 `CodeReader.read(repo_id, commit_sha, path, line_start, line_end)`
8. `list_symbols` / `search_symbols` — 委托 03 plan 的 `SymbolService.search(repo_id, commit_sha, name)`
9. `read_log` — 读 session_attachments + 行号片段
10. `ask_user` — 由 orchestrator 拦截（不真正"执行"，而是中断当前 turn 并 yield SSE `ask_user` 事件）

每个工具的 input_schema 用 JSON Schema 表达（draft 7）；具体 schema 在 Task 12 各 stage 实现里集中列出（见 §11 strong reference 列表）。

ToolContext 携带 `phase`，ToolRegistry 在 `call(name, args)` 时按 `agent-runtime.md` §3 表校验：

```text
input_analysis: read_log
scope_detection: select_feature, ask_user
knowledge_retrieval: search_wiki, search_reports, read_wiki_doc, read_report
sufficiency_judgement: (no tools)
code_investigation: grep_code, read_file, list_symbols
version_confirmation: ask_user
evidence_synthesis: (no tools)
answer_finalization: (no tools)
report_drafting: (read-only access to evidence already collected; no new tools)
ask_user: (the meta-tool that triggers the AskUser stage)
```

阶段不允许的工具调用 → 返回 `ToolResult(ok=False, error_code="TOOL_NOT_ALLOWED_IN_STAGE", recoverable=True)`。

- [ ] **Step 1: 写测试 `tests/unit/test_tool_registry.py`** — 用 fake services（每个返 stub ToolResult），断言：
  - 已注册的 tool 调用成功
  - 未注册的 tool 调用返回 `error_code="UNKNOWN_TOOL"`
  - 阶段不允许的 tool 调用返回 `error_code="TOOL_NOT_ALLOWED_IN_STAGE"`
  - 参数 schema 不通过返回 `error_code="INVALID_ARGS"`
  - REPO_NOT_READY 透传（fake service 抛 `RepoNotReadyError` → ToolResult error_code）

- [ ] **Step 2: 实现 `src/codeask/agent/tools.py`** —— 包含：
  - `ToolResult`、`ToolContext` Pydantic / dataclass
  - 工具注册装饰器 `@registry.register(name, schema, allowed_phases)`
  - `ToolRegistry` 类：维护 name → (schema, fn, allowed_phases)
  - `ToolRegistry.tool_defs(phase)` —— 返回当前阶段允许的 ToolDef 列表（用于注入 LLM）
  - `ToolRegistry.call(name, args, ctx) -> ToolResult` —— 校验 → 调用 fn
  - `ToolRegistry.bootstrap(wiki_search_service, code_search_service, attachment_repo)` —— 工厂方法注入实际服务

  实现要点：
  - 用 `jsonschema` 校验 args（已在 transitive deps 里；如未 ready 加到 pyproject）
  - 每个工具实现是 `async def fn(args: dict, ctx: ToolContext) -> ToolResult`
  - `select_feature` 工具的 `fn` 仅做"参数 echo + 标记接受"——真正决策在 stage 模块
  - `ask_user` 的 `fn` 抛 `AskUserSignal(question, options)` —— orchestrator 捕获

- [ ] **Step 3: 在 `pyproject.toml` 增加 `jsonschema>=4.23` 到 dependencies。**

- [ ] **Step 4: 跑测试 + 提交**

```bash
uv sync && uv run pytest tests/unit/test_tool_registry.py -v
git add src/codeask/agent/tools.py tests/unit/test_tool_registry.py pyproject.toml uv.lock
git commit -m "feat(agent): ToolRegistry with phase-aware dispatch + JSON schema validation"
```

---

## Task 13: Prompts & MockLLMClient

**Files:**
- Create: `src/codeask/agent/prompts.py`
- Create: `tests/mocks/__init__.py`
- Create: `tests/mocks/mock_llm.py`
- Create: `tests/unit/test_prompts.py`

按 `agent-runtime.md` §9 落地 L0..L6 prompt 分层。每层独立 builder，最后由 `assemble_messages(stage, ctx)` 组装。

**层级实现要点**：
- L0：固定字符串常量（角色 + 输出格式 + 工具协议） —— `agent-runtime.md` §9
- L1：当前 stage 描述 + 允许工具清单 + 退出条件
- L2：选中特性的 `summary_text` + `navigation_index` + feature skill —— 来自 wiki-knowledge plan 的 service
- L3：repo bindings + commit + 路径提示
- L4：预检索结果（搜索命中 + 报告高优先级合并）
- L5：会话历史 turns（含工具调用 + 结果）
- L6：当前用户输入（含日志摘要 + 附件摘要 + 上下文字段）

**MockLLMClient**（`tests/mocks/mock_llm.py`）：

```python
"""Scriptable LLM client for integration tests."""

from collections.abc import AsyncIterator

from codeask.llm.types import LLMEvent, LLMMessage, ToolDef


class MockLLMClient:
    """Replay a fixed list of LLMEvent sequences, one per stream() call."""

    def __init__(self, scripts: list[list[LLMEvent]]) -> None:
        self._scripts = list(scripts)
        self._idx = 0
        self._calls: list[dict] = []

    @property
    def calls(self) -> list[dict]:
        return self._calls

    async def stream(self, messages: list[LLMMessage], tools: list[ToolDef],
                     max_tokens: int, temperature: float) -> AsyncIterator[LLMEvent]:
        self._calls.append({
            "messages": [m.model_dump() for m in messages],
            "tools": [t.model_dump() for t in tools],
            "max_tokens": max_tokens, "temperature": temperature,
        })
        if self._idx >= len(self._scripts):
            raise AssertionError(f"MockLLMClient: ran out of scripts (call #{self._idx + 1})")
        script = self._scripts[self._idx]
        self._idx += 1
        for ev in script:
            yield ev
```

外加便捷构造器：

```python
def text_message(text: str) -> list[LLMEvent]:
    return [
        LLMEvent(type="message_start", data={}),
        LLMEvent(type="text_delta", data={"delta": text}),
        LLMEvent(type="message_stop", data={"stop_reason": "end_turn"}),
    ]


def tool_call_message(call_id: str, name: str, arguments: dict) -> list[LLMEvent]:
    return [
        LLMEvent(type="message_start", data={}),
        LLMEvent(type="tool_call_start", data={"id": call_id, "name": name}),
        LLMEvent(type="tool_call_done", data={"id": call_id, "name": name, "arguments": arguments}),
        LLMEvent(type="message_stop", data={"stop_reason": "tool_call"}),
    ]
```

- [ ] **Step 1: 写测试 `tests/unit/test_prompts.py`** — 用 stub digest / repo binding / turn history 输入，断言 L0..L6 都出现在最终 messages 里；L2 不含报告（仅文档摘要）；L4 含报告高优先级合并标记。

- [ ] **Step 2: 实现 `src/codeask/agent/prompts.py`**

主接口：`assemble_messages(stage: AgentState, ctx: PromptContext) -> list[LLMMessage]`

`PromptContext` dataclass 字段：
- `user_question: str`
- `feature_digests: list[FeatureDigest]`（每个含 summary_text / navigation_index / feature_skill）
- `global_skill: str | None`
- `repo_bindings: list[RepoBinding]`
- `pre_retrieval_hits: list[KnowledgeHit]`（含 report_high_priority bool）
- `turn_history: list[LLMMessage]`
- `log_analysis: dict[str, Any] | None`
- `attachment_summaries: list[dict[str, Any]]`
- `extra_context: dict[str, Any]`（如 environment / service 等 §3 字段）

实现里把 L0..L6 拼成一个 `system` LLMMessage（L0+L1+L2+L3 合并）+ 历史 LLMMessages（L5）+ 当前 `user` LLMMessage（L4 预检索 inline + L6 输入）。

- [ ] **Step 3: 实现 `tests/mocks/mock_llm.py`**（如上代码块）

- [ ] **Step 4: 跑测试 + 提交**

```bash
uv run pytest tests/unit/test_prompts.py tests/mocks -v
git add src/codeask/agent/prompts.py tests/mocks/ tests/unit/test_prompts.py
git commit -m "feat(agent): L0-L6 prompt assembly + MockLLMClient for tests"
```

---

## Task 14: Stage modules — ScopeDetection / KnowledgeRetrieval / SufficiencyJudgement / CodeInvestigation

**Files:**
- Create: `src/codeask/agent/stages/__init__.py`
- Create: `src/codeask/agent/stages/input_analysis.py`
- Create: `src/codeask/agent/stages/scope_detection.py`
- Create: `src/codeask/agent/stages/knowledge_retrieval.py`
- Create: `src/codeask/agent/stages/sufficiency_judgement.py`
- Create: `src/codeask/agent/stages/code_investigation.py`
- Create: `src/codeask/agent/stages/version_confirmation.py`
- Create: `src/codeask/agent/stages/answer_finalization.py`
- Create: `src/codeask/agent/stages/evidence_synthesis.py`
- Create: `src/codeask/agent/stages/report_drafting.py`
- Create: `src/codeask/agent/stages/ask_user.py`
- Create: `tests/unit/test_stage_scope_detection.py`
- Create: `tests/unit/test_stage_sufficiency.py`

每个 stage 模块导出 `async def run(orchestrator_ctx) -> StageResult`。`StageResult` 字段：
- `next_state: AgentState`
- `events: list[AgentEvent]`（要给 SSE 的事件，按时间顺序）
- `evidence_added: list[Evidence]`
- `messages_appended: list[LLMMessage]`（要附加到下一阶段 history 的内容）

**stage 通用合约**：
- 进入时由 orchestrator 调 `trace_logger.log_stage_enter(...)`
- stage 内部如调 LLM，自己 `log_llm_input` + 流式 `log_llm_event`
- stage 退出时 `log_stage_exit(...)` 由 orchestrator 兜底

**A. ScopeDetection** (`stages/scope_detection.py`)：

输入：`PromptContext.user_question` + 所有 features 的 (id, name, summary_text 摘录) + log_analysis。
工作：
1. 用 L0..L6 + tool_choice=`{type: "tool", name: "select_feature"}` 强制模型必须用 `select_feature` 工具
2. 解析 tool_call_done 拿到 `{feature_ids, confidence, reason}`
3. 写 `agent_traces` `scope_decision`（input + output）
4. 输出 `AgentEvent(type="scope_detection", data={...})`
5. 决策：
   - confidence==low 或 feature_ids==[] 且无全局降级 → next=AskUser，附 `ask_user` event 让用户从候选选
   - 其他 → next=KnowledgeRetrieval，把选定 feature_ids 写到 session_features 表（source="auto"）

**B. KnowledgeRetrieval** (`stages/knowledge_retrieval.py`)：

工作：
1. 由 orchestrator 注入的 wiki_search_service 直接调 `search(query, feature_ids, top_k)` —— **不走 LLM**（与 SDD §5 "API 网关在进入主循环前执行一次同步预检索" 对齐；本阶段 = 同步预检索）
2. search 返回 `KnowledgeHit[]`（含 doc / report，已合并排序，报告高权重）
3. 把 hits 转 `Evidence`（type="wiki_doc" 或 "report"），加到 evidence_added
4. 输出每个 evidence 一个 SSE `evidence` event
5. next=SufficiencyJudgement

**C. SufficiencyJudgement** (`stages/sufficiency_judgement.py`)：

工作：
1. 让 LLM 看 user_question + 已收集证据片段 + 相关性分数（L4 inline）
2. tool_choice=auto，但用 system prompt 强制 JSON 输出 `{verdict, reason, next}`，verdict ∈ {enough, partial, insufficient}
3. 解析 LLM text → JSON
4. 写 `agent_traces` `sufficiency_decision`（input + output）
5. 输出 SSE `sufficiency_judgement` event
6. 决策：
   - verdict=enough → next=AnswerFinalization
   - verdict=partial 或 insufficient → next=CodeInvestigation
7. **UI "再深查一下" 兜底**：orchestrator 暴露一个 flag `force_code_investigation`（来自 session_turns 的 user_message metadata），若为 True 则强制 next=CodeInvestigation 而忽略 verdict

**D. CodeInvestigation** (`stages/code_investigation.py`)：

工作：
1. 必要时先经 VersionConfirmation：当 ctx 没有 commit 但需要代码 → next=VersionConfirmation
2. 进入 LLM 工具循环（最多 20 次，per `agent-runtime.md` §10）
3. 允许工具：grep_code / read_file / list_symbols
4. 每次 tool_call_done → ToolRegistry.call → 把 result 转 evidence（type="code"）+ 输出 SSE tool_call/tool_result
5. 模型 message_stop 时退出循环
6. next=AnswerFinalization

**E. VersionConfirmation** (`stages/version_confirmation.py`)：

工作：
- 简单实现：如 ctx 已有 default ref + commit hint → 直接绑定，next=CodeInvestigation
- 否则触发 `ask_user`（"这份日志对应哪个版本？"）

**F. AnswerFinalization** (`stages/answer_finalization.py`)：

工作：
1. LLM 生成最终回答；prompt 强制按 `evidence-report.md` §4 + §5 结构（结论 / 建议操作 / 置信度 / 不确定点 / 证据 IDs）
2. 流式 text_delta → SSE
3. 把 LLM text 解析成 `{claim, confidence, evidence_ids, missing_information, recommended_checks}`
4. 写 session_turns（role="agent", content=raw_text, evidence={"items": [...]}）
5. next=EvidenceSynthesis

**G. EvidenceSynthesis** (`stages/evidence_synthesis.py`)：

工作：把 collected evidence list 物化到 session_turns.evidence JSON（已在 AnswerFinalization 步 4 完成；本阶段做最终一致性写入 + log）。next=Terminate（一期不默认走 ReportDrafting）。

**H. ReportDrafting** (`stages/report_drafting.py`)：

工作：可选。从 session 拉 turns + evidence → 调 LLM 生成 Markdown 报告草稿 → 写 reports 表（draft 状态，由 02 wiki-knowledge plan 提供的 ReportRepo）。一期 stage 注册但仅在用户显式触发时调用；本计划默认不进入此阶段。

**I. AskUser** (`stages/ask_user.py`)：

工作：
1. yield SSE `ask_user` event with `{question, options, ask_id}`
2. orchestrator 把当前 turn 标记为"等待用户"，结束 SSE 流
3. 下一次用户回复（POST messages，含 reply_to=ask_id）→ orchestrator 从 `agent_traces` 重建 ctx → 跳回 ask_user 之前的状态继续

**J. InputAnalysis** (`stages/input_analysis.py`)：

工作：用 GenericLogAnalyzer（一期占位实现：正则提取 error code + symbol + trace_id + version hint）从用户输入 + 附件 text 提取 LogAnalysis。next=ScopeDetection。

**只为 ScopeDetection 与 SufficiencyJudgement 写完整单测**（最关键的两个 A2/A3 落地点），其他 stage 在 Task 16 集成测试覆盖。

- [ ] **Step 1: 写 `tests/unit/test_stage_scope_detection.py`** — 用 MockLLMClient 注入 `select_feature` tool_call_done，断言：(a) AgentEvent 类型 `scope_detection`；(b) trace_logger 写了 `scope_decision`；(c) confidence=low 时 next=AskUser；(d) confidence=high 时 next=KnowledgeRetrieval。

- [ ] **Step 2: 写 `tests/unit/test_stage_sufficiency.py`** — 注入 LLM text 输出 JSON `{verdict: "insufficient", reason, next}`，断言：(a) AgentEvent 类型 `sufficiency_judgement`；(b) trace_logger 写 `sufficiency_decision`；(c) verdict=enough → next=AnswerFinalization；(d) `force_code_investigation=True` 时不论 verdict 强制 next=CodeInvestigation。

- [ ] **Step 3: 实现 11 个 stage 模块**（每个 ~30-80 行，按上述 A-J 描述落地）

- [ ] **Step 4: 跑两个单测 + 提交**

```bash
uv run pytest tests/unit/test_stage_scope_detection.py tests/unit/test_stage_sufficiency.py -v
git add src/codeask/agent/stages/ tests/unit/test_stage_scope_detection.py tests/unit/test_stage_sufficiency.py
git commit -m "feat(agent): 11 stage modules with ScopeDetection/SufficiencyJudgement A2/A3 hooks"
```

---

## Task 15: AgentOrchestrator + 主循环

**Files:**
- Create: `src/codeask/agent/orchestrator.py`
- Create: `tests/integration/test_orchestrator_sufficient.py`

`AgentOrchestrator` 持有：`gateway: LLMGateway`, `tool_registry: ToolRegistry`, `trace_logger: AgentTraceLogger`, `session_repo`, `wiki_search_service`, `code_search_service`, `prompts: PromptAssembler`。

主接口：`async def run(session_id, turn_id, user_message, force_code_investigation=False) -> AsyncIterator[AgentEvent]`

主循环骨架：

```python
async def run(self, session_id, turn_id, user_message, force_code_investigation=False):
    state = AgentState.Initialize
    ctx = await self._build_context(session_id, turn_id, user_message, force_code_investigation)
    while state != AgentState.Terminate:
        await self._trace.log_stage_enter(session_id, turn_id, state.value, {"summary": "..."})
        stage_fn = self._stage_dispatch[state]
        result = await stage_fn(ctx)
        for ev in result.events:
            yield ev
        ctx = self._merge(ctx, result)
        await self._trace.log_stage_exit(session_id, turn_id, state.value, {"next": result.next_state.value})
        if not is_valid_transition(state, result.next_state):
            yield AgentEvent(type="error", data={"code": "INVALID_TRANSITION",
                                                  "message": f"{state}→{result.next_state}"})
            return
        # stage_transition SSE
        yield AgentEvent(type="stage_transition",
                         data={"from": state.value, "to": result.next_state.value, "message": None})
        state = result.next_state
        if state == AgentState.AskUser:
            # AskUser stage already yielded ask_user event; halt this turn
            return
    yield AgentEvent(type="done", data={"turn_id": turn_id})
```

关键细节：
- `_build_context` 拉 session、session_features、session_repo_bindings、session_turns（历史）、attachments，并执行预检索（KnowledgeRetrieval 阶段调用前的 §5 "同步预检索"）
- `_merge(ctx, result)` 把 result.evidence_added、result.messages_appended 合到 ctx
- LLM 流式事件中的 `text_delta` 由 stage 转换成 SSE `text_delta` AgentEvent
- 单 stage 内部出错 → yield AgentEvent error，orchestrator 终止本 turn 流（next_state 强行 Terminate）

集成测试 `tests/integration/test_orchestrator_sufficient.py`（路径 1：ScopeDetection → KnowledgeRetrieval → SufficiencyJudgement(enough) → AnswerFinalization → EvidenceSynthesis → Terminate）：

```python
"""Full happy path: knowledge sufficient, no code investigation."""

from collections.abc import AsyncIterator
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
from codeask.db.models import AgentTrace, Session, SessionTurn
from codeask.llm.gateway import ClientFactory, LLMGateway
from codeask.llm.repo import LLMConfigInput, LLMConfigRepo
from codeask.llm.types import LLMEvent
from tests.mocks.mock_llm import MockLLMClient, text_message, tool_call_message


@pytest_asyncio.fixture()
async def orchestrator(tmp_path: Path):  # type: ignore[no-untyped-def]
    eng = create_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    async with eng.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    sf = session_factory(eng)
    crypto = Crypto(Fernet.generate_key().decode())
    repo = LLMConfigRepo(sf, crypto)
    cfg_id = await repo.create(LLMConfigInput(
        name="d", protocol="openai", base_url=None, api_key="x",
        model_name="m", max_tokens=100, temperature=0.0, is_default=True,
    ))

    # Pre-script LLM events for: scope_detection (tool_call) + sufficiency (text JSON) + answer (text)
    scope = tool_call_message("tc_scope", "select_feature",
                              {"feature_ids": ["feat_order"], "confidence": "high",
                               "reason": "log mentions OrderService"})
    sufficiency = text_message('{"verdict":"enough","reason":"docs cover this","next":"answer_finalization"}')
    answer = text_message("结论：可能用户上下文为空。证据 [ev_1].")
    mock = MockLLMClient([scope, sufficiency, answer])

    factory = ClientFactory(provider_clients={"openai": lambda **_: mock})
    gateway = LLMGateway(repo, factory, base_delay=0.0)
    trace = AgentTraceLogger(sf)

    # Fake wiki / code services
    class FakeWikiService:
        async def search(self, query, feature_ids, top_k=10):
            return [{"id": "ev_1", "type": "wiki_doc", "summary": "OrderService timeout doc",
                     "score": 0.9, "report_high_priority": False}]

    class FakeCodeService:
        async def grep(self, *_, **__): return []
        async def read(self, *_, **__): return ""
        async def search_symbols(self, *_, **__): return []

    registry = ToolRegistry.bootstrap(
        wiki_search_service=FakeWikiService(),
        code_search_service=FakeCodeService(),
        attachment_repo=None,
    )

    async with sf() as s:
        s.add(Session(id="sess_1", title="t", created_by_subject_id="alice@dev-1", status="active"))
        s.add(SessionTurn(id="turn_1", session_id="sess_1", turn_index=0, role="user",
                          content="为什么订单偶发 500", evidence=None))
        await s.commit()

    yield AgentOrchestrator(
        gateway=gateway, tool_registry=registry, trace_logger=trace,
        session_factory=sf, wiki_search_service=FakeWikiService(),
        code_search_service=FakeCodeService(),
    ), sf
    await eng.dispose()


@pytest.mark.asyncio
async def test_full_happy_path(orchestrator) -> None:  # type: ignore[no-untyped-def]
    orch, sf = orchestrator
    events = []
    async for ev in orch.run("sess_1", "turn_1", "为什么订单偶发 500"):
        events.append(ev)
    types = [e.type for e in events]
    # Expect at minimum: scope_detection, evidence (KnowledgeRetrieval), sufficiency_judgement,
    # text_delta (AnswerFinalization), done
    assert "scope_detection" in types
    assert "sufficiency_judgement" in types
    assert "evidence" in types
    assert types[-1] == "done"

    async with sf() as s:
        traces = (await s.execute(select(AgentTrace).order_by(AgentTrace.created_at, AgentTrace.id))).scalars().all()
    assert any(t.event_type == "scope_decision" for t in traces)
    assert any(t.event_type == "sufficiency_decision" for t in traces)
    assert any(t.event_type == "stage_enter" and t.stage == "answer_finalization" for t in traces)
```

- [ ] **Step 1-3：写测试 → 实现 orchestrator → 跑测试 PASS。**

- [ ] **Step 4：提交**

```bash
git add src/codeask/agent/orchestrator.py tests/integration/test_orchestrator_sufficient.py
git commit -m "feat(agent): AgentOrchestrator main loop + happy-path integration test"
```

---

## Task 16: 集成测试 — insufficient 路径 + ask_user 路径

**Files:**
- Create: `tests/integration/test_orchestrator_insufficient.py`
- Create: `tests/integration/test_orchestrator_ask_user.py`

**Path 2: insufficient → CodeInvestigation**

`tests/integration/test_orchestrator_insufficient.py`：脚本化 LLM events：
1. ScopeDetection: tool_call select_feature → high confidence
2. SufficiencyJudgement: text JSON `{verdict: "insufficient", ...}`
3. CodeInvestigation: tool_call `grep_code(repo_id, query="OrderService")` → fake service 返 1 hit；接 message_stop
4. AnswerFinalization: text 结论

断言：
- types 包含 `tool_call`, `tool_result`, `evidence` (code 类型)
- agent_traces 含 `stage_enter` for `code_investigation`
- session_turns.evidence JSON 含 wiki + code 两条

**Path 3: ScopeDetection low → AskUser**

`tests/integration/test_orchestrator_ask_user.py`：脚本化：
1. ScopeDetection: tool_call select_feature → confidence=low

断言：
- types 含 `ask_user`
- 流以 `ask_user` 事件结束，**没有** `done` 事件
- agent_traces 含 `scope_decision` 但**没有** `sufficiency_decision`（确认 stage 提前终止）

**Path 4: force_code_investigation 兜底**

附加在 `test_orchestrator_insufficient.py` 里：第二个测试用 `force_code_investigation=True` + LLM 给 `verdict=enough`，断言仍走到 CodeInvestigation。

- [ ] **Step 1-3：写两个测试文件 → 跑 → PASS。**

- [ ] **Step 4：提交**

```bash
git add tests/integration/test_orchestrator_insufficient.py tests/integration/test_orchestrator_ask_user.py
git commit -m "test(agent): insufficient + ask_user + force-deep-search paths"
```

---

## Task 17: API endpoints — /api/llm-configs + /api/skills + /api/sessions

**Files:**
- Create: `src/codeask/api/schemas/__init__.py`
- Create: `src/codeask/api/schemas/llm_config.py`
- Create: `src/codeask/api/schemas/skill.py`
- Create: `src/codeask/api/schemas/session.py`
- Create: `src/codeask/api/llm_configs.py`
- Create: `src/codeask/api/skills.py`
- Create: `src/codeask/api/sessions.py`
- Modify: `src/codeask/app.py`（include 新 router + 在 lifespan 创建 orchestrator + repos）
- Create: `tests/integration/test_llm_configs_api.py`
- Create: `tests/integration/test_skills_api.py`
- Create: `tests/integration/test_sessions_api.py`

**Schemas**（Pydantic v2）：

`schemas/llm_config.py`：
- `LLMConfigCreate`：name / protocol / base_url / api_key / model_name / max_tokens / temperature / is_default
- `LLMConfigResponse`：id / name / protocol / base_url / api_key_masked / model_name / max_tokens / temperature / is_default

`schemas/skill.py`：
- `SkillCreate`：name / scope / feature_id / prompt_template
- `SkillResponse`：id + 同 Create

`schemas/session.py`：
- `SessionCreate`：title
- `SessionResponse`：id / title / created_by_subject_id / status / created_at / updated_at
- `MessageCreate`：content / feature_ids?: list[str] / repo_bindings?: list[{repo_id, ref}] / force_code_investigation?: bool / reply_to?: str
- `AttachmentResponse`：id / kind / file_path / mime_type

**API: `/api/llm-configs`** (`api/llm_configs.py`)：
- `POST /` —— LLMConfigCreate → repo.create → 201 LLMConfigResponse
- `GET /` —— repo.list → list[LLMConfigResponse]（masked key）
- `GET /{id}` —— get item，仅返 masked
- `DELETE /{id}` —— repo.delete → 204
- `PATCH /{id}` —— 修改非密字段；如改密钥单独走 PATCH 也加密

**API: `/api/skills`** (`api/skills.py`)：
- `POST /` / `GET /` / `GET /{id}` / `PATCH /{id}` / `DELETE /{id}` —— 直接 CRUD `Skill` 表

**API: `/api/sessions`** (`api/sessions.py`)：
- `POST /` —— body=SessionCreate，subject_id 来自 request.state，写 sessions 表 → 201 SessionResponse
- `GET /` —— list user's sessions（按 created_by_subject_id 过滤）
- `GET /{id}` —— 单 session 详情（含 turns / features / repo_bindings 摘要）
- `POST /{id}/messages` —— body=MessageCreate；返 SSE StreamingResponse；流程：
  1. 写 session_turns（user role）
  2. 写 session_features（如 body 给了 feature_ids，source="manual"）
  3. 写 session_repo_bindings（如 body 给了；解析 ref → commit 由 03 plan 服务）
  4. orchestrator.run(session_id, turn_id, content, force_code_investigation) yield AgentEvent
  5. SSEMultiplexer.format(event) → bytes，push 出 StreamingResponse
- `POST /{id}/attachments` —— multipart upload，写文件到 `~/.codeask/sessions/<id>/<att_id>`，写 session_attachments 表，返 AttachmentResponse；按 `session-input.md` §4 校验：拒绝二进制非日志类（按 mime + 扩展名白名单 .log/.txt/.md/.png/.jpg），单文件 ≤10MB

**修改 `src/codeask/app.py`**：在 lifespan 启动后创建 `LLMConfigRepo` / `LLMGateway` / `ToolRegistry` / `AgentOrchestrator` 单例挂 `app.state`；route handler 通过 dependency 拿。

**测试**：

`test_llm_configs_api.py`：(a) POST 创建 → 201；(b) GET list → masked；(c) DELETE → 204；(d) 创建第二个 is_default=True → 第一个 is_default 自动归 False

`test_skills_api.py`：(a) POST global skill；(b) POST feature skill 但 feature_id=null → 422；(c) list 返两条

`test_sessions_api.py`：(a) POST session → 201；(b) POST messages 用 MockLLMClient 跑通 happy path → SSE 流包含 `event: scope_detection` / `event: done`；(c) POST attachments 上传日志 → 201 + 文件落到 `~/.codeask/sessions/`

> MockLLMClient 在 test 里通过 `app.state.llm_gateway.client_factory.provider_clients["openai"]` monkeypatch 注入。

- [ ] **Step 1-3: 实现 schemas / routes / app.py 修改 / 三套测试 → PASS。**

- [ ] **Step 4: 手工冒烟（可选）：起服务，curl POST /api/llm-configs + /api/sessions/x/messages 看 SSE 流。**

- [ ] **Step 5: 提交**

```bash
git add src/codeask/api/schemas/ src/codeask/api/llm_configs.py src/codeask/api/skills.py \
    src/codeask/api/sessions.py src/codeask/app.py \
    tests/integration/test_llm_configs_api.py tests/integration/test_skills_api.py \
    tests/integration/test_sessions_api.py
git commit -m "feat(api): /api/llm-configs + /api/skills + /api/sessions with SSE messages"
```

---

## Task 18: 全量回归 + lint + type check + Self-review

**Files:**
- 无新增；只跑 CI 风格本地校验 + Self-review。

**自我对照（每条都要在执行时确认）**：

1. **Spec coverage**：
   - 9/9 状态机阶段全部有 stage 模块（Task 14） ✓
   - 8/8 表全部有 ORM + migration（Tasks 1-4） ✓
   - 3/3 API 全部实现（Task 17） ✓
   - ToolRegistry 含 10 个工具（Task 12） ✓
   - SSEMultiplexer 含 10 种事件（Task 10） ✓
   - agent_traces 写入：stage_enter / stage_exit / llm_input / llm_event / tool_call / tool_result / scope_decision / sufficiency_decision / user_feedback ✓

2. **Placeholder 扫描**：grep `TBD\|TODO\|XXX\|类似\|适当错误处理` 整个 src/ + plans/agent-runtime.md，应为 0 命中（除测试 stub 字符串）。

3. **类型一致**：
   - `LLMEvent.type` 在 types.py / client.py / gateway.py / mock_llm.py / 测试 都用同一 8 项枚举
   - `AgentState` 12 项在 state.py / orchestrator.py / stages/* / 测试都用同一 enum

4. **Migration 链**：0001 → ... → 0007 → 0008 → 0009 → 0010 → 0011 → 0012 单链；revision id 在执行前如发现 02/03 plan 实际 revision 编号不同，**整体重编号** 0007..0012 接续上一份。

5. **独立性**：foundation 已完成 + wiki-knowledge plan 提供 `WikiSearchService` + code-index plan 提供 `CodeSearchService`/`SymbolService`/`CodeReader`/`worktree.resolve_ref` —— 这是本计划"Depends on"中三份 plan 的全部依赖；不引入更多上游。

- [ ] **Step 1: 跑 ruff**

Run: `uv run ruff check src tests && uv run ruff format --check src tests`
Expected: 无错误。

- [ ] **Step 2: 跑 pyright**

Run: `uv run pyright src/codeask`
Expected: `0 errors`

- [ ] **Step 3: 跑全量 pytest**

Run: `uv run pytest -v`
Expected: 全部 PASS。本计划新增测试预期数量：
- `test_llm_config_model.py`: 2
- `test_session_models.py`: 3
- `test_turn_attachment_skill_models.py`: 3
- `test_agent_trace_model.py`: 1
- `test_llm_types.py`: 7
- `test_llm_config_repo.py`: 3
- `test_llm_client_adapter.py`: 2
- `test_llm_gateway.py`: 2
- `test_agent_state.py`: 3
- `test_sse.py`: 3
- `test_trace.py`: 1
- `test_tool_registry.py`: 5
- `test_prompts.py`: 4
- `test_stage_scope_detection.py`: 4
- `test_stage_sufficiency.py`: 4
- `test_orchestrator_sufficient.py`: 1
- `test_orchestrator_insufficient.py`: 2
- `test_orchestrator_ask_user.py`: 1
- `test_llm_configs_api.py`: 4
- `test_skills_api.py`: 3
- `test_sessions_api.py`: 3
- 合计：~61 + foundation 已有 23 ≈ 84+

- [ ] **Step 4: 跑端到端冒烟（可选但推荐）**

```bash
export CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
export CODEASK_DATA_DIR=/tmp/codeask-agent-smoke
./start.sh &
SERVER_PID=$!
sleep 3
# 创建 mock LLM config（不会真调外部 API；只是测路由）
curl -fs -X POST http://127.0.0.1:8000/api/llm-configs \
    -H "Content-Type: application/json" -H "X-Subject-Id: dev@local" \
    -d '{"name":"mock","protocol":"openai","api_key":"sk-mock","model_name":"gpt-4o","max_tokens":1000,"temperature":0.0,"is_default":true}'
curl -fs http://127.0.0.1:8000/api/llm-configs -H "X-Subject-Id: dev@local"
kill $SERVER_PID
```

- [ ] **Step 5: 打 tag**

```bash
git tag -a agent-runtime-v0.1.0 -m "Agent runtime milestone: 9-stage state machine + LLM gateway + SSE + tools"
```

---

## Task 19: 子计划 Hand-off — 给 frontend / metrics-eval / deployment

**Files:**
- Create: `docs/v1.0/plans/agent-runtime-handoff.md`

明确给后续 plans 的契约。

- [ ] **Step 1: 创建 hand-off doc**

````markdown
# Agent Runtime Hand-off — 给 05 / 06 / 07 后续计划

## 1. SSE 事件契约（消费方：05 frontend-workbench）

事件类型清单（已锁定，前端按这 10 个分发）：
`stage_transition | text_delta | tool_call | tool_result | evidence | scope_detection | sufficiency_judgement | ask_user | done | error`

每个事件的 `data` 字段结构见 `agent-runtime.md plans` Task 10。`stage` / `from` / `to` 字段使用 snake_case 字符串，与 AgentState enum value 一致。

## 2. agent_traces 表（消费方：06 metrics-eval）

`event_type` 枚举值已锁定：`stage_enter | stage_exit | llm_input | llm_event | tool_call | tool_result | scope_decision | sufficiency_decision | user_feedback`。

eval 数据点：
- A2 验证：聚合 `event_type='scope_decision'` payload + `event_type='user_feedback'` 中"用户改特性？"
- A3 验证：聚合 `event_type='sufficiency_decision'` payload + 用户是否点了"再深查一下"（前端把这条意图通过 `force_code_investigation=True` 传到 messages API，本计划已支持）

## 3. ORM 表（共用）

新增 8 张表（见 Task 1-4），后续 plan 不要改它们 schema；如需扩列开新 migration。

## 4. /api/feedback 接口（消费方：06）

本计划 **未** 实现 `/api/feedback`。06 metrics-eval plan 自己加：
- 表 `feedback`（session_id, turn_id, subject_id, verdict in (resolved/partial/wrong), note）
- POST `/api/sessions/{id}/turns/{turn_id}/feedback`
- 写入后在 `agent_traces` 也写一行 `event_type='user_feedback'`（调用 `AgentTraceLogger.log_user_feedback`）

## 5. `/api/audit-log` 与 `/api/frontend-events`（消费方：06）

同样不在本计划范围。06 plan 各自加表 + API。

## 6. 真实 LLM 端到端（消费方：07 deployment）

本计划测试全部用 MockLLMClient。07 plan 提供"smoke check with real provider"——读 `CODEASK_SMOKE_LLM_CONFIG_ID` 环境变量，跑一次 hello-world session。

## 7. 不在本计划落地的工具

- 多模态（图片附件）：一期 read_log 不解析 image，仅记录 metadata。06 / 后续版本扩展。
- LSP / 调用图：03 plan 已说明扩展位；本计划工具接口稳定。
````

- [ ] **Step 2: 提交**

```bash
git add docs/v1.0/plans/agent-runtime-handoff.md
git commit -m "docs(plans): agent-runtime hand-off conventions for downstream plans"
```

---

## 验收标志（计划完整通过后应满足）

- [x] 8 张表全部建立，Alembic head 是 `0012`
- [x] `/api/llm-configs` POST/GET/PATCH/DELETE 通；list 永远 mask key；最多一条 is_default=True
- [x] `/api/skills` CRUD 通；scope/feature_id 一致性 check 生效
- [x] `/api/sessions/{id}/messages` 返回 SSE 流；MockLLMClient 注入下三条路径都能跑通：
  - 知识库充分 → AnswerFinalization
  - 知识库不足 → CodeInvestigation → AnswerFinalization
  - ScopeDetection low confidence → AskUser，等待用户回复
- [x] agent_traces 写入：每条 LLM 调用、每个工具调用、ScopeDetection 决策、SufficiencyJudgement 决策都能落库
- [x] LLM 网关 retry：流式开始前的 retryable error 重试 ≤ 3 次；首 token 后不重试
- [x] 全量 `uv run pytest` PASS（≥84 测试）
- [x] `uv run ruff check && uv run pyright src/codeask` 零错误
- [x] git tag `agent-runtime-v0.1.0` 已打

---

## 不在本计划范围（明确推迟）

| 项 | 推迟到 | 原因 |
|---|---|---|
| 前端消费 SSE / 渲染调查面板 / 证据折叠 UI | 05 frontend-workbench | 后端契约已锁，前端独立实现 |
| feedback / frontend_events / audit_log 表 + API | 06 metrics-eval | 涉及"答得对不对"环路，本计划只埋 trace 钩子 |
| Eval harness（cases JSON + runner） | 06 metrics-eval | MockLLMClient 已就绪 |
| 真实 LLM provider 端到端冒烟（gpt-4o / claude-3.5） | 07 deployment | 需要真 API key + 计费 |
| 多模态图片输入 / OCR | MVP+ | 一期附件白名单不含 image binary 解析 |
| Prompt cache 接入 | MVP+ | LiteLLM 现已透传，但 CodeAsk 缓存层未上 |
| AskUser 跨轮恢复（complex re-entry from agent_traces） | 一期简化版：halt 当前 turn，下一条 user message 当成新 turn 起点；orchestrator 只读最近一次 ask_user trace 决定 resume state |
| Skill 注入到 prompt（global → feature 链注入） | 已在 Task 13 prompts.py 实现 L0/L2 注入 |
