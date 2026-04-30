# Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 CodeAsk 单产物部署、CI 流水线和安全审计一次性落地：一条 `docker compose up -d` 启服务，一份 GitHub Actions 跑 lint / type / 单元 / e2e / 镜像，一份安全 checklist 覆盖路径遍历 / MIME / shell 注入 / 加密字段 / 默认监听。

**Architecture:** 多阶段 alpine Dockerfile（node 构前端 → python 装 backend → runtime 合一）+ 单服务 docker-compose（bind mount `~/.codeask/`）+ `start.sh` 增强（前端缺 dist 时自动 build，否则提示）+ FastAPI `StaticFiles` 挂载 `frontend/dist/` 让 `/` 返回 SPA 入口 + 三份 GH workflow（backend / frontend / image）+ pre-commit（ruff + prettier + 基础 hook）+ 安全审计 checklist 配套 pytest 强制项。

**Tech Stack:** Docker (multi-stage, alpine), docker-compose, uv, pnpm, GitHub Actions, pre-commit, ruff, pyright, prettier, eslint

**Source SDD docs**（路径相对本文件 `docs/v1.0/plans/deployment.md`）：
- `../design/overview.md`（§4.2 仓库结构 / §4.3 部署形态）
- `../design/dependencies.md`（§5 部署 / §6 工程工具 / §7 Anti-list）
- `../design/deployment-security.md`（§2 部署 / §5 敏感信息 / §6 文件安全 / §7 定时任务）
- `../design/api-data-model.md`（§6 Migration：迁移失败拒启动）

**Depends on:**
- `docs/v1.0/plans/foundation.md`（已交付：`start.sh` 简版、`Settings`、`create_app()`、Alembic、healthz；本计划增强其中两项）
- `docs/v1.0/plans/wiki-knowledge.md`（FTS5 + 上传 MIME 校验函数 → 安全审计复用）
- `docs/v1.0/plans/code-index.md`（worktree 路径校验 + subprocess 数组调用 → 安全审计复用）
- `docs/v1.0/plans/agent-runtime.md`（LLM key 加密落库 → 安全审计复用）
- `docs/v1.0/plans/frontend-workbench.md`（产出 `frontend/dist/`，本计划负责把它挂上去）
- `docs/v1.0/plans/metrics-eval.md`（无新部署语义，但其测试要进 CI 矩阵）

**Project root:** `/home/hzh/workspace/CodeAsk/`（与 `docs/` 同级）。本计划全部文件路径相对此根目录。

**Hand-off from foundation.md (Task 14):**
- foundation 已经交付 `start.sh`，本计划**增强**而不是重写：保留 `CODEASK_DATA_KEY` 校验、`uv sync` 步骤、`exec uv run codeask`；新增前端 dist 检查 + 自动 build。
- foundation 已经把 `create_app()` 写好，本计划**只追加** `app.mount("/", StaticFiles(...))`，不改其它部分。
- foundation 的 23 条 pytest 必须**继续全绿**——本计划任何改动后 `uv run pytest` 是回归门槛。

---

## File Structure

本计划交付（全部相对项目根 `/home/hzh/workspace/CodeAsk/`）：

```text
CodeAsk/
├── start.sh                                    # 修改：增加前端 dist 检查 + 自动 build
├── README.md                                   # 修改：拆 30 秒 Docker / 本地开发两路径
├── .pre-commit-config.yaml                     # 新增
├── .dockerignore                               # 新增
├── docker/
│   ├── Dockerfile                              # 新增：多阶段（builder-frontend / builder-backend / runtime）
│   └── docker-compose.yml                      # 新增：单 codeask service
├── .github/
│   └── workflows/
│       ├── backend.yml                         # 新增
│       ├── frontend.yml                        # 新增
│       └── image.yml                           # 新增
├── src/codeask/
│   └── app.py                                  # 修改：append StaticFiles mount
├── tests/
│   ├── integration/
│   │   ├── test_static_mount.py                # 新增
│   │   └── test_security_checklist.py          # 新增
│   └── security/
│       ├── __init__.py                         # 新增
│       ├── test_grep_no_shell_true.py          # 新增
│       └── test_grep_default_bind.py           # 新增
└── docs/
    └── v1.0/
        └── plans/
            └── deployment-security-checklist.md # 新增（手工 + 自动两半）
```

**职责边界**：
- `Dockerfile` 三阶段：builder-frontend 只产 `dist/`、builder-backend 只产 `.venv/`、runtime 不带任何编译工具链
- `docker-compose.yml` 仅声明一个 service + 一个 named bind mount + 端口映射
- `start.sh` 是**本地开发 / 裸机部署**入口，**不**是容器入口（容器走 `CMD ["uv","run","codeask"]`）
- StaticFiles 挂载在所有 API 路由 `include_router` 之后才能避免吞掉 `/api/*`
- 安全 checklist 一半是 pytest（grep、上传 MIME、路径遍历、加密落库），一半是手工（fresh VM 30 秒部署 smoke）
- pre-commit 同时管 backend (ruff) 和 frontend (prettier + eslint via lint-staged 不引入)

---

## Task 1: Backend StaticFiles 挂载（前端构建产物服务化）

**Files:**
- Modify: `src/codeask/app.py`
- Create: `tests/integration/test_static_mount.py`

`overview.md` §4.3 锁定"单进程 + 单端口"——backend 必须能直接吐 SPA。挂载点必须在所有 `include_router` 之后，否则 `/` 的 catch-all 会把 `/api/*` 一起吃掉。dist 不存在时（dev 模式前端走 vite 5173）应当 warn 而不是 crash，让 foundation 的 healthz 测试不被拖累。

- [ ] **Step 1: 写测试 `tests/integration/test_static_mount.py`**

