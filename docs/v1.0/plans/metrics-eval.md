# Metrics & Eval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 PRD §5 / §7.1 / §10 的"alpha 用户跟踪表 + Agent eval 基线"——交付 `feedback` / `frontend_events` / `audit_log` 三张表 + 对应 REST API + 公共 `record_audit_log(...)` 函数（替换 02 / 04 plan 留的 stub）+ `evals/` 目录骨架（scope_detection / sufficiency / answer_quality 三集 + 1-2 exemplar case + score）+ MockLLMClient 脚本化回放增强 + GitHub Actions eval workflow + 反向指标审计单测。

**Architecture:** 测量 / 评测层与业务 Agent 解耦。线上指标走 `feedback` / `frontend_events` / `audit_log` 三张原始事件表（聚合计算延后，本计划只准备 raw 数据 + 只读读取）；线下 Agent eval 走项目根级 `evals/` 目录（与 `src/` 平级，不进 `src/codeask/`）。`record_audit_log` 是公共幂等函数，供 02 wiki / 04 agent-runtime 在状态转换点调用，本计划负责真正落地 + 替换其它 plan 的占位 stub。Eval harness 用 MockLLMClient 脚本化回放，PR-time CI 跑 scope_detection + sufficiency 子集，answer_quality 与真模型 eval 走手动 `workflow_dispatch`。

**Tech Stack:** Python 3.11, SQLAlchemy 2.0 async, FastAPI, pytest + pytest-asyncio, MockLLMClient (自实现), GitHub Actions

> 2026-05-02 implementation note：frontend-workbench 在本计划前已追加 `0013` / `0014` / `0015` 三个迁移，因此 metrics-eval 实际迁移为 `alembic/versions/20260502_0016_metrics_tables.py`，`down_revision = "0015"`。原计划正文中早期示例仍保留 `0013` 的历史上下文；以本 note、roadmap migration 链和仓库文件为准。

**Source SDD docs**（路径相对本文件 `docs/v1.0/plans/metrics-eval.md`）：
- `../design/api-data-model.md`
- `../design/metrics-collection.md`
- `../design/testing-eval.md`
- `../design/agent-runtime.md`
- `../design/dependencies.md`

**Depends on:** `docs/v1.0/plans/foundation.md`、`docs/v1.0/plans/wiki-knowledge.md`、`docs/v1.0/plans/code-index.md`、`docs/v1.0/plans/agent-runtime.md`

**Project root:** `/home/hzh/workspace/CodeAsk/`（与 `docs/` 同级）。

---

## File Structure

```text
CodeAsk/
├── alembic/versions/
│   └── 20260502_0016_metrics_tables.py        # feedback / frontend_events / audit_log
├── src/codeask/
│   ├── api/
│   │   ├── metrics.py                          # POST /feedback / POST /events / GET /audit-log
│   │   └── schemas/
│   │       └── metrics.py                      # Pydantic v2 输入输出 schema
│   ├── db/models/
│   │   ├── feedback.py
│   │   ├── frontend_event.py
│   │   ├── audit_log.py
│   │   └── __init__.py                         # re-export
│   └── metrics/
│       ├── __init__.py
│       └── audit.py                            # record_audit_log(...)
├── tests/
│   ├── unit/
│   │   ├── test_metrics_audit_writer.py
│   │   ├── test_metrics_schemas.py
│   │   ├── test_no_reverse_kpi_endpoints.py    # §7 反向指标审计
│   │   └── test_mock_llm_scripted_replay.py
│   ├── integration/
│   │   ├── test_metrics_migration.py
│   │   ├── test_metrics_feedback_api.py
│   │   ├── test_metrics_events_api.py
│   │   ├── test_metrics_audit_api.py
│   │   ├── test_metrics_cross_plan_hooks.py
│   │   └── test_evals_runner_smoke.py
│   └── mocks/
│       └── mock_llm.py                          # 04 plan 已起；本 plan 增量
├── evals/                                       # 项目根级，与 src/ 平级
│   ├── __init__.py
│   ├── types.py                                 # Case / Score / ScoreDimensions
│   ├── run.py                                   # CLI runner
│   ├── _baseline.json                           # red-line 比对基线
│   ├── scope_detection/{__init__.py, cases/seed_001.jsonl, fixtures/feature_summaries.json, score.py}
│   ├── sufficiency/    {__init__.py, cases/seed_001.jsonl, fixtures/kb_snapshot.json, score.py}
│   └── answer_quality/ {__init__.py, cases/seed_001.jsonl, fixtures/session_context.json, score.py}
└── .github/workflows/
    └── eval.yml                                 # PR: scope+suf / manual: full+answer_quality
```

**职责边界**：

- `db/models/*.py` 只定义 ORM；不计算 deflection（聚合留到 dashboard cron）
- `api/metrics.py` 只编排 HTTP；事件白名单校验在 schema 层
- `metrics/audit.py` 是无状态公共函数，幂等（同一 entity_type+entity_id+action+at(秒级)+subject_id 重复写不冲突）
- `evals/` 不 import `src/codeask` 内部 agent 实现——通过 MockLLMClient 黑盒驱动
- 跨 plan stub 替换：02 plan reports verify/unverify、documents delete；04 plan llm_configs/skills update 的 `# AUDIT_LOG_STUB` 占位由本 plan Task 7 替换为 `record_audit_log` 调用

---

## Task 1: ORM 模型 — feedback / frontend_events / audit_log

**Files:**
- Create: `src/codeask/db/models/feedback.py` / `frontend_event.py` / `audit_log.py`
- Modify: `src/codeask/db/models/__init__.py`

`metrics-collection.md` §8 数据源汇总锁定三张表。`feedback.feedback` 取值固定 `solved | partial | wrong`（§4 / §5 口径一致）。`frontend_events` 是开放 schema（`payload` JSON），事件白名单在 API 层。`audit_log` 走 `from_status` / `to_status` 双字段（§5 报告拒绝率需按状态转换计数）。

- [ ] **Step 1: 创建 `src/codeask/db/models/feedback.py`**

```python
"""feedback: 用户对单次问答的显式反馈（PRD §5.1 deflection 双轨主信号）."""

from typing import Literal

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin

FeedbackVerdict = Literal["solved", "partial", "wrong"]


class Feedback(Base, TimestampMixin):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint(
            "feedback IN ('solved', 'partial', 'wrong')", name="ck_feedback_verdict"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_turn_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("session_turns.id", ondelete="CASCADE"), index=True, nullable=False
    )
    feedback: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
```

- [ ] **Step 2: 创建 `src/codeask/db/models/frontend_event.py`**

```python
"""frontend_events: 前端打点（录入耗时 / 兜底使用 / 反馈点击等）."""

from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class FrontendEvent(Base, TimestampMixin):
    __tablename__ = "frontend_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    subject_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
```

- [ ] **Step 3: 创建 `src/codeask/db/models/audit_log.py`**

```python
"""audit_log: DB 表状态转换审计（报告 verify / unverify / 删除文档 / LLM 配置改动等）."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    subject_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
```

- [ ] **Step 4: 更新 `src/codeask/db/models/__init__.py` re-export**

在既有 imports 末尾追加：

```python
from codeask.db.models.audit_log import AuditLog
from codeask.db.models.feedback import Feedback
from codeask.db.models.frontend_event import FrontendEvent
```

`__all__` 末尾追加 `"AuditLog"`, `"Feedback"`, `"FrontendEvent"`。

- [ ] **Step 5: 跑现有测试确认 import 没破**

Run: `uv run pytest -v`
Expected: 既有测试全部 PASS（模型登记到 Base.metadata，无新测试）

- [ ] **Step 6: 提交**

```bash
git add src/codeask/db/models/feedback.py src/codeask/db/models/frontend_event.py \
        src/codeask/db/models/audit_log.py src/codeask/db/models/__init__.py
git commit -m "feat(db): metrics tables — feedback / frontend_events / audit_log"
```

---

## Task 2: Alembic migration `0016_metrics_tables`

**Files:**
- Create: `alembic/versions/20260502_0016_metrics_tables.py`
- Create: `tests/integration/test_metrics_migration.py`

revision id `0016`，`down_revision = "0015"`（frontend-workbench 的最后一份迁移）。

