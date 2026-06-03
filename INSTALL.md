# CodeAsk 安装与本地开发

本文只保留第一次上手所需的安装、启动和基础验证步骤。版本设计、运维细节和长篇排障请看文末“相关文档”。

## 适用范围

当前支持两种本地启动方式：

| 方式 | 适用场景 | 浏览器地址 |
|---|---|---|
| 单进程启动 | 本地体验、轻量部署、后端托管前端构建产物 | `http://127.0.0.1:8000` |
| 前后端开发联调 | 前端开发、热更新、Playwright 调试 | `http://127.0.0.1:5173` |

Docker / Compose 暂不属于当前版本的部署路径。

## 环境要求

| 依赖 | 版本 / 用途 |
|---|---|
| Python | 3.11+ |
| uv | Python 依赖管理 |
| Node.js | 22+ |
| Corepack / pnpm | 前端依赖管理；项目声明 `pnpm@10.12.1` |
| git | clone、fetch、worktree |
| ripgrep (`rg`) | 代码全文检索 |
| universal-ctags (`ctags`) | 符号检索；缺失时部分能力和测试会受限 |

快速检查：

```bash
python3 --version
uv --version
node --version
corepack --version
corepack pnpm --version
git --version
rg --version
ctags --version
```

Debian / Ubuntu 最小系统包：

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates build-essential ripgrep universal-ctags
```

安装 uv：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
```

启用 Corepack：

```bash
corepack enable
```

如果系统没有 Node.js 22，请用 nvm、NodeSource、Homebrew 或内部基础镜像安装 Node.js 22 后再执行 `corepack enable`。

## 最短启动路径

把 `<repo-url>` 替换为实际仓库地址：

```bash
git clone <repo-url> CodeAsk
cd CodeAsk

uv sync
corepack pnpm --dir frontend install --frozen-lockfile

export CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
export CODEASK_ADMIN_USERNAME="admin"
export CODEASK_ADMIN_PASSWORD="admin"

./start.sh
```

启动后打开：

```text
http://127.0.0.1:8000
```

健康检查：

```bash
curl -s http://127.0.0.1:8000/api/healthz -H 'X-Subject-Id: alice@dev-1' | python3 -m json.tool
```

正式部署不要使用默认管理员密码：

```bash
export CODEASK_ADMIN_USERNAME="admin"
export CODEASK_ADMIN_PASSWORD="<strong-password>"
```

需要让其他机器访问时再改监听地址：

```bash
CODEASK_HOST=0.0.0.0 CODEASK_PORT=8000 ./start.sh
```

把 `CODEASK_HOST` 设为 `0.0.0.0` 前，应确认部署环境位于可信内网，或已有外层访问控制。

## 必需环境变量

`CODEASK_DATA_KEY` 用于加密 LLM API Key 等敏感字段。它不是登录密码，也不是访问 token。丢失后，已经加密存储的敏感字段无法恢复。

首次启动前生成：

