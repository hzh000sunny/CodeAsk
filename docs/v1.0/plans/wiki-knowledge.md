# Wiki Knowledge Implementation Plan

> **Implementation status:** 已完成并合入 `main`。本地 tag：`wiki-knowledge-v0.1.0`。当前 Alembic head 已到 `0005`，后续 `code-index` plan 从 `0006` 起步。
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 CodeAsk 知识库底座——特性 / 文档 / 报告三套 ORM 模型 + Alembic migrations、文档解析切块流水线、SQLite FTS5（分词 + n-gram + 报告）三表索引、`WikiSearchService` 多路召回、报告 draft → verified 闭环 + 一键回退、Pydantic v2 schemas 与 `/api/features` `/api/documents` `/api/reports` REST endpoints 全套打通。

**Architecture:** 在 foundation 计划提供的 FastAPI + SQLAlchemy 2.0 async + Alembic 地基上，新增 `src/codeask/wiki/` 业务域。文档上传走 `markdown-it-py` / `pypdfium2` / `python-docx` 解析为 chunks，落表 `document_chunks`，同步索引到 `docs_fts`（porter 分词 BM25）和 `docs_ngram_fts`（trigram 兜底）。报告生命周期由 `ReportService` 管，verified 时入 `reports_fts`，撤销时下架；撤销/验证两动作调用 `audit_log` writer 占位（实际 writer 由 06 metrics-eval 计划落地）。`WikiSearchService` 融合三路召回，命中报告时附 `verified_by` / `verified_at` / `commit_sha`。所有 endpoints 透过 `request.state.subject_id` 记录 owner 身份。

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0 async, aiosqlite, Alembic, markdown-it-py, pypdfium2, python-docx, structlog, pytest, pytest-asyncio, httpx

**Source SDD docs**（路径相对本文件 `docs/v1.0/plans/wiki-knowledge.md`）：
- `../design/api-data-model.md`
- `../design/wiki-search.md`
- `../design/evidence-report.md`
- `../design/dependencies.md`

**Depends on:** `docs/v1.0/plans/foundation.md`

**Project root:** `/home/hzh/workspace/CodeAsk/`。本计划全部文件路径相对此根目录。

---

## File Structure

本计划新增以下文件（全部相对项目根 `/home/hzh/workspace/CodeAsk/`）：

```text
CodeAsk/
├── alembic/
│   └── versions/
│       ├── 20260430_0002_features_documents.py        # features + documents + document_chunks
│       ├── 20260430_0003_document_references.py       # document_references（图片/相对链接）
│       ├── 20260430_0004_reports.py                   # reports
│       └── 20260430_0005_fts_tables.py                # docs_fts / docs_ngram_fts / reports_fts
├── src/
│   └── codeask/
│       ├── db/
│       │   └── models/
│       │       ├── feature.py                # Feature
│       │       ├── document.py               # Document, DocumentChunk, DocumentReference
│       │       └── report.py                 # Report
│       ├── wiki/
│       │   ├── __init__.py                   # 公共 re-export
│       │   ├── tokenizer.py                  # n-gram + 简易 jieba-friendly 分词 helper
│       │   ├── chunker.py                    # markdown / pdf / docx → DocumentChunk
│       │   ├── signals.py                    # 研发精确信号抽取
│       │   ├── indexer.py                    # 写 FTS5（docs_fts / docs_ngram_fts / reports_fts）
│       │   ├── search.py                     # WikiSearchService 多路召回 + 融合排序
│       │   ├── reports.py                    # ReportService（draft / verify / unverify）
│       │   └── audit.py                      # audit_log writer stub（06 计划替换为真实实现）
│       └── api/
│           ├── wiki.py                       # /api/features /api/documents /api/reports
│           └── schemas/
│               ├── __init__.py
│               └── wiki.py                   # Pydantic v2 schemas
└── tests/
    ├── unit/
    │   ├── test_wiki_tokenizer.py
    │   ├── test_wiki_chunker.py
    │   ├── test_wiki_signals.py
    │   └── test_wiki_audit.py
    └── integration/
        ├── test_wiki_migrations.py
        ├── test_wiki_features_api.py
        ├── test_wiki_documents_api.py
        ├── test_wiki_search.py
        ├── test_wiki_reports_lifecycle.py
        └── test_wiki_end_to_end.py
```

**职责边界**：
- `tokenizer.py` 是无状态 helper：原文 → 分词文本（空格分隔），原文 → n-gram 文本（trigram，空格分隔）
- `chunker.py` 把上传文件解析成 `DocumentChunk` 数据类列表，不写 DB
- `signals.py` 抽研发信号（错误码、接口路径、配置 key、符号），返回 `signals_json`
- `indexer.py` 把 `DocumentChunk` 写入 `docs_fts` / `docs_ngram_fts`，把 verified 报告写入 `reports_fts`；只接 session + chunk 对象
- `search.py` 编排多路 SQL 查询 + 融合排序，不知道 chunker / report lifecycle 细节
- `reports.py` 管报告状态机：`create_draft` / `update_draft` / `verify` / `unverify`；调 `indexer` 上下架，调 `audit.write` 记录验证动作
- `audit.py` 一期 stub：写 structlog（`event="audit_log"`），06 metrics-eval 替换为写 `audit_log` 表
- `api/wiki.py` 只编排 HTTP 协议，路由处理函数透过依赖注入拿 session
- `api/schemas/wiki.py` 只放 Pydantic 输入输出模型，不做 ORM ↔ schema 转换之外的逻辑

---

## Task 1: ORM 模型 features + documents + document_chunks + document_references

**Files:**
- Create: `src/codeask/db/models/feature.py`
- Create: `src/codeask/db/models/document.py`
- Modify: `src/codeask/db/models/__init__.py`
- Create: `tests/integration/test_wiki_models.py`

按 `wiki-search.md` §10 / `api-data-model.md` §3 落 `features` / `documents` / `document_chunks` / `document_references` 四张表。`reports` 在 Task 3。本步先确保模型可以 round-trip。

`features` 字段：`id` / `name` / `slug` / `description` / `owner_subject_id` / `summary_text` / `navigation_index_json` / `created_at` / `updated_at`。slug 唯一。

`documents` 字段：`id` / `feature_id` / `kind`（`markdown`/`pdf`/`docx`/`text`）/ `title` / `path` / `tags_json` / `raw_file_path` / `summary` / `is_deleted` / `uploaded_by_subject_id` / `created_at` / `updated_at`。

`document_chunks` 字段：`id` / `document_id` / `chunk_index` / `heading_path` / `raw_text` / `normalized_text` / `tokenized_text` / `ngram_text` / `signals_json` / `start_offset` / `end_offset` / `created_at` / `updated_at`。

`document_references` 字段：`id` / `document_id` / `target_path` / `kind`（`image`/`link`/`embed`）/ `created_at`。

- [ ] **Step 1: 写测试 `tests/integration/test_wiki_models.py`**

```python
"""Round-trip ORM tests for Feature / Document / DocumentChunk / DocumentReference."""

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from codeask.db import Base, create_engine, session_factory
from codeask.db.models import (
    Document,
    DocumentChunk,
    DocumentReference,
    Feature,
)


@pytest_asyncio.fixture()
async def engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    db_path = tmp_path / "test.db"
    eng = create_engine(f"sqlite+aiosqlite:///{db_path}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_feature_round_trip(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        f = Feature(
            name="Order Service",
            slug="order-service",
            description="订单核心域",
            owner_subject_id="alice@dev-7f2c",
        )
        s.add(f)
        await s.commit()
        feature_id = f.id

    async with factory() as s:
        row = (await s.execute(select(Feature).where(Feature.id == feature_id))).scalar_one()
        assert row.slug == "order-service"
        assert row.owner_subject_id == "alice@dev-7f2c"
        assert row.summary_text is None
        assert row.navigation_index_json is None
        assert row.created_at is not None


@pytest.mark.asyncio
async def test_document_with_chunks_and_refs(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        f = Feature(name="F1", slug="f1", owner_subject_id="bob@dev-1")
        s.add(f)
        await s.flush()
        d = Document(
            feature_id=f.id,
            kind="markdown",
            title="Submit Order Spec",
            path="order/submit.md",
            tags_json=["order", "spec"],
            raw_file_path="/tmp/submit.md",
            summary="how to submit an order",
            uploaded_by_subject_id="bob@dev-1",
        )
        s.add(d)
        await s.flush()
        s.add_all(
            [
                DocumentChunk(
                    document_id=d.id,
                    chunk_index=0,
                    heading_path="Submit Order Spec > Overview",
                    raw_text="# Submit Order\n\nOverview...",
                    normalized_text="submit order overview",
                    tokenized_text="submit order overview",
                    ngram_text="sub ubm bmi mit ord rde der",
                    signals_json={"routes": ["/api/order/submit"]},
                    start_offset=0,
                    end_offset=64,
                ),
                DocumentReference(document_id=d.id, target_path="img/diagram.png", kind="image"),
            ]
        )
        await s.commit()
        doc_id = d.id

    async with factory() as s:
        chunks = (
            await s.execute(select(DocumentChunk).where(DocumentChunk.document_id == doc_id))
        ).scalars().all()
        refs = (
            await s.execute(select(DocumentReference).where(DocumentReference.document_id == doc_id))
        ).scalars().all()
        assert len(chunks) == 1
        assert chunks[0].signals_json == {"routes": ["/api/order/submit"]}
        assert refs[0].kind == "image"


@pytest.mark.asyncio
async def test_feature_slug_unique(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        s.add(Feature(name="A", slug="dup", owner_subject_id="x@y"))
        await s.commit()
    async with factory() as s:
        s.add(Feature(name="B", slug="dup", owner_subject_id="x@y"))
        with pytest.raises(Exception):
            await s.commit()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/integration/test_wiki_models.py -v`
Expected: ImportError on `codeask.db.models.Feature`

- [ ] **Step 3: 创建 `src/codeask/db/models/feature.py`**

```python
"""Feature: 用户自定义粒度的知识集合（详见 design/wiki-search.md §2）。"""

from typing import Any

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class Feature(Base, TimestampMixin):
    __tablename__ = "features"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    navigation_index_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
```

- [ ] **Step 4: 创建 `src/codeask/db/models/document.py`**

```python
"""Document / DocumentChunk / DocumentReference."""

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    feature_id: Mapped[int] = mapped_column(
        ForeignKey("features.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    tags_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    raw_file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    uploaded_by_subject_id: Mapped[str] = mapped_column(String(128), nullable=False)


class DocumentChunk(Base, TimestampMixin):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_document_chunks_doc_index", "document_id", "chunk_index", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    heading_path: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    tokenized_text: Mapped[str] = mapped_column(Text, nullable=False)
    ngram_text: Mapped[str] = mapped_column(Text, nullable=False)
    signals_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class DocumentReference(Base, TimestampMixin):
    __tablename__ = "document_references"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
```

- [ ] **Step 5: 修改 `src/codeask/db/models/__init__.py`**

```python
"""ORM model definitions."""

from codeask.db.models.document import Document, DocumentChunk, DocumentReference
from codeask.db.models.feature import Feature
from codeask.db.models.system_settings import SystemSetting

__all__ = [
    "Document",
    "DocumentChunk",
    "DocumentReference",
    "Feature",
    "SystemSetting",
]
```

- [ ] **Step 6: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_wiki_models.py -v`
Expected: 三个测试 PASS

- [ ] **Step 7: 提交**

```bash
git add src/codeask/db/models/feature.py src/codeask/db/models/document.py src/codeask/db/models/__init__.py tests/integration/test_wiki_models.py
git commit -m "feat(wiki): ORM models for features / documents / chunks / references"
```

---

## Task 2: Alembic migration 0002 + 0003（features / documents / document_chunks / document_references）

**Files:**
- Create: `alembic/versions/20260430_0002_features_documents.py`
- Create: `alembic/versions/20260430_0003_document_references.py`
- Create: `tests/integration/test_wiki_migrations.py`

按 foundation.md Task 14 hand-off：新表对应新 migration，`down_revision` 接 `0001`。本步分两份：0002 建 features + documents + document_chunks，0003 建 document_references（演示后续可独立增量），方便后续 plan 学样。

- [ ] **Step 1: 创建 `alembic/versions/20260430_0002_features_documents.py`**

```python
"""features + documents + document_chunks

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-30 00:00:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "features",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_subject_id", sa.String(length=128), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("navigation_index_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_features_slug"),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("feature_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("tags_json", sa.JSON(), nullable=True),
        sa.Column("raw_file_path", sa.String(length=1024), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("uploaded_by_subject_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_documents_feature_id", "documents", ["feature_id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("heading_path", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("tokenized_text", sa.Text(), nullable=False),
        sa.Column("ngram_text", sa.Text(), nullable=False),
        sa.Column("signals_json", sa.JSON(), nullable=True),
        sa.Column("start_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("end_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index(
        "ix_document_chunks_doc_index",
        "document_chunks",
        ["document_id", "chunk_index"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_doc_index", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("ix_documents_feature_id", table_name="documents")
    op.drop_table("documents")
    op.drop_table("features")
```

- [ ] **Step 2: 创建 `alembic/versions/20260430_0003_document_references.py`**

```python
"""document_references

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-30 00:00:01
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_references",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("target_path", sa.String(length=2048), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_document_references_document_id", "document_references", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_document_references_document_id", table_name="document_references")
    op.drop_table("document_references")
```

- [ ] **Step 3: 写测试 `tests/integration/test_wiki_migrations.py`**

```python
"""Migrations 0002 + 0003 create wiki tables and remain idempotent on rerun."""

from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from codeask.migrations import run_migrations