- [ ] **Step 1: 创建 `alembic/versions/20260502_0016_metrics_tables.py`**

```python
"""metrics: feedback / frontend_events / audit_log

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-29 00:06:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("session_turn_id", sa.String(length=64), nullable=False),
        sa.Column("feedback", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("subject_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_turn_id"], ["session_turns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("feedback IN ('solved', 'partial', 'wrong')", name="ck_feedback_verdict"),
    )
    op.create_index("ix_feedback_session_turn_id", "feedback", ["session_turn_id"])
    op.create_index("ix_feedback_subject_id", "feedback", ["subject_id"])

    op.create_table(
        "frontend_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("subject_id", sa.String(length=128), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_frontend_events_event_type", "frontend_events", ["event_type"])
    op.create_index("ix_frontend_events_session_id", "frontend_events", ["session_id"])
    op.create_index("ix_frontend_events_subject_id", "frontend_events", ["subject_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("subject_id", sa.String(length=128), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_entity_type", "audit_log", ["entity_type"])
    op.create_index("ix_audit_log_entity_id", "audit_log", ["entity_id"])
    op.create_index("ix_audit_log_subject_id", "audit_log", ["subject_id"])
    op.create_index("ix_audit_log_at", "audit_log", ["at"])


def downgrade() -> None:
    for ix in ("ix_audit_log_at", "ix_audit_log_subject_id", "ix_audit_log_entity_id", "ix_audit_log_entity_type"):
        op.drop_index(ix, table_name="audit_log")
    op.drop_table("audit_log")
    for ix in ("ix_frontend_events_subject_id", "ix_frontend_events_session_id", "ix_frontend_events_event_type"):
        op.drop_index(ix, table_name="frontend_events")
    op.drop_table("frontend_events")
    op.drop_index("ix_feedback_subject_id", table_name="feedback")
    op.drop_index("ix_feedback_session_turn_id", table_name="feedback")
    op.drop_table("feedback")
```

- [ ] **Step 2: 写测试 `tests/integration/test_metrics_migration.py`**

```python
"""Migration 0016 creates the three metrics tables and indexes."""

from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from codeask.migrations import run_migrations


@pytest.mark.asyncio
async def test_creates_metrics_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    run_migrations(f"sqlite:///{db_path}")
    eng = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with eng.connect() as conn:
        tables = await conn.run_sync(lambda s: inspect(s).get_table_names())
    for required in ("feedback", "frontend_events", "audit_log"):
        assert required in tables, f"missing {required}"
    await eng.dispose()


@pytest.mark.asyncio
async def test_creates_indexes(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    run_migrations(f"sqlite:///{db_path}")
    eng = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with eng.connect() as conn:
        idx = await conn.run_sync(
            lambda s: {row["name"] for row in inspect(s).get_indexes("audit_log")}
        )
    assert {"ix_audit_log_entity_type", "ix_audit_log_entity_id", "ix_audit_log_subject_id"} <= idx
    await eng.dispose()
```

- [ ] **Step 3: 跑测试 + 提交**

```bash
uv run pytest tests/integration/test_metrics_migration.py -v   # 2 PASS
git add alembic/versions/20260502_0016_metrics_tables.py tests/integration/test_metrics_migration.py
git commit -m "feat(migrations): 0016 metrics — feedback / frontend_events / audit_log"
```

---

## Task 3: Pydantic v2 schemas（含前端事件白名单）

**Files:**
- Create: `src/codeask/api/schemas/__init__.py`（如不存在）
- Create: `src/codeask/api/schemas/metrics.py`
- Create: `tests/unit/test_metrics_schemas.py`

事件白名单锁定为 `metrics-collection.md` §3 / §4 引用的事件子集。超出白名单的 `event_type` 在 API 层 422——避免脏数据塞满表。

- [ ] **Step 1: 创建 `src/codeask/api/schemas/__init__.py`（若尚不存在）**

```python
"""Pydantic v2 schemas for REST API request / response."""
```

- [ ] **Step 2: 创建 `src/codeask/api/schemas/metrics.py`**

```python
"""Schemas for metrics API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

FeedbackVerdict = Literal["solved", "partial", "wrong"]

# 与 metrics-collection.md §3 / §4 锁定的事件白名单。
# 新增事件需先更新本列表 + 同步 SDD。
ALLOWED_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "doc_edit_session_started",
        "doc_edit_session_completed",
        "force_deeper_investigation",
        "feature_switch",
        "report_unverify_clicked",
        "feedback_submitted",
        "session_naturally_ended",
        "ask_for_human_clicked",
    }
)


class FeedbackCreate(BaseModel):
    session_turn_id: str = Field(..., min_length=1, max_length=64)
    feedback: FeedbackVerdict
    note: str | None = Field(default=None, max_length=4000)


class FeedbackAck(BaseModel):
    ok: Literal[True] = True


class FrontendEventCreate(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=64)
    session_id: str | None = Field(default=None, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def _check_whitelist(cls, v: str) -> str:
        if v not in ALLOWED_EVENT_TYPES:
            raise ValueError(
                f"event_type '{v}' not in whitelist; "
                "extend ALLOWED_EVENT_TYPES + metrics-collection.md before sending"
            )
        return v


class FrontendEventAck(BaseModel):
    ok: Literal[True] = True
    id: str


class AuditLogEntry(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    action: str
    from_status: str | None
    to_status: str | None
    subject_id: str
    at: datetime


class AuditLogResponse(BaseModel):
    entries: list[AuditLogEntry]
```

- [ ] **Step 3: 写测试 `tests/unit/test_metrics_schemas.py`**

```python
"""Schema validation: feedback verdict + frontend event whitelist."""

import pytest
from pydantic import ValidationError

from codeask.api.schemas.metrics import (
    ALLOWED_EVENT_TYPES,
    FeedbackCreate,
    FrontendEventCreate,
)


def test_feedback_accepts_valid_verdicts() -> None:
    for v in ("solved", "partial", "wrong"):
        m = FeedbackCreate(session_turn_id="t1", feedback=v)  # type: ignore[arg-type]
        assert m.feedback == v


def test_feedback_rejects_unknown_verdict() -> None:
    with pytest.raises(ValidationError):
        FeedbackCreate(session_turn_id="t1", feedback="maybe")  # type: ignore[arg-type]


def test_event_accepts_whitelisted() -> None:
    m = FrontendEventCreate(event_type="doc_edit_session_started", payload={"x": 1})
    assert m.event_type == "doc_edit_session_started"


def test_event_rejects_off_whitelist() -> None:
    with pytest.raises(ValidationError):
        FrontendEventCreate(event_type="random_thing")


def test_whitelist_contains_critical_events() -> None:
    """Regression: protect events metrics-collection.md §3 depends on."""
    required = {
        "doc_edit_session_started",
        "doc_edit_session_completed",
        "force_deeper_investigation",
        "feature_switch",
    }
    assert required <= ALLOWED_EVENT_TYPES
```

- [ ] **Step 4: 跑测试 + 提交**

```bash
uv run pytest tests/unit/test_metrics_schemas.py -v   # 5 PASS
git add src/codeask/api/schemas/__init__.py src/codeask/api/schemas/metrics.py \
        tests/unit/test_metrics_schemas.py
git commit -m "feat(metrics/schemas): feedback verdict + event whitelist"
```

---

## Task 4: `record_audit_log(...)` 公共函数

**Files:**
- Create: `src/codeask/metrics/__init__.py`
- Create: `src/codeask/metrics/audit.py`
- Create: `tests/unit/test_metrics_audit_writer.py`

公共函数，幂等（ID = sha1 of `entity_type|entity_id|action|at(秒级)|subject_id`）。供 02 / 04 等 plan 在状态转换处调用。

- [ ] **Step 1: 创建 `src/codeask/metrics/__init__.py`**

```python
"""Metrics layer: audit log writer + (later) deflection aggregation."""

from codeask.metrics.audit import record_audit_log

__all__ = ["record_audit_log"]
```

- [ ] **Step 2: 创建 `src/codeask/metrics/audit.py`**

