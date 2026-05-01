# Foundation Implementation Plan

> **Implementation status:** 已完成并合入 `main`。本地 tag：`foundation-v0.1.0`。后续 plan 应遵循 `foundation-handoff.md` 的接口契约。
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 CodeAsk 单进程地基——FastAPI 应用骨架、SQLAlchemy 2.0 async + Alembic、`~/.codeask/` 存储布局、Fernet 加密、自报身份中间件、structlog、`/api/healthz` 走通端到端。

**Architecture:** 单进程 Python 3.11+ 应用。FastAPI 提供 REST/SSE，SQLAlchemy 2.0 async（aiosqlite 驱动）+ Alembic 管 schema，`pydantic-settings` 读环境变量，`cryptography.Fernet` 加密敏感字段，`structlog` 写结构化日志。所有持久化默认落 `~/.codeask/`。一期无鉴权但走"自报身份"软识别（`X-Subject-Id` header → middleware → request.state）。后续 6 份子计划（wiki / code-index / agent / frontend / metrics / deployment）建立在本计划产出的地基上，各自添加自家表 + Alembic migration。

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, Pydantic v2, pydantic-settings, SQLAlchemy 2.0 (async), aiosqlite, Alembic, cryptography (Fernet), structlog, pytest, pytest-asyncio, httpx, uv（依赖管理）

**Source SDD docs**（路径相对本文件 `docs/v1.0/plans/foundation.md`）：
- `../design/api-data-model.md`（schema / API list / 文件目录 / Alembic 策略）
- `../design/deployment-security.md`（`CODEASK_DATA_KEY` / 自报身份 / 文件安全）
- `../design/dependencies.md`（uv / FastAPI / SQLAlchemy 2.0 async / Alembic / structlog / Fernet）
- `../design/overview.md`（单进程 / `127.0.0.1` / `/api/healthz`）

**Known SDD inconsistency to flag (do not fix here):** `llm-gateway.md` §8 用 `CODEASK_MASTER_KEY`，但 `deployment-security.md` §5 锁定为 `CODEASK_DATA_KEY`。本计划遵循 `deployment-security.md`。04 agent-runtime 计划接入 LLM 网关时同步把 `llm-gateway.md` 改为 `CODEASK_DATA_KEY`，本计划不动文档。

**Project root:** `/home/hzh/workspace/CodeAsk/`（与 `docs/` 同级）。本计划全部文件路径相对此根目录。

---

## File Structure

本计划交付以下文件（全部相对项目根 `/home/hzh/workspace/CodeAsk/`）：

```text
CodeAsk/
├── pyproject.toml                # uv 管 deps，src layout
├── README.md                     # 一段简介 + 启动方法
├── .gitignore
├── .python-version               # 3.11
├── start.sh                      # 启动脚本（迁移 + uvicorn）
├── alembic.ini
├── alembic/
│   ├── env.py                    # 读 Settings.database_url，同步驱动（避免 lifespan 内 asyncio.run 嵌套）
│   ├── script.py.mako
│   └── versions/
│       └── 20260429_0001_initial.py   # 创建 system_settings
├── src/
│   └── codeask/
│       ├── __init__.py           # 暴露 __version__
│       ├── main.py               # `python -m codeask` / `codeask` CLI 入口
│       ├── app.py                # FastAPI app factory + lifespan
│       ├── settings.py           # Settings（pydantic-settings）
│       ├── storage.py            # ~/.codeask/ 目录布局
│       ├── crypto.py             # Fernet 加密 helper
│       ├── logging_config.py     # structlog 配置
│       ├── identity.py           # subject_id 中间件
│       ├── db/
│       │   ├── __init__.py       # 公共 re-export
│       │   ├── engine.py         # AsyncEngine 工厂
│       │   ├── base.py           # DeclarativeBase + TimestampMixin
│       │   ├── session.py        # AsyncSession FastAPI 依赖
│       │   └── models/
│       │       ├── __init__.py
│       │       └── system_settings.py    # 唯一一张表
│       ├── api/
│       │   ├── __init__.py
│       │   └── healthz.py        # GET /api/healthz
│       └── migrations.py         # 启动时 alembic upgrade head
└── tests/
    ├── __init__.py
    ├── conftest.py               # 共用 fixtures（tmp data dir, settings, app）
    ├── unit/
    │   ├── __init__.py
    │   ├── test_settings.py
    │   ├── test_storage.py
    │   ├── test_crypto.py
    │   └── test_identity.py
    └── integration/
        ├── __init__.py
        ├── test_db_models.py
        └── test_healthz.py
```

**职责边界**：
- `settings.py` 不读文件系统、不读 DB——只把环境变量解析成强类型
- `storage.py` 只创建/校验目录，不读写业务数据
- `crypto.py` 是无状态 helper，只接 bytes/str → bytes/str
- `db/` 不知道业务模型；`db/models/` 才有具体表
- `api/` 只编排 HTTP 协议，不直接读 DB（透过依赖注入拿 session）
- `identity.py` 只解析 `X-Subject-Id` header，不做鉴权决策
- `migrations.py` 一个函数：`run_migrations(database_url) -> None`，封装 alembic 调用

---

## Task 1: 项目骨架（uv + pyproject + src layout）

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.python-version`
- Create: `README.md`
- Create: `src/codeask/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: 在项目根创建 `.python-version`**

```text
3.11
```

- [ ] **Step 2: 创建 `pyproject.toml`**