@pytest.mark.asyncio
async def test_wiki_tables_created(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    sync_url = f"sqlite:///{db_path}"
    async_url = f"sqlite+aiosqlite:///{db_path}"

    run_migrations(sync_url)

    eng = create_async_engine(async_url)
    async with eng.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    await eng.dispose()

    for name in ("features", "documents", "document_chunks", "document_references"):
        assert name in tables, f"missing table {name}"


@pytest.mark.asyncio
async def test_wiki_migrations_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    sync_url = f"sqlite:///{db_path}"
    run_migrations(sync_url)
    run_migrations(sync_url)  # should not raise
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_wiki_migrations.py -v`
Expected: 两个测试 PASS

- [ ] **Step 5: 验证命令行 alembic 也能跑到 head**

```bash
mkdir -p /tmp/codeask-wiki-mig-check
CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
CODEASK_DATA_DIR=/tmp/codeask-wiki-mig-check \
uv run alembic upgrade head
```
Expected: `Running upgrade 0001 -> 0002 ... -> 0003`

- [ ] **Step 6: 提交**

```bash
git add alembic/versions/20260430_0002_features_documents.py alembic/versions/20260430_0003_document_references.py tests/integration/test_wiki_migrations.py
git commit -m "feat(wiki): alembic 0002+0003 features / documents / chunks / references"
```

---

## Task 3: ORM 模型 + Alembic 0004（reports）

**Files:**
- Create: `src/codeask/db/models/report.py`
- Modify: `src/codeask/db/models/__init__.py`
- Create: `alembic/versions/20260430_0004_reports.py`
- Modify: `tests/integration/test_wiki_models.py`（追加 report 测试）

按 `evidence-report.md` §6 / §7 / §8 落 `reports`。字段：`id` / `feature_id`（nullable，可不绑特性）/ `title` / `body_markdown` / `metadata_json`（含 `feature_ids` / `repo_commits` / `error_signatures` / `trace_signals`）/ `status`（`draft` / `verified` / `stale` / `superseded` / `rejected`）/ `verified` / `verified_by` / `verified_at` / `created_by_subject_id` / `created_at` / `updated_at`。

- [ ] **Step 1: 创建 `src/codeask/db/models/report.py`**

```python
"""Report ORM (详见 design/evidence-report.md §6 + §7)."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class Report(Base, TimestampMixin):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    feature_id: Mapped[int | None] = mapped_column(
        ForeignKey("features.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
```

- [ ] **Step 2: 更新 `src/codeask/db/models/__init__.py`**

```python
"""ORM model definitions."""

from codeask.db.models.document import Document, DocumentChunk, DocumentReference
from codeask.db.models.feature import Feature
from codeask.db.models.report import Report
from codeask.db.models.system_settings import SystemSetting

__all__ = [
    "Document",
    "DocumentChunk",
    "DocumentReference",
    "Feature",
    "Report",
    "SystemSetting",
]
```

- [ ] **Step 3: 创建 `alembic/versions/20260430_0004_reports.py`**

```python
"""reports

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-30 00:00:02
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("feature_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="draft"),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verified_by", sa.String(length=128), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_subject_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_reports_feature_id", "reports", ["feature_id"])
    op.create_index("ix_reports_status_verified", "reports", ["status", "verified"])


def downgrade() -> None:
    op.drop_index("ix_reports_status_verified", table_name="reports")
    op.drop_index("ix_reports_feature_id", table_name="reports")
    op.drop_table("reports")
```

- [ ] **Step 4: 在 `tests/integration/test_wiki_models.py` 末尾追加 report 测试**

```python


@pytest.mark.asyncio
async def test_report_round_trip(engine) -> None:  # type: ignore[no-untyped-def]
    from codeask.db.models import Report

    factory = session_factory(engine)
    async with factory() as s:
        f = Feature(name="X", slug="x", owner_subject_id="x@y")
        s.add(f)
        await s.flush()
        r = Report(
            feature_id=f.id,
            title="ERR_ORDER_CONTEXT_EMPTY 故障定位",
            body_markdown="# 摘要\n\n用户上下文丢失...",
            metadata_json={
                "feature_ids": [f.id],
                "repo_commits": [{"repo_id": "repo_order", "commit_sha": "abc123"}],
                "error_signatures": ["ERR_ORDER_CONTEXT_EMPTY"],
                "trace_signals": [],
            },
            status="draft",
            verified=False,
            created_by_subject_id="alice@dev-7f2c",
        )
        s.add(r)
        await s.commit()
        report_id = r.id

    async with factory() as s:
        from sqlalchemy import select as _select

        row = (await s.execute(_select(Report).where(Report.id == report_id))).scalar_one()
        assert row.status == "draft"
        assert row.verified is False
        assert row.metadata_json["error_signatures"] == ["ERR_ORDER_CONTEXT_EMPTY"]
```

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_wiki_models.py tests/integration/test_wiki_migrations.py -v`
Expected: 全部 PASS

更新 `test_wiki_migrations.py::test_wiki_tables_created` 的断言列表，把 `"reports"` 加入 `for name in (...)`。

- [ ] **Step 6: 提交**

```bash
git add src/codeask/db/models/report.py src/codeask/db/models/__init__.py alembic/versions/20260430_0004_reports.py tests/integration/test_wiki_models.py tests/integration/test_wiki_migrations.py
git commit -m "feat(wiki): Report ORM + alembic 0004"
```

---

## Task 4: Alembic 0005（FTS5 虚拟表 docs_fts / docs_ngram_fts / reports_fts）

**Files:**
- Create: `alembic/versions/20260430_0005_fts_tables.py`
- Modify: `tests/integration/test_wiki_migrations.py`（追加 FTS5 表存在断言）

`api-data-model.md` §4 / `wiki-search.md` §10 锁三张 FTS5 表。FTS5 虚拟表无 SQLAlchemy 抽象，必须用 `op.execute(...)` 直接建。

- `docs_fts`：列 `chunk_id UNINDEXED`、`title`、`heading_path`、`tokenized_text`、`tags`、`path`，tokenizer = `porter unicode61 remove_diacritics 2`。
- `docs_ngram_fts`：列 `chunk_id UNINDEXED`、`ngram_text`，tokenizer = `unicode61 remove_diacritics 2`（n-gram 文本由应用预生成、空格分隔，所以用 unicode61 即可按空格切）。
- `reports_fts`：列 `report_id UNINDEXED`、`title`、`tokenized_text`、`error_signature`、`tags`，tokenizer = `porter unicode61 remove_diacritics 2`。

- [ ] **Step 1: 创建 `alembic/versions/20260430_0005_fts_tables.py`**

```python
"""fts5 virtual tables: docs_fts / docs_ngram_fts / reports_fts

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-30 00:00:03
"""
from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIRTUAL TABLE docs_fts USING fts5(
            chunk_id UNINDEXED,
            title,
            heading_path,
            tokenized_text,
            tags,
            path,
            tokenize = "porter unicode61 remove_diacritics 2"
        )
        """
    )
    op.execute(
        """
        CREATE VIRTUAL TABLE docs_ngram_fts USING fts5(
            chunk_id UNINDEXED,
            ngram_text,
            tokenize = "unicode61 remove_diacritics 2"
        )
        """
    )
    op.execute(
        """
        CREATE VIRTUAL TABLE reports_fts USING fts5(
            report_id UNINDEXED,
            title,
            tokenized_text,
            error_signature,
            tags,
            tokenize = "porter unicode61 remove_diacritics 2"
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reports_fts")
    op.execute("DROP TABLE IF EXISTS docs_ngram_fts")
    op.execute("DROP TABLE IF EXISTS docs_fts")
```

- [ ] **Step 2: 在 `tests/integration/test_wiki_migrations.py` 追加 FTS5 断言**

```python


@pytest.mark.asyncio
async def test_fts_tables_created(tmp_path: Path) -> None:
    from sqlalchemy import text

    db_path = tmp_path / "fts.db"
    sync_url = f"sqlite:///{db_path}"
    async_url = f"sqlite+aiosqlite:///{db_path}"

    run_migrations(sync_url)

    eng = create_async_engine(async_url)
    async with eng.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name IN ('docs_fts','docs_ngram_fts','reports_fts')"
                )
            )
        ).all()
    await eng.dispose()
    names = {r[0] for r in rows}
    assert names == {"docs_fts", "docs_ngram_fts", "reports_fts"}
```

- [ ] **Step 3: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_wiki_migrations.py -v`
Expected: 三个测试 PASS

- [ ] **Step 4: 验证 FTS5 在当前 SQLite 编译时启用**

```bash
mkdir -p /tmp/codeask-fts-check
CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
CODEASK_DATA_DIR=/tmp/codeask-fts-check \
uv run alembic upgrade head
sqlite3 /tmp/codeask-fts-check/data.db ".tables"
```
Expected: 输出包含 `docs_fts docs_ngram_fts reports_fts` 三张表（以及配套的 `_data` `_idx` `_content` 等 FTS5 内部表）。

- [ ] **Step 5: 提交**

```bash
git add alembic/versions/20260430_0005_fts_tables.py tests/integration/test_wiki_migrations.py
git commit -m "feat(wiki): alembic 0005 fts5 virtual tables (docs / ngram / reports)"
```

---

## Task 5: 分词与 n-gram helper

**Files:**
- Create: `src/codeask/wiki/__init__.py`
- Create: `src/codeask/wiki/tokenizer.py`
- Create: `tests/unit/test_wiki_tokenizer.py`

按 `wiki-search.md` §7 提供两个纯函数：
- `tokenize(text: str) -> str`：把原文转成空格分隔的 token 串。中文按字切，英文按单词切；写入 `tokenized_text` 后给 FTS5 的 porter tokenizer 用。
- `to_ngrams(text: str, n: int = 3) -> str`：生成 trigram 文本（移除空白符后滑窗），空格分隔；写入 `ngram_text` 后给 `docs_ngram_fts` 用。

不引 jieba（dependencies.md §2.5 没列；保留扩展点：调用方可在写库前替换 `tokenize`）。

- [ ] **Step 1: 写测试 `tests/unit/test_wiki_tokenizer.py`**

```python
"""Tests for wiki tokenizer + n-gram helpers."""

from codeask.wiki.tokenizer import to_ngrams, tokenize


def test_tokenize_english_words() -> None:
    out = tokenize("Submit Order Service v2 ")
    assert out == "submit order service v2"


def test_tokenize_chinese_per_char() -> None:
    out = tokenize("订单服务")
    assert out == "订 单 服 务"


def test_tokenize_mixed() -> None:
    out = tokenize("订单 SubmitOrder ERR_001")
    # English words preserved, Chinese split per char, identifier preserved
    assert "订" in out.split()
    assert "submitorder" in out.split()
    assert "err_001" in out.split()


def test_tokenize_strips_punctuation_but_keeps_underscore_and_dash() -> None:
    out = tokenize("call /api/order/submit, see ERR-123!")
    tokens = set(out.split())
    assert "/api/order/submit" not in tokens  # path is split by '/'
    assert "api" in tokens
    assert "order" in tokens
    assert "submit" in tokens
    assert "err-123" in tokens


def test_to_ngrams_trigram() -> None:
    out = to_ngrams("abcd", n=3)
    assert out.split() == ["abc", "bcd"]


def test_to_ngrams_strips_whitespace() -> None:
    out = to_ngrams("ab cd", n=3)
    # whitespace removed first; "abcd" → "abc","bcd"
    assert out.split() == ["abc", "bcd"]


def test_to_ngrams_short_input() -> None:
    out = to_ngrams("ab", n=3)
    assert out == "ab"


def test_to_ngrams_chinese() -> None:
    out = to_ngrams("订单服务", n=3)
    assert out.split() == ["订单服", "单服务"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_wiki_tokenizer.py -v`
Expected: ImportError on `codeask.wiki.tokenizer`

- [ ] **Step 3: 创建 `src/codeask/wiki/__init__.py`**

```python
"""Wiki domain: documents, chunks, search, reports."""
```

- [ ] **Step 4: 实现 `src/codeask/wiki/tokenizer.py`**

```python
"""Tokenization + n-gram helpers (详见 design/wiki-search.md §7)."""

import re

# Word characters: ASCII letters, digits, underscore, dash. Splits on everything else.
_WORD_RE = re.compile(r"[A-Za-z0-9_\-]+")
# CJK Unified Ideographs blocks (Basic + Extension A). Each char is one token.
_CJK_RE = re.compile(r"[㐀-䶿一-鿿]")


def tokenize(text: str) -> str:
    """Lower-cased, space-separated tokens.

    English / identifier runs become single tokens; CJK characters become
    one-token-per-char so FTS5 porter tokenizer can index them.
    """
    if not text:
        return ""
    tokens: list[str] = []
    for piece in re.split(r"\s+", text.strip()):
        if not piece:
            continue
        i = 0
        while i < len(piece):
            ch = piece[i]
            if _CJK_RE.match(ch):
                tokens.append(ch)
                i += 1
                continue
            m = _WORD_RE.match(piece, i)
            if m:
                tokens.append(m.group(0).lower())
                i = m.end()
            else:
                # Skip any other punctuation/symbol char.
                i += 1
    return " ".join(tokens)


def to_ngrams(text: str, n: int = 3) -> str:
    """Whitespace-stripped sliding-window n-grams, space-separated.

    Used to populate ``document_chunks.ngram_text`` for the trigram FTS5 fallback.
    """
    if not text:
        return ""
    compact = re.sub(r"\s+", "", text)
    if len(compact) <= n:
        return compact
    return " ".join(compact[i : i + n] for i in range(len(compact) - n + 1))
```

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_wiki_tokenizer.py -v`
Expected: 所有测试 PASS

- [ ] **Step 6: 提交**

```bash
git add src/codeask/wiki/__init__.py src/codeask/wiki/tokenizer.py tests/unit/test_wiki_tokenizer.py
git commit -m "feat(wiki): tokenizer + trigram n-gram helpers"
```

---

## Task 6: 研发精确信号抽取（signals）

**Files:**
- Create: `src/codeask/wiki/signals.py`
- Create: `tests/unit/test_wiki_signals.py`

按 `wiki-search.md` §5 抽研发信号。一期支持：错误码（大写蛇形 / `SQLSTATE xxxx`）、异常名（驼峰带 `Exception` / `Error` 后缀）、接口路径（`/api/...`）、配置 key（多段点分小写）、代码符号（CamelCase 类名 / lowerCamelCase 函数名）、文件路径（含 `.py/.ts/.java/.go` 等扩展名）。

返回 `dict[str, list[str]]`，可直接写入 `DocumentChunk.signals_json`。

- [ ] **Step 1: 写测试 `tests/unit/test_wiki_signals.py`**

```python
"""Tests for engineering signal extraction."""

from codeask.wiki.signals import extract_signals


def test_error_codes() -> None:
    sig = extract_signals("see ERR_ORDER_CONTEXT_EMPTY and SQLSTATE 40001")
    assert "ERR_ORDER_CONTEXT_EMPTY" in sig["error_codes"]
    assert "SQLSTATE 40001" in sig["error_codes"]


def test_exception_names() -> None:
    sig = extract_signals("got NullPointerException, then TimeoutError")
    assert "NullPointerException" in sig["exception_names"]
    assert "TimeoutError" in sig["exception_names"]


def test_routes() -> None:
    sig = extract_signals("call /api/order/submit and /api/v1/users/list")
    assert "/api/order/submit" in sig["routes"]
    assert "/api/v1/users/list" in sig["routes"]


def test_config_keys() -> None:
    sig = extract_signals("flag order.payment.retry.enabled = true")
    assert "order.payment.retry.enabled" in sig["config_keys"]


def test_symbols() -> None:
    sig = extract_signals("OrderService.submitOrder() inside UserContextInterceptor")
    assert "OrderService" in sig["symbols"]
    assert "submitOrder" in sig["symbols"]
    assert "UserContextInterceptor" in sig["symbols"]


def test_file_paths() -> None:
    sig = extract_signals("see src/order/service.py and src/main.ts")
    assert "src/order/service.py" in sig["file_paths"]
    assert "src/main.ts" in sig["file_paths"]


def test_empty_buckets_when_no_match() -> None:
    sig = extract_signals("just plain prose 中文文本")
    for k in ("error_codes", "exception_names", "routes", "config_keys", "symbols", "file_paths"):
        assert sig[k] == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_wiki_signals.py -v`
Expected: ImportError

- [ ] **Step 3: 实现 `src/codeask/wiki/signals.py`**

```python
"""Extract engineering precision signals from chunk text (design/wiki-search.md §5)."""

import re

_ERROR_CODE_RE = re.compile(r"\b(?:ERR|ERROR|E)_[A-Z][A-Z0-9_]{2,}\b")
_SQLSTATE_RE = re.compile(r"\bSQLSTATE\s+[0-9A-Z]{5}\b")
_EXCEPTION_RE = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:Exception|Error)\b")
_ROUTE_RE = re.compile(r"/api(?:/[A-Za-z0-9_\-]+)+")
_CONFIG_KEY_RE = re.compile(r"\b[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_]*){2,}\b")
_CLASS_SYMBOL_RE = re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z0-9]+){1,}\b")
_FN_SYMBOL_RE = re.compile(r"\b[a-z]+(?:[A-Z][a-z0-9]+){1,}\b")
_FILE_PATH_RE = re.compile(
    r"\b(?:[A-Za-z0-9_\-]+/)+[A-Za-z0-9_\-]+\.(?:py|ts|tsx|js|jsx|java|go|rs|rb|kt|cs|cpp|c|h|hpp|sql|md|yaml|yml|toml|json)\b"
)


def _dedup(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def extract_signals(text: str) -> dict[str, list[str]]:
    """Return a dict of signal-bucket → ordered unique matches."""
    if not text:
        return {
            "error_codes": [],
            "exception_names": [],
            "routes": [],
            "config_keys": [],
            "symbols": [],
            "file_paths": [],
        }
    error_codes = _dedup(_ERROR_CODE_RE.findall(text) + _SQLSTATE_RE.findall(text))
    exceptions = _dedup(_EXCEPTION_RE.findall(text))
    routes = _dedup(_ROUTE_RE.findall(text))
    config_keys = _dedup(_CONFIG_KEY_RE.findall(text))
    symbols = _dedup(_CLASS_SYMBOL_RE.findall(text) + _FN_SYMBOL_RE.findall(text))
    file_paths = _dedup(_FILE_PATH_RE.findall(text))
    # An exception name like "TimeoutError" matches the class-symbol regex too;
    # remove duplicates that are already captured as exceptions.
    symbols = [s for s in symbols if s not in exceptions]
    return {
        "error_codes": error_codes,
        "exception_names": exceptions,
        "routes": routes,
        "config_keys": config_keys,
        "symbols": symbols,
        "file_paths": file_paths,
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_wiki_signals.py -v`
Expected: 7 个测试 PASS

- [ ] **Step 5: 提交**

```bash
git add src/codeask/wiki/signals.py tests/unit/test_wiki_signals.py
git commit -m "feat(wiki): extract_signals for error codes / routes / symbols / paths"
```

---

## Task 7: DocumentChunker（markdown / pdf / docx → DocumentChunk dataclasses）

**Files:**
- Create: `src/codeask/wiki/chunker.py`
- Create: `tests/unit/test_wiki_chunker.py`
- Modify: `pyproject.toml`（加 `markdown-it-py>=3.0`、`pypdfium2>=4.30`、`python-docx>=1.1`）

按 `wiki-search.md` §3 / §4：markdown 走 `markdown-it-py` token 流，按 heading 切；纯文本回退到段落切。一个 chunk 上限 3000 字符（防巨型小节）。每个 chunk 自动跑 `tokenize` / `to_ngrams` / `extract_signals`。

dataclass `ParsedChunk(chunk_index, heading_path, raw_text, normalized_text, tokenized_text, ngram_text, signals_json, start_offset, end_offset)`，由 chunker 输出，由后续 indexer 落库。

- [ ] **Step 1: 在 `pyproject.toml` 的 `dependencies` 列表里追加三行**

```toml
    "markdown-it-py>=3.0",
    "pypdfium2>=4.30",
    "python-docx>=1.1",
```

跑 `uv sync` 拉新依赖。

- [ ] **Step 2: 写测试 `tests/unit/test_wiki_chunker.py`**

```python
"""Tests for DocumentChunker (markdown / text)."""

from pathlib import Path

import pytest

from codeask.wiki.chunker import DocumentChunker, ParsedChunk

MARKDOWN_SAMPLE = """# Submit Order Spec

## Overview

订单提交主流程。call /api/order/submit when ready.

## Edge Cases

If user is null we throw NullPointerException.

```python
def submit_order(user):
    return user.id
```
"""


def test_markdown_chunks_by_h2() -> None:
    ch = DocumentChunker()
    chunks = ch.chunk_markdown(MARKDOWN_SAMPLE)
    assert len(chunks) >= 2
    headings = [c.heading_path for c in chunks]
    assert any("Overview" in h for h in headings)
    assert any("Edge Cases" in h for h in headings)


def test_markdown_chunk_carries_signals() -> None:
    ch = DocumentChunker()
    chunks = ch.chunk_markdown(MARKDOWN_SAMPLE)
    flat_routes: list[str] = []
    flat_exceptions: list[str] = []
    for c in chunks:
        flat_routes += (c.signals_json or {}).get("routes", [])
        flat_exceptions += (c.signals_json or {}).get("exception_names", [])
    assert "/api/order/submit" in flat_routes
    assert "NullPointerException" in flat_exceptions


def test_markdown_chunk_has_tokenized_and_ngram() -> None:
    ch = DocumentChunker()
    chunks = ch.chunk_markdown(MARKDOWN_SAMPLE)
    c0 = chunks[0]
    assert c0.tokenized_text != ""
    assert c0.ngram_text != ""
    assert c0.chunk_index == 0


def test_text_fallback_chunks_by_paragraph() -> None:
    ch = DocumentChunker()
    chunks = ch.chunk_text("para one\n\npara two\n\npara three")
    assert len(chunks) == 3
    assert chunks[1].raw_text == "para two"
    assert [c.chunk_index for c in chunks] == [0, 1, 2]


def test_chunker_dispatches_by_extension(tmp_path: Path) -> None:
    f = tmp_path / "doc.md"
    f.write_text(MARKDOWN_SAMPLE, encoding="utf-8")
    ch = DocumentChunker()
    chunks = ch.chunk_file(f, kind="markdown")
    assert all(isinstance(c, ParsedChunk) for c in chunks)
    assert len(chunks) >= 2


def test_unknown_kind_raises(tmp_path: Path) -> None:
    f = tmp_path / "x.bin"
    f.write_bytes(b"\x00\x01")
    ch = DocumentChunker()
    with pytest.raises(ValueError, match="unsupported"):
        ch.chunk_file(f, kind="binary")
```

- [ ] **Step 3: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_wiki_chunker.py -v`
Expected: ImportError on `codeask.wiki.chunker`

- [ ] **Step 4: 实现 `src/codeask/wiki/chunker.py`**

```python
"""Parse markdown / pdf / docx / text into ParsedChunk dataclasses (design/wiki-search.md §3-§5)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt

from codeask.wiki.signals import extract_signals
from codeask.wiki.tokenizer import to_ngrams, tokenize

MAX_CHUNK_CHARS = 3000


@dataclass(slots=True)
class ParsedChunk:
    chunk_index: int
    heading_path: str
    raw_text: str
    normalized_text: str
    tokenized_text: str
    ngram_text: str
    signals_json: dict[str, list[str]]
    start_offset: int
    end_offset: int


def _build(index: int, heading_path: str, raw: str, start: int, end: int) -> ParsedChunk:
    normalized = " ".join(raw.split())
    return ParsedChunk(
        chunk_index=index,
        heading_path=heading_path,
        raw_text=raw,
        normalized_text=normalized,
        tokenized_text=tokenize(normalized),
        ngram_text=to_ngrams(normalized),
        signals_json=extract_signals(raw),
        start_offset=start,
        end_offset=end,
    )


def _split_oversize(text: str) -> list[str]:
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    parts: list[str] = []
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    buf = ""
    for p in paragraphs:
        if len(buf) + len(p) + 2 > MAX_CHUNK_CHARS and buf:
            parts.append(buf.strip())
            buf = p
        else:
            buf = (buf + "\n\n" + p) if buf else p
    if buf.strip():
        parts.append(buf.strip())
    return parts


class DocumentChunker:
    """Stateless: each call returns a fresh list."""

    def __init__(self) -> None:
        self._md = MarkdownIt("commonmark")

    # ---- public dispatchers ----
    def chunk_file(self, path: Path, kind: str) -> list[ParsedChunk]:
        if kind == "markdown":
            return self.chunk_markdown(path.read_text(encoding="utf-8"))
        if kind == "text":
            return self.chunk_text(path.read_text(encoding="utf-8"))
        if kind == "pdf":
            return self.chunk_pdf(path)
        if kind == "docx":
            return self.chunk_docx(path)
        raise ValueError(f"unsupported document kind: {kind}")

    # ---- markdown ----
    def chunk_markdown(self, source: str) -> list[ParsedChunk]:
        tokens = self._md.parse(source)
        # Group lines by heading; "heading_stack" tracks hierarchical path.
        sections: list[tuple[str, str]] = []  # (heading_path, body)
        heading_stack: list[tuple[int, str]] = []
        current_heading_path = ""
        current_body_lines: list[str] = []

        i = 0
        while i < len(tokens):
            t = tokens[i]
            if t.type == "heading_open":
                # flush current section
                if current_body_lines:
                    sections.append((current_heading_path, "\n".join(current_body_lines).strip()))
                    current_body_lines = []
                level = int(t.tag[1])  # 'h2' → 2
                # next token is inline with the heading text
                inline = tokens[i + 1]
                heading_text = inline.content.strip()
                # pop deeper-or-equal headings off the stack
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, heading_text))
                current_heading_path = " > ".join(h for _, h in heading_stack)
                # skip heading_open, inline, heading_close
                i += 3
                continue
            if t.type in ("paragraph_open", "bullet_list_open", "ordered_list_open"):
                # find matching close and grab raw markdown via map
                if t.map is not None:
                    start_line, end_line = t.map
                    snippet = "\n".join(source.splitlines()[start_line:end_line])
                    if snippet.strip():
                        current_body_lines.append(snippet)
                # Skip past the matching close token
                depth = 1
                i += 1
                close_tag = t.type.replace("_open", "_close")
                while i < len(tokens) and depth > 0:
                    if tokens[i].type == t.type:
                        depth += 1
                    elif tokens[i].type == close_tag:
                        depth -= 1
                    i += 1
                continue
            if t.type == "fence" or t.type == "code_block":
                fence = t.content.rstrip("\n")
                lang = t.info.strip() if t.info else ""
                rendered = f"```{lang}\n{fence}\n```" if t.type == "fence" else fence
                current_body_lines.append(rendered)
            elif t.type == "hr":
                current_body_lines.append("---")
            i += 1

        if current_body_lines:
            sections.append((current_heading_path, "\n".join(current_body_lines).strip()))

        # Flatten + split oversize + assign indices and offsets.
        chunks: list[ParsedChunk] = []
        offset = 0
        idx = 0
        for heading_path, body in sections:
            if not body:
                continue
            for piece in _split_oversize(body):
                start = offset
                end = offset + len(piece)
                chunks.append(_build(idx, heading_path, piece, start, end))
                idx += 1
                offset = end + 2  # account for blank-line separator
        return chunks

    # ---- plain text ----
    def chunk_text(self, source: str) -> list[ParsedChunk]:
        chunks: list[ParsedChunk] = []
        offset = 0
        idx = 0
        for paragraph in source.split("\n\n"):
            body = paragraph.strip()
            if not body:
                offset += len(paragraph) + 2
                continue
            for piece in _split_oversize(body):
                start = offset
                end = offset + len(piece)
                chunks.append(_build(idx, "", piece, start, end))
                idx += 1
                offset = end + 2
        return chunks

    # ---- pdf ----
    def chunk_pdf(self, path: Path) -> list[ParsedChunk]:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        try:
            full_text_pieces: list[str] = []
            for page in pdf:
                tp = page.get_textpage()
                try:
                    full_text_pieces.append(tp.get_text_range())
                finally:
                    tp.close()
                page.close()
            full_text = "\n\n".join(full_text_pieces)
        finally:
            pdf.close()
        return self.chunk_text(full_text)

    # ---- docx ----
    def chunk_docx(self, path: Path) -> list[ParsedChunk]:
        import docx  # python-docx

        document = docx.Document(str(path))
        # Treat each non-empty paragraph as a unit; respect Heading style as section break.
        sections: list[tuple[str, list[str]]] = []
        current_heading = ""
        current_paragraphs: list[str] = []
        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue
            style_name = paragraph.style.name if paragraph.style is not None else ""
            if style_name.startswith("Heading"):
                if current_paragraphs:
                    sections.append((current_heading, current_paragraphs))
                    current_paragraphs = []
                current_heading = text
            else:
                current_paragraphs.append(text)
        if current_paragraphs:
            sections.append((current_heading, current_paragraphs))

        chunks: list[ParsedChunk] = []
        offset = 0
        idx = 0
        for heading, paragraphs in sections:
            body = "\n\n".join(paragraphs)
            for piece in _split_oversize(body):
                start = offset
                end = offset + len(piece)
                chunks.append(_build(idx, heading, piece, start, end))
                idx += 1
                offset = end + 2
        return chunks
```

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_wiki_chunker.py -v`
Expected: 6 个测试 PASS

- [ ] **Step 6: 更新 README Configuration 表（无新 env var，但要把 `markdown-it-py / pypdfium2 / python-docx` 列入"运行时依赖"提示）**

在 `README.md` "Quick start" 之后追加一节：

```markdown
## 文档解析依赖

后端解析上传文档时使用以下库（已通过 `uv sync` 安装，无需手工配置）：

| 文件类型 | 解析库 |
|---|---|
| Markdown / 文本 | `markdown-it-py` |
| PDF | `pypdfium2` |
| DOCX | `python-docx` |

未来扩展类型（Excel 等）参考 `docs/v1.0/design/dependencies.md` §2.5。
```

- [ ] **Step 7: 提交**

```bash
git add pyproject.toml uv.lock src/codeask/wiki/chunker.py tests/unit/test_wiki_chunker.py README.md
git commit -m "feat(wiki): DocumentChunker for markdown / pdf / docx / text"
```

---

## Task 8: WikiIndexer（写 docs_fts / docs_ngram_fts / reports_fts）

**Files:**
- Create: `src/codeask/wiki/indexer.py`
- Create: `tests/integration/test_wiki_indexer.py`

`WikiIndexer` 负责把 `DocumentChunk` ORM 行写进 `docs_fts` 和 `docs_ngram_fts`，把 `Report` 写进 `reports_fts`，并提供"删除（chunk / report）→ 同步从 FTS 表中下架"的方法。

- `index_chunk(session, chunk, document)`：插入 `docs_fts` + `docs_ngram_fts`
- `unindex_chunks_for_document(session, document_id)`：从两张 fts 表删除该 doc 的所有 chunk 索引
- `index_report(session, report)`：插入 `reports_fts`
- `unindex_report(session, report_id)`：从 `reports_fts` 删除

- [ ] **Step 1: 写测试 `tests/integration/test_wiki_indexer.py`**

```python
"""Integration tests for WikiIndexer (writes/deletes against fts5 tables)."""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from codeask.db import session_factory
from codeask.db.models import Document, DocumentChunk, Feature, Report
from codeask.migrations import run_migrations
from codeask.wiki.indexer import WikiIndexer


async def _setup(tmp_path: Path):
    db_path = tmp_path / "idx.db"
    sync_url = f"sqlite:///{db_path}"
    async_url = f"sqlite+aiosqlite:///{db_path}"
    run_migrations(sync_url)
    eng = create_async_engine(async_url)
    return eng


@pytest.mark.asyncio
async def test_index_and_unindex_chunk(tmp_path: Path) -> None:
    eng = await _setup(tmp_path)
    factory = session_factory(eng)
    indexer = WikiIndexer()

    async with factory() as s:
        f = Feature(name="F", slug="f", owner_subject_id="u@1")
        s.add(f)
        await s.flush()
        d = Document(
            feature_id=f.id,
            kind="markdown",
            title="Submit Order",
            path="order/submit.md",
            tags_json=["order"],
            raw_file_path="/tmp/x.md",
            uploaded_by_subject_id="u@1",
        )
        s.add(d)
        await s.flush()
        c = DocumentChunk(
            document_id=d.id,
            chunk_index=0,
            heading_path="Overview",
            raw_text="hello world",
            normalized_text="hello world",
            tokenized_text="hello world",
            ngram_text="hel ell llo low owo wor orl rld",
            signals_json={},
        )
        s.add(c)
        await s.flush()
        await indexer.index_chunk(s, c, d)
        await s.commit()
        chunk_id = c.id

    async with factory() as s:
        rows = (
            await s.execute(
                text("SELECT chunk_id FROM docs_fts WHERE docs_fts MATCH :q"),
                {"q": "hello"},
            )
        ).all()
        assert any(int(r[0]) == chunk_id for r in rows)

        rows_ng = (
            await s.execute(
                text("SELECT chunk_id FROM docs_ngram_fts WHERE docs_ngram_fts MATCH :q"),
                {"q": "wor"},
            )
        ).all()
        assert any(int(r[0]) == chunk_id for r in rows_ng)

    async with factory() as s:
        await indexer.unindex_chunks_for_document(s, doc_id=chunk_id_to_doc_id := d.id)
        await s.commit()

    async with factory() as s:
        rows = (
            await s.execute(text("SELECT chunk_id FROM docs_fts WHERE docs_fts MATCH :q"), {"q": "hello"})
        ).all()
        assert all(int(r[0]) != chunk_id for r in rows)

    await eng.dispose()


@pytest.mark.asyncio
async def test_index_and_unindex_report(tmp_path: Path) -> None:
    eng = await _setup(tmp_path)
    factory = session_factory(eng)
    indexer = WikiIndexer()

    async with factory() as s:
        r = Report(
            title="ERR_ORDER_CONTEXT_EMPTY 故障",
            body_markdown="user 上下文为空导致提交失败",
            metadata_json={"error_signatures": ["ERR_ORDER_CONTEXT_EMPTY"], "tags": ["order"]},
            status="verified",
            verified=True,
            verified_by="alice@dev-1",
            created_by_subject_id="alice@dev-1",
        )
        s.add(r)
        await s.flush()
        await indexer.index_report(s, r)
        await s.commit()
        rid = r.id

    async with factory() as s:
        rows = (
            await s.execute(
                text("SELECT report_id FROM reports_fts WHERE reports_fts MATCH :q"),
                {"q": "ERR_ORDER_CONTEXT_EMPTY"},
            )
        ).all()
        assert any(int(x[0]) == rid for x in rows)

    async with factory() as s:
        await indexer.unindex_report(s, report_id=rid)
        await s.commit()

    async with factory() as s:
        rows = (
            await s.execute(
                text("SELECT report_id FROM reports_fts WHERE reports_fts MATCH :q"),
                {"q": "ERR_ORDER_CONTEXT_EMPTY"},
            )
        ).all()
        assert all(int(x[0]) != rid for x in rows)

    await eng.dispose()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/integration/test_wiki_indexer.py -v`
Expected: ImportError on `codeask.wiki.indexer`

- [ ] **Step 3: 实现 `src/codeask/wiki/indexer.py`**

```python
"""Write and remove rows from FTS5 virtual tables."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import Document, DocumentChunk, Report


def _join_tags(tags: list[str] | None) -> str:
    return " ".join(tags) if tags else ""


class WikiIndexer:
    async def index_chunk(
        self, session: AsyncSession, chunk: DocumentChunk, document: Document
    ) -> None:
        await session.execute(
            text(
                "INSERT INTO docs_fts (chunk_id, title, heading_path, tokenized_text, tags, path) "
                "VALUES (:chunk_id, :title, :heading_path, :tokenized, :tags, :path)"
            ),
            {
                "chunk_id": chunk.id,
                "title": document.title,
                "heading_path": chunk.heading_path,
                "tokenized": chunk.tokenized_text,
                "tags": _join_tags(document.tags_json if isinstance(document.tags_json, list) else None),
                "path": document.path,
            },
        )
        await session.execute(
            text(
                "INSERT INTO docs_ngram_fts (chunk_id, ngram_text) VALUES (:chunk_id, :ngram)"
            ),
            {"chunk_id": chunk.id, "ngram": chunk.ngram_text},
        )

    async def unindex_chunks_for_document(self, session: AsyncSession, doc_id: int) -> None:
        # Find chunk ids first; FTS5 doesn't support DELETE … FROM joins.
        chunk_ids = (
            await session.execute(
                text("SELECT id FROM document_chunks WHERE document_id = :doc_id"),
                {"doc_id": doc_id},
            )
        ).all()
        ids = [int(r[0]) for r in chunk_ids]
        for cid in ids:
            await session.execute(
                text("DELETE FROM docs_fts WHERE chunk_id = :cid"), {"cid": cid}
            )
            await session.execute(
                text("DELETE FROM docs_ngram_fts WHERE chunk_id = :cid"), {"cid": cid}
            )

    async def index_report(self, session: AsyncSession, report: Report) -> None:
        meta = report.metadata_json or {}
        error_sig = " ".join(meta.get("error_signatures", []) or [])
        tags = _join_tags(meta.get("tags") or [])
        await session.execute(
            text(
                "INSERT INTO reports_fts (report_id, title, tokenized_text, error_signature, tags) "
                "VALUES (:rid, :title, :tokenized, :err, :tags)"
            ),
            {
                "rid": report.id,
                "title": report.title,
                "tokenized": report.body_markdown,
                "err": error_sig,
                "tags": tags,
            },
        )

    async def unindex_report(self, session: AsyncSession, report_id: int) -> None:
        await session.execute(
            text("DELETE FROM reports_fts WHERE report_id = :rid"), {"rid": report_id}
        )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_wiki_indexer.py -v`
Expected: 两个测试 PASS

- [ ] **Step 5: 提交**

```bash
git add src/codeask/wiki/indexer.py tests/integration/test_wiki_indexer.py
git commit -m "feat(wiki): WikiIndexer for docs_fts / docs_ngram_fts / reports_fts"
```

---

## Task 9: WikiSearchService（多路召回 + 融合排序）

**Files:**
- Create: `src/codeask/wiki/search.py`
- Create: `tests/integration/test_wiki_search.py`

按 `wiki-search.md` §6 / §8 实现多路召回。一期通道：

| 通道 | 来源 | 权重 |
|---|---|---|
| `docs_fts` BM25 | 分词正文 | 1.0 |
| `docs_ngram_fts` BM25 | trigram 兜底 | 0.4 |
| `reports_fts` BM25 | 已验证报告 | 1.5（命中报告天然高优先级） |

接口：

```python
@dataclass
class DocumentSearchHit:
    chunk_id: int
    document_id: int
    document_title: str
    document_path: str
    feature_id: int
    heading_path: str
    snippet: str
    score: float
    source_channel: str

@dataclass
class ReportSearchHit:
    report_id: int
    title: str
    feature_id: int | None
    verified_by: str | None
    verified_at: datetime | None
    commit_sha: str | None
    snippet: str
    score: float

class WikiSearchService:
    async def search_documents(self, session, query, *, feature_id=None, limit=20) -> list[DocumentSearchHit]: ...
    async def search_reports(self, session, query, *, feature_id=None, limit=20) -> list[ReportSearchHit]: ...
```

FTS5 的 BM25 是越小越相关——本实现用 `-bm25(table)` 作正向 score（越大越相关）后乘权重。

- [ ] **Step 1: 写测试 `tests/integration/test_wiki_search.py`**

```python
"""Multi-channel recall + fusion ranking tests."""

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from codeask.db import session_factory
from codeask.db.models import Document, DocumentChunk, Feature, Report
from codeask.migrations import run_migrations
from codeask.wiki.indexer import WikiIndexer
from codeask.wiki.search import WikiSearchService


async def _seed(tmp_path: Path):
    db_path = tmp_path / "search.db"
    sync_url = f"sqlite:///{db_path}"
    async_url = f"sqlite+aiosqlite:///{db_path}"
    run_migrations(sync_url)
    eng = create_async_engine(async_url)
    factory = session_factory(eng)
    indexer = WikiIndexer()

    async with factory() as s:
        f = Feature(name="Order", slug="order", owner_subject_id="alice@dev-1")
        s.add(f)
        await s.flush()
        d1 = Document(
            feature_id=f.id, kind="markdown", title="Submit Order Spec",
            path="order/submit.md", tags_json=["order", "spec"],
            raw_file_path="/tmp/1.md", uploaded_by_subject_id="alice@dev-1",
        )
        d2 = Document(
            feature_id=f.id, kind="markdown", title="Payment Flow",
            path="order/payment.md", tags_json=["payment"],
            raw_file_path="/tmp/2.md", uploaded_by_subject_id="alice@dev-1",
        )
        s.add_all([d1, d2])
        await s.flush()
        c1 = DocumentChunk(
            document_id=d1.id, chunk_index=0, heading_path="Submit Order Spec > Overview",
            raw_text="user submits an order via /api/order/submit",
            normalized_text="user submits an order via /api/order/submit",
            tokenized_text="user submits an order via api order submit",
            ngram_text="use ser sub ubm bmi mit ord rde der api ord rde",
            signals_json={"routes": ["/api/order/submit"]},
        )
        c2 = DocumentChunk(
            document_id=d2.id, chunk_index=0, heading_path="Payment Flow > Retry",
            raw_text="payment retry uses order.payment.retry.enabled",
            normalized_text="payment retry uses order payment retry enabled",
            tokenized_text="payment retry uses order payment retry enabled",
            ngram_text="pay aym yme men ent",
            signals_json={"config_keys": ["order.payment.retry.enabled"]},
        )
        s.add_all([c1, c2])
        await s.flush()
        await indexer.index_chunk(s, c1, d1)
        await indexer.index_chunk(s, c2, d2)

        r = Report(
            feature_id=f.id,
            title="ERR_ORDER_CONTEXT_EMPTY 排查",
            body_markdown="日志含 ERR_ORDER_CONTEXT_EMPTY 时根因是 user 上下文丢失",
            metadata_json={
                "error_signatures": ["ERR_ORDER_CONTEXT_EMPTY"],
                "tags": ["order"],
                "repo_commits": [{"repo_id": "repo_order", "commit_sha": "abc1234"}],
            },
            status="verified", verified=True,
            verified_by="alice@dev-1",
            created_by_subject_id="alice@dev-1",
        )
        s.add(r)
        await s.flush()
        await indexer.index_report(s, r)
        await s.commit()
        return eng, factory, f.id, d1.id, d2.id, r.id


@pytest.mark.asyncio
async def test_search_documents_returns_hits_for_known_word(tmp_path: Path) -> None:
    eng, factory, _, d1, d2, _ = await _seed(tmp_path)
    svc = WikiSearchService()
    async with factory() as s:
        hits = await svc.search_documents(s, "submit order")
    assert any(h.document_id == d1 for h in hits)
    await eng.dispose()


@pytest.mark.asyncio
async def test_search_documents_filters_by_feature(tmp_path: Path) -> None:
    eng, factory, fid, d1, _, _ = await _seed(tmp_path)
    svc = WikiSearchService()
    async with factory() as s:
        hits = await svc.search_documents(s, "submit", feature_id=fid)
    assert hits
    assert all(h.feature_id == fid for h in hits)
    await eng.dispose()


@pytest.mark.asyncio
async def test_search_reports_returns_verified_metadata(tmp_path: Path) -> None:
    eng, factory, _, _, _, rid = await _seed(tmp_path)
    svc = WikiSearchService()
    async with factory() as s:
        hits = await svc.search_reports(s, "ERR_ORDER_CONTEXT_EMPTY")
    assert hits
    h = next(x for x in hits if x.report_id == rid)
    assert h.verified_by == "alice@dev-1"
    assert h.verified_at is not None
    assert h.commit_sha == "abc1234"
    await eng.dispose()


@pytest.mark.asyncio
async def test_ngram_fallback_when_token_split(tmp_path: Path) -> None:
    """Search for a substring that won't match porter-tokenized words but matches ngram."""
    eng, factory, _, d2, _, _ = await _seed(tmp_path)
    svc = WikiSearchService()
    async with factory() as s:
        # "ayme" is a substring of "payment" — porter tokenizer won't match,
        # but ngram_text contains "aym" / "yme".
        hits = await svc.search_documents(s, "ayme")
    # At least one hit should come from ngram channel.
    assert any(h.source_channel == "ngram" for h in hits)
    await eng.dispose()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/integration/test_wiki_search.py -v`
Expected: ImportError on `codeask.wiki.search`

- [ ] **Step 3: 实现 `src/codeask/wiki/search.py`**

```python
"""Multi-channel recall + fusion ranking (design/wiki-search.md §6 + §8)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.wiki.tokenizer import to_ngrams, tokenize

# Channel weights (higher = more relevant). Reports are inherently high-priority.
_W_DOCS = 1.0
_W_NGRAM = 0.4
_W_REPORTS = 1.5


@dataclass(slots=True)
class DocumentSearchHit:
    chunk_id: int
    document_id: int
    document_title: str
    document_path: str
    feature_id: int
    heading_path: str
    snippet: str
    score: float
    source_channel: str


@dataclass(slots=True)
class ReportSearchHit:
    report_id: int
    title: str
    feature_id: int | None
    verified_by: str | None
    verified_at: datetime | None
    commit_sha: str | None
    snippet: str
    score: float


def _bm25_to_score(bm25_value: float, weight: float) -> float:
    # FTS5 bm25() returns lower-is-more-relevant negative-ish numbers; flip sign.
    return (-1.0 * bm25_value) * weight


def _first_commit_sha(metadata: dict[str, Any] | None) -> str | None:
    if not metadata:
        return None
    rcs = metadata.get("repo_commits") or []
    if rcs and isinstance(rcs, list) and isinstance(rcs[0], dict):
        return rcs[0].get("commit_sha")
    return None


class WikiSearchService:
    async def search_documents(
        self,
        session: AsyncSession,
        query: str,
        *,
        feature_id: int | None = None,
        limit: int = 20,
    ) -> list[DocumentSearchHit]:
        if not query.strip():
            return []
        token_query = tokenize(query)
        ngram_query = to_ngrams(query)
        feature_clause = "AND d.feature_id = :feature_id" if feature_id is not None else ""

        params: dict[str, Any] = {
            "tq": token_query if token_query else query,
            "ng": ngram_query if ngram_query else query,
            "limit": limit * 4,  # over-fetch then fuse
        }
        if feature_id is not None:
            params["feature_id"] = feature_id

        docs_rows = (
            await session.execute(
                text(
                    f"""
                    SELECT f.chunk_id, c.document_id, d.title, d.path, d.feature_id,
                           c.heading_path, snippet(docs_fts, 3, '<b>', '</b>', '...', 24) AS snip,
                           bm25(docs_fts) AS bm
                    FROM docs_fts f
                    JOIN document_chunks c ON c.id = f.chunk_id
                    JOIN documents d ON d.id = c.document_id
                    WHERE docs_fts MATCH :tq
                      AND d.is_deleted = 0
                      {feature_clause}
                    ORDER BY bm
                    LIMIT :limit
                    """
                ),
                params,
            )
        ).all()

        ngram_rows = (
            await session.execute(
                text(
                    f"""
                    SELECT g.chunk_id, c.document_id, d.title, d.path, d.feature_id,
                           c.heading_path, snippet(docs_ngram_fts, 1, '<b>', '</b>', '...', 24) AS snip,
                           bm25(docs_ngram_fts) AS bm
                    FROM docs_ngram_fts g
                    JOIN document_chunks c ON c.id = g.chunk_id
                    JOIN documents d ON d.id = c.document_id
                    WHERE docs_ngram_fts MATCH :ng
                      AND d.is_deleted = 0
                      {feature_clause}
                    ORDER BY bm
                    LIMIT :limit
                    """
                ),
                params,
            )
        ).all()

        # Fuse: keyed by chunk_id, keep best score; remember which channel gave it.
        best: dict[int, DocumentSearchHit] = {}
        for r in docs_rows:
            cid = int(r[0])
            score = _bm25_to_score(float(r[7]), _W_DOCS)
            best[cid] = DocumentSearchHit(
                chunk_id=cid,
                document_id=int(r[1]),
                document_title=str(r[2]),
                document_path=str(r[3]),
                feature_id=int(r[4]),
                heading_path=str(r[5] or ""),
                snippet=str(r[6] or ""),
                score=score,
                source_channel="docs",
            )
        for r in ngram_rows:
            cid = int(r[0])
            score = _bm25_to_score(float(r[7]), _W_NGRAM)
            if cid in best:
                # Merge: keep the higher-scoring channel's snippet/score.
                if score > best[cid].score:
                    best[cid] = DocumentSearchHit(
                        chunk_id=cid,
                        document_id=int(r[1]),
                        document_title=str(r[2]),
                        document_path=str(r[3]),
                        feature_id=int(r[4]),
                        heading_path=str(r[5] or ""),
                        snippet=str(r[6] or ""),
                        score=score,
                        source_channel="ngram",
                    )
            else:
                best[cid] = DocumentSearchHit(
                    chunk_id=cid,
                    document_id=int(r[1]),
                    document_title=str(r[2]),
                    document_path=str(r[3]),
                    feature_id=int(r[4]),
                    heading_path=str(r[5] or ""),
                    snippet=str(r[6] or ""),
                    score=score,
                    source_channel="ngram",
                )

        ranked = sorted(best.values(), key=lambda h: h.score, reverse=True)
        return ranked[:limit]

    async def search_reports(
        self,
        session: AsyncSession,
        query: str,
        *,
        feature_id: int | None = None,
        limit: int = 20,
    ) -> list[ReportSearchHit]:
        if not query.strip():
            return []
        feature_clause = "AND r.feature_id = :feature_id" if feature_id is not None else ""
        params: dict[str, Any] = {"q": query, "limit": limit}
        if feature_id is not None:
            params["feature_id"] = feature_id

        rows = (
            await session.execute(
                text(
                    f"""
                    SELECT rf.report_id, r.title, r.feature_id, r.verified_by, r.verified_at,
                           r.metadata_json,
                           snippet(reports_fts, 2, '<b>', '</b>', '...', 24) AS snip,
                           bm25(reports_fts) AS bm
                    FROM reports_fts rf
                    JOIN reports r ON r.id = rf.report_id
                    WHERE reports_fts MATCH :q
                      AND r.verified = 1
                      {feature_clause}
                    ORDER BY bm
                    LIMIT :limit
                    """
                ),
                params,
            )
        ).all()

        hits: list[ReportSearchHit] = []
        for r in rows:
            rid = int(r[0])
            metadata = r[5] if isinstance(r[5], dict) else (r[5] or {})
            verified_at = r[4]
            if isinstance(verified_at, str):
                # SQLite returns ISO strings via text() unless typed; tolerate either.
                try:
                    verified_at = datetime.fromisoformat(verified_at)
                except ValueError:
                    verified_at = None
            hits.append(
                ReportSearchHit(
                    report_id=rid,
                    title=str(r[1]),
                    feature_id=int(r[2]) if r[2] is not None else None,
                    verified_by=str(r[3]) if r[3] is not None else None,
                    verified_at=verified_at,
                    commit_sha=_first_commit_sha(metadata),
                    snippet=str(r[6] or ""),
                    score=_bm25_to_score(float(r[7]), _W_REPORTS),
                )
            )
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_wiki_search.py -v`
Expected: 4 个测试 PASS

- [ ] **Step 5: 提交**

```bash
git add src/codeask/wiki/search.py tests/integration/test_wiki_search.py
git commit -m "feat(wiki): WikiSearchService multi-channel recall + fusion"
```

---

## Task 10: audit_log writer stub + ReportService（draft / verify / unverify）

**Files:**
- Create: `src/codeask/wiki/audit.py`
- Create: `src/codeask/wiki/reports.py`
- Create: `tests/unit/test_wiki_audit.py`
- Create: `tests/integration/test_wiki_reports_lifecycle.py`

按 `evidence-report.md` §7：
- `verify(report_id, subject_id)` 闸门：报告至少含一条日志或代码证据 / 代码证据全部带 `commit_sha` / 有适用条件 / 有修复建议或验证方式。条件不满足 → 抛 `ReportVerificationError`。
- `verify` 通过：写 `verified=True` / `verified_by` / `verified_at` / `status=verified`，调 `WikiIndexer.index_report`，调 `audit.write("report.verified", ...)`。
- `unverify(report_id, subject_id)`：把 `verified=False` / `status=draft`，调 `WikiIndexer.unindex_report`，调 `audit.write("report.unverified", ...)`。
- `audit.write(event, payload, *, subject_id, log)`：一期写 structlog（`event="audit_log"`），由 06 metrics-eval 替换为写 `audit_log` 表。

校验规则解析 `metadata_json`：

| 字段 | 通过条件 |
|---|---|
| `evidence` | 至少一条 `type="log"` 或 `type="code"` |
| `evidence` | 所有 `type="code"` 的条目都有非空 `source.commit_sha` |
| `applicability` | 非空字符串 |
| `recommended_fix` 或 `verification_steps` | 至少一个非空 |

- [ ] **Step 1: 写测试 `tests/unit/test_wiki_audit.py`**

```python
"""Tests for audit stub: must emit a structured log line."""

import json

from codeask.wiki.audit import AuditWriter


def test_audit_writer_emits_event(capsys) -> None:  # type: ignore[no-untyped-def]
    from codeask.logging_config import configure_logging

    configure_logging("INFO")
    writer = AuditWriter()
    writer.write("report.verified", {"report_id": 42}, subject_id="alice@dev-1")
    out = capsys.readouterr().out.strip()
    record = json.loads(out)
    assert record["event"] == "audit_log"
    assert record["audit_event"] == "report.verified"
    assert record["report_id"] == 42
    assert record["subject_id"] == "alice@dev-1"
```

- [ ] **Step 2: 实现 `src/codeask/wiki/audit.py`**

```python
"""Audit log writer stub (real implementation in 06 metrics-eval plan)."""

from typing import Any

import structlog


class AuditWriter:
    """Stub: writes structured 'audit_log' events to structlog.

    The 06 metrics-eval plan replaces this with a writer that also persists to
    the ``audit_log`` table. Callers must keep the same signature so the swap
    is non-breaking.
    """

    def __init__(self) -> None:
        self._log = structlog.get_logger("codeask.audit")

    def write(self, event: str, payload: dict[str, Any], *, subject_id: str) -> None:
        self._log.info("audit_log", audit_event=event, subject_id=subject_id, **payload)
```

- [ ] **Step 3: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_wiki_audit.py -v`
Expected: PASS

- [ ] **Step 4: 写测试 `tests/integration/test_wiki_reports_lifecycle.py`**

```python
"""draft → verify (gate-checked) → unverify lifecycle."""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from codeask.db import session_factory
from codeask.db.models import Feature, Report
from codeask.migrations import run_migrations
from codeask.wiki.reports import ReportService, ReportVerificationError


async def _setup(tmp_path: Path):
    db_path = tmp_path / "rep.db"
    sync_url = f"sqlite:///{db_path}"
    async_url = f"sqlite+aiosqlite:///{db_path}"
    run_migrations(sync_url)
    eng = create_async_engine(async_url)
    return eng


def _good_metadata() -> dict:
    return {
        "evidence": [
            {"type": "log", "summary": "stack trace shows null user"},
            {
                "type": "code",
                "source": {"repo_id": "repo_order", "commit_sha": "abc1234", "path": "src/order/service.py"},
                "summary": "submit_order reads user.id without null check",
            },
        ],
        "applicability": "v2.4.x with default config",
        "recommended_fix": "guard user before reading user.id",
        "repo_commits": [{"repo_id": "repo_order", "commit_sha": "abc1234"}],
        "error_signatures": ["ERR_ORDER_CONTEXT_EMPTY"],
        "tags": ["order"],
    }


@pytest.mark.asyncio
async def test_verify_succeeds_then_unverify(tmp_path: Path) -> None:
    eng = await _setup(tmp_path)
    factory = session_factory(eng)
    svc = ReportService()

    async with factory() as s:
        f = Feature(name="Order", slug="o", owner_subject_id="alice@dev-1")
        s.add(f)
        await s.flush()
        rid = await svc.create_draft(
            s,
            feature_id=f.id,
            title="Order ctx empty",
            body_markdown="see report",
            metadata=_good_metadata(),
            subject_id="alice@dev-1",
        )
        await s.commit()

    async with factory() as s:
        await svc.verify(s, report_id=rid, subject_id="alice@dev-1")
        await s.commit()

    async with factory() as s:
        rep = (await s.execute(text("SELECT verified, status, verified_by FROM reports WHERE id=:i"), {"i": rid})).one()
        assert int(rep[0]) == 1
        assert rep[1] == "verified"
        assert rep[2] == "alice@dev-1"
        rows = (await s.execute(text("SELECT report_id FROM reports_fts WHERE report_id=:i"), {"i": rid})).all()
        assert rows

    async with factory() as s:
        await svc.unverify(s, report_id=rid, subject_id="alice@dev-1")
        await s.commit()

    async with factory() as s:
        rep = (await s.execute(text("SELECT verified, status FROM reports WHERE id=:i"), {"i": rid})).one()
        assert int(rep[0]) == 0
        assert rep[1] == "draft"
        rows = (await s.execute(text("SELECT report_id FROM reports_fts WHERE report_id=:i"), {"i": rid})).all()
        assert not rows
    await eng.dispose()


@pytest.mark.asyncio
async def test_verify_fails_without_log_evidence(tmp_path: Path) -> None:
    eng = await _setup(tmp_path)
    factory = session_factory(eng)
    svc = ReportService()
    bad = _good_metadata()
    bad["evidence"] = [e for e in bad["evidence"] if e["type"] != "log"]

    async with factory() as s:
        rid = await svc.create_draft(
            s, feature_id=None, title="t", body_markdown="b", metadata=bad, subject_id="x@y"
        )
        await s.commit()
    async with factory() as s:
        with pytest.raises(ReportVerificationError, match="log"):
            await svc.verify(s, report_id=rid, subject_id="x@y")
    await eng.dispose()


@pytest.mark.asyncio
async def test_verify_fails_when_code_evidence_missing_commit(tmp_path: Path) -> None:
    eng = await _setup(tmp_path)
    factory = session_factory(eng)
    svc = ReportService()
    bad = _good_metadata()
    bad["evidence"][1]["source"].pop("commit_sha")

    async with factory() as s:
        rid = await svc.create_draft(
            s, feature_id=None, title="t", body_markdown="b", metadata=bad, subject_id="x@y"
        )
        await s.commit()
    async with factory() as s:
        with pytest.raises(ReportVerificationError, match="commit"):
            await svc.verify(s, report_id=rid, subject_id="x@y")
    await eng.dispose()


@pytest.mark.asyncio
async def test_verify_fails_without_applicability(tmp_path: Path) -> None:
    eng = await _setup(tmp_path)
    factory = session_factory(eng)
    svc = ReportService()
    bad = _good_metadata()
    bad["applicability"] = ""

    async with factory() as s:
        rid = await svc.create_draft(
            s, feature_id=None, title="t", body_markdown="b", metadata=bad, subject_id="x@y"
        )
        await s.commit()
    async with factory() as s:
        with pytest.raises(ReportVerificationError, match="applicability"):
            await svc.verify(s, report_id=rid, subject_id="x@y")
    await eng.dispose()
```

- [ ] **Step 5: 实现 `src/codeask/wiki/reports.py`**

```python
"""Report lifecycle service: draft / verify (gate-checked) / unverify.

design/evidence-report.md §6 + §7.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import Report
from codeask.wiki.audit import AuditWriter
from codeask.wiki.indexer import WikiIndexer


class ReportVerificationError(Exception):
    """Raised when a draft does not meet the verification gate."""


def _check_gate(metadata: dict[str, Any]) -> None:
    evidence = metadata.get("evidence") or []
    if not any(e.get("type") == "log" for e in evidence):
        raise ReportVerificationError(
            "report must include at least one log evidence before verification"
        )
    for e in evidence:
        if e.get("type") == "code":
            commit = (e.get("source") or {}).get("commit_sha")
            if not commit:
                raise ReportVerificationError(
                    "all code evidence must bind a commit_sha (no provisional_code allowed)"
                )
    applicability = (metadata.get("applicability") or "").strip()
    if not applicability:
        raise ReportVerificationError("report must have a non-empty applicability section")
    fix = (metadata.get("recommended_fix") or "").strip()
    steps = (metadata.get("verification_steps") or "").strip()
    if not fix and not steps:
        raise ReportVerificationError(
            "report must include either recommended_fix or verification_steps"
        )


class ReportService:
    def __init__(
        self,
        indexer: WikiIndexer | None = None,
        audit: AuditWriter | None = None,
    ) -> None:
        self._indexer = indexer or WikiIndexer()
        self._audit = audit or AuditWriter()

    async def create_draft(
        self,
        session: AsyncSession,
        *,
        feature_id: int | None,
        title: str,
        body_markdown: str,
        metadata: dict[str, Any],
        subject_id: str,
    ) -> int:
        r = Report(
            feature_id=feature_id,
            title=title,
            body_markdown=body_markdown,
            metadata_json=metadata,
            status="draft",
            verified=False,
            created_by_subject_id=subject_id,
        )
        session.add(r)
        await session.flush()
        return int(r.id)

    async def update_draft(
        self,
        session: AsyncSession,
        *,
        report_id: int,
        title: str | None = None,
        body_markdown: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        r = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()
        if r.status != "draft":
            raise ReportVerificationError("only draft reports can be edited")
        if title is not None:
            r.title = title
        if body_markdown is not None:
            r.body_markdown = body_markdown
        if metadata is not None:
            r.metadata_json = metadata

    async def verify(
        self, session: AsyncSession, *, report_id: int, subject_id: str
    ) -> None:
        r = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()
        _check_gate(r.metadata_json or {})
        r.verified = True
        r.status = "verified"
        r.verified_by = subject_id
        r.verified_at = datetime.now(timezone.utc)
        await session.flush()
        await self._indexer.index_report(session, r)
        self._audit.write(
            "report.verified",
            {"report_id": int(r.id), "feature_id": r.feature_id},
            subject_id=subject_id,
        )

    async def unverify(
        self, session: AsyncSession, *, report_id: int, subject_id: str
    ) -> None:
        r = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()
        r.verified = False
        r.status = "draft"
        # Keep verified_by / verified_at so the audit trail still shows who verified it.
        await session.flush()
        await self._indexer.unindex_report(session, report_id=int(r.id))
        self._audit.write(
            "report.unverified",
            {"report_id": int(r.id), "feature_id": r.feature_id},
            subject_id=subject_id,
        )
```

- [ ] **Step 6: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_wiki_reports_lifecycle.py tests/unit/test_wiki_audit.py -v`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add src/codeask/wiki/audit.py src/codeask/wiki/reports.py tests/unit/test_wiki_audit.py tests/integration/test_wiki_reports_lifecycle.py
git commit -m "feat(wiki): ReportService draft/verify/unverify + audit stub"
```

---

## Task 11: Pydantic v2 schemas

**Files:**
- Create: `src/codeask/api/schemas/__init__.py`
- Create: `src/codeask/api/schemas/wiki.py`

按 `api-data-model.md` §2 列 11 个 schema：`FeatureCreate` / `FeatureUpdate` / `FeatureRead` / `DocumentRead` / `DocumentUpload`（multipart 表单字段）/ `DocumentSearchHit` / `ReportCreate` / `ReportUpdate` / `ReportRead` / `ReportSearchHit` / `SearchResults`。

字段类型与 ORM / search.py 数据类一致（必要时直接 `from_attributes=True` 反射）。

- [ ] **Step 1: 创建 `src/codeask/api/schemas/__init__.py`**

```python
"""Pydantic v2 request/response models for the API layer."""
```

- [ ] **Step 2: 创建 `src/codeask/api/schemas/wiki.py`**

```python
"""Schemas for /api/features /api/documents /api/reports."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FeatureCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    description: str | None = None


class FeatureUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class FeatureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None
    owner_subject_id: str
    summary_text: str | None
    created_at: datetime
    updated_at: datetime


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    feature_id: int
    kind: str
    title: str
    path: str
    tags_json: list[str] | None
    summary: str | None
    is_deleted: bool
    uploaded_by_subject_id: str
    created_at: datetime
    updated_at: datetime


class DocumentSearchHit(BaseModel):
    chunk_id: int
    document_id: int
    document_title: str
    document_path: str
    feature_id: int
    heading_path: str
    snippet: str
    score: float
    source_channel: str


class ReportCreate(BaseModel):
    feature_id: int | None = None
    title: str = Field(..., min_length=1, max_length=500)
    body_markdown: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReportUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    body_markdown: str | None = None
    metadata: dict[str, Any] | None = None


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    feature_id: int | None
    title: str
    body_markdown: str
    metadata_json: dict[str, Any]
    status: str
    verified: bool
    verified_by: str | None
    verified_at: datetime | None
    created_by_subject_id: str
    created_at: datetime
    updated_at: datetime


class ReportSearchHit(BaseModel):
    report_id: int
    title: str
    feature_id: int | None
    verified_by: str | None
    verified_at: datetime | None
    commit_sha: str | None
    snippet: str
    score: float
```

- [ ] **Step 3: 提交（无新测试，schemas 在后续 Task 12+13 的 API 测试里覆盖）**

```bash
git add src/codeask/api/schemas/__init__.py src/codeask/api/schemas/wiki.py
git commit -m "feat(wiki): pydantic v2 schemas for features / documents / reports"
```

---

## Task 12: REST endpoints — /api/features + /api/documents（CRUD + 上传 + 搜索）

**Files:**
- Create: `src/codeask/api/wiki.py`
- Modify: `src/codeask/app.py`（include_router）
- Create: `tests/integration/test_wiki_features_api.py`
- Create: `tests/integration/test_wiki_documents_api.py`

Endpoints：

```text
GET    /api/features
POST   /api/features
GET    /api/features/{id}
PUT    /api/features/{id}
DELETE /api/features/{id}

GET    /api/documents?feature_id=&q=
POST   /api/documents              （multipart: feature_id + file + title? + tags?）
GET    /api/documents/{id}
DELETE /api/documents/{id}         （软删除：is_deleted=true，FTS 同步下架）
GET    /api/documents/search?q=&feature_id=&limit=
```

身份：所有写入操作的 owner / uploader 来自 `request.state.subject_id`。

上传流水线：保存原文 → 调 `DocumentChunker.chunk_file` → 落 `documents` + `document_chunks` + `document_references`（仅 markdown 解析图片链接）→ 调 `WikiIndexer.index_chunk`。

- [ ] **Step 1: 创建 `src/codeask/api/wiki.py` 的 features 部分（先实现 features，再加 documents 与 reports）**

```python
"""REST router: /api/features /api/documents /api/reports."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.api.schemas.wiki import (
    DocumentRead,
    DocumentSearchHit,
    FeatureCreate,
    FeatureRead,
    FeatureUpdate,
    ReportCreate,
    ReportRead,
    ReportSearchHit,
    ReportUpdate,
)
from codeask.db.models import Document, DocumentChunk, DocumentReference, Feature, Report
from codeask.wiki.chunker import DocumentChunker
from codeask.wiki.indexer import WikiIndexer
from codeask.wiki.reports import ReportService, ReportVerificationError
from codeask.wiki.search import WikiSearchService

router = APIRouter()

_KIND_BY_EXT: dict[str, str] = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".text": "text",
    ".pdf": "pdf",
    ".docx": "docx",
}
_IMG_LINK_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_REL_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)\s#]+)(?:\s+\"[^\"]*\")?\)")


async def _session(request: Request) -> AsyncSession:
    factory = request.app.state.session_factory
    async with factory() as s:
        yield s


# ---------- features ----------

@router.get("/features", response_model=list[FeatureRead])
async def list_features(session: AsyncSession = Depends(_session)) -> list[FeatureRead]:
    rows = (await session.execute(select(Feature).order_by(Feature.id))).scalars().all()
    return [FeatureRead.model_validate(r) for r in rows]


@router.post("/features", response_model=FeatureRead, status_code=status.HTTP_201_CREATED)
async def create_feature(
    payload: FeatureCreate,
    request: Request,
    session: AsyncSession = Depends(_session),
) -> FeatureRead:
    f = Feature(
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        owner_subject_id=request.state.subject_id,
    )
    session.add(f)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail=f"slug '{payload.slug}' already exists")
    await session.refresh(f)
    return FeatureRead.model_validate(f)


