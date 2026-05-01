# Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Status:** completed in `main`. Docker, compose, and image publishing remain intentionally deferred to a later packaging plan.

**Goal:** 落地 v1.0 的本地单进程部署链路：后端直接挂载前端构建产物、`start.sh` 负责裸机启动与前端构建兜底、前后端 CI 全绿、安全审计可重复执行。Docker、compose、镜像发布明确后置到后续非 v1.0 计划。

**Architecture:** 单进程 FastAPI 仍是部署核心，`frontend/dist/` 存在时由后端 `StaticFiles` 直接提供 SPA，不存在时开发态继续支持 Vite dev server。`start.sh` 只负责本地/裸机启动，不承担容器入口职责。CI 分成 backend 与 frontend 两条线，前端 e2e 在本地启动 backend 后运行。安全审计以 pytest + 手工 checklist 固化，保证路径、MIME、加密字段、默认监听这些边界不回退。

**Tech Stack:** FastAPI, uv, pnpm, React/Vite, pytest, Playwright, GitHub Actions, pre-commit, ruff, pyright, Pydantic, structlog

---

**Source SDD docs**（路径相对本文件 `docs/v1.0/plans/deployment.md`）：
- `../design/overview.md`
- `../design/deployment-security.md`
- `../design/dependencies.md`
- `../design/api-data-model.md`
- `../design/frontend-workbench.md`

**Depends on:**
- `docs/v1.0/plans/foundation.md`
- `docs/v1.0/plans/frontend-workbench.md`
- `docs/v1.0/plans/metrics-eval.md`
- `docs/v1.0/plans/agent-runtime.md`

**Project root:** `/home/hzh/workspace/CodeAsk/`（与 `docs/` 同级）。

---

## File Structure

```text
CodeAsk/
├── start.sh                                    # 修改：前端 dist 检查 + 自动构建或清晰警告
├── README.md                                   # 修改：本地启动、前端 dev、配置表
├── pyproject.toml                              # 修改：追加 pre-commit dev dependency
├── .pre-commit-config.yaml                     # 新增
├── src/codeask/
│   ├── app.py                                  # 修改：API 之后挂载 StaticFiles
│   └── settings.py                             # 修改：frontend_dist 配置
├── tests/
│   ├── integration/
│   │   ├── test_static_mount.py                # 新增
│   │   ├── test_security_checklist.py          # 新增
│   └── security/
│       ├── __init__.py                         # 新增
│       ├── test_grep_no_shell_true.py          # 新增
│       └── test_grep_default_bind.py           # 新增
├── .github/
│   └── workflows/
│       ├── backend.yml                         # 新增
│       └── frontend.yml                        # 新增
└── docs/
    └── v1.0/
        └── plans/
            └── deployment-security-checklist.md # 新增（自动 + 手工）
```

**职责边界**：
- `start.sh` 是本地 / 裸机入口，不做容器适配
- `StaticFiles` 只在 `frontend/dist/index.html` 存在时启用
- 前端开发仍然可以走 `frontend/` 下的 Vite dev server
- CI 不依赖 Docker；前端 e2e 通过本地启动 backend 完成
- Docker / compose / 镜像发布在后续独立计划处理，不属于 v1.0 deployment

---

## Task 1: 后端挂载前端构建产物

**Files:**
- Modify: `src/codeask/settings.py`
- Modify: `src/codeask/app.py`
- Create: `tests/integration/test_static_mount.py`

后端在 API 路由注册完成后，若检测到 `frontend/dist/index.html` 存在，就把整个 `frontend/dist/` 挂载到 `/`。这样 `uv run codeask` 即可同时提供 API 与 SPA。开发态如果没有 dist，应用必须继续启动，不能因为前端还没 build 就把 backend 卡死。

- [x] **Step 1: 写失败测试 `tests/integration/test_static_mount.py`**

