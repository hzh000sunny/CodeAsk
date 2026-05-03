# CodeAsk 安装与本地开发

本文承载 CodeAsk 的安装、配置、启动、开发联调和验证命令。产品介绍请看 [README.md](./README.md)。

## 环境要求

| 依赖 | 用途 |
|---|---|
| Python 3.11+ | 后端运行环境 |
| uv | Python 依赖管理和命令运行 |
| Node.js 22+ | 前端构建和测试 |
| Corepack / pnpm | 前端依赖管理 |
| git | clone、fetch、worktree |
| ripgrep (`rg`) | 代码全文检索 |
| universal-ctags (`ctags`) | 符号检索；缺失时相关测试会跳过 |

Debian / Ubuntu：

```bash
sudo apt-get install git ripgrep universal-ctags
```

macOS：

```bash
brew install git ripgrep universal-ctags
```

## 安装依赖

后端依赖通过 uv 安装：

```bash
uv sync
```

前端依赖通过 pnpm 安装：

```bash
corepack pnpm --dir frontend install
```

项目已在 `pyproject.toml` 配置 uv 默认包索引为清华 TUNA：

```toml
[[tool.uv.index]]
name = "tuna"
url = "https://pypi.tuna.tsinghua.edu.cn/simple/"
default = true
```

## 必需环境变量

`CODEASK_DATA_KEY` 用于加密 LLM API Key 等敏感字段。它不是登录密码，也不是访问 token。丢失后，已经加密存储的敏感字段无法恢复。

首次本地启动前生成一个 Fernet key：