@router.get("/features/{feature_id}", response_model=FeatureRead)
async def get_feature(feature_id: int, session: AsyncSession = Depends(_session)) -> FeatureRead:
    f = (await session.execute(select(Feature).where(Feature.id == feature_id))).scalar_one_or_none()
    if f is None:
        raise HTTPException(status_code=404, detail="feature not found")
    return FeatureRead.model_validate(f)


@router.put("/features/{feature_id}", response_model=FeatureRead)
async def update_feature(
    feature_id: int,
    payload: FeatureUpdate,
    session: AsyncSession = Depends(_session),
) -> FeatureRead:
    f = (await session.execute(select(Feature).where(Feature.id == feature_id))).scalar_one_or_none()
    if f is None:
        raise HTTPException(status_code=404, detail="feature not found")
    if payload.name is not None:
        f.name = payload.name
    if payload.description is not None:
        f.description = payload.description
    await session.commit()
    await session.refresh(f)
    return FeatureRead.model_validate(f)


@router.delete("/features/{feature_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feature(feature_id: int, session: AsyncSession = Depends(_session)) -> None:
    f = (await session.execute(select(Feature).where(Feature.id == feature_id))).scalar_one_or_none()
    if f is None:
        raise HTTPException(status_code=404, detail="feature not found")
    await session.delete(f)
    await session.commit()
```

- [ ] **Step 2: 在 `src/codeask/api/wiki.py` 末尾追加 documents + reports endpoints**

```python


# ---------- documents ----------

def _kind_from_filename(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext not in _KIND_BY_EXT:
        raise HTTPException(status_code=400, detail=f"unsupported file extension: {ext}")
    return _KIND_BY_EXT[ext]


def _wiki_storage_dir(request: Request) -> Path:
    settings = request.app.state.settings
    p = settings.data_dir / "wiki"
    p.mkdir(parents=True, exist_ok=True)
    return p


@router.get("/documents", response_model=list[DocumentRead])
async def list_documents(
    feature_id: int | None = None,
    session: AsyncSession = Depends(_session),
) -> list[DocumentRead]:
    stmt = select(Document).where(Document.is_deleted.is_(False))
    if feature_id is not None:
        stmt = stmt.where(Document.feature_id == feature_id)
    rows = (await session.execute(stmt.order_by(Document.id))).scalars().all()
    return [DocumentRead.model_validate(r) for r in rows]


@router.post("/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    feature_id: int = Form(...),
    title: str | None = Form(default=None),
    tags: str | None = Form(default=None),  # comma-separated
    file: UploadFile = File(...),
    session: AsyncSession = Depends(_session),
) -> DocumentRead:
    if not file.filename:
        raise HTTPException(status_code=400, detail="file must have a filename")
    feature = (
        await session.execute(select(Feature).where(Feature.id == feature_id))
    ).scalar_one_or_none()
    if feature is None:
        raise HTTPException(status_code=404, detail="feature not found")

    kind = _kind_from_filename(file.filename)
    storage_dir = _wiki_storage_dir(request) / f"feature_{feature_id}"
    storage_dir.mkdir(parents=True, exist_ok=True)
    target = storage_dir / file.filename
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()] or None

    chunker = DocumentChunker()
    parsed = chunker.chunk_file(target, kind=kind)
    if not parsed:
        raise HTTPException(status_code=400, detail="document parsed to zero chunks")

    document = Document(
        feature_id=feature_id,
        kind=kind,
        title=title or Path(file.filename).stem,
        path=file.filename,
        tags_json=tag_list,
        raw_file_path=str(target),
        uploaded_by_subject_id=request.state.subject_id,
    )
    session.add(document)
    await session.flush()

    indexer = WikiIndexer()
    raw_text = target.read_text(encoding="utf-8") if kind in ("markdown", "text") else ""
    seen_refs: set[tuple[str, str]] = set()
    if kind == "markdown":
        for m in _IMG_LINK_RE.finditer(raw_text):
            key = (m.group(1), "image")
            if key not in seen_refs:
                seen_refs.add(key)
                session.add(DocumentReference(document_id=document.id, target_path=m.group(1), kind="image"))
        for m in _REL_LINK_RE.finditer(raw_text):
            key = (m.group(1), "link")
            if key not in seen_refs:
                seen_refs.add(key)
                session.add(DocumentReference(document_id=document.id, target_path=m.group(1), kind="link"))

    for p in parsed:
        chunk = DocumentChunk(
            document_id=document.id,
            chunk_index=p.chunk_index,
            heading_path=p.heading_path,
            raw_text=p.raw_text,
            normalized_text=p.normalized_text,
            tokenized_text=p.tokenized_text,
            ngram_text=p.ngram_text,
            signals_json=p.signals_json,
            start_offset=p.start_offset,
            end_offset=p.end_offset,
        )
        session.add(chunk)
        await session.flush()
        await indexer.index_chunk(session, chunk, document)

    await session.commit()
    await session.refresh(document)
    return DocumentRead.model_validate(document)


@router.get("/documents/search", response_model=list[DocumentSearchHit])
async def search_documents(
    q: str,
    feature_id: int | None = None,
    limit: int = 20,
    session: AsyncSession = Depends(_session),
) -> list[DocumentSearchHit]:
    svc = WikiSearchService()
    raw_hits = await svc.search_documents(session, q, feature_id=feature_id, limit=limit)
    return [DocumentSearchHit(**h.__dict__) for h in raw_hits]


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(document_id: int, session: AsyncSession = Depends(_session)) -> DocumentRead:
    d = (await session.execute(select(Document).where(Document.id == document_id))).scalar_one_or_none()
    if d is None or d.is_deleted:
        raise HTTPException(status_code=404, detail="document not found")
    return DocumentRead.model_validate(d)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: int, session: AsyncSession = Depends(_session)) -> None:
    d = (await session.execute(select(Document).where(Document.id == document_id))).scalar_one_or_none()
    if d is None or d.is_deleted:
        raise HTTPException(status_code=404, detail="document not found")
    indexer = WikiIndexer()
    await indexer.unindex_chunks_for_document(session, doc_id=document_id)
    d.is_deleted = True
    await session.commit()