```python
"""StaticFiles mount serves SPA without blocking /api/*."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from codeask.app import create_app
from codeask.settings import Settings


@pytest_asyncio.fixture()
async def app_with_dist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> AsyncIterator[FastAPI]:
    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path / "data"))

    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><html><body>codeask spa</body></html>")
    assets = dist / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('ok');")

    monkeypatch.setenv("CODEASK_FRONTEND_DIST", str(dist))
    settings = Settings()  # type: ignore[call-arg]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        yield app


@pytest.mark.asyncio
async def test_root_returns_spa_index(app_with_dist: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app_with_dist), base_url="http://test") as ac:
        r = await ac.get("/")
    assert r.status_code == 200
    assert "codeask spa" in r.text


@pytest.mark.asyncio
async def test_api_routes_still_reachable(app_with_dist: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app_with_dist), base_url="http://test") as ac:
        r = await ac.get("/api/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_static_assets_served(app_with_dist: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app_with_dist), base_url="http://test") as ac:
        r = await ac.get("/assets/app.js")
    assert r.status_code == 200
    assert "console.log" in r.text


@pytest.mark.asyncio
async def test_missing_dist_does_not_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CODEASK_FRONTEND_DIST", str(tmp_path / "missing"))

    settings = Settings()  # type: ignore[call-arg]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.get("/api/healthz")
        assert r.status_code == 200
```

- [x] **Step 2: 在 `src/codeask/settings.py` 追加 `frontend_dist` 字段**

在 `database_url` 之后追加：

```python
    frontend_dist: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[2] / "frontend" / "dist",
        description="Path to compiled SPA served from / when index.html exists.",
    )
```

- [x] **Step 3: 在 `src/codeask/app.py` 的 API 路由之后挂载 StaticFiles**

在 `app.include_router(sessions_router, prefix="/api")` 之后追加：

```python
    from fastapi.staticfiles import StaticFiles

    dist = settings.frontend_dist
    if (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="static")
        log.info("static_mounted", path=str(dist))
    else:
        log.warning(
            "frontend_dist_missing",
            path=str(dist),
            hint=(
                "run `corepack pnpm --dir frontend build` or set CODEASK_FRONTEND_DIST; "
                "API still works (frontend dev server can proxy /api to :8000)"
            ),
        )
```

- [x] **Step 4: 跑测试**

Run: `uv run pytest tests/integration/test_static_mount.py -v`

Expected: 4 个测试全部 PASS。

- [x] **Step 5: 提交**

```bash
git add src/codeask/settings.py src/codeask/app.py tests/integration/test_static_mount.py
git commit -m "feat(app): serve frontend/dist from backend after api routes"
```

---

## Task 2: 本地启动脚本增强

**Files:**
- Modify: `start.sh`

`start.sh` 保持 foundation 的职责不变：校验 `CODEASK_DATA_KEY`、执行 `uv sync`、启动应用。新增的只是前端兜底逻辑：如果 `frontend/dist/index.html` 不存在，就在 `corepack pnpm` 可用时自动构建；如果不可用，则发出清晰警告但继续启动 backend。

- [x] **Step 1: 更新 `start.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

# CodeAsk start script for bare-metal / local-dev deployments.
#
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

if [[ ! -f frontend/dist/index.html ]]; then
    if command -v corepack >/dev/null 2>&1 && command -v pnpm >/dev/null 2>&1; then
        echo "frontend/dist not found — building frontend with pnpm..."
        corepack pnpm --dir frontend install --frozen-lockfile
        corepack pnpm --dir frontend build
    else
        cat >&2 <<EOF
WARNING: frontend/dist/index.html not found.

The backend will still start and /api/* will work.
To serve the SPA, build the frontend first:
    cd frontend
    corepack pnpm install --frozen-lockfile
    corepack pnpm build

Or run the frontend dev server while the backend is running:
    cd frontend
    corepack pnpm dev
EOF
    fi
fi

echo "Starting CodeAsk on ${CODEASK_HOST:-127.0.0.1}:${CODEASK_PORT:-8000}"
echo "Data dir: ${CODEASK_DATA_DIR:-$HOME/.codeask}"

exec uv run codeask
```