```python
"""Public audit-log writer. Idempotent at second-resolution."""

import hashlib
from datetime import datetime, timezone

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models.audit_log import AuditLog


def _stable_id(entity_type: str, entity_id: str, action: str, at: datetime, subject_id: str) -> str:
    h = hashlib.sha1(
        f"{entity_type}|{entity_id}|{action}|{at.isoformat(timespec='seconds')}|{subject_id}".encode()
    ).hexdigest()
    return f"al_{h[:24]}"


async def record_audit_log(
    session: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    subject_id: str,
    from_status: str | None = None,
    to_status: str | None = None,
    at: datetime | None = None,
) -> str:
    """Write one audit row. Returns the (possibly already-existing) row id.

    Idempotent: same (entity_type, entity_id, action, second-truncated at,
    subject_id) yields same id; SQLite INSERT OR IGNORE keeps the first write.
    """
    when = (at or datetime.now(timezone.utc)).replace(microsecond=0)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    row_id = _stable_id(entity_type, entity_id, action, when, subject_id)

    stmt = (
        sqlite_insert(AuditLog)
        .values(
            id=row_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            subject_id=subject_id,
            at=when,
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )
    await session.execute(stmt)
    return row_id
```

- [ ] **Step 3: 写测试 `tests/unit/test_metrics_audit_writer.py`**

```python
"""record_audit_log writes one row, idempotent on re-call."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from codeask.db import Base, create_engine, session_factory
from codeask.db.models import AuditLog
from codeask.metrics.audit import record_audit_log


@pytest_asyncio.fixture()
async def factory(tmp_path: Path):  # type: ignore[no-untyped-def]
    eng = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield session_factory(eng)
    await eng.dispose()


@pytest.mark.asyncio
async def test_writes_one_row(factory) -> None:  # type: ignore[no-untyped-def]
    async with factory() as s:
        row_id = await record_audit_log(
            s, entity_type="report", entity_id="rep_1", action="verify",
            from_status="draft", to_status="verified", subject_id="alice@dev",
        )
        await s.commit()
        row = (await s.execute(select(AuditLog).where(AuditLog.id == row_id))).scalar_one()
    assert row.entity_type == "report"
    assert row.from_status == "draft" and row.to_status == "verified"


@pytest.mark.asyncio
async def test_idempotent_at_second_resolution(factory) -> None:  # type: ignore[no-untyped-def]
    when = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)
    async with factory() as s:
        id1 = await record_audit_log(s, entity_type="report", entity_id="r1",
            action="verify", subject_id="alice@dev", at=when)
        id2 = await record_audit_log(s, entity_type="report", entity_id="r1",
            action="verify", subject_id="alice@dev", at=when)
        await s.commit()
    assert id1 == id2
    async with factory() as s:
        rows = (await s.execute(select(AuditLog))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_different_subject_distinct_rows(factory) -> None:  # type: ignore[no-untyped-def]
    when = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)
    async with factory() as s:
        id1 = await record_audit_log(s, entity_type="report", entity_id="r1",
            action="unverify", subject_id="alice@dev", at=when)
        id2 = await record_audit_log(s, entity_type="report", entity_id="r1",
            action="unverify", subject_id="bob@dev", at=when)
        await s.commit()
    assert id1 != id2
```

- [ ] **Step 4: 跑测试 + 提交**

```bash
uv run pytest tests/unit/test_metrics_audit_writer.py -v   # 3 PASS
git add src/codeask/metrics/__init__.py src/codeask/metrics/audit.py \
        tests/unit/test_metrics_audit_writer.py
git commit -m "feat(metrics): record_audit_log public function (idempotent at second-resolution)"
```

---

## Task 5: API endpoints — POST /feedback / POST /events / GET /audit-log

**Files:**
- Create: `src/codeask/api/metrics.py`
- Modify: `src/codeask/app.py`（include_router）
- Modify: `tests/conftest.py`（追加 `seeded_session_turn` fixture）
- Create: `tests/integration/test_metrics_feedback_api.py` / `test_metrics_events_api.py` / `test_metrics_audit_api.py`

`POST /feedback` 写一行 → 返回 `{ok: true}`，**deflection 计算延后**。`GET /audit-log` 必须按 `entity_type` + `entity_id` 过滤。

- [ ] **Step 1: 创建 `src/codeask/api/metrics.py`**

```python
"""Metrics REST API: feedback / events / audit-log read."""

import secrets
from datetime import timezone

import structlog
from fastapi import APIRouter, Query, Request, status
from sqlalchemy import select

from codeask.api.schemas.metrics import (
    AuditLogEntry,
    AuditLogResponse,
    FeedbackAck,
    FeedbackCreate,
    FrontendEventAck,
    FrontendEventCreate,
)
from codeask.db.models import AuditLog, Feedback, FrontendEvent

router = APIRouter()
log = structlog.get_logger("codeask.api.metrics")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


@router.post("/feedback", response_model=FeedbackAck, status_code=status.HTTP_201_CREATED)
async def post_feedback(payload: FeedbackCreate, request: Request) -> FeedbackAck:
    factory = request.app.state.session_factory
    subject_id = request.state.subject_id
    async with factory() as session:
        session.add(Feedback(
            id=_new_id("fb"),
            session_turn_id=payload.session_turn_id,
            feedback=payload.feedback,
            note=payload.note,
            subject_id=subject_id,
        ))
        await session.commit()
    log.info("feedback_recorded", session_turn_id=payload.session_turn_id, feedback=payload.feedback)
    # NOTE: deflection rate aggregation is intentionally deferred (offline cron).
    return FeedbackAck()


@router.post("/events", response_model=FrontendEventAck, status_code=status.HTTP_201_CREATED)
async def post_event(payload: FrontendEventCreate, request: Request) -> FrontendEventAck:
    factory = request.app.state.session_factory
    subject_id = request.state.subject_id
    event_id = _new_id("ev")
    async with factory() as session:
        session.add(FrontendEvent(
            id=event_id,
            event_type=payload.event_type,
            session_id=payload.session_id,
            subject_id=subject_id,
            payload=payload.payload,
        ))
        await session.commit()
    log.info("frontend_event_recorded", event_type=payload.event_type, session_id=payload.session_id)
    return FrontendEventAck(id=event_id)


@router.get("/audit-log", response_model=AuditLogResponse)
async def list_audit_log(
    request: Request,
    entity_type: str = Query(..., min_length=1, max_length=64),
    entity_id: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(default=50, ge=1, le=500),
) -> AuditLogResponse:
    factory = request.app.state.session_factory
    async with factory() as session:
        stmt = (
            select(AuditLog)
            .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
            .order_by(AuditLog.at.desc())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).scalars().all()
    entries = [
        AuditLogEntry(
            id=r.id, entity_type=r.entity_type, entity_id=r.entity_id, action=r.action,
            from_status=r.from_status, to_status=r.to_status, subject_id=r.subject_id,
            at=r.at if r.at.tzinfo else r.at.replace(tzinfo=timezone.utc),
        )
        for r in rows
    ]
    return AuditLogResponse(entries=entries)
```

- [ ] **Step 2: 修改 `src/codeask/app.py`**

在 `app.include_router(healthz_router, prefix="/api")` 之后追加：

```python
    from codeask.api.metrics import router as metrics_router
    app.include_router(metrics_router, prefix="/api")
```

- [ ] **Step 3: 在 `tests/conftest.py` 末尾追加 `seeded_session_turn` fixture**

> 如上游 plan 已提供此 fixture，跳过。

```python


@pytest_asyncio.fixture()
async def seeded_session_turn(app) -> str:  # type: ignore[no-untyped-def]
    """Insert a minimal session_turns row so feedback FK can be satisfied."""
    from sqlalchemy import text
    factory = app.state.session_factory
    async with factory() as s:
        await s.execute(
            text(
                "INSERT INTO session_turns (id, session_id, role, content, created_at, updated_at) "
                "VALUES ('turn_x', 'sess_x', 'assistant', 'hi', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        await s.commit()
    return "turn_x"
```

- [ ] **Step 4: 写 `tests/integration/test_metrics_feedback_api.py`**