# ---------- reports ----------

@router.get("/reports", response_model=list[ReportRead])
async def list_reports(
    feature_id: int | None = None,
    session: AsyncSession = Depends(_session),
) -> list[ReportRead]:
    stmt = select(Report)
    if feature_id is not None:
        stmt = stmt.where(Report.feature_id == feature_id)
    rows = (await session.execute(stmt.order_by(Report.id))).scalars().all()
    return [ReportRead.model_validate(r) for r in rows]


@router.post("/reports", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
async def create_report(
    payload: ReportCreate,
    request: Request,
    session: AsyncSession = Depends(_session),
) -> ReportRead:
    svc = ReportService()
    rid = await svc.create_draft(
        session,
        feature_id=payload.feature_id,
        title=payload.title,
        body_markdown=payload.body_markdown,
        metadata=payload.metadata,
        subject_id=request.state.subject_id,
    )
    await session.commit()
    r = (await session.execute(select(Report).where(Report.id == rid))).scalar_one()
    return ReportRead.model_validate(r)


@router.get("/reports/search", response_model=list[ReportSearchHit])
async def search_reports(
    q: str,
    feature_id: int | None = None,
    limit: int = 20,
    session: AsyncSession = Depends(_session),
) -> list[ReportSearchHit]:
    svc = WikiSearchService()
    raw_hits = await svc.search_reports(session, q, feature_id=feature_id, limit=limit)
    return [ReportSearchHit(**h.__dict__) for h in raw_hits]


@router.get("/reports/{report_id}", response_model=ReportRead)
async def get_report(report_id: int, session: AsyncSession = Depends(_session)) -> ReportRead:
    r = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="report not found")
    return ReportRead.model_validate(r)