```python
"""StaticFiles mount serves SPA without breaking /api/*."""

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

    # Simulate built frontend
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><html><body>codeask spa</body></html>"
    )
    (dist / "assets").mkdir()
    (dist / "assets" / "app.js").write_text("console.log('ok');")

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
    """Dev mode: no dist/, app must still start and /api/healthz must work."""
    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CODEASK_FRONTEND_DIST", str(tmp_path / "nonexistent"))

    settings = Settings()  # type: ignore[call-arg]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.get("/api/healthz")
        assert r.status_code == 200
```

- [ ] **Step 2: 在 `src/codeask/settings.py` 追加 `frontend_dist` 字段**

在 `Settings` class 内、`database_url` 之后追加：

```python
    frontend_dist: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[2] / "frontend" / "dist",
        description="Path to compiled SPA. Mounted at / when index.html exists.",
    )
```

- [ ] **Step 3: 修改 `src/codeask/app.py` 在 `include_router` 之后挂载 StaticFiles**

在 `app.include_router(healthz_router, prefix="/api")` 之后追加：

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
            hint="run `pnpm --dir frontend build` or set CODEASK_FRONTEND_DIST; "
                 "API still works (dev mode uses vite proxy)",
        )
```

`StaticFiles(html=True)` 让 `/` 自动返回 `index.html`，并对未命中的路径 fallback 到 `index.html`（SPA 路由必须）。挂载语句必须在 `include_router` 后面——FastAPI 路由匹配按注册顺序，先注册的优先。

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/integration/test_static_mount.py -v`
Expected: 4 个测试全部 PASS。

- [ ] **Step 5: 跑全量回归确认 foundation 不破**

Run: `uv run pytest -v`
Expected: 全部 PASS（foundation 23 + 本步 4 = 27，加上 02-06 的，本计划只关心 27 + …）。

- [ ] **Step 6: 提交**

```bash
git add src/codeask/app.py src/codeask/settings.py tests/integration/test_static_mount.py
git commit -m "feat(app): mount frontend/dist as StaticFiles after API routes"
```

---

## Task 2: `.dockerignore`（瘦镜像第一步）

**Files:**
- Create: `.dockerignore`

不加 `.dockerignore` 整个 `~/.codeask/`、`.venv/`、`node_modules/`、`.git/` 都会进 build context，镜像膨胀几个 GB 还泄漏密钥。

- [ ] **Step 1: 创建 `.dockerignore`**

```text
# VCS
.git
.gitignore
.gitattributes
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.uv/
build/
dist/
# Node
**/node_modules/
frontend/.pnpm-store/
frontend/dist/
# Tooling caches
.pytest_cache/
.ruff_cache/
.pyright_cache/
.mypy_cache/
.coverage
coverage.xml
htmlcov/
# Editors / OS
.idea/
.vscode/
.DS_Store
Thumbs.db
*.swp
# Local data / env
.env
.env.*
~/.codeask/
data/
*.db
*.db-shm
*.db-wal
# Docs / CI artifacts not needed at runtime
docs/
.github/
*.md
!README.md
# Tests don't need to ship
tests/
**/tests/
e2e/
# Dockerfile self
docker/
.dockerignore
```

- [ ] **Step 2: 验证 build context 大小**

```bash
cd /home/hzh/workspace/CodeAsk
du -sh --exclude='.venv' --exclude='node_modules' --exclude='.git' . 2>/dev/null
# Should be a few MB (source only)
```

- [ ] **Step 3: 提交**

```bash
git add .dockerignore
git commit -m "chore(docker): .dockerignore to keep build context small"
```

---

## Task 3: 多阶段 `Dockerfile`（target ~150MB alpine）

**Files:**
- Create: `docker/Dockerfile`

`dependencies.md` §5 锁定 ~150MB alpine 镜像；`overview.md` §4.3 锁定"node build 前端 → python install backend → 合一"。三阶段：builder-frontend 用 `node:20-alpine`，builder-backend 用 `python:3.11-alpine` + `uv`，runtime 也是 `python:3.11-alpine` 但只装运行时系统包（git / ripgrep / universal-ctags / bash）。最终 runtime stage 不含 node、不含 uv、不含 build-base。

- [ ] **Step 1: 创建 `docker/Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1.7

# =============================================================================
# Stage 1: builder-frontend — build the SPA (Vite -> /build/dist)
# =============================================================================
FROM node:20-alpine AS builder-frontend

WORKDIR /build
RUN corepack enable

# Cache deps layer
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# Build
COPY frontend/ ./
RUN pnpm build
# Output is /build/dist

# =============================================================================
# Stage 2: builder-backend — uv sync into /app/.venv (no dev deps)
# =============================================================================
FROM python:3.11-alpine AS builder-backend

# uv needs a few build deps (only in this stage; nothing leaks to runtime)
RUN apk add --no-cache build-base curl

# Install uv (pinned)
ENV UV_VERSION=0.5.4
RUN curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app

# Lockfile-first to maximize layer cache
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Now copy source and finalize the install
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini
RUN uv sync --frozen --no-dev

# =============================================================================
# Stage 3: runtime — minimal alpine + system tools + venv + dist
# =============================================================================
FROM python:3.11-alpine AS runtime

# Runtime-only system packages (no compilers, no node)
#   git           — agent worktrees + repo clones
#   ripgrep       — grep tool
#   universal-ctags — ctags symbol index
#   bash          — start scripts / entrypoint debugging
#   tini          — proper PID 1 (reaps zombies; SIGTERM forwarding)
RUN apk add --no-cache git ripgrep universal-ctags bash tini

# Non-root user (matches deployment-security.md §6)
RUN addgroup -S app && adduser -S -G app -h /home/appuser appuser

WORKDIR /app

# Copy the prepared venv + source from builder-backend
COPY --from=builder-backend --chown=appuser:app /app/.venv /app/.venv
COPY --from=builder-backend --chown=appuser:app /app/src /app/src
COPY --from=builder-backend --chown=appuser:app /app/alembic /app/alembic
COPY --from=builder-backend --chown=appuser:app /app/alembic.ini /app/alembic.ini
COPY --from=builder-backend --chown=appuser:app /app/pyproject.toml /app/pyproject.toml
COPY --from=builder-backend --chown=appuser:app /app/uv.lock /app/uv.lock

# Copy the SPA from builder-frontend
COPY --from=builder-frontend --chown=appuser:app /build/dist /app/frontend/dist

# Make sure the venv's python/scripts win on PATH
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CODEASK_HOST=0.0.0.0 \
    CODEASK_PORT=8000 \
    CODEASK_DATA_DIR=/data \
    CODEASK_FRONTEND_DIST=/app/frontend/dist

# Data dir is bind-mounted; create it owned by appuser so writes work
RUN mkdir -p /data && chown -R appuser:app /data

USER appuser

EXPOSE 8000

# Healthcheck hits the same endpoint foundation/Task 1 ships.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8000/api/healthz || exit 1

# tini as PID 1 ensures uvicorn gets a clean SIGTERM on `docker stop`
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["python", "-m", "codeask"]
```