```python
"""POST /api/feedback writes one row + returns ok."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import Feedback


@pytest.mark.asyncio
async def test_post_feedback_creates_row(  # type: ignore[no-untyped-def]
    client: AsyncClient, app, seeded_session_turn
) -> None:
    r = await client.post(
        "/api/feedback",
        json={"session_turn_id": seeded_session_turn, "feedback": "solved", "note": "thx"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert r.status_code == 201, r.text
    assert r.json() == {"ok": True}
    factory = app.state.session_factory
    async with factory() as s:
        rows = (await s.execute(select(Feedback))).scalars().all()
    assert len(rows) == 1
    assert rows[0].feedback == "solved"
    assert rows[0].subject_id == "alice@dev-1"


@pytest.mark.asyncio
async def test_post_feedback_rejects_unknown_verdict(client: AsyncClient) -> None:
    r = await client.post(
        "/api/feedback", json={"session_turn_id": "turn_x", "feedback": "ok-ish"}
    )
    assert r.status_code == 422
```

- [ ] **Step 5: 写 `tests/integration/test_metrics_events_api.py`**

```python
"""POST /api/events validates whitelist + writes payload."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import FrontendEvent


@pytest.mark.asyncio
async def test_event_writes_payload(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    r = await client.post(
        "/api/events",
        json={"event_type": "force_deeper_investigation", "session_id": "sess_1",
              "payload": {"sufficiency_verdict": "sufficient", "user_overrode": True}},
        headers={"X-Subject-Id": "bob@dev"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["ok"] is True
    assert r.json()["id"].startswith("ev_")
    factory = app.state.session_factory
    async with factory() as s:
        rows = (await s.execute(select(FrontendEvent))).scalars().all()
    assert len(rows) == 1
    assert rows[0].event_type == "force_deeper_investigation"
    assert rows[0].payload["sufficiency_verdict"] == "sufficient"


@pytest.mark.asyncio
async def test_event_rejects_off_whitelist(client: AsyncClient) -> None:
    r = await client.post("/api/events", json={"event_type": "totally_unknown_event", "payload": {}})
    assert r.status_code == 422
```

- [ ] **Step 6: 写 `tests/integration/test_metrics_audit_api.py`**

```python
"""GET /api/audit-log filters by entity + returns DESC by at."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from codeask.metrics.audit import record_audit_log


@pytest.mark.asyncio
async def test_audit_log_filters_and_orders(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    factory = app.state.session_factory
    base = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
    async with factory() as s:
        await record_audit_log(s, entity_type="report", entity_id="rep_a", action="verify",
            from_status="draft", to_status="verified", subject_id="alice@dev", at=base)
        await record_audit_log(s, entity_type="report", entity_id="rep_a", action="unverify",
            from_status="verified", to_status="draft", subject_id="bob@dev",
            at=base + timedelta(hours=2))
        await record_audit_log(s, entity_type="report", entity_id="rep_b", action="verify",
            subject_id="alice@dev", at=base)
        await s.commit()

    r = await client.get("/api/audit-log", params={"entity_type": "report", "entity_id": "rep_a"})
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert len(entries) == 2
    assert entries[0]["action"] == "unverify"
    assert entries[1]["action"] == "verify"


@pytest.mark.asyncio
async def test_audit_log_requires_filters(client: AsyncClient) -> None:
    r = await client.get("/api/audit-log")
    assert r.status_code == 422
```

- [ ] **Step 7: 跑全部新增测试 + 提交**

```bash
uv run pytest tests/integration/test_metrics_feedback_api.py \
              tests/integration/test_metrics_events_api.py \
              tests/integration/test_metrics_audit_api.py -v
git add src/codeask/api/metrics.py src/codeask/app.py tests/conftest.py \
        tests/integration/test_metrics_feedback_api.py \
        tests/integration/test_metrics_events_api.py \
        tests/integration/test_metrics_audit_api.py
git commit -m "feat(api/metrics): POST /feedback POST /events GET /audit-log"
```

---

## Task 6: 反向指标审计单测

**Files:**
- Create: `tests/unit/test_no_reverse_kpi_endpoints.py`

`metrics-collection.md` §7 锁定四项反向指标：token 消耗 / 工具调用次数 / 提问数量 / 回答字数 不作为 KPI 字段。本测试是产品防线——扫所有路由 + OpenAPI schema，禁止暴露这类字段。

- [ ] **Step 1: 创建 `tests/unit/test_no_reverse_kpi_endpoints.py`**

```python
"""Regression: metrics-collection.md §7 forbids token/tool-count KPI exposure."""

import re

import pytest
from fastapi import FastAPI

from codeask.app import create_app
from codeask.settings import Settings

REVERSE_KPI_PATTERNS = (
    re.compile(r"token[_-]?count", re.IGNORECASE),
    re.compile(r"tool[_-]?call[_-]?count", re.IGNORECASE),
    re.compile(r"question[_-]?count", re.IGNORECASE),
    re.compile(r"answer[_-]?word[_-]?count", re.IGNORECASE),
    re.compile(r"/api/(token|tool[_-]?call|word|cost)[_-]?count", re.IGNORECASE),
    re.compile(r"/api/kpi/(token|tool|cost)", re.IGNORECASE),
)


@pytest.fixture()
def app(monkeypatch: pytest.MonkeyPatch, tmp_path) -> FastAPI:  # type: ignore[no-untyped-def]
    from cryptography.fernet import Fernet

    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    return create_app(Settings())  # type: ignore[call-arg]


def test_no_endpoint_path_resembles_reverse_kpi(app: FastAPI) -> None:
    paths = [route.path for route in app.routes if hasattr(route, "path")]
    for p in paths:
        for pat in REVERSE_KPI_PATTERNS:
            assert not pat.search(p), (
                f"endpoint {p} looks like a reverse-indicator KPI exposure; "
                "see metrics-collection.md §7."
            )


def test_openapi_schema_has_no_reverse_kpi_field(app: FastAPI) -> None:
    schema = app.openapi()
    for component in schema.get("components", {}).get("schemas", {}).values():
        for prop in (component.get("properties") or {}):
            for pat in REVERSE_KPI_PATTERNS:
                assert not pat.search(prop), (
                    f"OpenAPI property {prop} matches reverse-KPI pattern {pat.pattern}; "
                    "see metrics-collection.md §7."
                )
```

- [ ] **Step 2: 跑测试 + 提交**

```bash
uv run pytest tests/unit/test_no_reverse_kpi_endpoints.py -v   # 2 PASS
git add tests/unit/test_no_reverse_kpi_endpoints.py
git commit -m "test(metrics): assert no reverse-KPI endpoints/fields exposed"
```

---

## Task 7: 跨 plan stub 替换（02 / 04 plan 留下的 audit-log 占位）

**Files:**
- Modify: 02 plan 的 `src/codeask/api/reports.py`、`src/codeask/api/documents.py` 中的 `# AUDIT_LOG_STUB`
- Modify: 04 plan 的 `src/codeask/api/llm_configs.py`、`src/codeask/api/skills.py` 中的 `# AUDIT_LOG_STUB`
- Create: `tests/integration/test_metrics_cross_plan_hooks.py`

02 / 04 plan 在状态转换 handler 留下占位 `# AUDIT_LOG_STUB: replace in metrics-eval plan`；本任务替换为 `record_audit_log` 调用。

> **执行约束**：搜 `# AUDIT_LOG_STUB` 注释 → 按 entity_type 替换；不重写整个 handler。

- [ ] **Step 1: 替换 02 plan reports verify handler**

```python
    from codeask.metrics.audit import record_audit_log

    await record_audit_log(
        session,
        entity_type="report",
        entity_id=report_id,
        action="verify",
        from_status="draft",
        to_status="verified",
        subject_id=request.state.subject_id,
    )
```

`unverify` 同理：`action="unverify", from_status="verified", to_status="draft"`。

- [ ] **Step 2: 替换 02 plan documents delete handler**

```python
    from codeask.metrics.audit import record_audit_log

    await record_audit_log(
        session,
        entity_type="document",
        entity_id=document_id,
        action="delete",
        from_status="active",
        to_status="deleted",
        subject_id=request.state.subject_id,
    )
```

- [ ] **Step 3: 替换 04 plan llm_configs / skills update handler**

```python
    from codeask.metrics.audit import record_audit_log

    await record_audit_log(
        session,
        entity_type="llm_config",  # or "skill"
        entity_id=config_id,        # or skill_id
        action="update",
        subject_id=request.state.subject_id,
    )
```