@router.put("/reports/{report_id}", response_model=ReportRead)
async def update_report(
    report_id: int,
    payload: ReportUpdate,
    session: AsyncSession = Depends(_session),
) -> ReportRead:
    svc = ReportService()
    try:
        await svc.update_draft(
            session,
            report_id=report_id,
            title=payload.title,
            body_markdown=payload.body_markdown,
            metadata=payload.metadata,
        )
    except ReportVerificationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await session.commit()
    r = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()
    return ReportRead.model_validate(r)


@router.post("/reports/{report_id}/verify", response_model=ReportRead)
async def verify_report(
    report_id: int,
    request: Request,
    session: AsyncSession = Depends(_session),
) -> ReportRead:
    svc = ReportService()
    try:
        await svc.verify(session, report_id=report_id, subject_id=request.state.subject_id)
    except ReportVerificationError as exc:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    await session.commit()
    r = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()
    return ReportRead.model_validate(r)


@router.post("/reports/{report_id}/unverify", response_model=ReportRead)
async def unverify_report(
    report_id: int,
    request: Request,
    session: AsyncSession = Depends(_session),
) -> ReportRead:
    svc = ReportService()
    await svc.unverify(session, report_id=report_id, subject_id=request.state.subject_id)
    await session.commit()
    r = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()
    return ReportRead.model_validate(r)