```bash
export CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

建议把正式环境的 key 写入部署系统的 secret 管理，不要提交到仓库。

## 启动单进程服务

```bash
./start.sh
```

默认服务地址：

```text
http://127.0.0.1:8000
```

如果需要让局域网或容器外部访问：

```bash
CODEASK_HOST=0.0.0.0 CODEASK_PORT=8000 ./start.sh
```

注意：当前普通用户无登录即可使用，只有全局配置由管理员登录保护。把 `CODEASK_HOST` 设为 `0.0.0.0` 前，应确认部署环境位于可信内网，或者已有外层访问控制。

健康检查：

```bash
curl -s http://127.0.0.1:8000/api/healthz -H 'X-Subject-Id: alice@dev-1' | python -m json.tool
```

## 管理员账号

内置管理员账号用于本地调试：

```text
username: admin
password: admin
```

正式部署必须覆盖默认密码：

```bash
export CODEASK_ADMIN_USERNAME="admin"
export CODEASK_ADMIN_PASSWORD="<strong-password>"
```

管理员用于维护：

- 全局 LLM 配置
- 全局仓库池
- 全局分析策略

普通用户不需要登录即可使用会话、附件、个人设置和个人 LLM 配置。

## 前端开发联调

单独启动后端：

```bash
CODEASK_HOST=0.0.0.0 CODEASK_PORT=8000 uv run codeask
```

启动 Vite dev server：

```bash
corepack pnpm --dir frontend dev --host 0.0.0.0 --port 5173
```

前端开发服务器：

```text
http://127.0.0.1:5173
```

Vite 会把 `/api/*` 代理到后端 `:8000`。

## 配置项

| 环境变量 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `CODEASK_DATA_KEY` | 是 | 无 | Fernet key，base64-url-safe 32 bytes，用于加密敏感字段 |
| `CODEASK_DATA_DIR` | 否 | `~/.codeask` | SQLite、上传文件、worktree、日志等本地数据根目录 |
| `CODEASK_HOST` | 否 | `127.0.0.1` | HTTP 监听地址 |
| `CODEASK_PORT` | 否 | `8000` | HTTP 监听端口 |
| `CODEASK_LOG_LEVEL` | 否 | `INFO` | 日志级别 |
| `CODEASK_DATABASE_URL` | 否 | 基于 `CODEASK_DATA_DIR` 派生 | 默认本地 SQLite |
| `CODEASK_FRONTEND_DIST` | 否 | `<repo>/frontend/dist` | 前端构建产物目录，存在 `index.html` 时由后端挂载 |
| `CODEASK_ADMIN_USERNAME` | 否 | `admin` | 内置管理员用户名 |
| `CODEASK_ADMIN_PASSWORD` | 否 | `admin` | 内置管理员密码，正式部署必须覆盖 |
| `CODEASK_ADMIN_SESSION_TTL_HOURS` | 否 | `12` | 管理员 cookie 有效期 |
| `LITELLM_LOCAL_MODEL_COST_MAP` | 否 | `True` | CodeAsk 启动时强制设为 `True`，禁用 LiteLLM 启动联网拉取模型价格表 |

## 本地数据目录

默认数据根目录是 `~/.codeask`：

```text
~/.codeask/
├── data.db
├── wiki/
├── skills/
├── sessions/
│   └── <session_id>/
│       ├── manifest.json
│       └── <attachment_id>.<ext>
├── repos/
│   └── <repo_id>/
│       ├── bare/
│       └── worktrees/
├── index/
└── logs/
```

关键约定：

- 会话附件按 `sessions/<session_id>/` 隔离。
- 附件物理文件名使用稳定 `attachment_id`，避免同名日志互相覆盖。
- `display_name` 可编辑，`original_filename` 不变，`aliases` 保留名称历史。
- `manifest.json` 是 DB 附件元数据的运维快照；DB 记录是主源。
- 删除会话时会清理对应会话存储目录。
- 仓库缓存使用 bare repo；会话调查通过 worktree 隔离。

## 构建前端静态产物

```bash
corepack pnpm --dir frontend build
```

构建产物默认在：

```text
frontend/dist
```

当 `frontend/dist/index.html` 存在时，后端会把前端静态产物挂载到 `/`。`/api/*` 始终由后端 API 处理，不会被静态路由吞掉。

## 测试与验证

后端：

```bash
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run pyright src/codeask
```

前端：

```bash
corepack pnpm --dir frontend test:run
corepack pnpm --dir frontend typecheck
corepack pnpm --dir frontend build
corepack pnpm --dir frontend test:e2e --project=chromium
```

常用全量收尾：

```bash
uv run pytest
uv run ruff check src tests
uv run pyright src/codeask
corepack pnpm --dir frontend test:run --maxWorkers=1 --minWorkers=1
corepack pnpm --dir frontend typecheck
corepack pnpm --dir frontend test:e2e --project=chromium
git diff --check
```

## 常见问题

### 启动时报 `CODEASK_DATA_KEY is not set`

先生成并导出 Fernet key：

```bash
export CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

### 前端 dev server 访问不到 API

确认后端运行在 `:8000`，并且 Vite dev server 使用仓库里的代理配置启动：

```bash
CODEASK_HOST=0.0.0.0 CODEASK_PORT=8000 uv run codeask
corepack pnpm --dir frontend dev --host 0.0.0.0 --port 5173
```

### 代码检索能力不完整

确认系统安装了 `ripgrep` 和 `universal-ctags`。缺少 `ctags` 时，符号检索相关能力和测试会受限。

### LiteLLM 启动时尝试联网

CodeAsk 已在项目级禁用 LiteLLM 启动联网拉取模型价格表。请确认环境中没有手动把 `LITELLM_LOCAL_MODEL_COST_MAP` 改为非 `True` 值。

## 相关文档

- [README.md](./README.md)：产品介绍。
- [docs/v1.0/design/deployment-security.md](./docs/v1.0/design/deployment-security.md)：部署和安全边界。
- [docs/v1.0/design/api-data-model.md](./docs/v1.0/design/api-data-model.md)：API 和数据模型契约。
- [docs/v1.0/design/agent-runtime.md](./docs/v1.0/design/agent-runtime.md)：Agent 状态机和运行时。
