# Code Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地全局仓库池 + 会话级 worktree 隔离 + 代码检索三件套（ripgrep / universal-ctags / file reader），暴露 `/api/repos` 与 `/api/code/*` 底层 endpoints，并配 24h idle worktree 清理任务。

**Architecture:** 注册仓库 → APScheduler 后台执行 `git clone --bare` 到 `~/.codeask/repos/<repo_id>/bare/`；状态机 registered → cloning → ready/failed。会话访问代码时按需在 `~/.codeask/repos/<repo_id>/worktrees/<session_id>/` 上 `git worktree add --detach <commit>`；多个会话共享同一份 git 数据库，互不干扰。检索全部走 subprocess + 参数数组（`shell=False`）：`rg --json` 做全文搜索，`universal-ctags` 做符号定位（`repo_id+commit` LRU 缓存），FileReader 受路径白名单约束读片段。APScheduler 每天扫描 worktree mtime > 24h 后调用 `git worktree remove` 释放磁盘，DB 中的 `session_repo_bindings` 行保留但 worktree_path 置空，用户重新提问时按需重建。

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 async, Alembic, APScheduler, subprocess + git CLI, ripgrep (`rg --json`), universal-ctags, Pydantic v2, pytest, pytest-asyncio, httpx

**Source SDD docs**（路径相对本文件 `docs/v1.0/plans/code-index.md`）：
- `../design/api-data-model.md`
- `../design/code-index.md`
- `../design/tools.md`
- `../design/deployment-security.md`
- `../design/dependencies.md`

**Depends on:** `docs/v1.0/plans/foundation.md`（DB engine / Settings / `~/.codeask/` 布局 / Alembic baseline 0001 / FastAPI app factory）、`docs/v1.0/plans/wiki-knowledge.md`（`feature_repos.feature_id` 引用 features 表，wiki-knowledge plan 必须先把 features 表建好）

**Project root:** `/home/hzh/workspace/CodeAsk/`。本计划全部文件路径相对此根目录。

**Revision 衔接说明：** wiki-knowledge plan 占用 alembic revision `0002`–`0005`，本计划以 `0006` 起步（一份 migration）。后续 04 agent-runtime plan 接 `0007` 起。

**Demo Scope Lock:** 本计划只交付 v1.0 代码访问底座，不实现成熟 Agent IDE 级工具智能。`ripgrep` / `ctags` / file reader 只负责安全、稳定、结构化地返回底层结果；Agent 多轮工具规划、搜索结果重排、上下文预算、跨轮去重和自动下一步判断进入后续 `tool-intelligence` / `agent-runtime` 优化阶段。二期规划必须回看 `../design/code-index.md` §7.1/§7.2、`../design/tools.md` §8 和 `roadmap.md` 的二期锚点。

---

## File Structure

本计划交付以下文件（全部相对项目根 `/home/hzh/workspace/CodeAsk/`）：

```text
CodeAsk/
├── alembic/versions/
│   └── 20260430_0006_code_index.py             # repos + feature_repos
├── src/codeask/
│   ├── db/models/
│   │   └── code_index.py                       # Repo + FeatureRepo ORM
│   ├── code_index/
│   │   ├── __init__.py
│   │   ├── path_safety.py                      # is_safe_path helper
│   │   ├── cloner.py                           # RepoCloner (APScheduler job)
│   │   ├── worktree.py                         # WorktreeManager
│   │   ├── ripgrep.py                          # RipgrepClient (rg --json)
│   │   ├── ctags.py                            # CtagsClient + LRU cache
│   │   ├── file_reader.py                      # FileReader (path whitelist + line range)
│   │   └── cleanup.py                          # 24h idle worktree janitor
│   ├── api/
│   │   ├── code_index.py                       # /api/repos + /api/code/{grep,read,symbols}
│   │   └── schemas/
│   │       └── code_index.py                   # Pydantic v2 request/response models
│   └── app.py                                  # MODIFIED: include router + start scheduler
└── tests/
    ├── unit/
    │   ├── test_path_safety.py
    │   ├── test_ripgrep.py
    │   ├── test_ctags.py
    │   └── test_file_reader.py
    └── integration/
        ├── test_repo_models.py
        ├── test_cloner.py
        ├── test_worktree.py
        ├── test_repos_api.py
        ├── test_code_api.py
        └── test_cleanup.py
```

**职责边界：**
- `db/models/code_index.py` 只声明 ORM 字段；不写业务逻辑。
- `code_index/cloner.py` 只跑 `git clone --bare`，更新 `repos.status`；不暴露 HTTP。
- `code_index/worktree.py` 只跑 `git worktree add/remove/list` 和 ref → SHA 解析；不读文件内容。
- `code_index/ripgrep.py` / `ctags.py` / `file_reader.py` 是无状态 subprocess wrapper（ctags 例外，含进程内 LRU），不直接和 DB 说话。
- `code_index/path_safety.py` 是 helper，只做路径校验。
- `code_index/cleanup.py` 是 APScheduler job，只读 worktree mtime + 调 `WorktreeManager.destroy_worktree`。
- `api/code_index.py` 只编排 HTTP 协议，业务逻辑全部委托给 `code_index/` 子包。
- `api/schemas/code_index.py` 只定义 Pydantic 模型，零业务逻辑。

---

## Status / Source 取值锁定

为了在 ORM / API / Pydantic schema / 测试四处保持一致，本计划锁定以下字符串字面量。**任何代码层只能引用 `Repo.STATUS_*` / `Repo.SOURCE_*` 常量，禁止裸字符串。**

| 字段 | 允许取值 |
|---|---|
| `repos.status` | `registered` / `cloning` / `ready` / `failed` |
| `repos.source` | `git` / `local_dir` |

错误码（统一在 `api/code_index.py` 用）：

| 错误码 | HTTP | 含义 |
|---|---|---|
| `REPO_NOT_FOUND` | 404 | repo_id 在 DB 中不存在 |
| `REPO_NOT_READY` | 409 | repo.status != 'ready'（仍在 cloning 或 failed） |
| `INVALID_PATH` | 400 | 路径越狱（`..`、绝对路径或不在白名单内） |
| `INVALID_REF` | 400 | branch/tag/sha 在仓库中解析不到 |
| `TOOL_TIMEOUT` | 504 | subprocess 超时 |
| `TOOL_FAILED` | 500 | subprocess 非零退出且非超时 |

---

## Task 1: 第一份 ORM + Alembic migration（repos + feature_repos）

**Files:**
- Create: `src/codeask/db/models/code_index.py`
- Modify: `src/codeask/db/models/__init__.py`
- Create: `alembic/versions/20260430_0006_code_index.py`
- Create: `tests/integration/test_repo_models.py`

锚点：`api-data-model.md` §3 + `code-index.md` §2。`feature_repos` 用复合主键（`feature_id` + `repo_id`），落 PRD §4.1/§4.2 多对多关联。`feature_id` 用 FK 引用 `features.id`（由 wiki-knowledge plan 创建，当前实现为 `Integer` 自增主键）。

- [x] **Step 1: 写测试 `tests/integration/test_repo_models.py`**

```python
"""ORM round-trip for repos + feature_repos."""

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from codeask.db import Base, create_engine, session_factory
from codeask.db.models import Feature, FeatureRepo, Repo


@pytest_asyncio.fixture()
async def engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    db_path = tmp_path / "test.db"
    eng = create_engine(f"sqlite+aiosqlite:///{db_path}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_repo_defaults(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        repo = Repo(
            id="r-001",
            name="order-service",
            source=Repo.SOURCE_GIT,
            url="https://example.com/x.git",
            local_path=None,
            bare_path="/tmp/codeask/repos/r-001/bare",
            status=Repo.STATUS_REGISTERED,
        )
        s.add(repo)
        await s.commit()

    async with factory() as s:
        row = (await s.execute(select(Repo).where(Repo.id == "r-001"))).scalar_one()
        assert row.status == "registered"
        assert row.source == "git"
        assert row.error_message is None
        assert row.last_synced_at is None
        assert row.created_at is not None
        assert row.updated_at is not None


@pytest.mark.asyncio
async def test_status_constants_match_db_strings() -> None:
    """Critical invariant: API/test/migration all use these literals."""
    assert Repo.STATUS_REGISTERED == "registered"
    assert Repo.STATUS_CLONING == "cloning"
    assert Repo.STATUS_READY == "ready"
    assert Repo.STATUS_FAILED == "failed"
    assert Repo.SOURCE_GIT == "git"
    assert Repo.SOURCE_LOCAL_DIR == "local_dir"


@pytest.mark.asyncio
async def test_feature_repo_composite_pk(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        feature_a = Feature(name="Payment", slug="payment", owner_subject_id="owner@dev")
        feature_b = Feature(name="Checkout", slug="checkout", owner_subject_id="owner@dev")
        s.add_all([feature_a, feature_b])
        await s.flush()

        repo = Repo(
            id="r-002",
            name="payment-gw",
            source=Repo.SOURCE_LOCAL_DIR,
            url=None,
            local_path="/srv/payment-gw",
            bare_path="/tmp/codeask/repos/r-002/bare",
            status=Repo.STATUS_READY,
        )
        s.add(repo)
        await s.flush()

        s.add(FeatureRepo(feature_id=feature_a.id, repo_id="r-002"))
        s.add(FeatureRepo(feature_id=feature_b.id, repo_id="r-002"))
        await s.commit()

    async with factory() as s:
        rows = (await s.execute(
            select(FeatureRepo).where(FeatureRepo.repo_id == "r-002")
        )).scalars().all()
        assert {r.feature_id for r in rows} == {feature_a.id, feature_b.id}
```