```

- [ ] **Step 3: 在 `src/codeask/app.py` 的 `create_app` 中 include router**

把现有的 healthz router 行下方追加：

```python
    from codeask.api.wiki import router as wiki_router

    app.include_router(wiki_router, prefix="/api")
```

确保 import 不形成环依赖（wiki 模块只依赖 db / wiki/）。

- [ ] **Step 4: 写测试 `tests/integration/test_wiki_features_api.py`**

```python
"""End-to-end /api/features tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_list_get_update_delete_feature(client: AsyncClient) -> None:
    r = await client.post(
        "/api/features",
        json={"name": "Order", "slug": "order", "description": "core"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    fid = body["id"]
    assert body["owner_subject_id"] == "alice@dev-1"
    assert body["slug"] == "order"

    r = await client.get("/api/features")
    assert r.status_code == 200
    assert any(f["id"] == fid for f in r.json())

    r = await client.get(f"/api/features/{fid}")
    assert r.status_code == 200

    r = await client.put(f"/api/features/{fid}", json={"description": "updated"})
    assert r.status_code == 200
    assert r.json()["description"] == "updated"

    r = await client.delete(f"/api/features/{fid}")
    assert r.status_code == 204

    r = await client.get(f"/api/features/{fid}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_slug_returns_409(client: AsyncClient) -> None:
    await client.post(
        "/api/features",
        json={"name": "A", "slug": "dup-slug"},
        headers={"X-Subject-Id": "x@y"},
    )
    r = await client.post(
        "/api/features",
        json={"name": "B", "slug": "dup-slug"},
        headers={"X-Subject-Id": "x@y"},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_invalid_slug_format_rejected(client: AsyncClient) -> None:
    r = await client.post(
        "/api/features",
        json={"name": "Bad", "slug": "Invalid Slug"},
        headers={"X-Subject-Id": "x@y"},
    )
    assert r.status_code == 422
```

- [ ] **Step 5: 写测试 `tests/integration/test_wiki_documents_api.py`**

```python
"""End-to-end /api/documents tests."""

from pathlib import Path

import pytest
from httpx import AsyncClient

MARKDOWN = """# Submit Order