- [ ] **Step 4: 写 `tests/integration/test_metrics_cross_plan_hooks.py`**

如 02 plan 未提供 `seeded_report_draft` / `seeded_report_verified` fixture，给两个 case 加 `@pytest.mark.skip(reason="seed fixtures from 02 plan not yet wired")` 等回填。本计划自身的责任只到 stub 替换。

```python
"""Cross-plan: report verify/unverify produces audit_log rows."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import AuditLog


@pytest.mark.asyncio
async def test_report_verify_creates_audit_row(  # type: ignore[no-untyped-def]
    client: AsyncClient, app, seeded_report_draft
) -> None:
    rid = seeded_report_draft
    r = await client.post(f"/api/reports/{rid}/verify", headers={"X-Subject-Id": "alice@dev"})
    assert r.status_code in (200, 204), r.text
    factory = app.state.session_factory
    async with factory() as s:
        rows = (await s.execute(
            select(AuditLog).where(
                AuditLog.entity_type == "report",
                AuditLog.entity_id == rid,
                AuditLog.action == "verify",
            )
        )).scalars().all()
    assert len(rows) == 1
    assert rows[0].from_status == "draft" and rows[0].to_status == "verified"
    assert rows[0].subject_id == "alice@dev"


@pytest.mark.asyncio
async def test_report_unverify_creates_audit_row(  # type: ignore[no-untyped-def]
    client: AsyncClient, app, seeded_report_verified
) -> None:
    rid = seeded_report_verified
    r = await client.post(f"/api/reports/{rid}/unverify", headers={"X-Subject-Id": "bob@dev"})
    assert r.status_code in (200, 204), r.text
    factory = app.state.session_factory
    async with factory() as s:
        rows = (await s.execute(
            select(AuditLog).where(AuditLog.entity_id == rid, AuditLog.action == "unverify")
        )).scalars().all()
    assert len(rows) == 1
    assert rows[0].from_status == "verified" and rows[0].to_status == "draft"
```

- [ ] **Step 5: 跑测试 + 提交**

```bash
uv run pytest tests/integration/test_metrics_cross_plan_hooks.py -v
git add src/codeask/api/reports.py src/codeask/api/llm_configs.py \
        src/codeask/api/skills.py src/codeask/api/documents.py \
        tests/integration/test_metrics_cross_plan_hooks.py
git commit -m "feat(metrics): replace 02/04 audit-log stubs with real record_audit_log calls"
```

---

## Task 8: MockLLMClient 脚本化回放增强

**Files:**
- Modify: `tests/mocks/mock_llm.py`（04 plan 已起骨架）
- Create: `tests/unit/test_mock_llm_scripted_replay.py`

04 plan 一期 `MockLLMClient` 只返回固定文本。本计划追加 `ScriptedMockLLMClient` 支持按预设顺序回放工具调用 + 文本。

- [ ] **Step 1: 在 `tests/mocks/mock_llm.py` 末尾追加**

```python


from dataclasses import dataclass
from typing import Any


@dataclass
class ScriptStep:
    """A single replay step. Either text or a tool call."""

    text: str | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] | None = None
    finish: bool = False


class ScriptedMockLLMClient:
    """Replay a fixed list of ScriptStep regardless of input.

    Used by evals/run.py to drive the agent through deterministic trajectories
    without hitting a real model.
    """

    def __init__(self, steps: list[ScriptStep]) -> None:
        if not steps:
            raise ValueError("ScriptedMockLLMClient requires at least one step")
        self._steps = list(steps)
        self._cursor = 0

    def reset(self) -> None:
        self._cursor = 0

    async def next_step(self) -> ScriptStep:
        if self._cursor >= len(self._steps):
            raise IndexError(
                "ScriptedMockLLMClient exhausted; eval case has more turns than scripted"
            )
        step = self._steps[self._cursor]
        self._cursor += 1
        return step
```

- [ ] **Step 2: 写测试 `tests/unit/test_mock_llm_scripted_replay.py`**

```python
"""ScriptedMockLLMClient replays steps in order and raises when exhausted."""

import pytest

from tests.mocks.mock_llm import ScriptedMockLLMClient, ScriptStep


@pytest.mark.asyncio
async def test_replays_in_order() -> None:
    client = ScriptedMockLLMClient([
        ScriptStep(tool_name="search_wiki", tool_arguments={"q": "order"}),
        ScriptStep(text="The answer is..."),
        ScriptStep(text="...done.", finish=True),
    ])
    s1 = await client.next_step()
    s2 = await client.next_step()
    s3 = await client.next_step()
    assert s1.tool_name == "search_wiki"
    assert s2.text == "The answer is..."
    assert s3.finish


@pytest.mark.asyncio
async def test_exhaustion_raises() -> None:
    client = ScriptedMockLLMClient([ScriptStep(text="only", finish=True)])
    await client.next_step()
    with pytest.raises(IndexError):
        await client.next_step()


def test_requires_at_least_one_step() -> None:
    with pytest.raises(ValueError):
        ScriptedMockLLMClient([])
```

- [ ] **Step 3: 跑测试 + 提交**

```bash
uv run pytest tests/unit/test_mock_llm_scripted_replay.py -v   # 3 PASS
git add tests/mocks/mock_llm.py tests/unit/test_mock_llm_scripted_replay.py
git commit -m "feat(mock_llm): ScriptedMockLLMClient for eval-driven replay"
```

---

## Task 9: Eval harness 框架（types / runner / scope_detection 集）

**Files:**
- Create: `evals/__init__.py` / `evals/types.py` / `evals/run.py`
- Create: `evals/scope_detection/{__init__.py, cases/seed_001.jsonl, fixtures/feature_summaries.json, score.py}`

`evals/` 在项目根级（dependencies.md §4 锁定）。`run.py` 是 CLI runner——加载 JSONL → 默认 stub agent（直接回放 expected）→ score → 输出聚合 JSON。`types.py` 共享 Case/Score schema。

- [ ] **Step 1: 创建 `evals/__init__.py`**

```python
"""Offline Agent eval harness. Layout described in testing-eval.md §4.1."""
```

- [ ] **Step 2: 创建 `evals/types.py`**

```python
"""Shared eval data types."""

from typing import Any

from pydantic import BaseModel, Field


class Case(BaseModel):
    """One test case, common across all eval suites."""

    id: str
    input: dict[str, Any]
    expected: dict[str, Any]
    annotator: str
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None


class ScoreDimensions(BaseModel):
    overall: float = Field(..., ge=0.0, le=1.0)
    breakdown: dict[str, float] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class Score(BaseModel):
    case_id: str
    dimensions: ScoreDimensions
    passed: bool


class SuiteReport(BaseModel):
    suite: str
    n_cases: int
    n_passed: int
    avg_score: float
    per_case: list[Score]
```

- [ ] **Step 3: 创建 `evals/scope_detection/__init__.py`**

```python
"""A2 — scope detection eval suite (testing-eval.md §4.2)."""
```

- [ ] **Step 4: 创建 `evals/scope_detection/fixtures/feature_summaries.json`**

```json
[
  {"id": "feat_order", "name": "订单", "summary": "下单 / 支付 / 退款 / 订单查询全流程", "owner": "alice@dev"},
  {"id": "feat_settle", "name": "结算", "summary": "对账 / 资金划转 / 商户结算", "owner": "bob@dev"},
  {"id": "feat_inventory", "name": "库存", "summary": "SKU 库存 / 锁库存 / 出入库", "owner": "carol@dev"}
]
```

- [ ] **Step 5: 创建 `evals/scope_detection/cases/seed_001.jsonl`**

> JSONL = 每行一个 JSON 对象。第一个 case 单特性明确命中、第二个 case 模糊应触发 ask_user。

```jsonl
{"id":"scope_001","input":{"question":"订单提交失败后多久退款？","attachments":[],"feature_fixture":"feature_summaries.json"},"expected":{"correct_feature_id":"feat_order","acceptable_feature_ids":["feat_order"],"should_trigger_ask_user":false},"annotator":"alice@2026-04-29","tags":["domain:order","complexity:low"],"notes":"显式提到订单 + 退款；命中 feat_order。"}
{"id":"scope_002","input":{"question":"那个金额对不上的问题怎么办","attachments":[],"feature_fixture":"feature_summaries.json"},"expected":{"correct_feature_id":null,"acceptable_feature_ids":["feat_order","feat_settle"],"should_trigger_ask_user":true},"annotator":"alice@2026-04-29","tags":["ambiguous","ask_user"],"notes":"指代不清；应主动追问是订单金额还是结算金额。"}
```