```toml
[project]
name = "codeask"
version = "0.1.0"
description = "Private-deployment R&D Q&A system"
requires-python = ">=3.11"
readme = "README.md"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "sqlalchemy[asyncio]>=2.0.36",
    "aiosqlite>=0.20",
    "alembic>=1.13",
    "cryptography>=43",
    "structlog>=24.4",
    "httpx>=0.27",
]

[project.scripts]
codeask = "codeask.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/codeask"]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-httpx>=0.32",
    "ruff>=0.7",
    "pyright>=1.1.385",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-ra -q"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM"]

[tool.pyright]
pythonVersion = "3.11"
include = ["src", "tests"]
strict = ["src/codeask"]
```

- [ ] **Step 3: 创建 `.gitignore`**

```text
# Python
__pycache__/
*.py[cod]
*$py.class
.venv/
.uv/
*.egg-info/
build/
dist/

# Tooling
.pytest_cache/
.ruff_cache/
.pyright_cache/

# Env / data
.env
.env.local
~/.codeask/
data/
*.db
*.db-shm
*.db-wal

# OS
.DS_Store
Thumbs.db

# Editors
.idea/
.vscode/
*.swp
```

- [ ] **Step 4: 创建 `README.md`**

```markdown
# CodeAsk

Private-deployment R&D Q&A system. See `docs/` for design and PRD.

## Quick start

```bash
export CODEASK_DATA_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
uv sync
./start.sh
```

Server listens on `127.0.0.1:8000`. Visit `http://127.0.0.1:8000/api/healthz`.

## Tests

```bash
uv run pytest
```
```

- [ ] **Step 5: 创建 `src/codeask/__init__.py`**

```python
"""CodeAsk: private-deployment R&D Q&A system."""

__version__ = "0.1.0"
```

- [ ] **Step 6: 创建空 test 包初始化文件**

```bash
mkdir -p tests/unit tests/integration
touch tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py
```

- [ ] **Step 7: 写 smoke test `tests/test_smoke.py`**

```python
"""Smoke test: package imports and exposes a version."""

import codeask


def test_version_string() -> None:
    assert isinstance(codeask.__version__, str)
    assert codeask.__version__ != ""
```

- [ ] **Step 8: `uv sync` 安装依赖，`uv run pytest` 跑 smoke test**

Run: `uv sync && uv run pytest tests/test_smoke.py -v`
Expected: PASS（一个测试通过）

- [ ] **Step 9: 初始化 git 仓库并提交（含 `uv.lock`）**

```bash
cd /home/hzh/workspace/CodeAsk
git init
git add pyproject.toml uv.lock .gitignore .python-version README.md src/ tests/
git commit -m "chore: project skeleton (uv + src layout + smoke test)"
```

`uv.lock` 必须提交：保证团队 / CI / 生产环境装一样的依赖版本。

---

## Task 2: Settings（pydantic-settings + CODEASK_DATA_KEY 校验）

**Files:**
- Create: `src/codeask/settings.py`
- Create: `tests/unit/test_settings.py`

`Settings` 只读环境变量，不读文件系统、不依赖 DB。`CODEASK_DATA_KEY` 是必需字段；缺失时启动失败（直接对应 `deployment-security.md` §5）。

- [ ] **Step 1: 写测试 `tests/unit/test_settings.py`**

```python
"""Tests for Settings env loading."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from codeask.settings import Settings


def test_missing_data_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODEASK_DATA_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_defaults_applied(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEASK_DATA_KEY", "TGltSXRlc3Rrcm5hYmFzZTY0LXVybHNhZmUtMzJieXRlcw==")
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))

    s = Settings()
    assert s.host == "127.0.0.1"
    assert s.port == 8000
    assert s.log_level == "INFO"
    assert s.data_dir == tmp_path
    assert s.database_url == f"sqlite+aiosqlite:///{tmp_path / 'data.db'}"


def test_database_url_explicit_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CODEASK_DATA_KEY", "TGltSXRlc3Rrcm5hYmFzZTY0LXVybHNhZmUtMzJieXRlcw==")
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CODEASK_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    s = Settings()
    assert s.database_url == "sqlite+aiosqlite:///:memory:"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_settings.py -v`
Expected: ImportError / collection error（`codeask.settings` 不存在）

- [ ] **Step 3: 实现 `src/codeask/settings.py`**

```python
"""Application settings (env-driven)."""

from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CODEASK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_key: str = Field(
        ...,
        description="Fernet master key (base64-urlsafe, 32 bytes). Encrypts sensitive DB fields.",
    )
    data_dir: Path = Field(
        default_factory=lambda: Path.home() / ".codeask",
        description="Root directory for SQLite + uploads + worktrees + logs.",
    )
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    database_url: str | None = None

    @model_validator(mode="after")
    def _derive_database_url(self) -> Self:
        if self.database_url is None:
            self.database_url = f"sqlite+aiosqlite:///{self.data_dir / 'data.db'}"
        return self
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_settings.py -v`
Expected: 三个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/codeask/settings.py tests/unit/test_settings.py
git commit -m "feat(settings): env-driven Settings with required CODEASK_DATA_KEY"
```

---

## Task 3: 存储布局（~/.codeask/ 子目录懒创建）

**Files:**
- Create: `src/codeask/storage.py`
- Create: `tests/unit/test_storage.py`

`storage.ensure_layout(settings)` 在启动时调用一次，幂等地创建 `wiki/ / skills/ / sessions/ / repos/ / index/ / logs/`（与 `api-data-model.md` §5 一致）。

- [ ] **Step 1: 写测试 `tests/unit/test_storage.py`**

```python
"""Tests for storage layout init."""

from pathlib import Path

import pytest

from codeask.settings import Settings
from codeask.storage import ensure_layout


@pytest.fixture()
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.setenv("CODEASK_DATA_KEY", "TGltSXRlc3Rrcm5hYmFzZTY0LXVybHNhZmUtMzJieXRlcw==")
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    return Settings()


def test_creates_all_subdirs(settings: Settings) -> None:
    ensure_layout(settings)
    for name in ("wiki", "skills", "sessions", "repos", "index", "logs"):
        d = settings.data_dir / name
        assert d.is_dir(), f"missing {name}/"


def test_idempotent(settings: Settings) -> None:
    ensure_layout(settings)
    ensure_layout(settings)  # second call must not raise


def test_creates_data_dir_itself(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "codeask"
    monkeypatch.setenv("CODEASK_DATA_KEY", "TGltSXRlc3Rrcm5hYmFzZTY0LXVybHNhZmUtMzJieXRlcw==")
    monkeypatch.setenv("CODEASK_DATA_DIR", str(nested))
    s = Settings()
    ensure_layout(s)
    assert nested.is_dir()
    assert (nested / "wiki").is_dir()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_storage.py -v`
Expected: ImportError on `codeask.storage`

- [ ] **Step 3: 实现 `src/codeask/storage.py`**

```python
"""Filesystem layout under ``settings.data_dir``."""

from codeask.settings import Settings

SUBDIRS: tuple[str, ...] = (
    "wiki",
    "skills",
    "sessions",
    "repos",
    "index",
    "logs",
)


def ensure_layout(settings: Settings) -> None:
    """Create ``data_dir`` and required subdirectories. Idempotent."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    for name in SUBDIRS:
        (settings.data_dir / name).mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_storage.py -v`
Expected: 三个测试 PASS

- [ ] **Step 5: 提交**

```bash
git add src/codeask/storage.py tests/unit/test_storage.py
git commit -m "feat(storage): idempotent ~/.codeask/ layout init"
```

---

## Task 4: Fernet 加密 helper

**Files:**
- Create: `src/codeask/crypto.py`
- Create: `tests/unit/test_crypto.py`

`Crypto` 是无状态 helper，构造时接受 `data_key`（base64 urlsafe 32 bytes 字符串），暴露 `encrypt(plaintext: str) -> str` 和 `decrypt(ciphertext: str) -> str`。错误密钥要明确报错，不能默默吞掉。

- [ ] **Step 1: 写测试 `tests/unit/test_crypto.py`**

```python
"""Tests for Fernet wrapper."""