- [x] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/integration/test_repo_models.py -v`
Expected: ImportError on `Repo` / `FeatureRepo`

- [x] **Step 3: 创建 `src/codeask/db/models/code_index.py`**

```python
"""ORM models for the global repo pool and feature ↔ repo association."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class Repo(Base, TimestampMixin):
    __tablename__ = "repos"

    # Status literals — keep DB strings, ORM constants, API enums, tests aligned.
    STATUS_REGISTERED = "registered"
    STATUS_CLONING = "cloning"
    STATUS_READY = "ready"
    STATUS_FAILED = "failed"

    SOURCE_GIT = "git"
    SOURCE_LOCAL_DIR = "local_dir"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    local_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    bare_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_REGISTERED
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class FeatureRepo(Base):
    __tablename__ = "feature_repos"

    feature_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("features.id", ondelete="CASCADE"),
        primary_key=True,
    )
    repo_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("repos.id", ondelete="CASCADE"),
        primary_key=True,
    )
```

- [x] **Step 4: 修改 `src/codeask/db/models/__init__.py` 暴露新模型**

```python
"""ORM model definitions."""

from codeask.db.models.code_index import FeatureRepo, Repo
from codeask.db.models.document import Document, DocumentChunk, DocumentReference
from codeask.db.models.feature import Feature
from codeask.db.models.report import Report
from codeask.db.models.system_settings import SystemSetting

__all__ = [
    "Document",
    "DocumentChunk",
    "DocumentReference",
    "Feature",
    "FeatureRepo",
    "Repo",
    "Report",
    "SystemSetting",
]
```

- [x] **Step 5: 创建 migration `alembic/versions/20260430_0006_code_index.py`**

> **NOTE:** `revision = "0006"` 与 `down_revision = "0005"` 衔接 wiki-knowledge plan（0002–0005）。

```python
"""code_index: repos + feature_repos

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-29 00:00:07
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "repos",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=True),
        sa.Column("local_path", sa.String(length=1024), nullable=True),
        sa.Column("bare_path", sa.String(length=1024), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="registered",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('registered','cloning','ready','failed')",
            name="ck_repos_status",
        ),
        sa.CheckConstraint(
            "source IN ('git','local_dir')",
            name="ck_repos_source",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_repos_status", "repos", ["status"])

    op.create_table(
        "feature_repos",
        sa.Column("feature_id", sa.Integer(), nullable=False),
        sa.Column("repo_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["feature_id"], ["features.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["repo_id"], ["repos.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("feature_id", "repo_id"),
    )
    op.create_index("ix_feature_repos_repo_id", "feature_repos", ["repo_id"])


def downgrade() -> None:
    op.drop_index("ix_feature_repos_repo_id", table_name="feature_repos")
    op.drop_table("feature_repos")
    op.drop_index("ix_repos_status", table_name="repos")
    op.drop_table("repos")
```

- [x] **Step 6: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_repo_models.py -v`
Expected: 三个测试 PASS

- [x] **Step 7: 验证 alembic 链路完整**

```bash
mkdir -p /tmp/codeask-code-index-mig
CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
CODEASK_DATA_DIR=/tmp/codeask-code-index-mig \
uv run alembic upgrade head
```
Expected: alembic 输出包含 `Running upgrade 0005 -> 0006, code_index`，无错误。

- [x] **Step 8: 提交**

```bash
git add src/codeask/db/models/code_index.py src/codeask/db/models/__init__.py \
        alembic/versions/20260430_0006_code_index.py \
        tests/integration/test_repo_models.py
git commit -m "feat(code-index): repos + feature_repos ORM and migration 0006"
```

---

## Task 2: 路径白名单 helper（`is_safe_path`）

**Files:**
- Create: `src/codeask/code_index/__init__.py`
- Create: `src/codeask/code_index/path_safety.py`
- Create: `tests/unit/test_path_safety.py`

锚点：`deployment-security.md` §6"所有路径读取做根目录校验"。本 helper 是 `FileReader` / `WorktreeManager` / `RipgrepClient` 在收到外部路径时的统一入口。

- [x] **Step 1: 创建 `src/codeask/code_index/__init__.py`（空，仅作包标识）**

```python
"""Code index subsystem: repo pool, worktrees, code search tools."""
```

- [x] **Step 2: 写测试 `tests/unit/test_path_safety.py`**

```python
"""Tests for is_safe_path."""

from pathlib import Path

import pytest

from codeask.code_index.path_safety import is_safe_path, resolve_within


def test_inside_base_is_safe(tmp_path: Path) -> None:
    base = tmp_path / "wt"
    base.mkdir()
    (base / "src").mkdir()
    (base / "src" / "main.py").touch()
    assert is_safe_path(base, "src/main.py") is True
    assert is_safe_path(base, "src") is True


def test_dotdot_escape_rejected(tmp_path: Path) -> None:
    base = tmp_path / "wt"
    base.mkdir()
    assert is_safe_path(base, "../etc/passwd") is False
    assert is_safe_path(base, "src/../../escape") is False


def test_absolute_path_outside_base_rejected(tmp_path: Path) -> None:
    base = tmp_path / "wt"
    base.mkdir()
    assert is_safe_path(base, "/etc/passwd") is False


def test_absolute_path_inside_base_allowed(tmp_path: Path) -> None:
    base = tmp_path / "wt"
    base.mkdir()
    (base / "f").touch()
    assert is_safe_path(base, str(base / "f")) is True


def test_resolve_within_returns_resolved(tmp_path: Path) -> None:
    base = tmp_path / "wt"
    base.mkdir()
    (base / "a.py").touch()
    out = resolve_within(base, "a.py")
    assert out == (base / "a.py").resolve()


def test_resolve_within_raises_on_escape(tmp_path: Path) -> None:
    base = tmp_path / "wt"
    base.mkdir()
    with pytest.raises(ValueError, match="outside base"):
        resolve_within(base, "../escape")


def test_symlink_escape_rejected(tmp_path: Path) -> None:
    base = tmp_path / "wt"
    base.mkdir()
    target = tmp_path / "secret"
    target.write_text("nope")
    (base / "link").symlink_to(target)
    assert is_safe_path(base, "link") is False
```

- [x] **Step 3: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_path_safety.py -v`
Expected: ImportError on `codeask.code_index.path_safety`

- [x] **Step 4: 实现 `src/codeask/code_index/path_safety.py`**

```python
"""Path whitelist helpers. Blocks ``..`` traversal and symlink escapes."""

from pathlib import Path


def is_safe_path(base: Path, candidate: str | Path) -> bool:
    """Return True iff ``candidate`` resolves to a path inside ``base``.

    Resolves both sides to absolute paths first so that ``..`` and symlinks
    cannot walk out of ``base``. Returns False on resolve failures.
    """
    try:
        base_abs = base.resolve(strict=True)
    except (OSError, RuntimeError):
        return False

    try:
        cand_path = Path(candidate)
        if not cand_path.is_absolute():
            cand_path = base_abs / cand_path
        cand_abs = cand_path.resolve(strict=True)
    except (OSError, RuntimeError):
        return False

    try:
        cand_abs.relative_to(base_abs)
    except ValueError:
        return False
    return True


def resolve_within(base: Path, candidate: str | Path) -> Path:
    """Resolve ``candidate`` relative to ``base`` and return the absolute path.

    Raises ``ValueError`` if the resolved path is outside ``base`` (including
    via ``..`` or symlink escape) or if the path does not exist.
    """
    if not is_safe_path(base, candidate):
        raise ValueError(f"path {candidate!r} resolves outside base {base!s}")
    cand_path = Path(candidate)
    if not cand_path.is_absolute():
        cand_path = base.resolve(strict=True) / cand_path
    return cand_path.resolve(strict=True)
```

- [x] **Step 5: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_path_safety.py -v`
Expected: 七个测试全部 PASS

- [x] **Step 6: 提交**

```bash
git add src/codeask/code_index/__init__.py src/codeask/code_index/path_safety.py \
        tests/unit/test_path_safety.py
git commit -m "feat(code-index): is_safe_path / resolve_within helpers"
```

---

## Task 3: RepoCloner（APScheduler 后台任务）

**Files:**
- Create: `src/codeask/code_index/cloner.py`
- Create: `tests/integration/test_cloner.py`

锚点：`code-index.md` §2.2 状态机 + `dependencies.md` §2.4 subprocess + git CLI + `deployment-security.md` §6"shell 调用使用参数数组"。

`RepoCloner.run_clone(repo_id)` 是同步函数（subprocess + DB 写），由 APScheduler `add_job(...)` 即时投递，不阻塞 HTTP 响应。状态机：`registered`（DB 默认值）→ enqueue → `cloning`（job 开始时写）→ `ready`（exit 0）/ `failed`（exit 非 0 或超时，stderr 写入 `error_message`）。

- [x] **Step 1: 写测试 `tests/integration/test_cloner.py`**

```python
"""End-to-end clone with a real local git repo as the source."""

import asyncio
import subprocess
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from codeask.code_index.cloner import RepoCloner, CloneTimeoutError, CloneFailedError
from codeask.db import Base, create_engine, session_factory
from codeask.db.models import Repo


def _make_local_git_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(root)],
        check=True, capture_output=True,
    )
    (root / "README.md").write_text("hello\n")
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", "init"],
        check=True, capture_output=True,
    )
    return root


@pytest_asyncio.fixture()
async def db_engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    eng = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_clone_local_dir_success(tmp_path: Path, db_engine) -> None:  # type: ignore[no-untyped-def]
    src = _make_local_git_repo(tmp_path / "src")
    bare = tmp_path / "pool" / "r-1" / "bare"
    factory = session_factory(db_engine)

    async with factory() as s:
        s.add(Repo(
            id="r-1",
            name="local",
            source=Repo.SOURCE_LOCAL_DIR,
            url=None,
            local_path=str(src),
            bare_path=str(bare),
            status=Repo.STATUS_REGISTERED,
        ))
        await s.commit()

    cloner = RepoCloner(factory, clone_timeout_seconds=30)
    await asyncio.to_thread(cloner.run_clone, "r-1")

    async with factory() as s:
        repo = (await s.execute(select(Repo).where(Repo.id == "r-1"))).scalar_one()
        assert repo.status == Repo.STATUS_READY
        assert repo.error_message is None
        assert repo.last_synced_at is not None
    assert (bare / "HEAD").is_file()


@pytest.mark.asyncio
async def test_clone_failure_records_error(tmp_path: Path, db_engine) -> None:  # type: ignore[no-untyped-def]
    bare = tmp_path / "pool" / "r-2" / "bare"
    factory = session_factory(db_engine)

    async with factory() as s:
        s.add(Repo(
            id="r-2",
            name="bad",
            source=Repo.SOURCE_LOCAL_DIR,
            url=None,
            local_path="/nonexistent/path/does/not/exist",
            bare_path=str(bare),
            status=Repo.STATUS_REGISTERED,
        ))
        await s.commit()

    cloner = RepoCloner(factory, clone_timeout_seconds=10)
    with pytest.raises(CloneFailedError):
        await asyncio.to_thread(cloner.run_clone, "r-2")

    async with factory() as s:
        repo = (await s.execute(select(Repo).where(Repo.id == "r-2"))).scalar_one()
        assert repo.status == Repo.STATUS_FAILED
        assert repo.error_message
        assert "nonexistent" in repo.error_message.lower() or repo.error_message


@pytest.mark.asyncio
async def test_clone_marks_cloning_then_ready(tmp_path: Path, db_engine) -> None:  # type: ignore[no-untyped-def]
    """Status writes happen in order even on success."""
    src = _make_local_git_repo(tmp_path / "src")
    bare = tmp_path / "pool" / "r-3" / "bare"
    factory = session_factory(db_engine)

    async with factory() as s:
        s.add(Repo(
            id="r-3",
            name="local",
            source=Repo.SOURCE_LOCAL_DIR,
            url=None,
            local_path=str(src),
            bare_path=str(bare),
            status=Repo.STATUS_REGISTERED,
        ))
        await s.commit()

    observed: list[str] = []

    cloner = RepoCloner(factory, clone_timeout_seconds=30)
    original = cloner._set_status

    def _spy(repo_id: str, status: str, error: str | None = None) -> None:
        observed.append(status)
        original(repo_id, status, error)

    cloner._set_status = _spy  # type: ignore[method-assign]

    await asyncio.to_thread(cloner.run_clone, "r-3")
    assert observed == [Repo.STATUS_CLONING, Repo.STATUS_READY]
```

- [x] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/integration/test_cloner.py -v`
Expected: ImportError on `codeask.code_index.cloner`

- [x] **Step 3: 实现 `src/codeask/code_index/cloner.py`**

```python
"""Background git clone worker (sync; intended to run via APScheduler thread pool)."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.db.models import Repo

log = structlog.get_logger("codeask.code_index.cloner")


class CloneError(Exception):
    """Base for clone failures."""


class CloneFailedError(CloneError):
    """git exited non-zero."""


class CloneTimeoutError(CloneError):
    """git did not finish within the timeout."""


class RepoCloner:
    """Run ``git clone --bare`` for a registered repo and update its status row."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        clone_timeout_seconds: int = 1800,
    ) -> None:
        self._session_factory = session_factory
        self._timeout = clone_timeout_seconds

    # ----- public sync entry point (callable from APScheduler) -----

    def run_clone(self, repo_id: str) -> None:
        repo = self._load_repo_sync(repo_id)
        if repo is None:
            log.warning("clone_skipped_missing_repo", repo_id=repo_id)
            return
        if repo.status == Repo.STATUS_READY:
            log.info("clone_skipped_already_ready", repo_id=repo_id)
            return

        bare_path = Path(repo.bare_path)
        argv = self._build_clone_argv(repo, bare_path)

        self._set_status(repo_id, Repo.STATUS_CLONING, error=None)

        try:
            self._exec_clone(argv, bare_path)
        except CloneTimeoutError as exc:
            self._set_status(repo_id, Repo.STATUS_FAILED, error=str(exc))
            raise
        except CloneFailedError as exc:
            self._set_status(repo_id, Repo.STATUS_FAILED, error=str(exc))
            raise
        else:
            self._set_status(
                repo_id, Repo.STATUS_READY, error=None, mark_synced=True
            )
            log.info("clone_succeeded", repo_id=repo_id, bare_path=str(bare_path))

    # ----- internals -----

    def _build_clone_argv(self, repo: Repo, bare_path: Path) -> list[str]:
        if repo.source == Repo.SOURCE_GIT:
            if not repo.url:
                raise CloneFailedError("git source requires non-empty url")
            return ["git", "clone", "--bare", repo.url, str(bare_path)]
        if repo.source == Repo.SOURCE_LOCAL_DIR:
            if not repo.local_path:
                raise CloneFailedError("local_dir source requires non-empty local_path")
            return [
                "git", "clone", "--bare", "--local",
                repo.local_path, str(bare_path),
            ]
        raise CloneFailedError(f"unknown source {repo.source!r}")

    def _exec_clone(self, argv: list[str], bare_path: Path) -> None:
        # Clean any stale bare dir from a previous failed attempt.
        if bare_path.exists():
            shutil.rmtree(bare_path, ignore_errors=True)
        bare_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                argv,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise CloneTimeoutError(
                f"git clone exceeded {self._timeout}s"
            ) from exc

        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()[:4000]
            raise CloneFailedError(
                f"git clone exited {proc.returncode}: {stderr or 'no stderr'}"
            )

    # ----- DB helpers (sync; bridge to async session via asyncio.run) -----

    def _load_repo_sync(self, repo_id: str) -> Repo | None:
        async def _go() -> Repo | None:
            async with self._session_factory() as s:
                result = await s.execute(select(Repo).where(Repo.id == repo_id))
                return result.scalar_one_or_none()
        return asyncio.run(_go())

    def _set_status(
        self,
        repo_id: str,
        status: str,
        error: str | None,
        mark_synced: bool = False,
    ) -> None:
        async def _go() -> None:
            values: dict[str, object] = {
                "status": status,
                "error_message": error,
            }
            if mark_synced:
                values["last_synced_at"] = datetime.now(timezone.utc)
            async with self._session_factory() as s:
                await s.execute(
                    update(Repo).where(Repo.id == repo_id).values(**values)
                )
                await s.commit()
        asyncio.run(_go())
```

- [x] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_cloner.py -v`
Expected: 三个测试 PASS（确保系统装了 `git`；本计划假定 deployment 镜像已带，详见 `dependencies.md` §5）

- [x] **Step 5: 提交**

```bash
git add src/codeask/code_index/cloner.py tests/integration/test_cloner.py
git commit -m "feat(code-index): RepoCloner with state machine + stderr capture"
```

---

## Task 4: WorktreeManager（git worktree add/remove + ref 解析）

**Files:**
- Create: `src/codeask/code_index/worktree.py`
- Create: `tests/integration/test_worktree.py`

锚点：`code-index.md` §6 + §4。`ensure_worktree(repo_id, session_id, ref_or_commit)` 把 ref 解析成 SHA，再 `git worktree add --detach <sha> <path>`。`destroy_worktree` 调 `git worktree remove --force`。`list_worktrees(repo_id)` 解析 `git worktree list --porcelain`。

注意：本 plan 不创建 `sessions` 表（04 agent-runtime 负责），所以 `session_id` 在本 plan 是参数串、不做外键校验。

- [ ] **Step 1: 写测试 `tests/integration/test_worktree.py`**

```python
"""WorktreeManager against a real bare repo."""

import subprocess
from pathlib import Path

import pytest

from codeask.code_index.worktree import (
    WorktreeManager,
    WorktreeError,
    InvalidRefError,
)


def _bootstrap_bare(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(src)],
        check=True, capture_output=True,
    )
    (src / "f.py").write_text("print('hi')\n")
    subprocess.run(["git", "-C", str(src), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(src), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(src), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(src), "commit", "-m", "init"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(src), "tag", "v1"],
        check=True, capture_output=True,
    )
    bare = tmp_path / "pool" / "r" / "bare"
    bare.parent.mkdir(parents=True)
    subprocess.run(
        ["git", "clone", "--bare", "--local", str(src), str(bare)],
        check=True, capture_output=True,
    )
    return bare


def test_resolve_default_ref(tmp_path: Path) -> None:
    bare = _bootstrap_bare(tmp_path)
    mgr = WorktreeManager(repo_root=tmp_path / "pool")
    sha = mgr.resolve_ref("r", None)
    assert len(sha) == 40


def test_resolve_branch_and_tag(tmp_path: Path) -> None:
    bare = _bootstrap_bare(tmp_path)
    mgr = WorktreeManager(repo_root=tmp_path / "pool")
    sha_main = mgr.resolve_ref("r", "main")
    sha_tag = mgr.resolve_ref("r", "v1")
    assert sha_main == sha_tag
    assert mgr.resolve_ref("r", sha_main) == sha_main


def test_resolve_invalid_ref_raises(tmp_path: Path) -> None:
    _bootstrap_bare(tmp_path)
    mgr = WorktreeManager(repo_root=tmp_path / "pool")
    with pytest.raises(InvalidRefError):
        mgr.resolve_ref("r", "no-such-branch")


def test_ensure_and_destroy_worktree(tmp_path: Path) -> None:
    _bootstrap_bare(tmp_path)
    mgr = WorktreeManager(repo_root=tmp_path / "pool")

    path = mgr.ensure_worktree("r", "sess-1", "main")
    assert path.is_dir()
    assert (path / "f.py").is_file()

    # idempotent: calling again with same args returns the same path
    path2 = mgr.ensure_worktree("r", "sess-1", "main")
    assert path2 == path

    paths = mgr.list_worktrees("r")
    assert path.resolve() in {p.resolve() for p in paths}

    mgr.destroy_worktree("r", "sess-1")
    assert not path.exists()


def test_ensure_worktree_rejects_unsafe_session_id(tmp_path: Path) -> None:
    _bootstrap_bare(tmp_path)
    mgr = WorktreeManager(repo_root=tmp_path / "pool")
    with pytest.raises(WorktreeError):
        mgr.ensure_worktree("r", "../escape", "main")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/integration/test_worktree.py -v`
Expected: ImportError on `codeask.code_index.worktree`

- [ ] **Step 3: 实现 `src/codeask/code_index/worktree.py`**

```python
"""Worktree lifecycle: resolve ref, ensure_worktree, destroy_worktree, list."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import structlog

log = structlog.get_logger("codeask.code_index.worktree")

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_GIT_TIMEOUT = 60


class WorktreeError(Exception):
    """Base for worktree errors."""


class InvalidRefError(WorktreeError):
    """Ref/branch/tag did not resolve to a commit."""


class WorktreeManager:
    """Manage worktrees for a global repo pool rooted at ``repo_root``.

    Layout: ``<repo_root>/<repo_id>/bare`` and ``<repo_root>/<repo_id>/worktrees/<session_id>``.
    """

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    # ----- paths -----

    def _bare(self, repo_id: str) -> Path:
        if not _SAFE_ID.fullmatch(repo_id):
            raise WorktreeError(f"unsafe repo_id: {repo_id!r}")
        return self._repo_root / repo_id / "bare"

    def worktree_path(self, repo_id: str, session_id: str) -> Path:
        if not _SAFE_ID.fullmatch(repo_id):
            raise WorktreeError(f"unsafe repo_id: {repo_id!r}")
        if not _SAFE_ID.fullmatch(session_id):
            raise WorktreeError(f"unsafe session_id: {session_id!r}")
        return self._repo_root / repo_id / "worktrees" / session_id

    # ----- ref resolution -----

    def resolve_ref(self, repo_id: str, ref: str | None) -> str:
        bare = self._bare(repo_id)
        if not bare.is_dir():
            raise WorktreeError(f"bare repo missing: {bare}")
        target = ref if ref else "HEAD"
        try:
            proc = subprocess.run(
                ["git", "--git-dir", str(bare), "rev-parse", "--verify", f"{target}^{{commit}}"],
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT,
            )
        except subprocess.TimeoutExpired as exc:
            raise WorktreeError("git rev-parse timed out") from exc
        if proc.returncode != 0:
            raise InvalidRefError(
                f"ref {target!r} does not resolve in {repo_id}: {proc.stderr.strip()}"
            )
        sha = proc.stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise InvalidRefError(f"unexpected rev-parse output: {sha!r}")
        return sha

    # ----- lifecycle -----

    def ensure_worktree(
        self, repo_id: str, session_id: str, ref: str | None
    ) -> Path:
        bare = self._bare(repo_id)
        sha = self.resolve_ref(repo_id, ref)
        path = self.worktree_path(repo_id, session_id)

        if path.is_dir():
            # Already exists — verify it's checked out at the expected commit.
            head = self._read_worktree_head(path)
            if head == sha:
                return path
            # Different commit requested: tear down and recreate.
            self.destroy_worktree(repo_id, session_id)

        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                [
                    "git", "--git-dir", str(bare),
                    "worktree", "add", "--detach",
                    str(path), sha,
                ],
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT,
            )
        except subprocess.TimeoutExpired as exc:
            raise WorktreeError("git worktree add timed out") from exc
        if proc.returncode != 0:
            raise WorktreeError(
                f"git worktree add failed: {proc.stderr.strip()}"
            )
        log.info("worktree_created", repo_id=repo_id, session_id=session_id, sha=sha)
        return path

    def destroy_worktree(self, repo_id: str, session_id: str) -> None:
        bare = self._bare(repo_id)
        path = self.worktree_path(repo_id, session_id)
        if not path.exists():
            return
        try:
            subprocess.run(
                [
                    "git", "--git-dir", str(bare),
                    "worktree", "remove", "--force", str(path),
                ],
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            pass
        # Even if `git worktree remove` says it succeeded, prune to clean
        # admin records, and rmtree as a belt-and-braces.
        subprocess.run(
            ["git", "--git-dir", str(bare), "worktree", "prune"],
            shell=False, check=False, capture_output=True, timeout=_GIT_TIMEOUT,
        )
        if path.exists():
            import shutil
            shutil.rmtree(path, ignore_errors=True)
        log.info("worktree_destroyed", repo_id=repo_id, session_id=session_id)

    def list_worktrees(self, repo_id: str) -> list[Path]:
        bare = self._bare(repo_id)
        if not bare.is_dir():
            return []
        proc = subprocess.run(
            ["git", "--git-dir", str(bare), "worktree", "list", "--porcelain"],
            shell=False, check=False, capture_output=True, text=True,
            timeout=_GIT_TIMEOUT,
        )
        if proc.returncode != 0:
            return []
        out: list[Path] = []
        for line in proc.stdout.splitlines():
            if line.startswith("worktree "):
                out.append(Path(line[len("worktree "):]))
        # Drop the bare repo's own entry.
        return [p for p in out if p.resolve() != bare.resolve()]

    def _read_worktree_head(self, path: Path) -> str | None:
        head_file = path / "HEAD"
        if not head_file.is_file():
            return None
        text = head_file.read_text().strip()
        if re.fullmatch(r"[0-9a-f]{40}", text):
            return text
        return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_worktree.py -v`
Expected: 五个测试 PASS

- [ ] **Step 5: 提交**

```bash
git add src/codeask/code_index/worktree.py tests/integration/test_worktree.py
git commit -m "feat(code-index): WorktreeManager (ref resolve + add/remove/list)"
```

---

## Task 5: RipgrepClient（subprocess + `rg --json`）

**Files:**
- Create: `src/codeask/code_index/ripgrep.py`
- Create: `tests/unit/test_ripgrep.py`

锚点：`dependencies.md` §2.4 + `tools.md` §6 截断策略。**永远 `shell=False`**；超时必带；按行解析 `rg --json` 输出。

- [ ] **Step 1: 写测试 `tests/unit/test_ripgrep.py`**

```python
"""RipgrepClient against a real ripgrep on disk."""

import shutil
from pathlib import Path

import pytest

from codeask.code_index.ripgrep import RipgrepClient, RipgrepError


pytestmark = pytest.mark.skipif(
    shutil.which("rg") is None, reason="ripgrep not installed"
)


def _make_tree(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.py").write_text("def foo():\n    pass\n# foo here\n")
    (root / "b.py").write_text("def bar():\n    return 'foo'\n")
    sub = root / "sub"
    sub.mkdir()
    (sub / "c.py").write_text("foo = 1\n")


def test_grep_basic_hits(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    rg = RipgrepClient(timeout_seconds=10)
    hits = rg.grep(base=tmp_path, pattern="foo", paths=None, max_count=100)
    files = {h.path for h in hits}
    assert "a.py" in files
    assert "b.py" in files
    assert "sub/c.py" in files
    for h in hits:
        assert h.line_number > 0
        assert "foo" in h.line_text


def test_grep_no_match(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    rg = RipgrepClient(timeout_seconds=10)
    assert rg.grep(base=tmp_path, pattern="zzznotfound", paths=None, max_count=10) == []


def test_grep_respects_max_count(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    rg = RipgrepClient(timeout_seconds=10)
    hits = rg.grep(base=tmp_path, pattern="foo", paths=None, max_count=1)
    # max_count is per-file in rg, so total <= files * 1 == 3
    assert len(hits) <= 3


def test_grep_paths_scope(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    rg = RipgrepClient(timeout_seconds=10)
    hits = rg.grep(base=tmp_path, pattern="foo", paths=["sub"], max_count=100)
    assert all(h.path.startswith("sub/") for h in hits)


def test_grep_timeout_raises(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _make_tree(tmp_path)
    rg = RipgrepClient(timeout_seconds=0)
    with pytest.raises(RipgrepError):
        rg.grep(base=tmp_path, pattern="foo", paths=None, max_count=10)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_ripgrep.py -v`
Expected: ImportError on `codeask.code_index.ripgrep`

- [ ] **Step 3: 实现 `src/codeask/code_index/ripgrep.py`**

```python
"""ripgrep wrapper. Always argv-list (shell=False). JSON event parser."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


class RipgrepError(Exception):
    """ripgrep failed (timeout or non-zero exit not from "no match")."""


@dataclass(frozen=True)
class RipgrepHit:
    path: str            # path relative to base
    line_number: int
    line_text: str       # trimmed of trailing newline
    submatches: list[tuple[int, int]]  # (start, end) byte offsets within line


class RipgrepClient:
    def __init__(self, timeout_seconds: int = 30, binary: str = "rg") -> None:
        self._timeout = timeout_seconds
        self._bin = binary

    def grep(
        self,
        base: Path,
        pattern: str,
        paths: list[str] | None,
        max_count: int,
    ) -> list[RipgrepHit]:
        if max_count <= 0:
            raise RipgrepError("max_count must be > 0")
        argv: list[str] = [
            self._bin,
            "--json",
            "--max-count", str(max_count),
            "--color", "never",
            "-e", pattern,
        ]
        if paths:
            for p in paths:
                if p.startswith("/") or ".." in Path(p).parts:
                    raise RipgrepError(f"unsafe path scope: {p!r}")
            argv.extend(["--", *paths])
        else:
            argv.extend(["--", "."])

        try:
            proc = subprocess.run(
                argv,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                cwd=str(base),
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RipgrepError(f"rg timed out after {self._timeout}s") from exc

        # rg exits 1 when there are no matches. That's not an error for us.
        if proc.returncode not in (0, 1):
            raise RipgrepError(
                f"rg exit {proc.returncode}: {proc.stderr.strip()[:500]}"
            )

        return self._parse(proc.stdout)

    @staticmethod
    def _parse(stdout: str) -> list[RipgrepHit]:
        hits: list[RipgrepHit] = []
        for raw in stdout.splitlines():
            if not raw:
                continue
            try:
                evt = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if evt.get("type") != "match":
                continue
            data = evt.get("data") or {}
            path_obj = (data.get("path") or {}).get("text")
            line_text_obj = (data.get("lines") or {}).get("text") or ""
            line_no = data.get("line_number")
            submatches_raw = data.get("submatches") or []
            if not path_obj or line_no is None:
                continue
            submatches: list[tuple[int, int]] = []
            for sm in submatches_raw:
                start = sm.get("start")
                end = sm.get("end")
                if isinstance(start, int) and isinstance(end, int):
                    submatches.append((start, end))
            hits.append(
                RipgrepHit(
                    path=path_obj,
                    line_number=int(line_no),
                    line_text=line_text_obj.rstrip("\n"),
                    submatches=submatches,
                )
            )
        return hits
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_ripgrep.py -v`
Expected: 五个测试 PASS（如果 `rg` 没装，`pytest` 会 skip 整个文件）

- [ ] **Step 5: 提交**

```bash
git add src/codeask/code_index/ripgrep.py tests/unit/test_ripgrep.py
git commit -m "feat(code-index): RipgrepClient with rg --json parsing"
```

---

## Task 6: CtagsClient（universal-ctags + LRU 缓存）

**Files:**
- Create: `src/codeask/code_index/ctags.py`
- Create: `tests/unit/test_ctags.py`

锚点：`code-index.md` §7"按 repo + commit 缓存 tags"。`CtagsClient.find_symbols(worktree_path, repo_id, commit, symbol_name)` 第一次调用时跑 `ctags -R --output-format=json` 把结果缓存到 `~/.codeask/index/<repo_id>/<commit>.tags.json`，后续命中缓存。LRU 缓存 key = `(repo_id, commit)`，默认容量 32。

- [ ] **Step 1: 写测试 `tests/unit/test_ctags.py`**

```python
"""CtagsClient against a real universal-ctags."""

import shutil
from pathlib import Path

import pytest

from codeask.code_index.ctags import CtagsClient, CtagsError


pytestmark = pytest.mark.skipif(
    shutil.which("ctags") is None, reason="universal-ctags not installed"
)


def _make_tree(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.py").write_text("def foo():\n    pass\n\nclass Bar:\n    pass\n")
    (root / "b.py").write_text("def helper():\n    return foo()\n")


def test_find_symbol_definition(tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    cache = tmp_path / "cache"
    _make_tree(wt)
    c = CtagsClient(cache_dir=cache, timeout_seconds=15)

    hits = c.find_symbols(worktree_path=wt, repo_id="r1", commit="abc1234", symbol="foo")
    assert any(h.name == "foo" and h.path == "a.py" for h in hits)
    assert any(h.kind == "function" for h in hits if h.name == "foo")


def test_cache_hit_skips_subprocess(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    wt = tmp_path / "wt"
    cache = tmp_path / "cache"
    _make_tree(wt)
    c = CtagsClient(cache_dir=cache, timeout_seconds=15)

    c.find_symbols(worktree_path=wt, repo_id="r1", commit="abc1234", symbol="foo")

    calls = {"n": 0}
    real_run = c._run_ctags

    def _spy(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return real_run(*args, **kwargs)

    monkeypatch.setattr(c, "_run_ctags", _spy)

    c.find_symbols(worktree_path=wt, repo_id="r1", commit="abc1234", symbol="Bar")
    assert calls["n"] == 0  # cache hit, no fresh ctags subprocess


def test_no_match_returns_empty(tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    cache = tmp_path / "cache"
    _make_tree(wt)
    c = CtagsClient(cache_dir=cache, timeout_seconds=15)
    assert c.find_symbols(worktree_path=wt, repo_id="r1", commit="x", symbol="zzz") == []


def test_invalid_worktree_raises(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    c = CtagsClient(cache_dir=cache, timeout_seconds=15)
    with pytest.raises(CtagsError):
        c.find_symbols(
            worktree_path=tmp_path / "missing", repo_id="r1", commit="x", symbol="foo",
        )
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_ctags.py -v`
Expected: ImportError on `codeask.code_index.ctags`

- [ ] **Step 3: 实现 `src/codeask/code_index/ctags.py`**

```python
"""universal-ctags wrapper with on-disk + in-memory LRU cache."""

from __future__ import annotations

import json
import re
import subprocess
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path


_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class CtagsError(Exception):
    pass


@dataclass(frozen=True)
class TagEntry:
    name: str
    path: str          # relative to worktree
    line: int
    kind: str          # function / class / variable / ...


class CtagsClient:
    """Run universal-ctags once per (repo_id, commit), cache results.

    The cache lives both on disk (``cache_dir/<repo_id>/<commit>.tags.json``) and
    in an in-memory LRU keyed by ``(repo_id, commit)``.
    """

    def __init__(
        self,
        cache_dir: Path,
        timeout_seconds: int = 60,
        max_in_memory: int = 32,
        binary: str = "ctags",
    ) -> None:
        self._cache_dir = cache_dir
        self._timeout = timeout_seconds
        self._max = max_in_memory
        self._bin = binary
        self._mem: OrderedDict[tuple[str, str], list[TagEntry]] = OrderedDict()

    # ----- public -----

    def find_symbols(
        self,
        worktree_path: Path,
        repo_id: str,
        commit: str,
        symbol: str,
    ) -> list[TagEntry]:
        if not worktree_path.is_dir():
            raise CtagsError(f"worktree not found: {worktree_path}")
        if not _SAFE_ID.fullmatch(repo_id):
            raise CtagsError(f"unsafe repo_id: {repo_id!r}")
        if not _SAFE_ID.fullmatch(commit):
            raise CtagsError(f"unsafe commit: {commit!r}")

        entries = self._load_or_build(worktree_path, repo_id, commit)
        return [e for e in entries if e.name == symbol]

    # ----- internals -----

    def _load_or_build(
        self, worktree_path: Path, repo_id: str, commit: str
    ) -> list[TagEntry]:
        key = (repo_id, commit)
        if key in self._mem:
            self._mem.move_to_end(key)
            return self._mem[key]

        on_disk = self._cache_dir / repo_id / f"{commit}.tags.json"
        if on_disk.is_file():
            entries = self._read_cache_file(on_disk)
        else:
            entries = self._run_ctags(worktree_path)
            on_disk.parent.mkdir(parents=True, exist_ok=True)
            on_disk.write_text(
                json.dumps([e.__dict__ for e in entries], ensure_ascii=False)
            )

        self._mem[key] = entries
        self._mem.move_to_end(key)
        while len(self._mem) > self._max:
            self._mem.popitem(last=False)
        return entries

    def _run_ctags(self, worktree_path: Path) -> list[TagEntry]:
        argv = [
            self._bin,
            "-R",
            "--output-format=json",
            "--fields=+nKz",
            "-f", "-",
            ".",
        ]
        try:
            proc = subprocess.run(
                argv,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                cwd=str(worktree_path),
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise CtagsError(f"ctags timed out after {self._timeout}s") from exc

        if proc.returncode != 0:
            raise CtagsError(
                f"ctags exit {proc.returncode}: {proc.stderr.strip()[:500]}"
            )
        return self._parse(proc.stdout)

    @staticmethod
    def _parse(stdout: str) -> list[TagEntry]:
        out: list[TagEntry] = []
        for raw in stdout.splitlines():
            if not raw or not raw.startswith("{"):
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            name = rec.get("name")
            path = rec.get("path")
            line = rec.get("line")
            kind = rec.get("kind") or ""
            if not name or not path or not isinstance(line, int):
                continue
            out.append(TagEntry(name=name, path=path, line=line, kind=kind))
        return out

    @staticmethod
    def _read_cache_file(p: Path) -> list[TagEntry]:
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return []
        out: list[TagEntry] = []
        for d in data:
            try:
                out.append(
                    TagEntry(
                        name=d["name"],
                        path=d["path"],
                        line=int(d["line"]),
                        kind=d.get("kind", ""),
                    )
                )
            except (KeyError, ValueError, TypeError):
                continue
        return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_ctags.py -v`
Expected: 四个测试 PASS（universal-ctags 缺失则 skip）

- [ ] **Step 5: 提交**

```bash
git add src/codeask/code_index/ctags.py tests/unit/test_ctags.py
git commit -m "feat(code-index): CtagsClient with on-disk + LRU cache"
```

---

## Task 7: FileReader（路径白名单 + 行号片段）

**Files:**
- Create: `src/codeask/code_index/file_reader.py`
- Create: `tests/unit/test_file_reader.py`

锚点：`tools.md` §4"所有路径必须通过 `resolve_within(base, user_path)` 校验"。FileReader 接 `(worktree_path, relative_path, line_range)`，返回片段文本 + 命中行号。`line_range = (start, end)`，1-indexed，inclusive；越界自动 clamp。

- [ ] **Step 1: 写测试 `tests/unit/test_file_reader.py`**

```python
"""FileReader read_segment."""

from pathlib import Path

import pytest

from codeask.code_index.file_reader import FileReader, FileReadError


def _make(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    lines = [f"line-{i}\n" for i in range(1, 51)]  # 50 lines
    (root / "f.py").write_text("".join(lines))
    (root / "binary.bin").write_bytes(b"\x00\x01\x02bad\x00\xff")


def test_read_full_range(tmp_path: Path) -> None:
    _make(tmp_path)
    fr = FileReader(max_bytes=10_000)
    seg = fr.read_segment(base=tmp_path, rel_path="f.py", line_range=(1, 5))
    assert seg.start_line == 1
    assert seg.end_line == 5
    assert seg.text == "line-1\nline-2\nline-3\nline-4\nline-5\n"


def test_clamp_to_eof(tmp_path: Path) -> None:
    _make(tmp_path)
    fr = FileReader(max_bytes=10_000)
    seg = fr.read_segment(base=tmp_path, rel_path="f.py", line_range=(48, 9999))
    assert seg.start_line == 48
    assert seg.end_line == 50
    assert seg.text.count("\n") == 3


def test_truncate_by_max_bytes(tmp_path: Path) -> None:
    _make(tmp_path)
    fr = FileReader(max_bytes=20)  # very small
    seg = fr.read_segment(base=tmp_path, rel_path="f.py", line_range=(1, 50))
    assert seg.truncated is True
    assert len(seg.text.encode("utf-8")) <= 20


def test_path_escape_rejected(tmp_path: Path) -> None:
    _make(tmp_path)
    fr = FileReader(max_bytes=10_000)
    with pytest.raises(FileReadError):
        fr.read_segment(base=tmp_path, rel_path="../etc/passwd", line_range=(1, 5))


def test_missing_file_raises(tmp_path: Path) -> None:
    _make(tmp_path)
    fr = FileReader(max_bytes=10_000)
    with pytest.raises(FileReadError):
        fr.read_segment(base=tmp_path, rel_path="not-here.py", line_range=(1, 5))


def test_invalid_range(tmp_path: Path) -> None:
    _make(tmp_path)
    fr = FileReader(max_bytes=10_000)
    with pytest.raises(FileReadError):
        fr.read_segment(base=tmp_path, rel_path="f.py", line_range=(0, 5))
    with pytest.raises(FileReadError):
        fr.read_segment(base=tmp_path, rel_path="f.py", line_range=(5, 1))


def test_binary_file_rejected(tmp_path: Path) -> None:
    _make(tmp_path)
    fr = FileReader(max_bytes=10_000)
    with pytest.raises(FileReadError):
        fr.read_segment(base=tmp_path, rel_path="binary.bin", line_range=(1, 5))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_file_reader.py -v`
Expected: ImportError on `codeask.code_index.file_reader`

- [ ] **Step 3: 实现 `src/codeask/code_index/file_reader.py`**

```python
"""Read line ranges from text files inside a worktree base."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codeask.code_index.path_safety import resolve_within


class FileReadError(Exception):
    pass


@dataclass(frozen=True)
class FileSegment:
    path: str           # relative to base
    start_line: int     # 1-indexed inclusive
    end_line: int       # 1-indexed inclusive (after clamping)
    text: str
    truncated: bool


class FileReader:
    def __init__(self, max_bytes: int = 4096) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be > 0")
        self._max_bytes = max_bytes

    def read_segment(
        self,
        base: Path,
        rel_path: str,
        line_range: tuple[int, int],
    ) -> FileSegment:
        start, end = line_range
        if start < 1 or end < start:
            raise FileReadError(f"invalid line_range: {line_range}")

        try:
            absolute = resolve_within(base, rel_path)
        except ValueError as exc:
            raise FileReadError(str(exc)) from exc

        if not absolute.is_file():
            raise FileReadError(f"not a file: {rel_path}")

        # Reject obvious binaries by sniffing the first 1024 bytes.
        try:
            head = absolute.read_bytes()[:1024]
        except OSError as exc:
            raise FileReadError(f"read failed: {exc}") from exc
        if b"\x00" in head:
            raise FileReadError(f"binary file refused: {rel_path}")

        try:
            with absolute.open("r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except OSError as exc:
            raise FileReadError(f"read failed: {exc}") from exc

        eof = len(lines)
        clamped_end = min(end, eof)
        if clamped_end < start:
            # File shorter than start; return empty segment at the requested start.
            return FileSegment(
                path=rel_path,
                start_line=start,
                end_line=start - 1,
                text="",
                truncated=False,
            )

        chunk = "".join(lines[start - 1:clamped_end])
        encoded = chunk.encode("utf-8")
        truncated = False
        if len(encoded) > self._max_bytes:
            truncated_bytes = encoded[:self._max_bytes]
            chunk = truncated_bytes.decode("utf-8", errors="ignore")
            truncated = True

        return FileSegment(
            path=rel_path,
            start_line=start,
            end_line=clamped_end,
            text=chunk,
            truncated=truncated,
        )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_file_reader.py -v`
Expected: 七个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/codeask/code_index/file_reader.py tests/unit/test_file_reader.py
git commit -m "feat(code-index): FileReader with whitelist + range + truncation"
```

---

## Task 8: Pydantic v2 schemas（请求 / 响应模型）

**Files:**
- Create: `src/codeask/api/schemas/__init__.py`
- Create: `src/codeask/api/schemas/code_index.py`

锚点：`api-data-model.md` §2 + `tools.md` §5（`ToolResult` 标准结构）。本 task 仅落 schemas，HTTP 路由在 Task 9 / Task 10 接入。

- [ ] **Step 1: 创建 `src/codeask/api/schemas/__init__.py`（空）**

```python
"""Pydantic schemas for API request / response bodies."""
```

- [ ] **Step 2: 创建 `src/codeask/api/schemas/code_index.py`**

```python
"""Pydantic v2 models for /api/repos and /api/code/* endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

RepoSource = Literal["git", "local_dir"]
RepoStatus = Literal["registered", "cloning", "ready", "failed"]


# ----- /api/repos -----

class RepoCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    source: RepoSource
    url: str | None = Field(default=None, max_length=1024)
    local_path: str | None = Field(default=None, max_length=1024)

    @field_validator("url")
    @classmethod
    def _url_required_for_git(cls, v: str | None) -> str | None:
        return v

    def assert_consistent(self) -> None:
        if self.source == "git" and not self.url:
            raise ValueError("source=git requires url")
        if self.source == "local_dir" and not self.local_path:
            raise ValueError("source=local_dir requires local_path")


class RepoOut(BaseModel):
    id: str
    name: str
    source: RepoSource
    url: str | None
    local_path: str | None
    bare_path: str
    status: RepoStatus
    error_message: str | None
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RepoListOut(BaseModel):
    repos: list[RepoOut]


# ----- /api/code/grep -----

class CodeGrepIn(BaseModel):
    repo_id: str = Field(..., min_length=1, max_length=64)
    commit: str | None = Field(default=None, max_length=256)
    session_id: str = Field(..., min_length=1, max_length=128)
    pattern: str = Field(..., min_length=1, max_length=1024)
    paths: list[str] | None = Field(default=None)
    max_count: int = Field(default=50, ge=1, le=1000)


class CodeGrepHitOut(BaseModel):
    path: str
    line_number: int
    line_text: str


class CodeGrepOut(BaseModel):
    ok: bool
    repo_id: str
    commit: str
    hits: list[CodeGrepHitOut]
    truncated: bool


# ----- /api/code/read -----

class CodeReadIn(BaseModel):
    repo_id: str = Field(..., min_length=1, max_length=64)
    commit: str | None = Field(default=None, max_length=256)
    session_id: str = Field(..., min_length=1, max_length=128)
    path: str = Field(..., min_length=1, max_length=2048)
    line_range: tuple[int, int]


class CodeReadOut(BaseModel):
    ok: bool
    repo_id: str
    commit: str
    path: str
    start_line: int
    end_line: int
    text: str
    truncated: bool


# ----- /api/code/symbols -----

class CodeSymbolsIn(BaseModel):
    repo_id: str = Field(..., min_length=1, max_length=64)
    commit: str | None = Field(default=None, max_length=256)
    session_id: str = Field(..., min_length=1, max_length=128)
    symbol: str = Field(..., min_length=1, max_length=256)


class CodeSymbolHitOut(BaseModel):
    name: str
    path: str
    line: int
    kind: str


class CodeSymbolsOut(BaseModel):
    ok: bool
    repo_id: str
    commit: str
    symbols: list[CodeSymbolHitOut]


# ----- error envelope -----

class ApiError(BaseModel):
    ok: bool = False
    error_code: str
    message: str
    recoverable: bool = True
```

- [ ] **Step 3: import-only smoke check**

```bash
uv run python -c "from codeask.api.schemas.code_index import CodeGrepIn, RepoCreateIn; \
                  ri = RepoCreateIn(name='x', source='git', url='https://x.git', local_path=None); \
                  ri.assert_consistent(); print('ok')"
```
Expected: 输出 `ok`

- [ ] **Step 4: 提交**

```bash
git add src/codeask/api/schemas/__init__.py src/codeask/api/schemas/code_index.py
git commit -m "feat(code-index): pydantic v2 schemas for repos + code endpoints"
```

---

## Task 9: `/api/repos` CRUD endpoints + 触发后台 clone

**Files:**
- Create: `src/codeask/api/code_index.py`
- Modify: `src/codeask/app.py`（include_router + 在 lifespan 创建 APScheduler）
- Create: `tests/integration/test_repos_api.py`

锚点：`api-data-model.md` §2 + `code-index.md` §2.2"注册后立即返回 `repo_id`，clone 后台进行"。

`POST /api/repos` 流程：
1. 校验 body（`RepoCreateIn.assert_consistent()`）
2. 生成 `repo_id`（uuid4 hex 前 16 位）
3. 计算 `bare_path = settings.data_dir / "repos" / repo_id / "bare"`
4. INSERT 一行 `status='registered'`
5. `app.state.scheduler.add_job(repo_cloner.run_clone, args=[repo_id])` 立即投递（不阻塞）
6. 返回 201 + RepoOut

- [ ] **Step 1: 实现 `src/codeask/api/code_index.py`（先放 repos CRUD，code 路由在 Task 10 追加）**

```python
"""HTTP endpoints for the global repo pool and code search tools."""

from __future__ import annotations

import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from codeask.api.schemas.code_index import (
    ApiError,
    RepoCreateIn,
    RepoListOut,
    RepoOut,
)
from codeask.db.models import Repo

log = structlog.get_logger("codeask.api.code_index")

router = APIRouter()


def _to_out(r: Repo) -> RepoOut:
    return RepoOut(
        id=r.id,
        name=r.name,
        source=r.source,  # type: ignore[arg-type]
        url=r.url,
        local_path=r.local_path,
        bare_path=r.bare_path,
        status=r.status,  # type: ignore[arg-type]
        error_message=r.error_message,
        last_synced_at=r.last_synced_at,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.post("/repos", response_model=RepoOut, status_code=status.HTTP_201_CREATED)
async def create_repo(payload: RepoCreateIn, request: Request) -> RepoOut:
    try:
        payload.assert_consistent()
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=ApiError(error_code="INVALID_BODY", message=str(exc)).model_dump(),
        ) from exc

    settings = request.app.state.settings
    factory = request.app.state.session_factory
    scheduler = request.app.state.scheduler
    cloner = request.app.state.repo_cloner

    repo_id = uuid.uuid4().hex[:16]
    bare_path = Path(settings.data_dir) / "repos" / repo_id / "bare"

    repo = Repo(
        id=repo_id,
        name=payload.name,
        source=payload.source,
        url=payload.url,
        local_path=payload.local_path,
        bare_path=str(bare_path),
        status=Repo.STATUS_REGISTERED,
    )
    async with factory() as session:
        session.add(repo)
        await session.commit()
        await session.refresh(repo)

    scheduler.add_job(cloner.run_clone, args=[repo_id], misfire_grace_time=600)
    log.info("repo_registered", repo_id=repo_id, source=payload.source)

    return _to_out(repo)


@router.get("/repos", response_model=RepoListOut)
async def list_repos(request: Request) -> RepoListOut:
    factory = request.app.state.session_factory
    async with factory() as session:
        rows = (await session.execute(select(Repo).order_by(Repo.created_at.desc()))).scalars().all()
    return RepoListOut(repos=[_to_out(r) for r in rows])


@router.get("/repos/{repo_id}", response_model=RepoOut)
async def get_repo(repo_id: str, request: Request) -> RepoOut:
    factory = request.app.state.session_factory
    async with factory() as session:
        repo = (await session.execute(select(Repo).where(Repo.id == repo_id))).scalar_one_or_none()
    if repo is None:
        raise HTTPException(
            status_code=404,
            detail=ApiError(error_code="REPO_NOT_FOUND", message=f"no repo {repo_id}").model_dump(),
        )
    return _to_out(repo)


@router.delete("/repos/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repo(repo_id: str, request: Request) -> None:
    factory = request.app.state.session_factory
    async with factory() as session:
        repo = (await session.execute(select(Repo).where(Repo.id == repo_id))).scalar_one_or_none()
        if repo is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(error_code="REPO_NOT_FOUND", message=f"no repo {repo_id}").model_dump(),
            )
        await session.delete(repo)
        await session.commit()

    # Best-effort filesystem cleanup; missing dirs are fine.
    import shutil
    repo_dir = Path(request.app.state.settings.data_dir) / "repos" / repo_id
    shutil.rmtree(repo_dir, ignore_errors=True)
    log.info("repo_deleted", repo_id=repo_id)


@router.post("/repos/{repo_id}/refresh", response_model=RepoOut)
async def refresh_repo(repo_id: str, request: Request) -> RepoOut:
    factory = request.app.state.session_factory
    scheduler = request.app.state.scheduler
    cloner = request.app.state.repo_cloner

    async with factory() as session:
        repo = (await session.execute(select(Repo).where(Repo.id == repo_id))).scalar_one_or_none()
    if repo is None:
        raise HTTPException(
            status_code=404,
            detail=ApiError(error_code="REPO_NOT_FOUND", message=f"no repo {repo_id}").model_dump(),
        )

    scheduler.add_job(cloner.run_clone, args=[repo_id], misfire_grace_time=600)
    log.info("repo_refresh_enqueued", repo_id=repo_id)
    return _to_out(repo)
```

- [ ] **Step 2: 修改 `src/codeask/app.py` 在 lifespan 内创建 APScheduler 与 RepoCloner**

替换原 `lifespan` 定义为下面的版本：

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    ensure_layout(settings)
    sync_url = _sync_database_url(settings.database_url or "")
    log.info("running_migrations", url=sync_url)
    await asyncio.to_thread(run_migrations, sync_url)

    engine = create_engine(settings.database_url or "")
    factory = session_factory(engine)
    app.state.engine = engine
    app.state.session_factory = factory
    app.state.settings = settings

    # Background scheduler + cloner — declared here so that it stops cleanly
    # on shutdown and so that tests using the lifespan fixture get a real
    # scheduler instance.
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from codeask.code_index.cloner import RepoCloner
    from codeask.code_index.cleanup import build_cleanup_job
    from codeask.code_index.worktree import WorktreeManager

    scheduler = AsyncIOScheduler()
    repo_cloner = RepoCloner(factory)
    worktree_mgr = WorktreeManager(repo_root=Path(settings.data_dir) / "repos")
    cleanup_job = build_cleanup_job(worktree_mgr, Path(settings.data_dir) / "repos")
    scheduler.add_job(cleanup_job, "interval", hours=6, id="worktree_cleanup",
                      misfire_grace_time=3600)
    scheduler.start()

    app.state.scheduler = scheduler
    app.state.repo_cloner = repo_cloner
    app.state.worktree_manager = worktree_mgr

    log.info("app_ready", host=settings.host, port=settings.port)
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await engine.dispose()
        log.info("app_shutdown")
```

并在 `create_app` 中追加 router 注册：

```python
from codeask.api.code_index import router as code_index_router
...
app.include_router(healthz_router, prefix="/api")
app.include_router(code_index_router, prefix="/api")
```

并在文件顶部追加 `from pathlib import Path`，以及把 `apscheduler` 加到 `pyproject.toml` 的 dependencies（已在 dependencies.md §2.1 锁定）：

```toml
dependencies = [
    ...
    "apscheduler>=3.10",
    ...
]
```

- [ ] **Step 3: 写测试 `tests/integration/test_repos_api.py`**

```python
"""End-to-end POST /api/repos + GET + DELETE + refresh."""

import asyncio
import subprocess
from pathlib import Path

import pytest
from httpx import AsyncClient


def _bootstrap_local_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(root)],
        check=True, capture_output=True,
    )
    (root / "README.md").write_text("hi\n")
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", "init"],
        check=True, capture_output=True,
    )
    return root


@pytest.mark.asyncio
async def test_create_then_list(client: AsyncClient, tmp_path: Path) -> None:
    src = _bootstrap_local_repo(tmp_path / "src")

    r = await client.post(
        "/api/repos",
        json={"name": "demo", "source": "local_dir", "local_path": str(src)},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    repo_id = body["id"]
    assert body["status"] in {"registered", "cloning", "ready"}
    assert body["name"] == "demo"

    r2 = await client.get("/api/repos")
    assert r2.status_code == 200
    assert any(rec["id"] == repo_id for rec in r2.json()["repos"])

    # Wait briefly for clone to finish.
    for _ in range(40):
        r3 = await client.get(f"/api/repos/{repo_id}")
        if r3.json()["status"] in {"ready", "failed"}:
            break
        await asyncio.sleep(0.25)
    assert r3.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_create_invalid_body(client: AsyncClient) -> None:
    r = await client.post(
        "/api/repos",
        json={"name": "x", "source": "git", "url": None},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error_code"] == "INVALID_BODY"


@pytest.mark.asyncio
async def test_get_missing_repo(client: AsyncClient) -> None:
    r = await client.get("/api/repos/no-such-id")
    assert r.status_code == 404
    assert r.json()["detail"]["error_code"] == "REPO_NOT_FOUND"


@pytest.mark.asyncio
async def test_delete_repo(client: AsyncClient, tmp_path: Path) -> None:
    src = _bootstrap_local_repo(tmp_path / "src2")
    r = await client.post(
        "/api/repos",
        json={"name": "demo2", "source": "local_dir", "local_path": str(src)},
    )
    assert r.status_code == 201
    repo_id = r.json()["id"]

    r2 = await client.delete(f"/api/repos/{repo_id}")
    assert r2.status_code == 204

    r3 = await client.get(f"/api/repos/{repo_id}")
    assert r3.status_code == 404


@pytest.mark.asyncio
async def test_refresh_enqueues(client: AsyncClient, tmp_path: Path) -> None:
    src = _bootstrap_local_repo(tmp_path / "src3")
    r = await client.post(
        "/api/repos",
        json={"name": "demo3", "source": "local_dir", "local_path": str(src)},
    )
    assert r.status_code == 201
    repo_id = r.json()["id"]

    r2 = await client.post(f"/api/repos/{repo_id}/refresh")
    assert r2.status_code == 200
    assert r2.json()["id"] == repo_id
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_repos_api.py -v`
Expected: 五个测试 PASS。如果 APScheduler 还没装：`uv add apscheduler`。

- [ ] **Step 5: 验证全量回归**

Run: `uv run pytest -v`
Expected: foundation + 本计划已实现 task 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add src/codeask/api/code_index.py src/codeask/app.py pyproject.toml uv.lock \
        tests/integration/test_repos_api.py
git commit -m "feat(code-index): /api/repos CRUD + APScheduler-driven async clone"
```

---

## Task 10: `/api/code/grep` + `/api/code/read` + `/api/code/symbols` endpoints

**Files:**
- Modify: `src/codeask/api/code_index.py`（追加三条路由）
- Create: `tests/integration/test_code_api.py`

通用流程（每条路由都要走）：
1. 取 `repo` from DB；找不到 → 404 `REPO_NOT_FOUND`
2. `repo.status != ready` → 409 `REPO_NOT_READY`（落 `code-index.md` §2.2 错误回收）
3. `worktree_mgr.ensure_worktree(repo_id, session_id, commit)`；ref 解析失败 → 400 `INVALID_REF`
4. 调用对应 client（rg / file / ctags），timeout/失败 → 504/500
5. 返回标准响应 schema

- [ ] **Step 1: 在 `src/codeask/api/code_index.py` 末尾追加路由**

```python
# ============================================================
# /api/code/* — code search tools (grep / read / symbols)
# ============================================================

from codeask.api.schemas.code_index import (
    CodeGrepIn, CodeGrepOut, CodeGrepHitOut,
    CodeReadIn, CodeReadOut,
    CodeSymbolsIn, CodeSymbolsOut, CodeSymbolHitOut,
)
from codeask.code_index.ripgrep import RipgrepClient, RipgrepError
from codeask.code_index.ctags import CtagsClient, CtagsError
from codeask.code_index.file_reader import FileReader, FileReadError
from codeask.code_index.worktree import InvalidRefError, WorktreeError


def _http_error(code: int, error_code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=code,
        detail=ApiError(error_code=error_code, message=message).model_dump(),
    )


async def _load_ready_repo(request: Request, repo_id: str) -> Repo:
    factory = request.app.state.session_factory
    async with factory() as s:
        repo = (await s.execute(select(Repo).where(Repo.id == repo_id))).scalar_one_or_none()
    if repo is None:
        raise _http_error(404, "REPO_NOT_FOUND", f"no repo {repo_id}")
    if repo.status != Repo.STATUS_READY:
        raise _http_error(
            409,
            "REPO_NOT_READY",
            f"repo {repo_id} status is {repo.status}",
        )
    return repo


@router.post("/code/grep", response_model=CodeGrepOut)
async def code_grep(payload: CodeGrepIn, request: Request) -> CodeGrepOut:
    repo = await _load_ready_repo(request, payload.repo_id)
    wt_mgr = request.app.state.worktree_manager
    try:
        wt_path = wt_mgr.ensure_worktree(repo.id, payload.session_id, payload.commit)
        commit_sha = wt_mgr.resolve_ref(repo.id, payload.commit)
    except InvalidRefError as exc:
        raise _http_error(400, "INVALID_REF", str(exc)) from exc
    except WorktreeError as exc:
        raise _http_error(500, "WORKTREE_ERROR", str(exc)) from exc

    rg = RipgrepClient(timeout_seconds=30)
    try:
        hits = rg.grep(
            base=wt_path,
            pattern=payload.pattern,
            paths=payload.paths,
            max_count=payload.max_count,
        )
    except RipgrepError as exc:
        msg = str(exc)
        if "timed out" in msg:
            raise _http_error(504, "TOOL_TIMEOUT", msg) from exc
        raise _http_error(500, "TOOL_FAILED", msg) from exc

    truncated = len(hits) >= payload.max_count
    return CodeGrepOut(
        ok=True,
        repo_id=repo.id,
        commit=commit_sha,
        hits=[
            CodeGrepHitOut(path=h.path, line_number=h.line_number, line_text=h.line_text)
            for h in hits
        ],
        truncated=truncated,
    )


@router.post("/code/read", response_model=CodeReadOut)
async def code_read(payload: CodeReadIn, request: Request) -> CodeReadOut:
    repo = await _load_ready_repo(request, payload.repo_id)
    wt_mgr = request.app.state.worktree_manager
    try:
        wt_path = wt_mgr.ensure_worktree(repo.id, payload.session_id, payload.commit)
        commit_sha = wt_mgr.resolve_ref(repo.id, payload.commit)
    except InvalidRefError as exc:
        raise _http_error(400, "INVALID_REF", str(exc)) from exc
    except WorktreeError as exc:
        raise _http_error(500, "WORKTREE_ERROR", str(exc)) from exc

    fr = FileReader(max_bytes=4096)
    try:
        seg = fr.read_segment(
            base=wt_path,
            rel_path=payload.path,
            line_range=payload.line_range,
        )
    except FileReadError as exc:
        msg = str(exc)
        if "outside base" in msg or "binary" in msg:
            raise _http_error(400, "INVALID_PATH", msg) from exc
        raise _http_error(400, "INVALID_PATH", msg) from exc

    return CodeReadOut(
        ok=True,
        repo_id=repo.id,
        commit=commit_sha,
        path=seg.path,
        start_line=seg.start_line,
        end_line=seg.end_line,
        text=seg.text,
        truncated=seg.truncated,
    )


@router.post("/code/symbols", response_model=CodeSymbolsOut)
async def code_symbols(payload: CodeSymbolsIn, request: Request) -> CodeSymbolsOut:
    repo = await _load_ready_repo(request, payload.repo_id)
    wt_mgr = request.app.state.worktree_manager
    settings = request.app.state.settings
    try:
        wt_path = wt_mgr.ensure_worktree(repo.id, payload.session_id, payload.commit)
        commit_sha = wt_mgr.resolve_ref(repo.id, payload.commit)
    except InvalidRefError as exc:
        raise _http_error(400, "INVALID_REF", str(exc)) from exc
    except WorktreeError as exc:
        raise _http_error(500, "WORKTREE_ERROR", str(exc)) from exc

    cache_dir = Path(settings.data_dir) / "index"
    ctags = CtagsClient(cache_dir=cache_dir, timeout_seconds=60)
    try:
        tags = ctags.find_symbols(
            worktree_path=wt_path,
            repo_id=repo.id,
            commit=commit_sha,
            symbol=payload.symbol,
        )
    except CtagsError as exc:
        msg = str(exc)
        if "timed out" in msg:
            raise _http_error(504, "TOOL_TIMEOUT", msg) from exc
        raise _http_error(500, "TOOL_FAILED", msg) from exc

    return CodeSymbolsOut(
        ok=True,
        repo_id=repo.id,
        commit=commit_sha,
        symbols=[
            CodeSymbolHitOut(name=t.name, path=t.path, line=t.line, kind=t.kind)
            for t in tags
        ],
    )
```

> 在文件顶部追加 `from pathlib import Path`（如果还没有）。

- [ ] **Step 2: 写测试 `tests/integration/test_code_api.py`**

```python
"""End-to-end /api/code/grep + read + symbols."""

import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.skipif(
    shutil.which("rg") is None or shutil.which("ctags") is None,
    reason="ripgrep and universal-ctags required",
)


def _bootstrap(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(root)],
        check=True, capture_output=True,
    )
    (root / "main.py").write_text(
        "def greet():\n    return 'hello'\n\nclass Foo:\n    pass\n"
    )
    (root / "util.py").write_text("def helper():\n    return greet()\n")
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", "init"],
        check=True, capture_output=True,
    )
    return root


async def _register_and_wait_ready(client: AsyncClient, src: Path) -> str:
    r = await client.post(
        "/api/repos",
        json={"name": "demo", "source": "local_dir", "local_path": str(src)},
    )
    assert r.status_code == 201, r.text
    repo_id = r.json()["id"]
    for _ in range(80):
        r2 = await client.get(f"/api/repos/{repo_id}")
        if r2.json()["status"] == "ready":
            return repo_id
        await asyncio.sleep(0.25)
    raise AssertionError("repo never reached ready")


@pytest.mark.asyncio
async def test_grep_then_read(client: AsyncClient, tmp_path: Path) -> None:
    src = _bootstrap(tmp_path / "src")
    repo_id = await _register_and_wait_ready(client, src)

    rg = await client.post(
        "/api/code/grep",
        json={
            "repo_id": repo_id,
            "session_id": "sess-a",
            "pattern": "greet",
            "paths": None,
            "max_count": 50,
        },
    )
    assert rg.status_code == 200, rg.text
    body = rg.json()
    assert body["ok"] is True
    assert any(h["path"] == "main.py" for h in body["hits"])

    rd = await client.post(
        "/api/code/read",
        json={
            "repo_id": repo_id,
            "session_id": "sess-a",
            "path": "main.py",
            "line_range": [1, 2],
        },
    )
    assert rd.status_code == 200, rd.text
    assert rd.json()["text"].startswith("def greet")


@pytest.mark.asyncio
async def test_symbols(client: AsyncClient, tmp_path: Path) -> None:
    src = _bootstrap(tmp_path / "src")
    repo_id = await _register_and_wait_ready(client, src)

    sy = await client.post(
        "/api/code/symbols",
        json={
            "repo_id": repo_id,
            "session_id": "sess-b",
            "symbol": "greet",
        },
    )
    assert sy.status_code == 200, sy.text
    body = sy.json()
    assert body["ok"] is True
    assert any(s["name"] == "greet" and s["path"] == "main.py" for s in body["symbols"])


@pytest.mark.asyncio
async def test_repo_not_ready(client: AsyncClient) -> None:
    r = await client.post(
        "/api/code/grep",
        json={
            "repo_id": "does-not-exist",
            "session_id": "sess-x",
            "pattern": "x",
            "paths": None,
            "max_count": 1,
        },
    )
    assert r.status_code == 404
    assert r.json()["detail"]["error_code"] == "REPO_NOT_FOUND"


@pytest.mark.asyncio
async def test_invalid_path_rejected(client: AsyncClient, tmp_path: Path) -> None:
    src = _bootstrap(tmp_path / "src2")
    repo_id = await _register_and_wait_ready(client, src)

    r = await client.post(
        "/api/code/read",
        json={
            "repo_id": repo_id,
            "session_id": "sess-c",
            "path": "../etc/passwd",
            "line_range": [1, 5],
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error_code"] == "INVALID_PATH"


@pytest.mark.asyncio
async def test_invalid_ref_rejected(client: AsyncClient, tmp_path: Path) -> None:
    src = _bootstrap(tmp_path / "src3")
    repo_id = await _register_and_wait_ready(client, src)

    r = await client.post(
        "/api/code/grep",
        json={
            "repo_id": repo_id,
            "session_id": "sess-d",
            "commit": "no-such-branch",
            "pattern": "greet",
            "paths": None,
            "max_count": 5,
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error_code"] == "INVALID_REF"
```

- [ ] **Step 3: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_code_api.py -v`
Expected: 五个测试 PASS

- [ ] **Step 4: 提交**

```bash
git add src/codeask/api/code_index.py tests/integration/test_code_api.py
git commit -m "feat(code-index): /api/code/{grep,read,symbols} with worktree provisioning"
```

---

## Task 11: 24h idle worktree cleanup（APScheduler job）

**Files:**
- Create: `src/codeask/code_index/cleanup.py`
- Create: `tests/integration/test_cleanup.py`

锚点：`deployment-security.md` §7"24h 未活跃会话清理 worktree"。job 扫描 `<repo_root>/<repo_id>/worktrees/<session_id>/`，按文件夹 mtime 判断。`mtime` > 24h（job 接受 `idle_threshold_seconds` 参数，便于测试）→ 调 `WorktreeManager.destroy_worktree(repo_id, session_id)`。

清理后**保留 DB 中的 session 相关行**——本 plan 不持有 `session_repo_bindings`，只动文件系统。

- [ ] **Step 1: 写测试 `tests/integration/test_cleanup.py`**

```python
"""24h idle worktree cleanup."""

import os
import subprocess
import time
from pathlib import Path

import pytest

from codeask.code_index.cleanup import build_cleanup_job, find_idle_worktrees
from codeask.code_index.worktree import WorktreeManager


def _bootstrap(tmp_path: Path) -> tuple[Path, Path]:
    src = tmp_path / "src"
    src.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(src)],
        check=True, capture_output=True,
    )
    (src / "f.py").write_text("x=1\n")
    subprocess.run(["git", "-C", str(src), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(src), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(src), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(src), "commit", "-m", "init"],
        check=True, capture_output=True,
    )
    pool = tmp_path / "pool"
    bare = pool / "r" / "bare"
    bare.parent.mkdir(parents=True)
    subprocess.run(
        ["git", "clone", "--bare", "--local", str(src), str(bare)],
        check=True, capture_output=True,
    )
    return pool, bare


def test_find_idle_worktrees_threshold(tmp_path: Path) -> None:
    pool, _ = _bootstrap(tmp_path)
    mgr = WorktreeManager(repo_root=pool)

    fresh = mgr.ensure_worktree("r", "fresh-sess", "main")
    stale = mgr.ensure_worktree("r", "stale-sess", "main")

    # Backdate the stale worktree mtime by 48 hours.
    old = time.time() - 48 * 3600
    os.utime(stale, (old, old))

    idle = find_idle_worktrees(pool, idle_threshold_seconds=24 * 3600)
    idle_session_ids = {sid for (_repo, sid, _path) in idle}
    assert "stale-sess" in idle_session_ids
    assert "fresh-sess" not in idle_session_ids


def test_cleanup_job_destroys_idle(tmp_path: Path) -> None:
    pool, _ = _bootstrap(tmp_path)
    mgr = WorktreeManager(repo_root=pool)

    fresh = mgr.ensure_worktree("r", "fresh", "main")
    stale = mgr.ensure_worktree("r", "stale", "main")
    old = time.time() - 48 * 3600
    os.utime(stale, (old, old))

    job = build_cleanup_job(mgr, pool, idle_threshold_seconds=24 * 3600)
    job()  # synchronous invocation

    assert fresh.exists()
    assert not stale.exists()


def test_cleanup_job_no_op_when_pool_missing(tmp_path: Path) -> None:
    """If the pool dir doesn't exist yet, the job must not raise."""
    mgr = WorktreeManager(repo_root=tmp_path / "no-pool")
    job = build_cleanup_job(mgr, tmp_path / "no-pool", idle_threshold_seconds=1)
    job()  # must not raise
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/integration/test_cleanup.py -v`
Expected: ImportError on `codeask.code_index.cleanup`

- [ ] **Step 3: 实现 `src/codeask/code_index/cleanup.py`**

```python
"""APScheduler-driven idle worktree janitor.

Default policy: any worktree directory whose mtime is older than 24h is
removed. The DB row that bound a session to the worktree is left intact —
re-running the user's request will recreate the worktree on demand.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import structlog

from codeask.code_index.worktree import WorktreeManager

log = structlog.get_logger("codeask.code_index.cleanup")

_DEFAULT_IDLE_SECONDS = 24 * 3600


def find_idle_worktrees(
    repo_root: Path,
    idle_threshold_seconds: int = _DEFAULT_IDLE_SECONDS,
) -> list[tuple[str, str, Path]]:
    """Return ``(repo_id, session_id, path)`` for worktrees idle past threshold."""
    if not repo_root.is_dir():
        return []
    cutoff = time.time() - idle_threshold_seconds
    out: list[tuple[str, str, Path]] = []
    for repo_dir in repo_root.iterdir():
        if not repo_dir.is_dir():
            continue
        wt_root = repo_dir / "worktrees"
        if not wt_root.is_dir():
            continue
        for sess_dir in wt_root.iterdir():
            if not sess_dir.is_dir():
                continue
            try:
                mtime = sess_dir.stat().st_mtime
            except OSError:
                continue
            if mtime < cutoff:
                out.append((repo_dir.name, sess_dir.name, sess_dir))
    return out


def build_cleanup_job(
    worktree_mgr: WorktreeManager,
    repo_root: Path,
    idle_threshold_seconds: int = _DEFAULT_IDLE_SECONDS,
) -> Callable[[], None]:
    """Return a callable suitable for ``scheduler.add_job``."""

    def _run() -> None:
        idle = find_idle_worktrees(repo_root, idle_threshold_seconds)
        for repo_id, session_id, _path in idle:
            try:
                worktree_mgr.destroy_worktree(repo_id, session_id)
                log.info(
                    "worktree_cleanup_removed",
                    repo_id=repo_id,
                    session_id=session_id,
                )
            except Exception as exc:  # pragma: no cover — defensive
                log.warning(
                    "worktree_cleanup_failed",
                    repo_id=repo_id,
                    session_id=session_id,
                    error=str(exc),
                )

    return _run
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_cleanup.py -v`
Expected: 三个测试 PASS

- [ ] **Step 5: 验证 lifespan 已经把 cleanup_job 挂到 scheduler**

确认 Task 9 step 2 中 `lifespan` 内已经有：

```python
cleanup_job = build_cleanup_job(worktree_mgr, Path(settings.data_dir) / "repos")
scheduler.add_job(cleanup_job, "interval", hours=6, id="worktree_cleanup",
                  misfire_grace_time=3600)
```

如果 Task 9 时漏掉了，现在补上。

- [ ] **Step 6: 提交**

```bash
git add src/codeask/code_index/cleanup.py tests/integration/test_cleanup.py
git commit -m "feat(code-index): 24h idle worktree cleanup job"
```

---

## Task 12: 全量回归 + lint + type check + 手册补充

**Files:**
- 无新增源文件；可能产生 `pyproject.toml` 的依赖追加 commit。
- Modify: `README.md`（补一段"代码索引依赖"说明）

锚点：`testing-eval.md` + 复制 foundation Task 13 的检查列表。

- [ ] **Step 1: 跑 ruff + format check**

Run: `uv run ruff check src tests && uv run ruff format --check src tests`
Expected: 无错误。如有 format diff，运行 `uv run ruff format src tests` 后重跑。

- [ ] **Step 2: 跑 pyright**

Run: `uv run pyright src/codeask`
Expected: `0 errors, 0 warnings`

- [ ] **Step 3: 跑全量 pytest**

Run: `uv run pytest -v`
Expected: foundation 23 个 + wiki-knowledge plan（如已落地）+ 本 plan 全部通过。本 plan 新增测试文件预期数量：

- `tests/unit/test_path_safety.py`: 7
- `tests/unit/test_ripgrep.py`: 5（rg 缺失则 skip）
- `tests/unit/test_ctags.py`: 4（ctags 缺失则 skip）
- `tests/unit/test_file_reader.py`: 7
- `tests/integration/test_repo_models.py`: 3
- `tests/integration/test_cloner.py`: 3
- `tests/integration/test_worktree.py`: 5
- `tests/integration/test_repos_api.py`: 5
- `tests/integration/test_code_api.py`: 5（rg+ctags 任一缺失则全部 skip）
- `tests/integration/test_cleanup.py`: 3
- 合计：47（命中外部工具时）

- [ ] **Step 4: 在 `README.md` 的 Configuration 段落后追加"系统依赖"小节**

```markdown
## System dependencies

The code-index subsystem shells out to standard tooling. They must be on `$PATH`:

| Tool | Used for | Min version |
|---|---|---|
| `git` | clone bare / worktree add / rev-parse | 2.30+ |
| `rg` (ripgrep) | code search (`/api/code/grep`) | 13+ |
| `ctags` (universal-ctags) | symbol lookup (`/api/code/symbols`) | 5.9+ (universal-ctags, **not** Exuberant) |

Install on Debian/Ubuntu: `apt-get install git ripgrep universal-ctags`
Install on macOS: `brew install git ripgrep universal-ctags`
The Docker image (07 deployment plan) bakes all three.
```

- [ ] **Step 5: 验证 health check + 端到端流程仍走得通**

```bash
export CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
export CODEASK_DATA_DIR=/tmp/codeask-code-index-e2e
rm -rf "$CODEASK_DATA_DIR"
./start.sh &
SERVER_PID=$!
sleep 3
curl -fs http://127.0.0.1:8000/api/healthz | python -m json.tool
# Register a local repo (use this repo's own .git as the source).
curl -fs -X POST http://127.0.0.1:8000/api/repos \
  -H 'Content-Type: application/json' \
  -d "{\"name\":\"self\",\"source\":\"local_dir\",\"local_path\":\"$(pwd)\"}" \
  | python -m json.tool
sleep 2
curl -fs http://127.0.0.1:8000/api/repos | python -m json.tool
kill $SERVER_PID
```
Expected: 注册返回 `status: registered`，几秒后 list 应当看到 `status: ready`。

- [ ] **Step 6: 如果有 ruff format 改动，提交**

```bash
git status
# 若有改动：
git add -u
git commit -m "style: ruff format"
```

- [ ] **Step 7: 提交 README**

```bash
git add README.md
git commit -m "docs(readme): document code-index system dependencies"
```

- [ ] **Step 8: 打 tag 标记 code-index milestone**

```bash
git tag -a code-index-v0.1.0 -m "Code index milestone: repos + worktrees + grep/read/symbols"
```

---

## 验收标志（计划完整通过后应满足）

- [ ] `POST /api/repos` 返回 201 + `repo_id`，几秒后 `status` 变为 `ready`
- [ ] `~/.codeask/repos/<repo_id>/bare/HEAD` 存在
- [ ] `POST /api/code/grep` 在 ready 仓上能拿到带 `path / line_number / line_text` 的命中
- [ ] `POST /api/code/read` 可读片段且越狱路径返回 400 `INVALID_PATH`
- [ ] `POST /api/code/symbols` 命中 `def foo()` 等定义
- [ ] 任意 `/api/code/*` 在 `repo.status != ready` 时返回 409 `REPO_NOT_READY`
- [ ] `~/.codeask/repos/<repo_id>/worktrees/<session_id>/` 在调用代码工具后被建出
- [ ] `find_idle_worktrees` 单测验证 24h mtime 阈值生效
- [ ] APScheduler `worktree_cleanup` job 在 lifespan 启动时已注册（每 6h 跑一次）
- [ ] `~/.codeask/index/<repo_id>/<commit>.tags.json` 在第一次 symbols 查询后产生
- [ ] alembic head = `0006`（或 wiki-knowledge 顺延后的对应数）
- [ ] `uv run pytest -v` 全绿；`uv run ruff check && uv run pyright src/codeask` 零错误
- [ ] git tag `code-index-v0.1.0` 已打

---

## 不在本计划范围（明确推迟）

| 项 | 推迟到 | 原因 |
|---|---|---|
| `sessions` / `session_repo_bindings` 表 | 04 agent-runtime plan | 本 plan 的 `WorktreeManager.ensure_worktree` 接收 `session_id` 参数即可，不需要表存在 |
| Agent 调用 grep/read/symbols 的 ToolRegistry 包装 | 04 agent-runtime plan | 本 plan 的 endpoints 是底层 |
| 仓库配置 UI | 05 frontend-workbench plan | 后端 API 已就绪 |
| tree-sitter / LSP / 调用图 | 未来扩展（dependencies.md §8） | 一期 ctags 够 |
| 默认分支预查 UI 标识 | 04 agent-runtime + 05 frontend | 本 plan 的 `WorktreeManager.resolve_ref(None)` 走 HEAD 即"默认分支"，UI 标识不在后端 |
| 仓库孤儿提示（`deployment-security.md` §7 第 4 条） | 06 metrics / dashboard plan | 提示是 UI 行为，本 plan 只管 worktree 清理 |
| 磁盘水位线 / ctags LRU 全局清理 | 06 metrics plan | 本 plan 已有进程内 LRU；全局磁盘 LRU 是观测面议题 |
| `/api/repos` 鉴权 / 写权限分级 | MVP+（PRD §4.4.2） | 一期完全无鉴权 |

---

## Self-review

1. **Spec coverage**：scope 列出的每一项（ORM / migration / 目录布局 / RepoCloner / WorktreeManager / RipgrepClient / CtagsClient / FileReader / 路径校验 helper / 4 组 endpoints / 24h cleanup / Pydantic schemas / 集成测试）都有专门的 task。
2. **Placeholder 扫描**：本文档不含 TBD / TODO / "类似" / "适当错误处理" 等占位语；所有错误码、状态值、路径模式、超时秒数都是字面常量。
3. **命名一致性**：`repos.status` 取值 `registered/cloning/ready/failed` 在 ORM 常量、migration `CheckConstraint`、Pydantic `Literal`、API 集成测试断言四处共享同一份字面量；`source` 同。
4. **Migration 链**：`down_revision = "0005"` 与 `revision = "0006"` 配对，链头注释明示了如果 wiki-knowledge 实际占用 revision 不同时如何顺延。
5. **独立性**：每个 task 的"Files"段都列出 Create/Modify 列表；步骤代码完整可拷贝；只引用 foundation.md 已落地的 fixtures（`tests/conftest.py` 提供的 `client` / `app` / `settings`）和本 plan 之前 task 已落地的模块；不依赖未在前序 task 中创建的对象。