- [ ] **Step 6: 创建 `evals/scope_detection/score.py`**

```python
"""Score scope_detection runs (testing-eval.md §4.2)."""

from typing import Any

from evals.types import Case, Score, ScoreDimensions


def score(case: Case, agent_output: dict[str, Any]) -> Score:
    """agent_output schema: {selected_feature_id, ranked_feature_ids, confidence, triggered_ask_user}."""
    expected = case.expected
    acceptable = set(expected.get("acceptable_feature_ids") or [])
    selected = agent_output.get("selected_feature_id")
    ranked = agent_output.get("ranked_feature_ids") or []
    triggered = bool(agent_output.get("triggered_ask_user"))
    expected_trigger = bool(expected.get("should_trigger_ask_user"))

    top1 = 1.0 if selected in acceptable else 0.0
    top3 = 1.0 if any(fid in acceptable for fid in ranked[:3]) else 0.0
    ask_user_match = 1.0 if triggered == expected_trigger else 0.0

    notes: list[str] = []
    if expected_trigger and triggered:
        overall = (top3 + ask_user_match) / 2
        notes.append("ask_user case: scoring on top3 + ask_user_match only")
    else:
        overall = top1 * 0.5 + top3 * 0.3 + ask_user_match * 0.2

    return Score(
        case_id=case.id,
        dimensions=ScoreDimensions(
            overall=overall,
            breakdown={"top1": top1, "top3": top3, "ask_user_match": ask_user_match},
            notes=notes,
        ),
        passed=overall >= 0.7,
    )
```

- [ ] **Step 7: 创建 `evals/run.py`**

```python
"""CLI runner: load JSONL cases, drive (stub) agent, score, print report.

Usage:
    uv run python -m evals.run --suite scope_detection
    uv run python -m evals.run --suite sufficiency --limit 5
    uv run python -m evals.run --suite answer_quality --emit-json /tmp/report.json
"""

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any

from evals.types import Case, Score, SuiteReport

_HERE = Path(__file__).resolve().parent


def _load_cases(suite: str, limit: int | None) -> list[Case]:
    path = _HERE / suite / "cases" / "seed_001.jsonl"
    cases: list[Case] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(Case.model_validate_json(line))
        if limit and len(cases) >= limit:
            break
    return cases


def _load_score(suite: str):  # type: ignore[no-untyped-def]
    return importlib.import_module(f"evals.{suite}.score").score


def _stub_agent_run(case: Case, suite: str) -> dict[str, Any]:
    """Default stub: replay `expected` as agent_output (smoke harness end-to-end).

    Real eval-time replacement plugs ScriptedMockLLMClient + agent runtime in.
    """
    if suite == "scope_detection":
        return {
            "selected_feature_id": case.expected.get("correct_feature_id"),
            "ranked_feature_ids": case.expected.get("acceptable_feature_ids") or [],
            "confidence": "medium",
            "triggered_ask_user": case.expected.get("should_trigger_ask_user", False),
        }
    if suite == "sufficiency":
        return {
            "decision": case.expected.get("decision"),
            "rationale": " ".join(case.expected.get("rationale_keywords") or []),
            "recommend_code_investigation": case.expected.get("should_recommend_code_investigation", False),
        }
    if suite == "answer_quality":
        return {
            "answer_text": "[stub answer]",
            "cited_evidence": case.expected.get("must_cite_evidence", False),
            "disclosed_uncertainty": case.expected.get("must_disclose_uncertainty") or [],
            "decision_phrasing": False,
            "code_evidence_bound_to_commit": case.expected.get("must_bind_commit_for_code_evidence", False),
        }
    raise ValueError(f"unknown suite: {suite}")


def run_suite(suite: str, limit: int | None = None) -> SuiteReport:
    cases = _load_cases(suite, limit)
    score_fn = _load_score(suite)
    per_case: list[Score] = [score_fn(c, _stub_agent_run(c, suite)) for c in cases]
    n_passed = sum(1 for s in per_case if s.passed)
    avg = sum(s.dimensions.overall for s in per_case) / max(len(per_case), 1)
    return SuiteReport(suite=suite, n_cases=len(per_case), n_passed=n_passed, avg_score=avg, per_case=per_case)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True, choices=("scope_detection", "sufficiency", "answer_quality"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--emit-json", type=str, default=None)
    args = parser.parse_args()

    report = run_suite(args.suite, args.limit)
    out = report.model_dump(mode="json")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    if args.emit_json:
        Path(args.emit_json).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if report.n_passed == report.n_cases else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 8: 跑 scope_detection eval 冒烟**

Run: `uv run python -m evals.run --suite scope_detection`
Expected: stdout 输出 JSON 报告，`n_cases=2, n_passed=2`（stub agent 直接回放 expected）

- [ ] **Step 9: 提交**

```bash
git add evals/__init__.py evals/types.py evals/run.py evals/scope_detection/
git commit -m "feat(evals): A2 scope_detection harness — types / runner / 2 seed cases / score"
```

---

## Task 10: Eval — sufficiency 集 + answer_quality 集

**Files:**
- Create: `evals/sufficiency/{__init__.py, cases/seed_001.jsonl, fixtures/kb_snapshot.json, score.py}`
- Create: `evals/answer_quality/{__init__.py, cases/seed_001.jsonl, fixtures/session_context.json, score.py}`

`testing-eval.md` §4.3 sufficiency 评分（决策准确率 / 漏判率 / 误判率 / 理由覆盖率，漏判致命）；§4.4 answer_quality（必须引用证据 / 绑定 commit / 承认不确定性 / 避免决策语气）。

- [ ] **Step 1: 创建 `evals/sufficiency/__init__.py`**

```python
"""A3 — sufficiency judgement eval suite (testing-eval.md §4.3)."""
```

- [ ] **Step 2: 创建 `evals/sufficiency/fixtures/kb_snapshot.json`**

```json
{
  "feat_order": [
    {"doc_id": "doc_order_refund_policy", "summary": "退款时效与金额规则", "matched_chunks": ["退款 T+1 到账..."]},
    {"doc_id": "doc_order_status_machine", "summary": "订单状态机", "matched_chunks": ["created → paid → shipped..."]}
  ]
}
```

- [ ] **Step 3: 创建 `evals/sufficiency/cases/seed_001.jsonl`**

```jsonl
{"id":"suf_001","input":{"question":"订单退款 T+1 还是 T+0？","feature_id":"feat_order","kb_fixture":"kb_snapshot.json"},"expected":{"decision":"sufficient","rationale_keywords":["退款时效","T+1"],"should_recommend_code_investigation":false},"annotator":"alice@2026-04-29","tags":["kb_hit","baseline"],"notes":"知识库直接命中退款时效。"}
{"id":"suf_002","input":{"question":"如果在 order 表里把 payment_method 改成枚举，下游会有哪些代码受影响？","feature_id":"feat_order","kb_fixture":"kb_snapshot.json"},"expected":{"decision":"insufficient","rationale_keywords":["字段变更","影响清单","下游"],"should_recommend_code_investigation":true},"annotator":"alice@2026-04-29","tags":["schema_change","needs_code"],"notes":"知识库无字段变更影响清单；必须进代码层。"}
```

- [ ] **Step 4: 创建 `evals/sufficiency/score.py`**

```python
"""Score sufficiency runs (testing-eval.md §4.3)."""

from typing import Any

from evals.types import Case, Score, ScoreDimensions