```bash
export CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

首次启动成功后，CodeAsk 会把该 key 缓存在：

```text
<CODEASK_DATA_DIR>/secrets/data.key
```

后续再次启动时，如果没有设置 `CODEASK_DATA_KEY`，服务会从数据目录缓存读取 key。

关键规则：

- 同一个 `CODEASK_DATA_DIR` 必须使用同一个 `CODEASK_DATA_KEY`。
- 正式环境应把 key 写入 secret 管理。
- 备份和迁移必须保留整个数据目录，至少包含 `data.db` 和 `secrets/data.key`。
- 不要每次启动都重新生成 key。

## 常用配置

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `CODEASK_DATA_DIR` | `~/.codeask` | SQLite、上传文件、worktree、日志等本地数据根目录 |
| `CODEASK_HOST` | `127.0.0.1` | HTTP 监听地址 |
| `CODEASK_PORT` | `8000` | HTTP 监听端口 |
| `CODEASK_ADMIN_USERNAME` | `admin` | 内置管理员用户名 |
| `CODEASK_ADMIN_PASSWORD` | `admin` | 内置管理员密码，正式部署必须覆盖 |
| `CODEASK_FRONTEND_DIST` | `<repo>/frontend/dist` | 前端构建产物目录 |
| `CODEASK_OPENCODE_BIN` | 自动解析 | 找不到 `opencode` 时可显式指定绝对路径 |
| `CODEASK_OPENVIKING_BIN` | 自动解析 | 找不到 `openviking-server` 时可显式指定绝对路径 |

更多数据目录说明见 [docs/operations/data-directory.md](./docs/operations/data-directory.md)，跨版本规则见 [docs/rules/upgrade-compatibility.md](./docs/rules/upgrade-compatibility.md)。

## OpenViking RAG

v1.0.5 起，opencode 会话可通过 OpenViking 检索 Wiki 语义候选。OpenViking 随 `uv sync` 安装，运行期由 CodeAsk 后端拉起 `openviking-server` 子进程。

默认 embedding provider 是 OpenViking local；首次使用 local 模型时，OpenViking 会按自身缓存规则下载模型。Ollama、OpenAI-compatible 和其他 provider 是可选配置，可在 admin 设置页切换。

常见规则：

- Wiki UI 搜索仍走 SQL ILIKE，不依赖 OpenViking。
- Report 不进入 OpenViking，只维护本地文件视图。
- 代码仓内容进入 OpenViking 已延后；源码证据仍通过 CodeAsk worktree 读取。
- 切换 embedding 会重启 OpenViking、清理索引并重新同步 Wiki。

详细说明见 [docs/operations/openviking-rag.md](./docs/operations/openviking-rag.md)。

## 前后端开发联调

开发模式需要两个终端。

终端 1：启动后端：

```bash
CODEASK_HOST=0.0.0.0 CODEASK_PORT=8000 uv run codeask
```

终端 2：启动 Vite：

```bash
corepack pnpm --dir frontend dev --host 0.0.0.0 --port 5173
```

浏览器访问：

```text
http://127.0.0.1:5173
```

如果后端不在默认 `:8000`：

```bash
CODEASK_API_PROXY_TARGET=http://127.0.0.1:8010 corepack pnpm --dir frontend dev --host 0.0.0.0 --port 5173
```

## 构建前端

```bash
corepack pnpm --dir frontend build
```

构建产物在：

```text
frontend/dist
```

当 `frontend/dist/index.html` 存在时，后端会把前端静态产物挂载到 `/`。`/api/*` 始终由后端 API 处理。

## 升级已有部署

升级前先读 [docs/operations/upgrade.md](./docs/operations/upgrade.md) 和 [docs/rules/upgrade-compatibility.md](./docs/rules/upgrade-compatibility.md)。

最小安全流程：

1. 停止 CodeAsk。
2. 确认当前 `CODEASK_DATA_DIR`，默认是 `~/.codeask`。
3. 备份整个 `CODEASK_DATA_DIR`，不要只备份 `data.db`。
4. 拉取新代码或切换 release tag。
5. 运行 `uv sync`。
6. 运行 `corepack pnpm --dir frontend install --frozen-lockfile`。
7. 运行 `corepack pnpm --dir frontend build`。
8. 使用原数据目录启动 `./start.sh`。
9. 打开浏览器确认会话、Wiki、设置页和管理员登录可用。

如果新版本已经启动并执行了 migration，回滚时不要只回滚代码；应恢复升级前备份的整个数据目录。

## 测试与验证

后端常用检查：

```bash
uv run pytest
uv run ruff check src tests
uv run pyright src/codeask
```

前端常用检查：

```bash
corepack pnpm --dir frontend test:run
corepack pnpm --dir frontend typecheck
corepack pnpm --dir frontend build
```

端到端测试：

```bash
corepack pnpm --dir frontend test:e2e --project=chromium
```

Playwright 会自动拉起隔离服务，不复用本地 `5173 + 8000` 联调环境，也不污染默认 `~/.codeask` 数据目录。

## 常见问题

| 问题 | 处理 |
|---|---|
| `uv: command not found` | 安装 uv，并确认 `$HOME/.local/bin` 在 `PATH` 中 |
| `corepack: command not found` | 确认 Node.js 22+，然后执行 `corepack enable` |
| 前端依赖安装失败 | 确认 `node --version` 是 22+，再执行 `corepack enable` |
| `CODEASK_DATA_KEY is not set` | 按“必需环境变量”生成并导出 key |
| `CODEASK_DATA_KEY conflicts with cached data key` | 当前 key 与数据目录缓存不一致；使用原 key 或恢复正确数据目录 |
| 浏览器访问不到服务 | 确认 `CODEASK_HOST`、端口、防火墙和安全组 |
| 端口被占用 | 用 `CODEASK_PORT=8010 ./start.sh` 或调整开发代理 |
| 找不到 opencode | 执行 `command -v opencode`；必要时设置 `CODEASK_OPENCODE_BIN` |
| 代码检索能力不完整 | 确认 `rg --version` 和 `ctags --version` |

## 相关文档

- [README.md](./README.md)：产品介绍。
- [docs/README.md](./docs/README.md)：版本文档入口。
- [docs/operations/](./docs/operations/)：部署、升级、数据目录、排障和部署验收。
- [docs/operations/openviking-rag.md](./docs/operations/openviking-rag.md)：OpenViking RAG 运维说明。
- [docs/rules/upgrade-compatibility.md](./docs/rules/upgrade-compatibility.md)：升级、数据目录和 key 规则。
- [docs/rules/temp-directory.md](./docs/rules/temp-directory.md)：临时目录规则。
- [docs/v1.0.5/README.md](./docs/v1.0.5/README.md)：当前版本范围和 release 状态。