- [x] **Step 2: 保留可执行权限**

```bash
chmod +x start.sh
```

- [x] **Step 3: 回归 foundation 的启动约束**

```bash
unset CODEASK_DATA_KEY
./start.sh
```

Expected: stderr 提示 `CODEASK_DATA_KEY is not set`，进程退出码为 `1`。

- [x] **Step 4: 验证 dist 缺失时的兜底**

```bash
export CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
export CODEASK_DATA_DIR=/tmp/codeask-startsh
rm -rf "$CODEASK_DATA_DIR" frontend/dist
./start.sh &
SERVER_PID=$!
sleep 3
curl -fs http://127.0.0.1:8000/api/healthz | python -m json.tool
kill "$SERVER_PID"
```

Expected: healthz 通过，stderr 有 frontend build 或 warning 信息。

- [x] **Step 5: 验证 dist 存在时 `/` 可直接访问**

```bash
mkdir -p frontend/dist
echo '<!doctype html><body>spa</body>' > frontend/dist/index.html
export CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
./start.sh &
SERVER_PID=$!
sleep 3
curl -fs http://127.0.0.1:8000/ | head -1
curl -fs http://127.0.0.1:8000/api/healthz | python -m json.tool
kill "$SERVER_PID"
rm -rf frontend/dist
```

Expected: `/` 返回 SPA 页面，`/api/healthz` 返回 `ok`。

- [x] **Step 6: 提交**

```bash
git add start.sh
git commit -m "feat(start.sh): auto-build frontend dist when needed"
```

---

## Task 3: README 本地部署与开发路径

**Files:**
- Modify: `README.md`

README 要把一期真实可用的路径讲清楚：`./start.sh` 是本地单机启动入口；`frontend/` 下的 Vite dev server 是前端联调用；`frontend/dist/` 由 `pnpm build` 生成并可被后端直接服务。不要再把容器化写成一期默认路径。

- [x] **Step 1: 替换 README 的快速开始与部署说明**

````markdown
## 快速启动

```bash
# 1) 生成一次加密密钥，并把它保存到安全位置
export CODEASK_DATA_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

# 2) 启动服务
./start.sh
```

服务默认监听：

```text
http://127.0.0.1:8000
```

如果 `frontend/dist/index.html` 不存在，`start.sh` 会在 `corepack pnpm` 可用时自动构建前端，否则只启动 backend 并提示你手动构建。

### 前端联调

```bash
cd frontend
corepack pnpm install
corepack pnpm dev
```

前端开发服务器监听 `http://127.0.0.1:5173`，会把 `/api/*` 反代到后端 `:8000`。

### 测试

```bash
uv run pytest
(cd frontend && corepack pnpm test:run)
(cd frontend && corepack pnpm build)
```
````

- [x] **Step 2: 更新配置表**

把配置表改成只保留与本地启动有关的字段：

```markdown
| Env var | Required | Default | Notes |
|---|---|---|---|
| `CODEASK_DATA_KEY` | yes | — | Fernet key. Lose it = lose encrypted fields. |
| `CODEASK_DATA_DIR` | no | `~/.codeask` | SQLite、上传物、worktree、日志根目录。 |
| `CODEASK_HOST` | no | `127.0.0.1` | 本地单机默认只监听回环地址。 |
| `CODEASK_PORT` | no | `8000` | |
| `CODEASK_LOG_LEVEL` | no | `INFO` | |
| `CODEASK_DATABASE_URL` | no | derived | 仅测试或迁移时覆盖。 |
| `CODEASK_FRONTEND_DIST` | no | `<repo>/frontend/dist` | 自定义前端构建产物目录。 |
```

- [x] **Step 3: 更新仓库结构与实现状态段落**