def score(case: Case, agent_output: dict[str, Any]) -> Score:
    """agent_output schema: {decision, rationale, recommend_code_investigation}."""
    expected = case.expected
    expected_decision = expected.get("decision")
    expected_keywords: list[str] = expected.get("rationale_keywords") or []
    expected_recommend = bool(expected.get("should_recommend_code_investigation"))

    actual_decision = agent_output.get("decision")
    rationale = (agent_output.get("rationale") or "").lower()
    actual_recommend = bool(agent_output.get("recommend_code_investigation"))

    decision_match = 1.0 if actual_decision == expected_decision else 0.0
    # asymmetric: false_sufficient (说够了但其实不够) is fatal — A3 leak
    false_sufficient = 1.0 if (
        expected_decision == "insufficient" and actual_decision == "sufficient"
    ) else 0.0
    recommend_match = 1.0 if actual_recommend == expected_recommend else 0.0
    if expected_keywords:
        hit = sum(1 for kw in expected_keywords if kw.lower() in rationale)
        rationale_coverage = hit / len(expected_keywords)
    else:
        rationale_coverage = 1.0

    overall = (
        decision_match * 0.5
        + (1.0 - false_sufficient) * 0.2
        + recommend_match * 0.15
        + rationale_coverage * 0.15
    )
    notes: list[str] = []
    if false_sufficient:
        notes.append("FATAL: judged sufficient when expected insufficient (A3 leak)")
    return Score(
        case_id=case.id,
        dimensions=ScoreDimensions(
            overall=overall,
            breakdown={
                "decision_match": decision_match,
                "false_sufficient": false_sufficient,
                "recommend_match": recommend_match,
                "rationale_coverage": rationale_coverage,
            },
            notes=notes,
        ),
        passed=(overall >= 0.7 and false_sufficient == 0.0),
    )
```

- [ ] **Step 5: 创建 `evals/answer_quality/__init__.py`**

```python
"""Answer quality eval suite (testing-eval.md §4.4)."""
```

- [ ] **Step 6: 创建 `evals/answer_quality/fixtures/session_context.json`**

```json
{
  "session_with_code_ref": {
    "feature_id": "feat_order",
    "repo_id": "repo_main",
    "commit_sha": "abc1234",
    "user_question": "订单状态机有哪几个状态？",
    "kb_hits": ["doc_order_status_machine"]
  }
}
```

- [ ] **Step 7: 创建 `evals/answer_quality/cases/seed_001.jsonl`**

```jsonl
{"id":"qa_001","input":{"context_fixture":"session_context.json","context_key":"session_with_code_ref"},"expected":{"must_cite_evidence":true,"must_disclose_uncertainty":[],"must_not_phrase_as_decision":true,"must_bind_commit_for_code_evidence":true},"annotator":"alice@2026-04-29","tags":["doc_hit","code_ref"],"notes":"代码相关回答必须绑定 commit。"}
```

- [ ] **Step 8: 创建 `evals/answer_quality/score.py`**

```python
"""Score answer_quality runs (testing-eval.md §4.4)."""

from typing import Any

from evals.types import Case, Score, ScoreDimensions


def score(case: Case, agent_output: dict[str, Any]) -> Score:
    """agent_output schema: {answer_text, cited_evidence, disclosed_uncertainty,
    decision_phrasing, code_evidence_bound_to_commit}."""
    expected = case.expected

    cited = agent_output.get("cited_evidence", False)
    cite_score = 1.0 if (cited or not expected.get("must_cite_evidence")) else 0.0

    disclosed = agent_output.get("disclosed_uncertainty") or []
    expected_disclose: list[str] = expected.get("must_disclose_uncertainty") or []
    if expected_disclose:
        disclose_score = sum(1 for x in expected_disclose if x in disclosed) / len(expected_disclose)
    else:
        disclose_score = 1.0

    decision_phrasing = bool(agent_output.get("decision_phrasing"))
    no_decision_score = 1.0 if (
        not decision_phrasing or not expected.get("must_not_phrase_as_decision")
    ) else 0.0

    bound = agent_output.get("code_evidence_bound_to_commit", False)
    commit_score = 1.0 if (bound or not expected.get("must_bind_commit_for_code_evidence")) else 0.0

    overall = (cite_score + disclose_score + no_decision_score + commit_score) / 4
    return Score(
        case_id=case.id,
        dimensions=ScoreDimensions(
            overall=overall,
            breakdown={
                "cite": cite_score,
                "disclose": disclose_score,
                "no_decision_phrasing": no_decision_score,
                "commit_binding": commit_score,
            },
        ),
        passed=overall >= 0.75,
    )
```

- [ ] **Step 9: 跑两套 eval 冒烟**

```bash
uv run python -m evals.run --suite sufficiency
uv run python -m evals.run --suite answer_quality
```
Expected: 两套都返回 JSON 报告，`n_passed == n_cases`

- [ ] **Step 10: 提交**

```bash
git add evals/sufficiency/ evals/answer_quality/
git commit -m "feat(evals): A3 sufficiency + answer_quality suites — exemplar cases + score"
```

---

## Task 11: Eval runner 集成测试

**Files:**
- Create: `tests/integration/test_evals_runner_smoke.py`

确保 `evals/run.py` 不光"能从命令行跑出 JSON"，而且**能从 pytest 进程里 import 并跑通**——避免 CI 写错路径却没人发现。

- [ ] **Step 1: 创建 `tests/integration/test_evals_runner_smoke.py`**

```python
"""evals/run.py loadable from pytest, runs each suite, all stub cases pass."""

import pytest

from evals.run import run_suite


@pytest.mark.parametrize("suite", ["scope_detection", "sufficiency", "answer_quality"])
def test_suite_runs_and_passes_stub(suite: str) -> None:
    report = run_suite(suite)
    assert report.n_cases >= 1
    assert report.n_passed == report.n_cases, (
        f"suite {suite} failing stub cases: "
        f"{[s.case_id for s in report.per_case if not s.passed]}"
    )
    assert 0.0 <= report.avg_score <= 1.0


def test_score_dimensions_breakdown_present() -> None:
    report = run_suite("scope_detection")
    for s in report.per_case:
        assert s.dimensions.breakdown, f"case {s.case_id} missing breakdown"
        for k, v in s.dimensions.breakdown.items():
            assert 0.0 <= v <= 1.0, f"dimension {k} out of range: {v}"
```

- [ ] **Step 2: 跑测试 + 提交**

```bash
uv run pytest tests/integration/test_evals_runner_smoke.py -v   # 4 PASS
git add tests/integration/test_evals_runner_smoke.py
git commit -m "test(evals): runner smoke + dimension breakdown sanity"
```

---

## Task 12: GitHub Actions eval workflow

**Files:**
- Create: `evals/_baseline.json`
- Create: `.github/workflows/eval.yml`

PR 时跑 `scope_detection` + `sufficiency`（MockLLM/stub 模式，单次 < 30s）；红线：A2 top-1 不退化 > 5pp / A3 漏判率不上升。`answer_quality` 与真模型 eval 走 `workflow_dispatch`。

`evals/_baseline.json` 是仓库内的"基线快照"，PR 报告与之对比。初始化用本计划 stub 跑出来的结果（avg=1.0），后续随真 agent 接入再更新。

- [ ] **Step 1: 创建 `evals/_baseline.json`**

```json
{
  "scope_detection": {"avg_score": 1.0, "n_passed_ratio": 1.0},
  "sufficiency": {"avg_score": 1.0, "n_passed_ratio": 1.0}
}
```

- [ ] **Step 2: 创建 `.github/workflows/eval.yml`**

```yaml
name: Agent Eval

on:
  pull_request:
    paths:
      - "src/codeask/**"
      - "evals/**"
      - "tests/mocks/mock_llm.py"
      - ".github/workflows/eval.yml"
  workflow_dispatch:
    inputs:
      include_answer_quality:
        description: "Run answer_quality suite (slow, real model in future)"
        type: boolean
        default: false