## Overview

调用 /api/order/submit 完成订单提交。当 user 为空抛 NullPointerException.
"""


async def _create_feature(client: AsyncClient) -> int:
    r = await client.post(
        "/api/features",
        json={"name": "Order", "slug": "order"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    return r.json()["id"]


@pytest.mark.asyncio
async def test_upload_then_list_then_search(client: AsyncClient, tmp_path: Path) -> None:
    fid = await _create_feature(client)
    md_path = tmp_path / "submit.md"
    md_path.write_text(MARKDOWN, encoding="utf-8")

    with md_path.open("rb") as f:
        r = await client.post(
            "/api/documents",
            data={"feature_id": str(fid), "title": "Submit Order Spec", "tags": "order,spec"},
            files={"file": ("submit.md", f, "text/markdown")},
            headers={"X-Subject-Id": "alice@dev-1"},
        )
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]

    r = await client.get(f"/api/documents?feature_id={fid}")
    assert r.status_code == 200
    assert any(d["id"] == doc_id for d in r.json())

    r = await client.get("/api/documents/search?q=submit+order")
    assert r.status_code == 200
    hits = r.json()
    assert any(h["document_id"] == doc_id for h in hits)


@pytest.mark.asyncio
async def test_soft_delete_document_removes_from_search(
    client: AsyncClient, tmp_path: Path
) -> None:
    fid = await _create_feature(client)
    md_path = tmp_path / "x.md"
    md_path.write_text(MARKDOWN, encoding="utf-8")
    with md_path.open("rb") as f:
        r = await client.post(
            "/api/documents",
            data={"feature_id": str(fid)},
            files={"file": ("x.md", f, "text/markdown")},
            headers={"X-Subject-Id": "u@1"},
        )
    doc_id = r.json()["id"]

    r = await client.delete(f"/api/documents/{doc_id}")
    assert r.status_code == 204

    r = await client.get("/api/documents/search?q=submit+order")
    hits = r.json()
    assert all(h["document_id"] != doc_id for h in hits)


@pytest.mark.asyncio
async def test_unsupported_extension_rejected(client: AsyncClient, tmp_path: Path) -> None:
    fid = await _create_feature(client)
    bin_path = tmp_path / "x.bin"
    bin_path.write_bytes(b"\x00\x01")
    with bin_path.open("rb") as f:
        r = await client.post(
            "/api/documents",
            data={"feature_id": str(fid)},
            files={"file": ("x.bin", f, "application/octet-stream")},
            headers={"X-Subject-Id": "u@1"},
        )
    assert r.status_code == 400
```

- [ ] **Step 6: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_wiki_features_api.py tests/integration/test_wiki_documents_api.py -v`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add src/codeask/api/wiki.py src/codeask/app.py tests/integration/test_wiki_features_api.py tests/integration/test_wiki_documents_api.py
git commit -m "feat(wiki): /api/features + /api/documents endpoints + upload pipeline"
```

---

## Task 13: REST endpoints — /api/reports（测试 + 端到端）

**Files:**
- Create: `tests/integration/test_wiki_reports_api.py`
- Create: `tests/integration/test_wiki_end_to_end.py`

报告 endpoints 已在 Task 12 实现，本任务只补 API 级别测试 + 一个跨组件端到端测试，证明 spec 列出的全套流程跑通。

- [ ] **Step 1: 写测试 `tests/integration/test_wiki_reports_api.py`**

```python
"""End-to-end /api/reports tests."""

import pytest
from httpx import AsyncClient


def _good_meta() -> dict:
    return {
        "evidence": [
            {"type": "log", "summary": "stack trace null user"},
            {
                "type": "code",
                "source": {"repo_id": "repo_order", "commit_sha": "abc1234", "path": "src/x.py"},
                "summary": "missing null check",
            },
        ],
        "applicability": "v2.4.x default config",
        "recommended_fix": "guard user before user.id",
        "repo_commits": [{"repo_id": "repo_order", "commit_sha": "abc1234"}],
        "error_signatures": ["ERR_ORDER_CONTEXT_EMPTY"],
        "tags": ["order"],
    }


@pytest.mark.asyncio
async def test_create_then_verify_then_unverify(client: AsyncClient) -> None:
    r = await client.post(
        "/api/features",
        json={"name": "Order", "slug": "order"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    fid = r.json()["id"]

    r = await client.post(
        "/api/reports",
        json={
            "feature_id": fid,
            "title": "Order ctx empty",
            "body_markdown": "see metadata",
            "metadata": _good_meta(),
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert r.status_code == 201
    rid = r.json()["id"]
    assert r.json()["status"] == "draft"
    assert r.json()["verified"] is False

    r = await client.post(f"/api/reports/{rid}/verify", headers={"X-Subject-Id": "alice@dev-1"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verified"] is True
    assert body["status"] == "verified"
    assert body["verified_by"] == "alice@dev-1"
    assert body["verified_at"] is not None

    r = await client.get("/api/reports/search?q=ERR_ORDER_CONTEXT_EMPTY")
    assert r.status_code == 200
    hits = r.json()
    assert any(h["report_id"] == rid for h in hits)
    found = next(h for h in hits if h["report_id"] == rid)
    assert found["verified_by"] == "alice@dev-1"
    assert found["commit_sha"] == "abc1234"

    r = await client.post(f"/api/reports/{rid}/unverify", headers={"X-Subject-Id": "alice@dev-1"})
    assert r.status_code == 200
    assert r.json()["verified"] is False
    assert r.json()["status"] == "draft"

    r = await client.get("/api/reports/search?q=ERR_ORDER_CONTEXT_EMPTY")
    hits = r.json()
    assert all(h["report_id"] != rid for h in hits)


@pytest.mark.asyncio
async def test_verify_gate_rejects_missing_log_evidence(client: AsyncClient) -> None:
    bad = _good_meta()
    bad["evidence"] = [e for e in bad["evidence"] if e["type"] != "log"]
    r = await client.post(
        "/api/reports",
        json={"title": "t", "body_markdown": "b", "metadata": bad},
        headers={"X-Subject-Id": "x@y"},
    )
    rid = r.json()["id"]
    r = await client.post(f"/api/reports/{rid}/verify", headers={"X-Subject-Id": "x@y"})
    assert r.status_code == 422
    assert "log" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_draft_then_verify(client: AsyncClient) -> None:
    bad = _good_meta()
    bad["applicability"] = ""
    r = await client.post(
        "/api/reports",
        json={"title": "t", "body_markdown": "b", "metadata": bad},
        headers={"X-Subject-Id": "x@y"},
    )
    rid = r.json()["id"]
    fixed = _good_meta()
    r = await client.put(
        f"/api/reports/{rid}",
        json={"metadata": fixed},
        headers={"X-Subject-Id": "x@y"},
    )
    assert r.status_code == 200
    r = await client.post(f"/api/reports/{rid}/verify", headers={"X-Subject-Id": "x@y"})
    assert r.status_code == 200
```

- [ ] **Step 2: 写跨组件端到端 `tests/integration/test_wiki_end_to_end.py`**

```python
"""Spec-level end-to-end:
upload doc → search hit → create report draft → verify → report search hit
→ unverify → report search no longer hits.
"""

from pathlib import Path

import pytest
from httpx import AsyncClient


MARKDOWN = """# Order ctx