删除 README 里任何 `docker/` 目录展示、Docker 部署说明和“镜像会在 deployment 阶段内置”之类的句子，改成：

```markdown
后续如果需要容器化分发，会作为单独的后置计划处理，不属于 v1.0 deployment。
```

- [x] **Step 4: 提交**

```bash
git add README.md
git commit -m "docs(readme): document local deployment and frontend dev flow"
```

---

## Task 4: pre-commit 与基础格式化

**Files:**
- Create: `.pre-commit-config.yaml`
- Modify: `pyproject.toml`

`dependencies.md` 已锁定 ruff 与 pre-commit。这里把最基本的质量门加上：空白、EOF、TOML/JSON/YAML 基础检查、Python 的 ruff、前端文件的 prettier。

- [x] **Step 1: 新增 `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
        args: [--allow-multiple-documents]
      - id: check-added-large-files
        args: [--maxkb=512]
      - id: check-merge-conflict
      - id: check-toml
      - id: check-json
        exclude: ^frontend/tsconfig.*\.json$

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.7.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v4.0.0-alpha.8
    hooks:
      - id: prettier
        files: ^frontend/.*\.(ts|tsx|css|scss|json|md|yml|yaml|html)$
        exclude: ^frontend/(dist|node_modules|tsconfig.*\.json)
```

- [x] **Step 2: 在 `pyproject.toml` 的 dev 依赖组中追加 `pre-commit`**

```toml
[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-httpx>=0.32",
    "ruff>=0.7",
    "pyright>=1.1.385",
    "pre-commit>=4.0",
]
```

- [x] **Step 3: 安装并跑一次**

```bash
uv sync
uv run pre-commit install
uv run pre-commit run --all-files
```

Expected: 首次执行可能自动修复格式，第二次必须全绿。

- [x] **Step 4: 提交**

```bash
git add .pre-commit-config.yaml pyproject.toml uv.lock
git commit -m "chore(precommit): add baseline hooks for backend and frontend"
```

---

## Task 5: GitHub Actions - backend 与 frontend

**Files:**
- Create: `.github/workflows/backend.yml`
- Create: `.github/workflows/frontend.yml`

v1.0 只保留两条 CI：backend 和 frontend。backend 跑 lint / type / pytest；frontend 跑 typecheck / unit / build / e2e，并在 job 内本地启动 backend，不依赖容器。

- [x] **Step 1: 创建 `.github/workflows/backend.yml`**

```yaml
name: backend

on:
  push:
    branches: [main]
    paths:
      - "src/**"
      - "tests/**"
      - "alembic/**"
      - "alembic.ini"
      - "pyproject.toml"
      - "uv.lock"
      - ".python-version"
      - ".github/workflows/backend.yml"
  pull_request:
    branches: [main]

concurrency:
  group: backend-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    env:
      CODEASK_DATA_KEY: TGltSXRlc3Rrcm5hYmFzZTY0LXVybHNhZmUtMzJieXRlcw==
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: "0.5.4"
          enable-cache: true

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version-file: ".python-version"

      - name: Install system tools
        run: sudo apt-get update && sudo apt-get install -y --no-install-recommends ripgrep universal-ctags

      - name: uv sync
        run: uv sync --frozen

      - name: Ruff lint
        run: uv run ruff check src tests

      - name: Ruff format check
        run: uv run ruff format --check src tests

      - name: Pyright
        run: uv run pyright src/codeask

      - name: Pytest
        run: uv run pytest -v --maxfail=1
```

- [x] **Step 2: 创建 `.github/workflows/frontend.yml`**