jobs:
  pr-suites:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v3
      - name: Setup Python
        run: uv python install 3.11
      - name: Install deps
        run: uv sync
      - name: Run scope_detection eval
        run: uv run python -m evals.run --suite scope_detection --emit-json scope_detection.json
      - name: Run sufficiency eval
        run: uv run python -m evals.run --suite sufficiency --emit-json sufficiency.json
      - name: Compare vs baseline (red line)
        run: |
          uv run python - <<'PY'
          import json, sys
          from pathlib import Path

          baseline = json.loads(Path("evals/_baseline.json").read_text())
          for suite, threshold_drop in (("scope_detection", 0.05), ("sufficiency", 0.0)):
              report = json.loads(Path(f"{suite}.json").read_text())
              base = baseline[suite]["avg_score"]
              drop = base - report["avg_score"]
              print(f"{suite}: avg_score={report['avg_score']:.3f} baseline={base:.3f} drop={drop:.3f}")
              if drop > threshold_drop:
                  print(f"FAIL: {suite} dropped > {threshold_drop:.2f} from baseline")
                  sys.exit(1)
          print("Eval red lines OK")
          PY
      - name: Upload reports
        uses: actions/upload-artifact@v4
        with:
          name: eval-reports
          path: |
            scope_detection.json
            sufficiency.json

  full-suites-manual:
    if: github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v3
      - name: Setup Python
        run: uv python install 3.11
      - name: Install deps
        run: uv sync
      - name: Run scope_detection
        run: uv run python -m evals.run --suite scope_detection
      - name: Run sufficiency
        run: uv run python -m evals.run --suite sufficiency
      - name: Run answer_quality
        if: ${{ inputs.include_answer_quality }}
        run: uv run python -m evals.run --suite answer_quality
```

- [ ] **Step 3: 本地 dry-run 校验 workflow YAML 语法（可选）**

```bash
actionlint .github/workflows/eval.yml || echo "actionlint not installed; CI 第一次跑会暴露"
```

- [ ] **Step 4: 提交**

```bash
git add .github/workflows/eval.yml evals/_baseline.json
git commit -m "ci(eval): PR workflow with red-line check + manual answer_quality dispatch"
```

---

## Task 13: 全量回归 + 验收

**Files:** 无新增；跑 CI 风格本地校验 + 打 tag。

- [ ] **Step 1: 跑 ruff**

Run: `uv run ruff check src tests evals && uv run ruff format --check src tests evals`
Expected: 无错误。如有 format diff，运行 `uv run ruff format src tests evals` 后重跑。

- [ ] **Step 2: 跑 pyright**

Run: `uv run pyright src/codeask evals`
Expected: 0 errors

- [ ] **Step 3: 跑全量 pytest**

Run: `uv run pytest -v`

本计划新增的测试预期数量：

- `tests/integration/test_metrics_migration.py`: 2
- `tests/unit/test_metrics_schemas.py`: 5
- `tests/unit/test_metrics_audit_writer.py`: 3
- `tests/integration/test_metrics_feedback_api.py`: 2
- `tests/integration/test_metrics_events_api.py`: 2
- `tests/integration/test_metrics_audit_api.py`: 2
- `tests/unit/test_no_reverse_kpi_endpoints.py`: 2
- `tests/integration/test_metrics_cross_plan_hooks.py`: 2（可能 skip）
- `tests/unit/test_mock_llm_scripted_replay.py`: 3
- `tests/integration/test_evals_runner_smoke.py`: 4
- 合计：本计划新增 **27** 条；与 foundation + 02/03/04 既有测试合计 PASS

- [ ] **Step 4: 跑 CLI eval 验收**

```bash
uv run python -m evals.run --suite scope_detection
uv run python -m evals.run --suite sufficiency
uv run python -m evals.run --suite answer_quality
```
Expected: 三套都 `n_passed == n_cases`

- [ ] **Step 5: 端到端冒烟（API 三个端点）**

```bash
export CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
export CODEASK_DATA_DIR=/tmp/codeask-metrics-check
./start.sh &
SERVER_PID=$!
sleep 3
curl -fs -X POST http://127.0.0.1:8000/api/events \
  -H "X-Subject-Id: alice@local" -H "Content-Type: application/json" \
  -d '{"event_type":"doc_edit_session_started","session_id":"s1","payload":{"feature_id":"feat_order"}}'; echo
curl -fs "http://127.0.0.1:8000/api/audit-log?entity_type=report&entity_id=rep_x"; echo
kill $SERVER_PID
```
Expected: events 返回 `{"ok":true,"id":"ev_..."}`；audit-log 返回 `{"entries":[]}`。

- [ ] **Step 6: 如有 ruff format 改动，提交**

```bash
git status
git add -u && git commit -m "style: ruff format" || true
```

- [ ] **Step 7: 打 tag**

```bash
git tag -a metrics-eval-v0.1.0 -m "Metrics & Eval milestone: feedback / events / audit_log + eval harness"
```

---

## 验收标志

- [x] `feedback` / `frontend_events` / `audit_log` 三表创建，migration `0016` 接 `0015`
- [x] `POST /api/feedback` 写一行 + 返回 `{ok:true}`；非法 verdict → 422
- [x] `POST /api/events` 白名单生效；非白名单 → 422；payload 写入 JSON 字段
- [x] `GET /api/audit-log?entity_type=&entity_id=&limit=` 只读、按 `at desc`
- [x] `record_audit_log(...)` 幂等（同秒 + 同 actor + 同 action 重复写不增行）
- [x] 02 plan reports verify/unverify、documents delete、04 plan llm_configs/skills update 占位 stub 全部替换为 `record_audit_log` 调用
- [x] `evals/scope_detection` / `evals/sufficiency` / `evals/answer_quality` 各自 ≥ 1 exemplar case + score + harness 跑通
- [x] `evals/run.py --suite ...` 三套 stub agent 全 `n_passed == n_cases`
- [x] `tests/mocks/mock_llm.py` 增加 `ScriptedMockLLMClient`，eval harness 引用得到
- [x] `.github/workflows/eval.yml` PR 触发 + manual `workflow_dispatch`，含 red-line 校验
- [x] `tests/unit/test_no_reverse_kpi_endpoints.py` PASS — 无 token / tool-count / question-count / answer-word-count 路由或字段
- [x] 全量 `uv run pytest` 本计划新增 27 条 PASS
- [x] `uv run ruff check && uv run pyright` 0 错误
- [x] git tag `metrics-eval-v0.1.0` 已打

---

## 不在本计划范围（明确推迟）

| 项 | 推迟到 | 原因 |
|---|---|---|
| 真模型 eval 跑批 | 手动 ad-hoc（`workflow_dispatch`） | 真模型成本与速度都不适合 PR 阻塞 |
| 完整 30+ 种子 case | alpha 内容工作 | 本 plan 只交付 schema + harness + 1-2 exemplar |
| Maintainer Dashboard UI | metrics-eval 之后的前端增强 | 本 plan 准备 raw 数据并接入会话反馈；Dashboard 仍需基于 raw 数据另做视图 |
| Deflection rate 完整聚合（cron） | 后续优化 | 本 plan 仅 raw `feedback` + 写入 API |
| 答得过浅率自动化、回流率向量算法 | alpha 后期 | metrics-collection.md §3.3 / §5 锁定 alpha 先人工抽样 |
| 隐式 deflection N 分钟阈值校准 | alpha 第一周 | metrics-collection.md §4 拍 30 分钟 → 真实数据校准 |
| `feedback.note` 内容关键词分析 | 数据科学侧 | 一期只存原文 |
| 标注一致性度量（A3 双标注 disagreement 池） | alpha 内容流程 | 工程侧只交付存储 + 评分公式 |

---

## 与其它 plan 的衔接 + SDD 同步

- 依赖 foundation.md：`Base` / `TimestampMixin` / `Settings` / `SubjectIdMiddleware` / `app.state.session_factory` / `migrations.run_migrations` 全部沿用
- 依赖 02 wiki-knowledge plan：reports / documents handler 的 `# AUDIT_LOG_STUB` 由 Task 7 替换
- 依赖 03 code-index plan：`session_turns` 表（feedback FK）由 03/04 创建；测试用 `seeded_session_turn` fixture 注入最小行
- 依赖 04 agent-runtime plan：`MockLLMClient` 骨架由 04 plan 交付；Task 8 增量增强；llm_configs/skills handler stub 由 Task 7 替换
- 被 05 frontend-workbench plan 依赖：前端调用 `POST /api/events` + `POST /api/feedback`；Maintainer Dashboard 读 `audit_log` + 派生指标
- 被 07 deployment plan 依赖：`.github/workflows/eval.yml` 与 07 的 `backend.yml` / `frontend.yml` 并列

本计划不改动 SDD——它实现 `metrics-collection.md` + `testing-eval.md` §4 的既有契约。如实施过程中需 SDD 改动（如新增事件类型），按 foundation hand-off §6 同步更新；本 plan 落地后冻结。