## Overview

call /api/order/submit; on null user we throw NullPointerException with code ERR_ORDER_CONTEXT_EMPTY.
"""


@pytest.mark.asyncio
async def test_full_wiki_flow(client: AsyncClient, tmp_path: Path) -> None:
    # 1. Create feature
    r = await client.post(
        "/api/features",
        json={"name": "Order", "slug": "order"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert r.status_code == 201
    fid = r.json()["id"]

    # 2. Upload markdown doc
    md_path = tmp_path / "spec.md"
    md_path.write_text(MARKDOWN, encoding="utf-8")
    with md_path.open("rb") as f:
        r = await client.post(
            "/api/documents",
            data={"feature_id": str(fid), "title": "Order Spec"},
            files={"file": ("spec.md", f, "text/markdown")},
            headers={"X-Subject-Id": "alice@dev-1"},
        )
    assert r.status_code == 201
    doc_id = r.json()["id"]

    # 3. Document search hits the new chunk
    r = await client.get("/api/documents/search?q=ERR_ORDER_CONTEXT_EMPTY")
    hits = r.json()
    assert any(h["document_id"] == doc_id for h in hits)

    # 4. Create draft report referencing the same error
    r = await client.post(
        "/api/reports",
        json={
            "feature_id": fid,
            "title": "ERR_ORDER_CONTEXT_EMPTY 排查",
            "body_markdown": "见 evidence",
            "metadata": {
                "evidence": [
                    {"type": "log", "summary": "stack trace shows ERR_ORDER_CONTEXT_EMPTY"},
                    {
                        "type": "code",
                        "source": {"repo_id": "repo_order", "commit_sha": "abc1234", "path": "src/x.py"},
                        "summary": "no null guard",
                    },
                ],
                "applicability": "v2.4.x",
                "recommended_fix": "guard user",
                "repo_commits": [{"repo_id": "repo_order", "commit_sha": "abc1234"}],
                "error_signatures": ["ERR_ORDER_CONTEXT_EMPTY"],
                "tags": ["order"],
            },
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    rid = r.json()["id"]

    # 5. Before verify: report search must NOT hit
    r = await client.get("/api/reports/search?q=ERR_ORDER_CONTEXT_EMPTY")
    assert all(h["report_id"] != rid for h in r.json())

    # 6. Verify
    r = await client.post(f"/api/reports/{rid}/verify", headers={"X-Subject-Id": "alice@dev-1"})
    assert r.status_code == 200

    # 7. Now report search hits and carries verified_by/at + commit_sha
    r = await client.get("/api/reports/search?q=ERR_ORDER_CONTEXT_EMPTY")
    hits = r.json()
    found = next(h for h in hits if h["report_id"] == rid)
    assert found["verified_by"] == "alice@dev-1"
    assert found["verified_at"] is not None
    assert found["commit_sha"] == "abc1234"

    # 8. Unverify removes from search
    r = await client.post(f"/api/reports/{rid}/unverify", headers={"X-Subject-Id": "alice@dev-1"})
    assert r.status_code == 200
    r = await client.get("/api/reports/search?q=ERR_ORDER_CONTEXT_EMPTY")
    assert all(h["report_id"] != rid for h in r.json())
```

- [ ] **Step 3: 跑全部 wiki 相关测试**

Run: `uv run pytest tests/integration/test_wiki_reports_api.py tests/integration/test_wiki_end_to_end.py -v`
Expected: 4 个测试 PASS

- [ ] **Step 4: 提交**

```bash
git add tests/integration/test_wiki_reports_api.py tests/integration/test_wiki_end_to_end.py
git commit -m "test(wiki): /api/reports lifecycle + spec-level end-to-end"
```

---

## Task 14: 全量回归 + lint + type check + 计划交接更新

**Files:**
- Modify: `docs/v1.0/plans/foundation-handoff.md`（追加"02 wiki-knowledge 已落地的 hook"小节）

按 foundation Task 14 hand-off 约定：本计划新增了 `wiki/`、`api/wiki.py`、`api/schemas/`、4 份 alembic migration、3 张 FTS5 表、`AuditWriter` 占位。后续 03 / 04 / 06 计划在自家 endpoint 写入 verify-类操作时**沿用** `AuditWriter` 接口；06 metrics-eval 计划替换 `audit.py` 实现为写 `audit_log` 表。

- [ ] **Step 1: 跑 ruff lint + format check**

Run: `uv run ruff check src tests && uv run ruff format --check src tests`
Expected: 无错误。如有 format diff，先运行 `uv run ruff format src tests` 再继续。

- [ ] **Step 2: 跑 pyright**

Run: `uv run pyright src/codeask`
Expected: `0 errors, 0 warnings`

- [ ] **Step 3: 跑全量 pytest**

Run: `uv run pytest -v`
Expected: foundation 计划 23 条 + 本计划新增（粗略统计）：
- `tests/unit/test_wiki_tokenizer.py`: 8
- `tests/unit/test_wiki_signals.py`: 7
- `tests/unit/test_wiki_chunker.py`: 6
- `tests/unit/test_wiki_audit.py`: 1
- `tests/integration/test_wiki_models.py`: 4
- `tests/integration/test_wiki_migrations.py`: 3
- `tests/integration/test_wiki_indexer.py`: 2
- `tests/integration/test_wiki_search.py`: 4
- `tests/integration/test_wiki_reports_lifecycle.py`: 4
- `tests/integration/test_wiki_features_api.py`: 3
- `tests/integration/test_wiki_documents_api.py`: 3
- `tests/integration/test_wiki_reports_api.py`: 3
- `tests/integration/test_wiki_end_to_end.py`: 1
- 本计划新增：49（合计 72）

全部 PASS。

- [ ] **Step 4: 在 `docs/v1.0/plans/foundation-handoff.md` 末尾追加新小节**

```markdown

## 7. 02 wiki-knowledge 已落地的 hook

| Hook | 形态 | 后续计划如何使用 |
|---|---|---|
| `WikiIndexer` | `src/codeask/wiki/indexer.py` | 03 / 04 计划如需把自家内容加进 FTS5（比如代码符号），在新增 FTS 表后参考此模块加 `index_xxx` / `unindex_xxx` 方法 |
| `AuditWriter` | `src/codeask/wiki/audit.py`（stub）| 06 metrics-eval 计划替换为写 `audit_log` 表的实现；调用方接口不变 |
| `WikiSearchService` | `src/codeask/wiki/search.py` | 04 agent-runtime 的 `search_wiki` / `search_reports` tool 直接调用 |
| `DocumentChunker` | `src/codeask/wiki/chunker.py` | 03 / 04 如有新文档类型，在 `chunk_file` 的 dispatcher 加 `kind` 分支即可 |
| `tokenize` / `to_ngrams` | `src/codeask/wiki/tokenizer.py` | 任何写 FTS5 内容的模块都先过这两个函数，保持索引与查询同 tokenization |
| Alembic 链 | head 现在是 `0005` | 后续 plan 第一份 migration 的 `down_revision = "0005"` |
```

- [ ] **Step 5: 打 tag 标记 wiki-knowledge 完成**

```bash
git add docs/v1.0/plans/foundation-handoff.md
git commit -m "docs(plans): record wiki hooks for follow-on plans"
git tag -a wiki-knowledge-v0.1.0 -m "Wiki milestone: features + documents + reports + multi-channel search"
```

---

## 验收标志（计划完整通过后应满足）

- [x] `alembic upgrade head` 把 head 推到 `0005`，`docs_fts` / `docs_ngram_fts` / `reports_fts` 三张 FTS5 虚拟表存在
- [x] `POST /api/features` 创建特性，`owner_subject_id` 来自 `X-Subject-Id` header
- [x] `POST /api/documents`（multipart）上传 .md 文档：保存原文 → 切 chunk → 写 `documents` + `document_chunks` + `document_references` → 索引 `docs_fts` + `docs_ngram_fts`
- [x] `GET /api/documents/search?q=...` 返回融合排序的多路命中（含 `source_channel` 字段）
- [x] `POST /api/reports` 建草稿，`POST /api/reports/{id}/verify` 通过 4 项闸门后入 `reports_fts`
- [x] `GET /api/reports/search?q=...` 命中 verified 报告，附 `verified_by` / `verified_at` / `commit_sha`
- [x] `POST /api/reports/{id}/unverify` 把报告下架且 audit 事件写入 structlog
- [x] 全量 `uv run pytest` 72 条全 PASS（foundation 23 + 本计划 49）
- [x] `uv run ruff check && uv run pyright src/codeask` 零错误
- [x] git tag `wiki-knowledge-v0.1.0` 已打

---

## 不在本计划范围（明确推迟）

| 项 | 推迟到 | 原因 |
|---|---|---|
| `repos` / `feature_repos` 表 | 03 code-index plan | 仓库注册不属于知识库范畴 |
| `sessions` / `session_*` / `agent_traces` 表 | 04 agent-runtime plan | 会话与 Agent 状态机非本计划范围 |
| 前端 Wiki 管理页 / 报告详情页 / 撤销验证按钮 UI | 05 frontend-workbench plan | 本计划只交付后端 API |
| `feedback` / `audit_log` 表落表实现 | 06 metrics-eval plan | 本计划 `AuditWriter` 是 stub，写 structlog；接口契约稳定 |
| `summary_text` / `navigation_index` digest 重算 worker | 04 或 06（视 dashboard 需求） | 一期检索本身不依赖 digest；digest 用于 Agent prompt L2 注入，归属 04 |
| 向量召回叠加 | MVP+ | dependencies.md §8 锁定为扩展位 |
| jieba / 自定义业务词典 | MVP+ | tokenizer 已留替换点（调用方可在写库前替换 `tokenize`） |
| Skills CRUD（`/api/skills`） | 04 agent-runtime plan | skill 与 prompt 注入耦合，与 Agent 一起落 |
| `document_references` 解析（链接相对路径校验、图片实际可达性） | MVP+ | 一期只记录引用，不主动校验 |