import pytest
from cryptography.fernet import Fernet, InvalidToken

from codeask.crypto import Crypto


@pytest.fixture()
def key() -> str:
    return Fernet.generate_key().decode()


def test_round_trip(key: str) -> None:
    c = Crypto(key)
    cipher = c.encrypt("sk-secret-12345")
    assert cipher != "sk-secret-12345"
    assert c.decrypt(cipher) == "sk-secret-12345"


def test_wrong_key_raises(key: str) -> None:
    c1 = Crypto(key)
    c2 = Crypto(Fernet.generate_key().decode())
    cipher = c1.encrypt("payload")
    with pytest.raises(InvalidToken):
        c2.decrypt(cipher)


def test_invalid_key_format_raises() -> None:
    with pytest.raises(ValueError):
        Crypto("not-a-valid-fernet-key")


def test_empty_string_round_trip(key: str) -> None:
    c = Crypto(key)
    assert c.decrypt(c.encrypt("")) == ""
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_crypto.py -v`
Expected: ImportError on `codeask.crypto`

- [ ] **Step 3: 实现 `src/codeask/crypto.py`**

```python
"""Fernet-backed encryption helper for sensitive DB fields (LLM API keys etc.)."""

from cryptography.fernet import Fernet


class Crypto:
    def __init__(self, data_key: str) -> None:
        try:
            self._fernet = Fernet(data_key.encode())
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "Invalid CODEASK_DATA_KEY (must be base64-urlsafe-encoded 32 bytes; "
                "generate with `python -c 'from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())'`)"
            ) from exc

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_crypto.py -v`
Expected: 四个测试 PASS

- [ ] **Step 5: 提交**

```bash
git add src/codeask/crypto.py tests/unit/test_crypto.py
git commit -m "feat(crypto): Fernet wrapper with explicit invalid-key error"
```

---

## Task 5: structlog 配置（一处配置，处处用）

**Files:**
- Create: `src/codeask/logging_config.py`
- Create: `tests/unit/test_logging_config.py`

提供 `configure_logging(level: str)`，返回幂等 setup（重复调用不重复 attach handler）。日志走 JSON renderer，方便后续接 ELK（`dependencies.md` §2.7）。

- [ ] **Step 1: 写测试 `tests/unit/test_logging_config.py`**

```python
"""Tests for structlog configuration."""

import json
import logging

import structlog

from codeask.logging_config import configure_logging


def test_logger_outputs_json(capsys) -> None:  # type: ignore[no-untyped-def]
    configure_logging("INFO")
    log = structlog.get_logger("test")
    log.info("hello", foo="bar", n=42)
    out = capsys.readouterr().out.strip()
    assert out, "expected log line on stdout"
    record = json.loads(out)
    assert record["event"] == "hello"
    assert record["foo"] == "bar"
    assert record["n"] == 42
    assert record["level"] == "info"


def test_reconfigure_does_not_corrupt_output(capsys) -> None:  # type: ignore[no-untyped-def]
    """Reconfiguring twice (e.g., across tests) still yields valid JSON."""
    configure_logging("DEBUG")
    configure_logging("DEBUG")
    log = structlog.get_logger("test")
    log.info("second")
    out = capsys.readouterr().out.strip()
    record = json.loads(out)
    assert record["event"] == "second"