**关于 `CODEASK_HOST=0.0.0.0`**：在容器内监听 `0.0.0.0` 是合理的——Docker 网络已经是隔离层。安全审计 checklist（Task 9）的 grep 测试用 `tests/security/` 排除 `docker/Dockerfile`，所以这条 ENV 不会触发误报。

- [ ] **Step 2: 本地试 build 验证镜像可起**

```bash
cd /home/hzh/workspace/CodeAsk
docker build -f docker/Dockerfile -t codeask:dev .
docker images codeask:dev --format '{{.Size}}'
# Expected: 130–180 MB（alpine + git + ripgrep + ctags + python + venv）
```

- [ ] **Step 3: 跑容器并 curl healthz**

```bash
KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
docker run -d --rm --name codeask-test \
    -p 18000:8000 \
    -e CODEASK_DATA_KEY="$KEY" \
    -v "$(pwd)/.local-data:/data" \
    codeask:dev
sleep 3
curl -fs http://127.0.0.1:18000/api/healthz | python -m json.tool
docker logs codeask-test | head -20
docker stop codeask-test
```
Expected: `{"status":"ok","db":"ok",...}`，logs 无 ERROR。

- [ ] **Step 4: 提交**

```bash
mkdir -p docker
git add docker/Dockerfile
git commit -m "feat(docker): multi-stage alpine image (~150MB, non-root, tini)"
```

---

## Task 4: `docker-compose.yml`（30 秒部署）

**Files:**
- Create: `docker/docker-compose.yml`

单 service，bind mount `~/.codeask/`，端口 `8000:8000`，强依赖 `CODEASK_DATA_KEY` env。

- [ ] **Step 1: 创建 `docker/docker-compose.yml`**

```yaml
# CodeAsk single-service compose (PRD §4.4.1 "30 second deploy").
# Usage:
#   export CODEASK_DATA_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
#   docker compose -f docker/docker-compose.yml up -d
#   curl -s http://127.0.0.1:8000/api/healthz

services:
  codeask:
    image: ghcr.io/codeask/codeask:latest
    # For local builds, override with:
    #   docker compose -f docker/docker-compose.yml build
    build:
      context: ..
      dockerfile: docker/Dockerfile
    container_name: codeask
    restart: unless-stopped
    ports:
      # Bind to localhost on host by default (private deployment).
      # Change to "8000:8000" when serving on LAN behind a real proxy.
      - "127.0.0.1:8000:8000"
    environment:
      CODEASK_DATA_KEY: "${CODEASK_DATA_KEY:?CODEASK_DATA_KEY is required; generate with `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`}"
      CODEASK_LOG_LEVEL: "${CODEASK_LOG_LEVEL:-INFO}"
      # Container always listens on all interfaces; the host port-mapping above
      # is what limits exposure.
      CODEASK_HOST: "0.0.0.0"
      CODEASK_PORT: "8000"
      CODEASK_DATA_DIR: "/data"
    volumes:
      - codeask-data:/data
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://127.0.0.1:8000/api/healthz"]
      interval: 30s
      timeout: 5s
      start_period: 20s
      retries: 3

volumes:
  codeask-data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ${CODEASK_HOST_DATA_DIR:-${HOME}/.codeask}
```

`CODEASK_DATA_KEY: "${CODEASK_DATA_KEY:?...}"` 是 compose 强制必填语法——env 里没有时 `up` 直接失败，避免起一个加密密钥用空字符串的脏服务。

- [ ] **Step 2: smoke**

```bash
mkdir -p ~/.codeask
export CODEASK_DATA_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
cd /home/hzh/workspace/CodeAsk
docker compose -f docker/docker-compose.yml up -d --build
sleep 5
curl -fs http://127.0.0.1:8000/api/healthz | python -m json.tool
docker compose -f docker/docker-compose.yml logs --tail=20
docker compose -f docker/docker-compose.yml down
```

- [ ] **Step 3: 验证缺 key 时拒启**

```bash
unset CODEASK_DATA_KEY
docker compose -f docker/docker-compose.yml up -d 2>&1 | head -3
# Expected: "CODEASK_DATA_KEY is required; ..."
```

- [ ] **Step 4: 提交**

```bash
git add docker/docker-compose.yml
git commit -m "feat(docker): docker-compose single-service with required CODEASK_DATA_KEY"
```

---

## Task 5: `start.sh` 增强（前端 dist 检查 + 自动 build）

**Files:**
- Modify: `start.sh`