```yaml
name: frontend

on:
  push:
    branches: [main]
    paths:
      - "frontend/**"
      - "src/**"
      - "tests/**"
      - "pyproject.toml"
      - "uv.lock"
      - ".github/workflows/frontend.yml"
  pull_request:
    branches: [main]

concurrency:
  group: frontend-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 25
    env:
      CODEASK_DATA_KEY: TGltSXRlc3Rrcm5hYmFzZTY0LXVybHNhZmUtMzJieXRlcw==
    steps:
      - uses: actions/checkout@v4

      - name: Setup pnpm
        uses: pnpm/action-setup@v4
        with:
          version: 10

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: pnpm
          cache-dependency-path: frontend/pnpm-lock.yaml

      - name: Install frontend deps
        working-directory: frontend
        run: pnpm install --frozen-lockfile

      - name: Typecheck
        working-directory: frontend
        run: pnpm typecheck

      - name: Unit tests
        working-directory: frontend
        run: pnpm test:run

      - name: Build frontend
        working-directory: frontend
        run: pnpm build

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: "0.5.4"
          enable-cache: true

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version-file: ".python-version"

      - name: uv sync
        run: uv sync --frozen

      - name: Start backend
        run: |
          export CODEASK_FRONTEND_DIST="$GITHUB_WORKSPACE/frontend/dist"
          ./start.sh > /tmp/codeask-backend.log 2>&1 &
          echo $! > /tmp/codeask-backend.pid
          for i in {1..30}; do
            if curl -fs http://127.0.0.1:8000/api/healthz; then
              break
            fi
            sleep 1
          done

      - name: Install Playwright browsers
        working-directory: frontend
        run: pnpm exec playwright install --with-deps chromium

      - name: E2E
        working-directory: frontend
        env:
          PLAYWRIGHT_BASE_URL: http://127.0.0.1:8000
        run: pnpm test:e2e

      - name: Backend logs
        if: failure()
        run: cat /tmp/codeask-backend.log || true

      - name: Stop backend
        if: always()
        run: kill "$(cat /tmp/codeask-backend.pid)" || true
```

- [x] **Step 3: 跑本地验证**

如果本机有 `act`，执行：

```bash
act -W .github/workflows/backend.yml pull_request
act -W .github/workflows/frontend.yml pull_request
```

如果没有 `act`，就在 GitHub Actions 页面检查 workflow 触发是否符合预期。

- [x] **Step 4: 提交**

```bash
git add .github/workflows/backend.yml .github/workflows/frontend.yml
git commit -m "ci: split backend and frontend workflows for local deployment"
```

---

## Task 6: 安全审计 checklist 与 pytest

**Files:**
- Create: `tests/security/__init__.py`
- Create: `tests/security/test_grep_no_shell_true.py`
- Create: `tests/security/test_grep_default_bind.py`
- Create: `tests/integration/test_security_checklist.py`
- Create: `docs/v1.0/plans/deployment-security-checklist.md`

这一组测试把部署安全边界写死：默认只监听 `127.0.0.1`、生产代码不使用 `shell=True`、加密字段不落明文、路径读取拒绝越界、上传 MIME 校验能拦住伪装文件、匿名身份默认能生成。手工 checklist 只保留本地单机部署相关项，不再写任何容器内容。

- [x] **Step 1: 新增 `tests/security/__init__.py`**

```python
"""Security regression tests for deployment boundaries."""
```

- [x] **Step 2: 新增 `tests/security/test_grep_no_shell_true.py`**

```python
"""Static check: production source must not use shell=True."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
PATTERN = re.compile(r"\bshell\s*=\s*True\b")


def test_no_shell_true_in_src() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if PATTERN.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, "shell=True found in production source:\n  " + "\n  ".join(offenders)
```

- [x] **Step 3: 新增 `tests/security/test_grep_default_bind.py`**

```python
"""Static check: business code must not hard-code 0.0.0.0."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
PATTERN = re.compile(r'["\']0\.0\.0\.0["\']')


def test_no_business_zero_zero_zero_zero() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if PATTERN.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Hard-coded 0.0.0.0 found in src/. Default bind must be 127.0.0.1:\n  "
        + "\n  ".join(offenders)
    )
```