def test_respects_stdlib_level() -> None:
    configure_logging("WARNING")
    assert logging.getLogger().level == logging.WARNING
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_logging_config.py -v`
Expected: ImportError on `codeask.logging_config`

- [ ] **Step 3: 实现 `src/codeask/logging_config.py`**

```python
"""structlog setup. Idempotent. Writes JSON to stdout via PrintLoggerFactory."""

import logging

import structlog


def configure_logging(level: str = "INFO") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)
    # Stdlib level so libraries that use logging (uvicorn / sqlalchemy / httpx) honor it.
    logging.getLogger().setLevel(log_level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        # PrintLoggerFactory writes to sys.stdout dynamically (re-evaluated at each
        # call). Critical so pytest capsys can capture output across reconfigurations.
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_logging_config.py -v`
Expected: 三个测试 PASS

- [ ] **Step 5: 提交**

```bash
git add src/codeask/logging_config.py tests/unit/test_logging_config.py
git commit -m "feat(logging): idempotent structlog JSON setup"
```

---

## Task 6: SQLAlchemy 2.0 async engine + Base + TimestampMixin

**Files:**
- Create: `src/codeask/db/__init__.py`
- Create: `src/codeask/db/base.py`
- Create: `src/codeask/db/engine.py`
- Create: `src/codeask/db/session.py`

提供：
- `Base = declarative_base()`（实际用 `DeclarativeBase` 子类）
- `TimestampMixin`：`created_at`、`updated_at` 自动维护
- `create_engine(database_url) -> AsyncEngine`：开 WAL（`dependencies.md` §2.2）
- `get_session(engine) -> AsyncSession`：FastAPI 依赖注入用

本步**只搭壳**，不定义业务模型；下一步会加第一张表。

- [ ] **Step 1: 创建 `src/codeask/db/__init__.py`**

```python
"""Database layer: engine factory, declarative base, session dependency."""

from codeask.db.base import Base, TimestampMixin
from codeask.db.engine import create_engine
from codeask.db.session import get_session, session_factory

__all__ = [
    "Base",
    "TimestampMixin",
    "create_engine",
    "get_session",
    "session_factory",
]
```

- [ ] **Step 2: 创建 `src/codeask/db/base.py`**

```python
"""Declarative base + shared mixins."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )
```

- [ ] **Step 3: 创建 `src/codeask/db/engine.py`**

```python
"""AsyncEngine factory with SQLite WAL pragma."""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_engine(database_url: str, echo: bool = False) -> AsyncEngine:
    engine = create_async_engine(
        database_url,
        echo=echo,
        future=True,
        pool_pre_ping=True,
    )

    if database_url.startswith("sqlite"):
        @event.listens_for(engine.sync_engine, "connect")
        def _enable_wal(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

    return engine
```

- [ ] **Step 4: 创建 `src/codeask/db/session.py`**

```python
"""AsyncSession factory + FastAPI dependency."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session
```

- [ ] **Step 5: 跑现有测试确认 import 没破**

Run: `uv run pytest -v`
Expected: 已有测试全部 PASS（本步骤无新测试，只是搭壳）

- [ ] **Step 6: 提交**

```bash
git add src/codeask/db/
git commit -m "feat(db): SQLAlchemy 2.0 async engine + Base + TimestampMixin"
```

---

## Task 7: 第一张表 `system_settings` + ORM round-trip 测试

**Files:**
- Create: `src/codeask/db/models/__init__.py`
- Create: `src/codeask/db/models/system_settings.py`
- Create: `tests/integration/test_db_models.py`

`system_settings(key text pk, value json, updated_at timestamp)`——给后面所有计划用作 kv-store 落地点。后续 02 / 03 / 04 等子计划会按需加自家表，本计划只造一张作为 schema baseline。

- [ ] **Step 1: 创建 `src/codeask/db/models/__init__.py`**

```python
"""ORM model definitions."""

from codeask.db.models.system_settings import SystemSetting

__all__ = ["SystemSetting"]
```

- [ ] **Step 2: 创建 `src/codeask/db/models/system_settings.py`**

```python
"""system_settings: shared key-value store."""

from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class SystemSetting(Base, TimestampMixin):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
```

- [ ] **Step 3: 写集成测试 `tests/integration/test_db_models.py`**

```python
"""Round-trip test against in-memory SQLite."""

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from codeask.db import Base, create_engine, session_factory
from codeask.db.models import SystemSetting


@pytest_asyncio.fixture()
async def engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    db_path = tmp_path / "test.db"
    eng = create_engine(f"sqlite+aiosqlite:///{db_path}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_insert_and_select(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        s.add(SystemSetting(key="install_id", value={"id": "abc-123"}))
        await s.commit()

    async with factory() as s:
        result = await s.execute(select(SystemSetting).where(SystemSetting.key == "install_id"))
        row = result.scalar_one()
        assert row.value == {"id": "abc-123"}
        assert row.created_at is not None
        assert row.updated_at is not None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_db_models.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/codeask/db/models/ tests/integration/test_db_models.py
git commit -m "feat(db): system_settings table + round-trip integration test"
```

---

## Task 8: Alembic 初始化 + 第一份 migration

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/20260429_0001_initial.py`
- Create: `src/codeask/migrations.py`
- Create: `tests/integration/test_migrations.py`

`alembic/env.py` 走 async 风格，从 `Settings` 读 `database_url`。`migrations.run_migrations(database_url)` 是启动时调用的入口；迁移失败抛异常，让 lifespan 拒绝启动（`api-data-model.md` §6）。

- [ ] **Step 1: 在项目根创建 `alembic.ini`**

```ini
[alembic]
script_location = alembic
file_template = %%(year)d%%(month).2d%%(day).2d_%%(rev)s_%%(slug)s
prepend_sys_path = src
version_path_separator = os

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stdout,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: 创建 `alembic/script.py.mako`**

```python
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 3: 创建 `alembic/env.py`**

```python
"""Alembic env (sync). Uses sqlite:// URL — async URL must be converted before calling."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from codeask.db import Base
from codeask.db import models  # noqa: F401  ensure all models are registered with Base
from codeask.settings import Settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Manual `alembic upgrade head` doesn't pass sqlalchemy.url; derive from Settings.
if not config.get_main_option("sqlalchemy.url"):
    _settings = Settings()  # type: ignore[call-arg]
    _async_url = _settings.database_url or ""
    _sync_url = _async_url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    config.set_main_option("sqlalchemy.url", _sync_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: 创建初始 migration `alembic/versions/20260429_0001_initial.py`**

```python
"""initial: system_settings

Revision ID: 0001
Revises:
Create Date: 2026-04-29 00:00:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("system_settings")
```

- [ ] **Step 5: 创建 `src/codeask/migrations.py`**

```python
"""Apply Alembic migrations programmatically. Called from app lifespan."""

from pathlib import Path

from alembic import command
from alembic.config import Config

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _PROJECT_ROOT / "alembic.ini"


def run_migrations(database_url: str) -> None:
    """Upgrade DB to head. Raises if migration fails (caller must reject startup)."""
    if not _ALEMBIC_INI.is_file():
        raise FileNotFoundError(f"alembic.ini not found at {_ALEMBIC_INI}")
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")
```

- [ ] **Step 6: 写测试 `tests/integration/test_migrations.py`**

```python
"""run_migrations creates schema and is idempotent."""

from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from codeask.migrations import run_migrations


@pytest.mark.asyncio
async def test_run_migrations_creates_table(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    sync_url = f"sqlite:///{db_path}"

    run_migrations(sync_url)

    eng = create_async_engine(url)
    async with eng.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    assert "system_settings" in tables
    await eng.dispose()


@pytest.mark.asyncio
async def test_run_migrations_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    sync_url = f"sqlite:///{db_path}"
    run_migrations(sync_url)
    run_migrations(sync_url)  # second call must not raise
```

- [ ] **Step 7: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_migrations.py -v`
Expected: 两个测试 PASS

- [ ] **Step 8: 验证 `alembic upgrade head` 命令行也能跑**

```bash
mkdir -p /tmp/codeask-alembic-check
CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
CODEASK_DATA_DIR=/tmp/codeask-alembic-check \
uv run alembic upgrade head
```
Expected: `INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial`

- [ ] **Step 9: 提交**

```bash
git add alembic.ini alembic/ src/codeask/migrations.py tests/integration/test_migrations.py
git commit -m "feat(migrations): Alembic async setup + 0001 initial (system_settings)"
```

---

## Task 9: 自报身份中间件（X-Subject-Id → request.state）

**Files:**
- Create: `src/codeask/identity.py`
- Create: `tests/unit/test_identity.py`

中间件从 header 读 `X-Subject-Id`（前端 §8.1 写入的 `nickname@client_id` 或 `device@<short_id>`）。缺失时降级为 `anonymous@<8 位随机>`，并把 subject_id 同时绑到 structlog contextvars，让本次请求的所有日志都携带 `subject_id`。

不做任何鉴权决策——一期所有人可读可写（`deployment-security.md` §3）。

- [ ] **Step 1: 写测试 `tests/unit/test_identity.py`**

```python
"""Tests for SubjectIdMiddleware."""

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from codeask.identity import SubjectIdMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SubjectIdMiddleware)

    @app.get("/whoami")
    async def whoami(request: Request) -> dict:  # type: ignore[type-arg]
        return {"subject_id": request.state.subject_id}

    return app


@pytest.mark.asyncio
async def test_uses_header_when_provided() -> None:
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/whoami", headers={"X-Subject-Id": "alice@dev-7f2c"})
    assert r.status_code == 200
    assert r.json()["subject_id"] == "alice@dev-7f2c"


@pytest.mark.asyncio
async def test_falls_back_to_anonymous_when_missing() -> None:
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/whoami")
    assert r.status_code == 200
    sid = r.json()["subject_id"]
    assert sid.startswith("anonymous@")
    assert len(sid) > len("anonymous@")


@pytest.mark.asyncio
async def test_rejects_obviously_malformed_header() -> None:
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/whoami", headers={"X-Subject-Id": "x" * 300})
    assert r.status_code == 200
    assert r.json()["subject_id"].startswith("anonymous@")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_identity.py -v`
Expected: ImportError on `codeask.identity`

- [ ] **Step 3: 实现 `src/codeask/identity.py`**

```python
"""Self-report identity middleware (one-shot, no auth)."""

import re
import secrets

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

_SUBJECT_PATTERN = re.compile(r"^[A-Za-z0-9._\-@]{1,128}$")
_HEADER_NAME = "X-Subject-Id"


class SubjectIdMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        raw = request.headers.get(_HEADER_NAME, "").strip()
        subject_id = raw if _SUBJECT_PATTERN.fullmatch(raw) else f"anonymous@{secrets.token_hex(4)}"
        request.state.subject_id = subject_id

        structlog.contextvars.bind_contextvars(subject_id=subject_id)
        try:
            response: Response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("subject_id")
        return response
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_identity.py -v`
Expected: 三个测试 PASS

- [ ] **Step 5: 提交**

```bash
git add src/codeask/identity.py tests/unit/test_identity.py
git commit -m "feat(identity): self-report subject_id middleware"
```

---

## Task 10: FastAPI app factory + /api/healthz + lifespan（迁移 + 启动失败拒绝）

**Files:**
- Create: `src/codeask/api/__init__.py`
- Create: `src/codeask/api/healthz.py`
- Create: `src/codeask/app.py`
- Create: `src/codeask/main.py`
- Create: `tests/conftest.py`
- Create: `tests/integration/test_healthz.py`

App 工厂在 lifespan 启动阶段：
1. 调用 `ensure_layout(settings)`
2. 调用 `run_migrations(settings.database_url 的 sync 形式)`——失败直接 raise，FastAPI 拒绝启动（`api-data-model.md` §6）
3. 创建 engine + session_factory，挂到 `app.state`

`/api/healthz` 返回版本 + DB 是否可读。

- [ ] **Step 1: 创建 `src/codeask/api/__init__.py`**

```python
"""API routers."""
```

- [ ] **Step 2: 创建 `src/codeask/api/healthz.py`**

```python
"""Liveness + DB readiness endpoint."""

from fastapi import APIRouter, Request
from sqlalchemy import text

from codeask import __version__

router = APIRouter()


@router.get("/healthz")
async def healthz(request: Request) -> dict:  # type: ignore[type-arg]
    factory = request.app.state.session_factory
    db_ok = False
    async with factory() as session:
        result = await session.execute(text("SELECT 1"))
        db_ok = result.scalar_one() == 1
    return {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "db": "ok" if db_ok else "fail",
        "subject_id": request.state.subject_id,
    }
```

- [ ] **Step 3: 创建 `src/codeask/app.py`**

```python
"""FastAPI application factory."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from codeask.api.healthz import router as healthz_router
from codeask.db import create_engine, session_factory
from codeask.identity import SubjectIdMiddleware
from codeask.logging_config import configure_logging
from codeask.migrations import run_migrations
from codeask.settings import Settings
from codeask.storage import ensure_layout


def _sync_database_url(async_url: str) -> str:
    """Convert sqlite+aiosqlite:// to sqlite:// for Alembic (sync driver)."""
    return async_url.replace("sqlite+aiosqlite://", "sqlite://", 1)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()  # type: ignore[call-arg]
    configure_logging(settings.log_level)
    log = structlog.get_logger("codeask.app")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        ensure_layout(settings)
        sync_url = _sync_database_url(settings.database_url or "")
        log.info("running_migrations", url=sync_url)
        # run_migrations is sync (Alembic command API); offload to thread so we
        # don't block the event loop or trigger nested asyncio.run.
        await asyncio.to_thread(run_migrations, sync_url)

        engine = create_engine(settings.database_url or "")
        app.state.engine = engine
        app.state.session_factory = session_factory(engine)
        app.state.settings = settings
        log.info("app_ready", host=settings.host, port=settings.port)
        try:
            yield
        finally:
            await engine.dispose()
            log.info("app_shutdown")

    app = FastAPI(title="CodeAsk", lifespan=lifespan)
    app.add_middleware(SubjectIdMiddleware)
    app.include_router(healthz_router, prefix="/api")
    return app
```

- [ ] **Step 4: 创建 `src/codeask/main.py`**

```python
"""Console entry point: `codeask` runs uvicorn."""

import uvicorn

from codeask.settings import Settings


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    uvicorn.run(
        "codeask.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 创建 `tests/conftest.py`**

```python
"""Shared pytest fixtures."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from codeask.app import create_app
from codeask.settings import Settings


@pytest.fixture()
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    return Settings()  # type: ignore[call-arg]


@pytest_asyncio.fixture()
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture()
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
```

- [ ] **Step 6: 写测试 `tests/integration/test_healthz.py`**

```python
"""End-to-end /api/healthz."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_healthz_returns_ok(client: AsyncClient) -> None:
    r = await client.get("/api/healthz", headers={"X-Subject-Id": "alice@dev-7f2c"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["version"]
    assert body["subject_id"] == "alice@dev-7f2c"


@pytest.mark.asyncio
async def test_healthz_anonymous_subject(client: AsyncClient) -> None:
    r = await client.get("/api/healthz")
    assert r.status_code == 200
    assert r.json()["subject_id"].startswith("anonymous@")
```

- [ ] **Step 7: 跑全部测试**

Run: `uv run pytest -v`
Expected: 之前所有测试 + healthz 两条 = 全部 PASS

- [ ] **Step 8: 手工验证服务能起**

```bash
export CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
export CODEASK_DATA_DIR=/tmp/codeask-manual-check
uv run codeask &
SERVER_PID=$!
sleep 2
curl -s http://127.0.0.1:8000/api/healthz -H "X-Subject-Id: bob@dev-1234" | python -m json.tool
kill $SERVER_PID
```
Expected JSON：`{"status":"ok","version":"0.1.0","db":"ok","subject_id":"bob@dev-1234"}`

- [ ] **Step 9: 提交**

```bash
git add src/codeask/api/ src/codeask/app.py src/codeask/main.py tests/conftest.py tests/integration/test_healthz.py
git commit -m "feat(app): FastAPI factory + lifespan + /api/healthz + uvicorn entrypoint"
```

---

## Task 11: 启动失败拒绝路径（迁移失败 → app 拒绝启动）

**Files:**
- Modify: `tests/integration/test_healthz.py`（追加测试）

`api-data-model.md` §6 锁定："迁移失败时服务启动失败，不能进入半迁移状态"。本步加测试覆盖反路径。

- [ ] **Step 1: 在 `tests/integration/test_healthz.py` 末尾追加测试**

```python


@pytest.mark.asyncio
async def test_lifespan_fails_when_migrations_broken(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """If alembic upgrade raises, lifespan must propagate the error."""
    from cryptography.fernet import Fernet

    from codeask.app import create_app
    from codeask.settings import Settings
    from codeask import migrations

    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))

    def _boom(database_url: str) -> None:
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr(migrations, "run_migrations", _boom)
    # also patch the binding inside app.py
    from codeask import app as app_module
    monkeypatch.setattr(app_module, "run_migrations", _boom)

    settings = Settings()  # type: ignore[call-arg]
    application = create_app(settings)

    with pytest.raises(RuntimeError, match="simulated migration failure"):
        async with application.router.lifespan_context(application):
            pass  # pragma: no cover
```

- [ ] **Step 2: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_healthz.py -v`
Expected: 三条测试 PASS（包括新增的"启动失败拒绝"）

- [ ] **Step 3: 提交**

```bash
git add tests/integration/test_healthz.py
git commit -m "test(app): assert lifespan rejects startup when migrations fail"
```

---

## Task 12: `start.sh` + 手册更新

**Files:**
- Create: `start.sh`
- Modify: `README.md`

`start.sh` 是 PRD §4.4.1 "30 秒部署"承诺的第一个落地点：单脚本启动、清晰错误信息、不依赖 systemd。

- [ ] **Step 1: 创建 `start.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

# CodeAsk start script: validates env, runs migrations via app lifespan, starts uvicorn.
# Usage:
#   export CODEASK_DATA_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
#   ./start.sh

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

if [[ -z "${CODEASK_DATA_KEY:-}" ]]; then
    cat >&2 <<EOF
ERROR: CODEASK_DATA_KEY is not set.

Generate one (and save it — losing it makes encrypted DB fields unreadable):

    export CODEASK_DATA_KEY="\$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

Then re-run ./start.sh.
EOF
    exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: 'uv' not found. Install from https://docs.astral.sh/uv/ first." >&2
    exit 1
fi

uv sync --frozen 2>/dev/null || uv sync

echo "Starting CodeAsk on ${CODEASK_HOST:-127.0.0.1}:${CODEASK_PORT:-8000}"
echo "Data dir: ${CODEASK_DATA_DIR:-$HOME/.codeask}"

exec uv run codeask
```

- [ ] **Step 2: 给脚本可执行权限**

```bash
chmod +x start.sh
```

- [ ] **Step 3: 在 `README.md` 替换"Quick start"段落**

把 README 里的 Quick start 段落改为：

```markdown
## Quick start

```bash
# 1) Generate the encryption key once and save it somewhere safe
export CODEASK_DATA_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

# 2) Start the server
./start.sh
```

Server listens on `http://127.0.0.1:8000`. Smoke check:

```bash
curl -s http://127.0.0.1:8000/api/healthz -H 'X-Subject-Id: alice@dev-1' | python -m json.tool
```

## Configuration

| Env var | Required | Default | Notes |
|---|---|---|---|
| `CODEASK_DATA_KEY` | yes | — | Fernet key (base64-urlsafe 32 bytes). Lose it = lose encrypted fields. |
| `CODEASK_DATA_DIR` | no | `~/.codeask` | SQLite, uploads, worktrees, logs. |
| `CODEASK_HOST` | no | `127.0.0.1` | Default binds local-only on purpose (no auth in MVP). |
| `CODEASK_PORT` | no | `8000` | |
| `CODEASK_LOG_LEVEL` | no | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR`. |
| `CODEASK_DATABASE_URL` | no | derived | Override only when testing or migrating away from SQLite. |
```

- [ ] **Step 4: 端到端冒烟**

```bash
export CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
export CODEASK_DATA_DIR=/tmp/codeask-startsh-check
./start.sh &
SERVER_PID=$!
sleep 3
curl -fs http://127.0.0.1:8000/api/healthz -H "X-Subject-Id: e2e@local" | python -m json.tool
kill $SERVER_PID
ls /tmp/codeask-startsh-check  # 应当看到 data.db / wiki/ / sessions/ 等
```
Expected: JSON 返回 `{"status":"ok",...}`，`/tmp/codeask-startsh-check/data.db` 存在，子目录全部就绪。

- [ ] **Step 5: 提交**

```bash
git add start.sh README.md
git commit -m "feat(deploy): start.sh + README quick-start + env var reference"
```

---

## Task 13: 全量回归 + lint + type check

**Files:**
- 无新增文件，只跑 CI 风格的本地校验。

确认地基没有"测过的部分能跑、其他偷偷坏掉"的问题。

- [ ] **Step 1: 跑 ruff（lint + format check）**

Run: `uv run ruff check src tests && uv run ruff format --check src tests`
Expected: 无错误。如有 format diff，运行 `uv run ruff format src tests` 后重跑。

- [ ] **Step 2: 跑 pyright（type check）**

Run: `uv run pyright src/codeask`
Expected: `0 errors, 0 warnings`。

- [ ] **Step 3: 跑全量 pytest**

Run: `uv run pytest -v`
Expected: 全部 PASS。当前预期数量（只统计本计划新增的）：
- `tests/test_smoke.py`: 1
- `tests/unit/test_settings.py`: 3
- `tests/unit/test_storage.py`: 3
- `tests/unit/test_crypto.py`: 4
- `tests/unit/test_logging_config.py`: 3
- `tests/unit/test_identity.py`: 3
- `tests/integration/test_db_models.py`: 1
- `tests/integration/test_migrations.py`: 2
- `tests/integration/test_healthz.py`: 3
- 合计：23

- [ ] **Step 4: 如果有 ruff 自动 format 改动，提交**

```bash
git status
# 如果有改动：
git add -u
git commit -m "style: ruff format"
```

- [ ] **Step 5: 打 tag 标记 foundation 完成**

```bash
git tag -a foundation-v0.1.0 -m "Foundation milestone: scaffold + DB + healthz"
```

---

## Task 14: 子计划交接清单

**Files:**
- Create: `docs/v1.0/plans/foundation-handoff.md`

写一份 hand-off doc 给 02 / 03 / 04 等后续计划，明确"地基已经提供哪些 hook，新计划要遵循哪些约定"。这避免后续 6 份计划各自"重新发明 db engine / settings 形态 / 中间件接入方式"。

- [ ] **Step 1: 创建 `docs/v1.0/plans/foundation-handoff.md`**

````markdown
# Foundation Hand-off — 给后续 6 份子计划

本文档记录 foundation 计划留下的"接口契约"。02 / 03 / 04 / 05 / 06 / 07 在添加自家功能时遵循以下约定。

## 1. 添加新表

每份后续计划添加自家表的标准流程：

1. 在 `src/codeask/db/models/` 下新建模块（按业务域命名，如 `wiki.py` / `code_repo.py` / `session.py` / `agent_trace.py`）
2. 在 `src/codeask/db/models/__init__.py` 把新模型 re-export
3. 在 `alembic/versions/` 加一份新 migration，`down_revision` 指向上一个 revision
4. 用 `op.create_table(...)` 显式建表（不用 autogenerate，避免漂移）
5. 跑 `uv run pytest` 必须仍全绿（已有测试不能破）

**禁止**：直接在 `0001_initial.py` 中加表——0001 已发布，会 break 所有部署。

## 2. 添加新 API

1. 在 `src/codeask/api/` 下新建 router 模块
2. 在 `src/codeask/app.py` 的 `create_app()` 中 `app.include_router(..., prefix="/api")`
3. 路由处理函数通过 `request.app.state.session_factory` 拿 session，通过 `request.state.subject_id` 拿身份
4. 集成测试用 `tests/conftest.py` 提供的 `client` fixture

## 3. 加密敏感字段

任何 DB 字段存 LLM API key / 用户 token 等敏感数据时：
- 字段命名后缀 `_encrypted`
- 写入前用 `Crypto(settings.data_key).encrypt(plaintext)`
- 读出后用 `Crypto(settings.data_key).decrypt(ciphertext)`

不要绕过这层——原始密钥落库就是事故。

## 4. 新增配置

新计划如果需要新环境变量：
- 加到 `Settings` 类，字段名小写、加 `description`
- 改 README 的 Configuration 表格
- 如果是必填，用 `Field(...)` 强制，缺失时 fail-fast（不要默默 fallback）

## 5. 不在本地基范围

- LLM 网关：04 agent-runtime 计划负责（含 `CODEASK_DATA_KEY` vs llm-gateway.md 旧文档 `CODEASK_MASTER_KEY` 的统一）
- 仓库 / worktree：03 code-index 计划负责
- 文档 / 报告 / FTS5：02 wiki-knowledge 计划负责
- agent_traces / feedback / frontend_events / audit_log：04 / 06 各自负责
- 前端编译产物挂载：05 frontend-workbench 计划负责
- 容器化包装 / 多阶段镜像：后续独立 packaging 计划负责，不属于 v1.0 deployment

## 6. SDD 文档同步

凡是改动了某个 SDD 文档对应的实现，要同步更新该文档的"与 PRD 的对齐"小节。本计划没有改动任何 SDD，因为它就是 SDD 的第一次实现。
````

- [ ] **Step 2: 提交**

```bash
git add docs/v1.0/plans/foundation-handoff.md
git commit -m "docs(plans): foundation hand-off conventions for follow-on plans"
```

---

## 验收标志（计划完整通过后应满足）

- [x] `./start.sh` 在 30 秒内（本机首次 `uv sync` 之后）跑起服务
- [x] `curl http://127.0.0.1:8000/api/healthz` 返回 `{"status":"ok","db":"ok","version":"0.1.0","subject_id":...}`
- [x] `~/.codeask/data.db` 创建，含 `system_settings` 表，`alembic_version` 表显示 head 是 `0001`
- [x] `~/.codeask/{wiki,skills,sessions,repos,index,logs}` 目录就绪
- [x] 缺失 `CODEASK_DATA_KEY` 时 `start.sh` 给清晰错误，**不**启动到一半
- [x] 全量 `uv run pytest` 23 测试 PASS
- [x] `uv run ruff check && uv run pyright src/codeask` 零错误
- [x] git tag `foundation-v0.1.0` 已打

---

## 不在本计划范围（明确推迟）

| 项 | 推迟到 | 原因 |
|---|---|---|
| 14 张业务表 + FTS5 | 02 / 03 / 04 / 06 各自负责 | 每份计划拥有自己的 schema，避免 foundation 膨胀 |
| LLM 网关接入 + `llm-gateway.md` 文档名修正 | 04 agent-runtime | 没有 LLM 调用就不需要 gateway 落地 |
| SSE 流 | 04 agent-runtime | healthz 不需要 |
| AuthProvider 协议 + `<UserMenu />` slot | MVP+（PRD §4.4.2） | 一期完全无鉴权 |
| Docker 多阶段构建 + alpine | 后续独立 packaging 计划 | start.sh 在 v1.0 小团队场景已足够 |
| 前端构建产物挂载 | 05 frontend-workbench | 一期前端独立 dev server，发布前再挂 |
| pre-commit / GitHub Actions | 07 deployment | 本计划只跑本地 lint + type check |