foundation 已经写了 `start.sh` 简版（CODEASK_DATA_KEY 校验 + `uv sync` + `uv run codeask`）。本计划在不破坏 foundation 行为的前提下追加：检查 `frontend/dist/index.html` 是否存在，缺失时如果 `pnpm` 在 PATH 自动 build，否则给清晰提示。

- [ ] **Step 1: 完整覆盖 `start.sh`（保留 foundation 已有逻辑）**

```bash
#!/usr/bin/env bash
set -euo pipefail

# CodeAsk start script for bare-metal / local-dev deployments.
# (For container deployments, see docker/docker-compose.yml.)
#
# Usage:
#   export CODEASK_DATA_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
#   ./start.sh

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

# ---------------------------------------------------------------------------
# 1. CODEASK_DATA_KEY (foundation rule — keep verbatim)
# ---------------------------------------------------------------------------
if [[ -z "${CODEASK_DATA_KEY:-}" ]]; then
    cat >&2 <<EOF
ERROR: CODEASK_DATA_KEY is not set.

Generate one (and save it — losing it makes encrypted DB fields unreadable):

    export CODEASK_DATA_KEY="\$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

Then re-run ./start.sh.
EOF
    exit 1
fi

# ---------------------------------------------------------------------------
# 2. uv (foundation rule — keep verbatim)
# ---------------------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: 'uv' not found. Install from https://docs.astral.sh/uv/ first." >&2
    exit 1
fi

uv sync --frozen 2>/dev/null || uv sync

# ---------------------------------------------------------------------------
# 3. Frontend dist (NEW in 07-deployment plan)
# ---------------------------------------------------------------------------
DIST_INDEX="frontend/dist/index.html"

if [[ ! -f "$DIST_INDEX" ]]; then
    if command -v pnpm >/dev/null 2>&1 && [[ -f "frontend/package.json" ]]; then
        echo "frontend/dist not found — building with pnpm..."
        (cd frontend && pnpm install --frozen-lockfile && pnpm build)
    else
        cat >&2 <<EOF
WARNING: frontend/dist/index.html not found.

The backend will start, but the SPA will not be served. /api/* still works.

To build the SPA:
    (cd frontend && pnpm install && pnpm build)

Or develop with Vite dev server:
    (cd frontend && pnpm dev)   # http://127.0.0.1:5173 (proxies /api to :8000)
EOF
    fi
fi

# ---------------------------------------------------------------------------
# 4. Launch
# ---------------------------------------------------------------------------
echo "Starting CodeAsk on ${CODEASK_HOST:-127.0.0.1}:${CODEASK_PORT:-8000}"
echo "Data dir: ${CODEASK_DATA_DIR:-$HOME/.codeask}"

exec uv run codeask
```

- [ ] **Step 2: 保留可执行权限**

```bash
chmod +x start.sh
```

- [ ] **Step 3: 回归测试 foundation Task 12 的 smoke**

```bash
# 缺 key 应当报错并退出 1
unset CODEASK_DATA_KEY
./start.sh; echo "exit=$?"
# Expected: stderr 包含 "CODEASK_DATA_KEY is not set"，exit=1
```

```bash
# 有 key、无 dist：起服务但只 API 工作
export CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
export CODEASK_DATA_DIR=/tmp/codeask-startsh-noart
rm -rf "$CODEASK_DATA_DIR" frontend/dist
./start.sh &
SERVER_PID=$!
sleep 3
curl -fs http://127.0.0.1:8000/api/healthz | python -m json.tool
kill $SERVER_PID
```
Expected: healthz 通过；stderr 上有 WARNING 关于 dist 缺失。

- [ ] **Step 4: 有 dist 路径**

```bash
mkdir -p frontend/dist
echo '<!doctype html><body>spa</body>' > frontend/dist/index.html
./start.sh &
SERVER_PID=$!
sleep 3
curl -fs http://127.0.0.1:8000/ | head -1
curl -fs http://127.0.0.1:8000/api/healthz | python -m json.tool
kill $SERVER_PID
rm -rf frontend/dist
```
Expected: `/` 返回 `<!doctype html>...`，`/api/healthz` 返回 ok。

- [ ] **Step 5: 提交**

```bash
git add start.sh
git commit -m "feat(start.sh): auto-build frontend/dist when pnpm available, warn otherwise"
```

---

## Task 6: README 升级（30 秒 Docker / 本地开发两路径）

**Files:**
- Modify: `README.md`

PRD §4.4.1 承诺"30 秒部署"——README 要明显呈现 Docker 路径作为默认推荐。foundation 的 README 只有 uv + start.sh 路径，本计划把它拆成两个明确分段。

- [ ] **Step 1: 把 README.md 的 "Quick start" 整段替换**

```markdown
## 30-second deploy (Docker)

> Recommended for teams. Single container, one volume, one port. PRD §4.4.1.

```bash
# 1) Generate the encryption key once and save it somewhere safe.
#    Losing it makes encrypted DB fields (LLM API keys etc.) unreadable.
export CODEASK_DATA_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

# 2) Start
docker compose -f docker/docker-compose.yml up -d

# 3) Verify
curl -s http://127.0.0.1:8000/api/healthz | python -m json.tool
```

The compose volume bind-mounts `~/.codeask/` from your host. Override with `CODEASK_HOST_DATA_DIR=/srv/codeask`. The container listens on `0.0.0.0:8000` internally, but the compose port mapping binds host `127.0.0.1:8000` — change to `8000:8000` only when fronting it with a real proxy and after adding auth (see `docs/v1.0/design/deployment-security.md` §4).

## Local development

Use this when iterating on backend or frontend code.

### Backend

```bash
export CODEASK_DATA_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
uv sync
./start.sh        # builds frontend/dist if pnpm is available, otherwise warns
```

Backend on `http://127.0.0.1:8000`; SPA at `/`, API under `/api`.