- [x] **Step 4: 新增 `tests/integration/test_security_checklist.py`**

```python
"""Behavioral security regressions tied to deployment-security.md."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from codeask.app import create_app
from codeask.crypto import Crypto
from codeask.settings import Settings


@pytest_asyncio.fixture()
async def app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[FastAPI]:
    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    settings = Settings()  # type: ignore[call-arg]
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


def test_default_settings_bind_localhost(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CODEASK_HOST", raising=False)
    s = Settings()  # type: ignore[call-arg]
    assert s.host == "127.0.0.1"


@pytest.mark.asyncio
async def test_encrypted_field_is_not_plaintext_in_db(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("CODEASK_DATA_KEY", key)
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))

    settings = Settings()  # type: ignore[call-arg]
    application = create_app(settings)
    secret = "sk-supersecret-deadbeef-0000"
    async with application.router.lifespan_context(application):
        factory = application.state.session_factory
        c = Crypto(settings.data_key)
        ciphertext = c.encrypt(secret)
        async with factory() as s:
            await s.execute(
                text("INSERT INTO system_settings(key, value) VALUES (:k, :v)"),
                {"k": "llm.api_key_encrypted", "v": f'"{ciphertext}"'},
            )
            await s.commit()

    db_path = tmp_path / "data.db"
    assert db_path.is_file()
    raw = db_path.read_bytes()
    assert secret.encode() not in raw
    assert c.decrypt(ciphertext) == secret


def test_safe_join_rejects_traversal(tmp_path: Path) -> None:
    pytest.importorskip(
        "codeask.fs_safety",
        reason="If fs_safety is not yet wired by earlier plans, skip until it lands",
    )
    from codeask.fs_safety import PathOutsideRoot, safe_join

    root = tmp_path / "root"
    root.mkdir()
    assert safe_join(root, "a/b.txt").is_relative_to(root)
    with pytest.raises(PathOutsideRoot):
        safe_join(root, "../etc/passwd")
    with pytest.raises(PathOutsideRoot):
        safe_join(root, "/etc/passwd")


def test_upload_mime_rejects_exe_disguised_as_pdf(tmp_path: Path) -> None:
    pytest.importorskip(
        "codeask.wiki.uploads",
        reason="If wiki upload validator is not yet wired, skip until it lands",
    )
    from codeask.wiki.uploads import UnsupportedMime, validate_upload

    fake = tmp_path / "evil.pdf"
    fake.write_bytes(b"MZ\x90\x00\x03\x00" + b"\x00" * 1024)
    with pytest.raises(UnsupportedMime):
        validate_upload(fake, declared_mime="application/pdf")


@pytest.mark.asyncio
async def test_anonymous_subject_id_assigned(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/healthz")
    assert r.status_code == 200
    assert r.json()["subject_id"].startswith("anonymous@")
```

- [x] **Step 5: 新增 `docs/v1.0/plans/deployment-security-checklist.md`**

````markdown
# Deployment Security Checklist

> Companion to `docs/v1.0/plans/deployment.md`. Maps deployment-security.md §5–§7 to auto and manual checks.

## Auto (pytest)

| ID | Checklist line | Test |
|---|---|---|
| AUTO-1 | shell 调用使用参数数组，不使用 `shell=True` | `tests/security/test_grep_no_shell_true.py` |
| AUTO-2 | 默认监听 127.0.0.1（代码默认值） | `tests/security/test_grep_default_bind.py` |
| AUTO-3 | 默认监听 127.0.0.1（Settings 运行时默认） | `tests/integration/test_security_checklist.py::test_default_settings_bind_localhost` |
| AUTO-4 | LLM API Key 加密存储 | `tests/integration/test_security_checklist.py::test_encrypted_field_is_not_plaintext_in_db` |
| AUTO-5 | 路径读取做根目录校验 | `tests/integration/test_security_checklist.py::test_safe_join_rejects_traversal` |
| AUTO-6 | 上传文件做 MIME 和后缀检查 | `tests/integration/test_security_checklist.py::test_upload_mime_rejects_exe_disguised_as_pdf` |
| AUTO-7 | 匿名身份默认生成 | `tests/integration/test_security_checklist.py::test_anonymous_subject_id_assigned` |