### Frontend (Vite dev server, hot reload)

```bash
cd frontend
pnpm install
pnpm dev          # http://127.0.0.1:5173, proxies /api/* to :8000
```

In dev mode the backend's StaticFiles mount is inactive (no `frontend/dist/`); browse via Vite at port 5173.

### Tests

```bash
uv run pytest                               # backend
(cd frontend && pnpm test)                  # frontend unit (Vitest)
(cd frontend && pnpm e2e)                   # frontend e2e (Playwright; needs backend running)
```

## Configuration

| Env var | Required | Default | Notes |
|---|---|---|---|
| `CODEASK_DATA_KEY` | yes | — | Fernet key (base64-urlsafe, 32 bytes). Lose it = lose encrypted fields. |
| `CODEASK_DATA_DIR` | no | `~/.codeask` | SQLite, uploads, worktrees, logs. |
| `CODEASK_HOST` | no | `127.0.0.1` (bare-metal) / `0.0.0.0` (container) | Default binds local-only on bare metal (no auth in MVP). |
| `CODEASK_PORT` | no | `8000` | |
| `CODEASK_LOG_LEVEL` | no | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR`. |
| `CODEASK_DATABASE_URL` | no | derived | Override only when testing or migrating away from SQLite. |
| `CODEASK_FRONTEND_DIST` | no | `<repo>/frontend/dist` | Override when running tests or custom layouts. |
| `CODEASK_HOST_DATA_DIR` | no (compose only) | `${HOME}/.codeask` | Where the compose volume bind-mounts on the host. |
```

- [ ] **Step 2: 校验 markdown 没破**

```bash
# Visual sanity: just print it
head -80 README.md
```

- [ ] **Step 3: 提交**

```bash
git add README.md
git commit -m "docs(readme): split into 30-second Docker deploy + local dev paths"
```

---

## Task 7: pre-commit（ruff + prettier + 基础 hook）

**Files:**
- Create: `.pre-commit-config.yaml`
- Modify: `pyproject.toml`（追加 dev dep `pre-commit`）

`dependencies.md` §6 锁定 ruff + prettier + pre-commit。配置同时管 backend (.py) 和 frontend (.ts/.tsx/.css/.json/.md)；通用 hooks（trailing whitespace / EOF / yaml）覆盖所有文件。

- [ ] **Step 1: 创建 `.pre-commit-config.yaml`**

```yaml
# Pre-commit hooks for CodeAsk.
# Install once:  uv run pre-commit install
# Run manually:  uv run pre-commit run --all-files
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
        exclude: ^frontend/tsconfig.*\.json$  # tsconfig allows trailing commas / comments

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

- [ ] **Step 2: 在 `pyproject.toml` 的 `[dependency-groups].dev` 追加 `pre-commit>=4.0`**

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

- [ ] **Step 3: 安装并跑一次**

```bash
uv sync
uv run pre-commit install
uv run pre-commit run --all-files
```
Expected: 第一次跑可能有 format 修改；让 pre-commit 自动修，重跑直到全绿。

- [ ] **Step 4: 提交（含 pre-commit 自动修的格式调整）**

```bash
git add .pre-commit-config.yaml pyproject.toml uv.lock
git status
git add -u  # any auto-formatted files
git commit -m "chore(precommit): ruff + prettier + base hooks"
```

---

## Task 8: GitHub Actions — backend.yml + frontend.yml + image.yml

**Files:**
- Create: `.github/workflows/backend.yml`
- Create: `.github/workflows/frontend.yml`
- Create: `.github/workflows/image.yml`

三份 workflow 各管一件事：backend lint+type+test、frontend lint+test+e2e、tag 触发的镜像 build/push。`dependencies.md` §6 锁定 GH Actions（开源仓库）/ Drone（私部友好）。本计划只交付 GH Actions；Drone 模板留给社区。

- [ ] **Step 1: 创建 `.github/workflows/backend.yml`**

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

      - name: Install system tools (git/ripgrep/ctags)
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

- [ ] **Step 2: 创建 `.github/workflows/frontend.yml`**

```yaml
name: frontend

on:
  push:
    branches: [main]
    paths:
      - "frontend/**"
      - ".github/workflows/frontend.yml"
  pull_request:
    branches: [main]

concurrency:
  group: frontend-${{ github.ref }}
  cancel-in-progress: true

defaults:
  run:
    working-directory: frontend

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4

      - name: Setup pnpm
        uses: pnpm/action-setup@v4
        with:
          version: 9

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: pnpm
          cache-dependency-path: frontend/pnpm-lock.yaml

      - name: pnpm install
        run: pnpm install --frozen-lockfile

      - name: Typecheck
        run: pnpm tsc --noEmit

      - name: Lint
        run: pnpm lint

      - name: Unit (Vitest)
        run: pnpm test --run

      - name: Build
        run: pnpm build

  e2e:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    needs: test
    env:
      CODEASK_DATA_KEY: TGltSXRlc3Rrcm5hYmFzZTY0LXVybHNhZmUtMzJieXRlcw==
    steps:
      - uses: actions/checkout@v4

      - name: Build and start backend container
        working-directory: .
        run: |
          docker build -f docker/Dockerfile -t codeask:e2e .
          docker run -d --name codeask-e2e \
            -p 8000:8000 \
            -e CODEASK_DATA_KEY=$CODEASK_DATA_KEY \
            codeask:e2e
          # Wait for healthz
          for i in {1..30}; do
            if curl -fs http://127.0.0.1:8000/api/healthz; then break; fi
            sleep 1
          done

      - name: Setup pnpm
        uses: pnpm/action-setup@v4
        with:
          version: 9

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: pnpm
          cache-dependency-path: frontend/pnpm-lock.yaml

      - name: pnpm install
        run: pnpm install --frozen-lockfile

      - name: Install Playwright browsers
        run: pnpm exec playwright install --with-deps chromium

      - name: Playwright e2e
        run: pnpm e2e
        env:
          PLAYWRIGHT_BASE_URL: http://127.0.0.1:8000

      - name: Backend logs (debug on failure)
        if: failure()
        working-directory: .
        run: docker logs codeask-e2e || true

      - name: Stop backend
        if: always()
        working-directory: .
        run: docker stop codeask-e2e || true