Run:

```bash
uv run pytest tests/security tests/integration/test_security_checklist.py -v
```

## Manual

| ID | Step |
|---|---|
| MANUAL-1 | `./start.sh` 在干净环境里启动，`/api/healthz` 返回 `ok`。 |
| MANUAL-2 | `./start.sh` 缺少 `CODEASK_DATA_KEY` 时退出并打印明确错误。 |
| MANUAL-3 | `frontend/dist/index.html` 存在时，`/` 直接返回 SPA。 |
| MANUAL-4 | `frontend/dist/index.html` 不存在时，backend 仍然启动且 `/api/*` 可用。 |
| MANUAL-5 | `frontend/` 通过 `corepack pnpm dev` 运行时可正常代理 `/api/*`。 |
| MANUAL-6 | 手工检查结构化日志输出为 JSON。 |

## When a checklist line moves from manual to auto

1. 在 `tests/security/` 或 `tests/integration/test_security_checklist.py` 新增测试。
2. 更新上面的 AUTO/MANUAL 表。
3. 同一个 PR 里合入，避免口头约定漂移。
````

- [x] **Step 6: 跑安全测试**

```bash
uv run pytest tests/security tests/integration/test_security_checklist.py -v
```

Expected: PASS，允许 `pytest.importorskip` 标记的 skip。

- [x] **Step 7: 提交**

```bash
git add tests/security/ tests/integration/test_security_checklist.py docs/v1.0/plans/deployment-security-checklist.md
git commit -m "feat(security): pytest-backed deployment safety checks"
```

---

## Task 7: 全量回归与本地发布自检

**Files:**
- 无新增文件

最后一轮把 deployment 相关改动整体跑通，确认本地启动、前端静态挂载、CI、预提交和安全边界都收口。Docker / compose / 镜像发布不在本轮验收内。

- [x] **Step 1: 跑后端检查**

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pyright src/codeask
uv run pytest -v
```

Expected: 全部 PASS。

- [x] **Step 2: 跑 pre-commit**

```bash
uv run pre-commit run --all-files
```

Expected: 全部 hook PASS；如有自动修复，第二次运行必须无变更。

- [x] **Step 3: 本地启动 smoke**

```bash
export CODEASK_DATA_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
./start.sh &
SERVER_PID=$!
sleep 3
curl -fs http://127.0.0.1:8000/api/healthz | python -m json.tool
kill "$SERVER_PID"
```

Expected: `status: ok`，backend 正常启动。

- [x] **Step 4: 前端静态产物 smoke**

```bash
cd frontend
corepack pnpm install
corepack pnpm build
cd ..
export CODEASK_DATA_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
./start.sh &
SERVER_PID=$!
sleep 3
curl -fs http://127.0.0.1:8000/ | head -1
kill "$SERVER_PID"
```

Expected: `/` 返回 SPA HTML。

- [x] **Step 5: 提交**

```bash
git add start.sh README.md src/codeask/app.py src/codeask/settings.py \
        .pre-commit-config.yaml pyproject.toml .github/workflows/backend.yml \
        .github/workflows/frontend.yml tests/security tests/integration \
        docs/v1.0/plans/deployment-security-checklist.md
git commit -m "feat(deployment): ship local single-process deployment without docker"
```

---

## Deferred to a later plan

The following are intentionally **not** part of this v1.0 deployment plan:

- Dockerfile / compose packaging
- Image build and push workflows
- Container-specific security checklist items
- Image size budget and non-root container verification

These will be planned as a separate post-v1.0 packaging task once the local deployment path is stable.