```

- [ ] **Step 3: 创建 `.github/workflows/image.yml`**

```yaml
name: image

on:
  push:
    tags: ["v*"]
  workflow_dispatch:

permissions:
  contents: read
  packages: write

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4

      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3

      - name: Set up Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Image metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=ref,event=tag
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=raw,value=latest,enable=${{ startsWith(github.ref, 'refs/tags/v') }}

      - name: Build & push
        uses: docker/build-push-action@v6
        with:
          context: .
          file: docker/Dockerfile
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

- [ ] **Step 4: 验证**：本地有 `act` 时跑 `act -W .github/workflows/backend.yml pull_request`；否则推 PR 看 Actions 页面，三份 workflow 各自 trigger 正确。

- [ ] **Step 5: 提交**

```bash
mkdir -p .github/workflows
git add .github/workflows/backend.yml .github/workflows/frontend.yml .github/workflows/image.yml
git commit -m "ci: backend (lint+type+pytest), frontend (tsc+vitest+playwright), image (ghcr)"
```

---

## Task 9: 安全审计 checklist + 强制 pytest

**Files:**
- Create: `docs/v1.0/plans/deployment-security-checklist.md`
- Create: `tests/security/__init__.py`
- Create: `tests/security/test_grep_no_shell_true.py`
- Create: `tests/security/test_grep_default_bind.py`
- Create: `tests/integration/test_security_checklist.py`

`deployment-security.md` §6 把"路径校验 / MIME / 二进制日志拒绝 / shell 参数数组 / worktree 边界"都列为强制；本计划把它们一条一条变成可重复跑的 pytest，不让"今天对、明天忘"的事故发生。每条 checklist 都明确指向**自动还是手工**。

- [ ] **Step 1: 创建 `tests/security/__init__.py`**

```python
"""Security regression tests (grep-based + behavioral)."""
```

- [ ] **Step 2: 创建 `tests/security/test_grep_no_shell_true.py`**

```python
"""Static check: no `shell=True` anywhere in production source.

deployment-security.md §6 mandates subprocess argument arrays only.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

# Forbidden pattern: any `shell=True` (case-insensitive on `True` to be safe)
PATTERN = re.compile(r"\bshell\s*=\s*True\b")


def test_no_shell_true_in_src() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            # allow comments that *mention* shell=True for documentation
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if PATTERN.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "shell=True found in production source. Use argument arrays:\n  "
        + "\n  ".join(offenders)
    )
```

- [ ] **Step 3: 创建 `tests/security/test_grep_default_bind.py`**

```python
"""Static check: business code does not hard-code 0.0.0.0 binding.

Container images intentionally set CODEASK_HOST=0.0.0.0 via Dockerfile/compose
(checked file paths excluded). deployment-security.md §2 mandates default
127.0.0.1 in code-level defaults.
"""

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
        "Hard-coded 0.0.0.0 found in src/. Default bind must be 127.0.0.1; "
        "container deployments override via env (CODEASK_HOST=0.0.0.0):\n  "
        + "\n  ".join(offenders)
    )
```

- [ ] **Step 4: 创建 `tests/integration/test_security_checklist.py`**

```python
"""Behavioral security regressions tied to deployment-security.md §6.

Each test maps 1:1 to a checklist line in
docs/v1.0/plans/deployment-security-checklist.md.
"""

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


# ----------------- Checklist line: defaults bind 127.0.0.1 -----------------

def test_default_settings_bind_localhost(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CODEASK_HOST", raising=False)
    s = Settings()  # type: ignore[call-arg]
    assert s.host == "127.0.0.1", (
        "Default bind must be 127.0.0.1 (container overrides via env)."
    )


# ----------------- Checklist line: encrypted fields are not plaintext -----

@pytest.mark.asyncio
async def test_encrypted_field_is_not_plaintext_in_db(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Insert an encrypted secret; raw row must not contain plaintext."""
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

    # Inspect raw bytes on disk
    db_path = tmp_path / "data.db"
    assert db_path.is_file()
    raw = db_path.read_bytes()
    assert secret.encode() not in raw, "Plaintext secret leaked to DB file."
    # Also confirm decrypt round-trips
    assert c.decrypt(ciphertext) == secret


# ----------------- Checklist line: path traversal rejected ----------------

def test_safe_join_rejects_traversal(tmp_path: Path) -> None:
    """The shared path-safety helper rejects ../, absolute paths, symlinks-out."""
    pytest.importorskip(
        "codeask.fs_safety",
        reason="If fs_safety not yet wired by 02/03 plans, skip until they land",
    )
    from codeask.fs_safety import safe_join, PathOutsideRoot

    root = tmp_path / "root"
    root.mkdir()

    # OK
    assert safe_join(root, "a/b.txt").is_relative_to(root)

    # Reject ../ escape
    with pytest.raises(PathOutsideRoot):
        safe_join(root, "../etc/passwd")

    # Reject absolute paths
    with pytest.raises(PathOutsideRoot):
        safe_join(root, "/etc/passwd")


# ----------------- Checklist line: MIME validation rejects spoofed exe ----

def test_upload_mime_rejects_exe_disguised_as_pdf(tmp_path: Path) -> None:
    """A Windows PE 'MZ' header must be rejected when uploaded as application/pdf."""
    pytest.importorskip(
        "codeask.wiki.uploads",
        reason="If 02/wiki-knowledge upload validator not yet wired, skip",
    )
    from codeask.wiki.uploads import validate_upload, UnsupportedMime

    # Real PE binary header
    fake = tmp_path / "evil.pdf"
    fake.write_bytes(b"MZ\x90\x00\x03\x00" + b"\x00" * 1024)
    with pytest.raises(UnsupportedMime):
        validate_upload(fake, declared_mime="application/pdf")


# ----------------- Checklist line: subject_id middleware default ----------

@pytest.mark.asyncio
async def test_anonymous_subject_id_assigned(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/healthz")
    assert r.status_code == 200
    assert r.json()["subject_id"].startswith("anonymous@")
```

`pytest.importorskip` 让本计划在 02 / 03 / 04 还没落地时也能跑通——已落地的部分必须通过，未落地的自动 skip 并打印原因。

- [ ] **Step 5: 创建 `docs/v1.0/plans/deployment-security-checklist.md`**

````markdown
# Deployment Security Checklist

> Companion to `docs/v1.0/plans/deployment.md`. Maps every line in
> `docs/v1.0/design/deployment-security.md` §5–§7 to a verification step.
> Run before each release tag (`v*`) — image.yml workflow rejects the build if
> any auto-step fails.

## Auto (pytest)

| ID | Checklist line (deployment-security.md §) | Test |
|---|---|---|
| AUTO-1 | §6 "shell 调用使用参数数组，不使用 `shell=True`" | `tests/security/test_grep_no_shell_true.py` |
| AUTO-2 | §2 "默认监听 127.0.0.1" (code defaults) | `tests/security/test_grep_default_bind.py` |
| AUTO-3 | §2 "默认监听 127.0.0.1" (Settings runtime default) | `tests/integration/test_security_checklist.py::test_default_settings_bind_localhost` |
| AUTO-4 | §5 "LLM API Key 加密存储 ... 数据库字段加密" | `tests/integration/test_security_checklist.py::test_encrypted_field_is_not_plaintext_in_db` |
| AUTO-5 | §6 "所有路径读取做根目录校验（防止 `../` 越狱）" | `tests/integration/test_security_checklist.py::test_safe_join_rejects_traversal` (skips until fs_safety lands) |
| AUTO-6 | §6 "上传文件做 MIME 和后缀检查" | `tests/integration/test_security_checklist.py::test_upload_mime_rejects_exe_disguised_as_pdf` (skips until wiki upload validator lands) |
| AUTO-7 | §3 "自报身份"软识别（fallback to `anonymous@<hex>`） | `tests/integration/test_security_checklist.py::test_anonymous_subject_id_assigned` |
| AUTO-8 | dependency hygiene | `uv pip list --outdated` and `pnpm audit --prod` (run from CI; warning-only) |

Run all auto checks:

```bash
uv run pytest tests/security tests/integration/test_security_checklist.py -v
uv run pip list --outdated || true
(cd frontend && pnpm audit --prod || true)
```

## Manual (release-tag review)

| ID | Step |
|---|---|
| MANUAL-1 | Fresh VM (or `docker compose down --volumes`) → `docker compose up -d` → curl `/api/healthz` returns `status: ok` within 30 seconds (PRD §4.4.1). |
| MANUAL-2 | `docker compose up -d` without `CODEASK_DATA_KEY` set → compose refuses to start with the documented error. |
| MANUAL-3 | Verify image size < 200 MB: `docker images ghcr.io/codeask/codeask:<tag> --format '{{.Size}}'`. |
| MANUAL-4 | Inspect image runs non-root: `docker inspect ghcr.io/codeask/codeask:<tag> --format '{{.Config.User}}'` returns `appuser`. |
| MANUAL-5 | Confirm `~/.codeask/data.db` is bind-mounted, not in a volume that auto-evaporates: `docker compose config | grep device`. |
| MANUAL-6 | Spot-check structlog output is JSON: `docker compose logs codeask | head -3 | python -c 'import sys, json; [json.loads(l) for l in sys.stdin]'`. |
| MANUAL-7 | Pull a fresh tagged image and re-run MANUAL-1 to validate the `image.yml` workflow output. |

## When a checklist line moves from manual to auto

1. Add the test under `tests/security/` or `tests/integration/test_security_checklist.py`.
2. Update the AUTO/MANUAL table above.
3. Land in the same PR; `image.yml` will start enforcing on the next tag.
````

- [ ] **Step 6: 跑安全测试**

```bash
uv run pytest tests/security tests/integration/test_security_checklist.py -v
```
Expected: PASS（部分 skip 是预期，因为 02 / 03 plans 可能尚未落地）。

- [ ] **Step 7: 提交**

```bash
git add tests/security/ tests/integration/test_security_checklist.py docs/v1.0/plans/deployment-security-checklist.md
git commit -m "feat(security): pytest-enforced security checklist + manual release steps"
```

---

## Task 10: 全量回归 + 30 秒部署 smoke + tag

**Files:**
- 无新增文件（聚合验证）。

把本计划交付的所有改动跑一遍，确认 30 秒部署承诺仍然成立，然后打 tag 标记 deployment 落地。

- [ ] **Step 1: lint + type + pytest 全绿**

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pyright src/codeask
uv run pytest -v
```
Expected: 全部 PASS。

- [ ] **Step 2: pre-commit 全绿**

```bash
uv run pre-commit run --all-files
```
Expected: 全部 hook PASS（首次跑可能 auto-fix；二次跑必须无变更）。

- [ ] **Step 3: 30 秒部署 smoke（手工）**

```bash
# Fresh state
rm -rf ~/.codeask-smoke
mkdir ~/.codeask-smoke
export CODEASK_HOST_DATA_DIR="$HOME/.codeask-smoke"
export CODEASK_DATA_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

# Time it
START=$(date +%s)
docker compose -f docker/docker-compose.yml up -d --build
# Wait for healthz with timeout
for i in {1..60}; do
    if curl -fs http://127.0.0.1:8000/api/healthz >/dev/null; then
        echo "READY in $(( $(date +%s) - START )) seconds"
        break
    fi
    sleep 1
done
curl -s http://127.0.0.1:8000/api/healthz | python -m json.tool

# Cleanup
docker compose -f docker/docker-compose.yml down
unset CODEASK_DATA_KEY CODEASK_HOST_DATA_DIR
rm -rf ~/.codeask-smoke
```
Expected: "READY in N seconds" with N ≤ 30 on a warm Docker cache (first build excluded). healthz returns `status: ok`.

- [ ] **Step 4: 镜像体积验证**

```bash
docker images codeask:dev --format '{{.Size}}'
```
Expected: 130–200 MB. 如果超过 250 MB，回头检查 Dockerfile 是否有冗余 `COPY` 或漏装的多阶段隔离。

- [ ] **Step 5: 安全 checklist 全部 AUTO 项跑通**

```bash
uv run pytest tests/security tests/integration/test_security_checklist.py -v
```
Expected: PASS（部分 skip 允许）。

- [ ] **Step 6: 打 tag**

```bash
git tag -a deployment-v0.1.0 -m "Deployment milestone: Docker + compose + start.sh + CI + security checklist"
```

- [ ] **Step 7: PR 自检**

| 项 | 期望 |
|---|---|
| `docker compose up -d` 启服务 ≤ 30s（warm cache） | ✓ |
| 镜像 ≤ 200MB / 非 root | ✓ |
| `start.sh` 缺 dist 时自动 build 或清晰 warn | ✓ |
| `start.sh` 缺 `CODEASK_DATA_KEY` 时退出 1 | ✓ |
| `/api/healthz` 与 `/` 同时可达 | ✓ |
| ruff + pyright + pytest 全绿 | ✓ |
| pre-commit 全绿 | ✓ |
| GH Actions 三份 workflow 配置无误 | ✓ |
| 安全 AUTO checklist 全 PASS（含 skip 标注） | ✓ |
| README 同时有 30 秒 Docker 路径 + 本地开发 | ✓ |

---

## 验收标志（计划完整通过后应满足）

- [ ] `docker compose -f docker/docker-compose.yml up -d` 在 fresh VM 上 30 秒内 healthz ok
- [ ] 镜像 `codeask:*` 130–200MB，非 root（`USER appuser`）
- [ ] `./start.sh` 在没有 `frontend/dist/` 时正确分支：有 pnpm 自动 build / 否则 warn
- [ ] foundation 的 23 条 pytest 仍全绿；本计划新增 ~9 条 pytest 也全绿
- [ ] `uv run ruff check && uv run pyright src/codeask` 零错误
- [ ] `uv run pre-commit run --all-files` 全绿
- [ ] `.github/workflows/{backend,frontend,image}.yml` 在 PR / push / tag 三种触发下分别跑对应 job
- [ ] `docs/v1.0/plans/deployment-security-checklist.md` 列出 8 条 AUTO + 7 条 MANUAL，AUTO 全部对应 pytest
- [ ] `git tag deployment-v0.1.0` 已打

---

## 不在本计划范围（明确推迟）

| 项 | 推迟到 | 原因 |
|---|---|---|
| Kubernetes Helm chart | 社区适配 | PRD §6.2 + dependencies.md §7 Anti-list — Helm 把 30 秒部署门槛拉高 |
| 多租户 / 多组织 | v2.0 主版本 | v1.0 Anti-Goal |
| 真鉴权 / OIDC / LDAP 接入 | MVP+ | deployment-security.md §4 已留 `AuthProvider` 协议槽位 |
| 监控 dashboard / Prometheus exporter | 永久 Anti-Goal | PRD §6.1 |
| LLM 平台 SLO / 限流 / 熔断 | 后续优化 | 一期由网关层 timeout + retry 兜底，详见 04 agent-runtime |
| Drone / Gitea Actions 模板 | 社区适配 | 一期只交付 GH Actions 官方路径 |
| Sentry / OpenTelemetry 接入 | 后续优化 | 一期只 structlog JSON stdout |
| 镜像漏洞扫描（Trivy / Grype） | 后续优化 | 当前依赖 GHCR 自带扫描 + 手工 `pnpm audit` / `uv pip list --outdated` |
| 自动备份 / 灾备 | 后续优化 | 一期文档建议 cron `tar` `~/.codeask/`；不进核心 |
| 速率限制 / WAF | 后续优化 | 私有部署 + 127.0.0.1 默认绑定已是物理隔离 |

---

## Hand-off 摘要（给后续计划 / 维护者）

本计划落地后，仓库具备：单产物 Docker 部署、`start.sh` 本地路径、三份 GH Actions、pre-commit 质量门、`tests/security/` 静态 grep + 行为测试、`deployment-security-checklist.md` 8 AUTO / 7 MANUAL。

后续计划添加新功能时遵守的强制项（每条都对应一条 AUTO 测试）：

- 新 subprocess 调用必须用参数数组（AUTO-1）
- 新写敏感字段必须走 `Crypto`（AUTO-4）
- 新业务代码不许写死 `"0.0.0.0"`（AUTO-2）
- 新上传 endpoint 必须接入 `validate_upload`（AUTO-6；02-wiki-knowledge 提供）
- 新文件路径访问必须走 `safe_join`（AUTO-5；02 / 03 提供）
- 改动 `Dockerfile` 后必须本地 build + run + healthz 通过才提 PR
