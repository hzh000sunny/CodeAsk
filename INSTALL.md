# CodeAsk 安装与本地开发

本文承载 CodeAsk 的安装、配置、启动、开发联调和验证命令。产品介绍请看 [README.md](./README.md)。

## 适用范围

这份文档的目标是让第一次接触项目的人，或者 AI 编码助手，在一台新机器上可以按步骤完成本地部署、开发联调和基础验证。

当前支持两种启动方式：

| 方式 | 适用场景 | 浏览器地址 |
|---|---|---|
| 单进程启动 | 本地体验、轻量部署、让后端直接托管前端构建产物 | `http://127.0.0.1:8000` |
| 前后端开发联调 | 日常前端开发、Playwright 调试、热更新 | `http://127.0.0.1:5173` |

说明：

- `8000` 是后端端口。只有前端已经构建到 `frontend/dist` 时，后端才会在 `/` 托管页面。
- `5173` 是 Vite 前端开发端口。开发联调时应访问 `5173`，由 Vite 把 `/api/*` 代理到后端 `8000`。
- Docker / Compose 暂不属于当前版本的部署路径，后续版本再补。

## 环境要求

| 依赖 | 用途 |
|---|---|
| Python 3.11+ | 后端运行环境 |
| uv | Python 依赖管理和命令运行 |
| Node.js 22+ | 前端构建、开发服务器和测试 |
| Corepack / pnpm 10.x | 前端依赖管理；项目声明 `pnpm@10.12.1` |
| git | clone、fetch、worktree |
| ripgrep (`rg`) | 代码全文检索 |
| universal-ctags (`ctags`) | 符号检索；缺失时相关测试会跳过 |
| curl / ca-certificates | 安装工具链和访问本地接口 |
| build-essential / Xcode Command Line Tools | 编译部分 Python 或 Node 依赖时可能需要 |

## 全新环境安装工具链

如果机器已经安装了 Python 3.11+、uv、Node.js 22+、Corepack 或 pnpm 10.x、git、ripgrep 和 ctags，可以跳过本节，直接进入“部署前检查”。

### Debian / Ubuntu

安装系统工具：

```bash
sudo apt-get update
sudo apt-get install -y \
  git curl ca-certificates build-essential \
  ripgrep universal-ctags
```

确认 Python 版本：

```bash
python3 --version
```

如果系统没有 Python 3.11+，请使用发行版包管理器、pyenv 或内部基础镜像安装。安装完成后再次确认：

```bash
python3 --version
```

安装 uv：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
```

安装 Node.js 22。推荐使用 nvm，便于固定 Node 主版本：

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
nvm install 22
nvm use 22
corepack enable
```

如果部署环境禁止从 GitHub 下载 nvm，请使用系统镜像、NodeSource 或公司内部 Node.js 22 包，但仍需执行：

```bash
corepack enable
```

### macOS

安装系统工具：

```bash
xcode-select --install
brew install git ripgrep universal-ctags uv node@22
corepack enable
```

如果 `node` 未指向 Node.js 22，请按 Homebrew 输出把 `node@22` 加入 `PATH`，或使用 nvm 安装 Node.js 22。

## 部署前检查

在 clone 项目前或进入项目根目录后，先确认工具链可用：

```bash
python3 --version
uv --version
node --version
corepack --version
git --version
rg --version
ctags --version
```

期望结果：

- Python 显示 `3.11` 或更高。
- Node 显示 `v22` 或更高。
- `uv`、`git`、`rg`、`ctags` 都能正常输出版本。
- `corepack pnpm --version` 或 `pnpm --version` 至少有一个可用；裸机离线环境可以只安装 pnpm 10.x。

如果 `python` 命令不存在但 `python3` 存在，不需要特别处理；项目命令统一通过 `uv` 运行。

## 从源码启动一套可访问服务

这是给新环境和 AI 部署使用的最短完整路径。请把 `<repo-url>` 替换为实际仓库地址。

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

如果部署环境没有 Corepack，但已经安装了 pnpm 10.x，可以把上面的前端命令替换为：

```bash
pnpm --dir frontend install --frozen-lockfile
```

启动成功后会看到类似输出：

```text
Starting CodeAsk on 127.0.0.1:8000
Data dir: /home/<user>/.codeask
```

打开：

```text
http://127.0.0.1:8000
```

健康检查：

```bash
curl -s http://127.0.0.1:8000/api/healthz -H 'X-Subject-Id: alice@dev-1' | python3 -m json.tool
```

正式部署时不要使用默认管理员密码，必须覆盖：

```bash
export CODEASK_ADMIN_USERNAME="admin"
export CODEASK_ADMIN_PASSWORD="<strong-password>"
```

如果需要让其它机器访问：

```bash
CODEASK_HOST=0.0.0.0 CODEASK_PORT=8000 ./start.sh
```

## 安装依赖

后端依赖通过 uv 安装：

```bash
uv sync
```

前端依赖通过 pnpm 安装：

```bash
corepack pnpm --dir frontend install --frozen-lockfile
```

如果环境无法使用 Corepack，也可以直接使用系统 pnpm：

```bash
pnpm --dir frontend install --frozen-lockfile
```

`start.sh` 在 `frontend/dist/index.html` 不存在时会优先使用系统 `pnpm` 自动构建前端；没有系统 `pnpm` 时再尝试 `corepack pnpm`。

项目已在 `pyproject.toml` 配置 uv 默认包索引为清华 TUNA：

```toml
[[tool.uv.index]]
name = "tuna"
url = "https://pypi.tuna.tsinghua.edu.cn/simple/"
default = true
```

## 必需环境变量

`CODEASK_DATA_KEY` 用于加密 LLM API Key 等敏感字段。它不是登录密码，也不是访问 token。丢失后，已经加密存储的敏感字段无法恢复。

首次启动前生成一个 Fernet key：

```bash
export CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

首次启动成功后，CodeAsk 会把该 key 缓存在：

```text
<CODEASK_DATA_DIR>/secrets/data.key
```

后续再次启动时，如果没有设置 `CODEASK_DATA_KEY`，服务会从数据目录缓存读取 key。正式环境仍建议把 key 写入部署系统的 secret 管理，不要提交到仓库。

关键规则：

- `CODEASK_DATA_KEY` 是数据目录主密钥，不能随意重新生成。
- 如果缓存文件已存在，环境变量中的 key 必须和缓存一致，否则服务会拒绝启动。
- 备份和迁移时必须保留 `secrets/data.key`，否则数据库中已加密的敏感字段无法恢复。
- CodeAsk 不会在没有环境变量、也没有缓存文件时自动生成 key；首次启动仍需要用户显式提供。

## 启动单进程服务

```bash
./start.sh
```

默认单进程服务地址：

```text
http://127.0.0.1:8000
```

`8000` 是后端服务端口。当前端构建产物 `frontend/dist/index.html` 存在时，后端会把前端页面挂载到 `/`，此时可以直接用浏览器打开 `8000`。开发联调时请打开 Vite dev server 的 `5173`，见下文“前端开发联调”。

如果需要让局域网或容器外部访问：

```bash
CODEASK_HOST=0.0.0.0 CODEASK_PORT=8000 ./start.sh
```

注意：当前普通用户无登录即可使用，只有全局配置由管理员登录保护。把 `CODEASK_HOST` 设为 `0.0.0.0` 前，应确认部署环境位于可信内网，或者已有外层访问控制。

健康检查：

```bash
curl -s http://127.0.0.1:8000/api/healthz -H 'X-Subject-Id: alice@dev-1' | python3 -m json.tool
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
- 会话附件上传开关
- 用户密码清空
- 特性创建、归档和特性管理员授权

未登录访客可以直接使用会话、查看特性和 Wiki，并可以在浏览器本地保存访客 LLM 配置。普通用户登录后可以管理自己的会话、用户设置和用户级 LLM 配置。特性、Wiki、仓库关联、全局配置等写操作由 admin 和特性管理员权限控制。

## Ollama 与 RAG embedding（v1.0.5）

v1.0.5 起，会话主链路 RAG 由 OpenViking 提供（详见 [docs/v1.0.5/](./docs/v1.0.5/)）。OpenViking 作为 CodeAsk 的声明依赖随 `uv sync` 安装，运行期由 CodeAsk 后端通过 `openviking-server` 子进程直接拉起；如果 `openviking-server` 缺失，请先重新执行 `uv sync`，或用 `CODEASK_OPENVIKING_BIN` 指向正确的可执行文件。但 **Ollama 进程和 embedding 模型由 operator 负责**：CodeAsk 不会自动安装 Ollama，也不会自动 `ollama pull` 模型。如果只使用 v1.0.4 行为（不启用 OpenViking），可跳过本节。

### 安装 Ollama

Linux（Ubuntu / Debian / 其他 systemd 发行版）：

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

脚本会创建 `ollama` 系统用户、写入 `/etc/systemd/system/ollama.service` 并启动监听 `127.0.0.1:11434`。详细落地路径与磁盘占用实测见 [docs/v1.0.5/specs/ollama-installation.md](./docs/v1.0.5/specs/ollama-installation.md)。

macOS：

```bash
brew install ollama
brew services start ollama
```

### 拉取 embedding 模型

v1.0.5 默认 embedding 模型是 `bge-m3`（约 1.2 GB，1024 维，中文优先）：

```bash
ollama pull bge-m3
```

如果磁盘紧张，可以临时改用更小的候选（`nomic-embed-text` ~270 MB / 768 维，`mxbai-embed-large` ~670 MB / 1024 维），但需要在 CodeAsk admin UI 中显式切换。切换 embedding 模型会触发 OpenViking 全量向量重建。

### 验证

```bash
# Ollama 自身
curl -sf http://127.0.0.1:11434/api/version
curl -sf http://127.0.0.1:11434/api/tags | python3 -m json.tool
```

`/api/tags` 应返回包含 `bge-m3`（或所选模型）的 `models` 数组。

### CodeAsk 探测行为

CodeAsk 启动时只**探测**Ollama，不操作：

- Ollama 不可达 → admin 仪表盘 `embedding_unhealthy`，OpenViking 同步任务退避，会话报错
- Ollama 可达但目标模型不在 `/api/tags` → admin 仪表盘 `embedding_model_missing`，OpenViking server 不让空转

任何情况下，CodeAsk **不会**自动执行 `ollama pull`、不会改 Ollama systemd 配置；admin 在仪表盘看到提示后需要手动在主机上 `ollama pull <model>`。

### 磁盘与端口注意

- Ollama 0.24.0 install.sh 在无 GPU 主机上仍会落地 CUDA / Vulkan runtime，安装本体约 **3.5 GB**；模型文件存放在 `/usr/share/ollama/.ollama/models`
- API 默认绑定 `127.0.0.1:11434`；跨容器或远程访问需要 operator 自行设置 `Environment="OLLAMA_HOST=0.0.0.0:11434"`，这会扩大暴露面，必须单独评估
- CPU 模式下 Ollama 一次只能跑一个 embedding；OpenViking 的 `embedding.max_concurrent` 在 CPU 部署下必须设为 `1`（CodeAsk 默认 ov.conf 已经如此配置）

## 前端开发联调

开发模式需要两个终端。

终端 1：启动后端：

```bash
CODEASK_HOST=0.0.0.0 CODEASK_PORT=8000 uv run codeask
```

终端 2：启动 Vite dev server：

```bash
corepack pnpm --dir frontend dev --host 0.0.0.0 --port 5173
```

前端开发服务器：

```text
http://127.0.0.1:5173
```

Vite 会把 `/api/*` 代理到后端 `:8000`。

如需把前端 dev server 或浏览器测试代理到非默认后端地址，可覆盖：

```bash
CODEASK_API_PROXY_TARGET=http://127.0.0.1:8010 corepack pnpm --dir frontend dev --host 0.0.0.0 --port 5173
```

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
| `CODEASK_OPENCODE_KEEPALIVE_INTERVAL_SECONDS` | 否 | `30` | opencode backend 启用时，shared `opencode serve` 进程保活检测间隔；进程退出后会自动重新拉起 |
| `LITELLM_LOCAL_MODEL_COST_MAP` | 否 | `True` | CodeAsk 启动时强制设为 `True`，禁用 LiteLLM 启动联网拉取模型价格表 |

## 本地数据目录

默认数据根目录是 `~/.codeask`：

```text
~/.codeask/
├── data.db
├── secrets/
│   └── data.key
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

- `secrets/data.key` 是本地敏感字段加密主密钥缓存，权限应为 `0600`，必须随数据目录一起备份。
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

## 升级现有部署

升级前请先阅读跨版本规则：[docs/rules/upgrade-compatibility.md](./docs/rules/upgrade-compatibility.md)。

CodeAsk 当前的升级原则是：**代码可以更新，依赖可以重装，用户数据目录不能被破坏。**

标准升级流程：

```bash
# 1. 停止当前 CodeAsk 服务

# 2. 确认数据目录，默认是 ~/.codeask
export CODEASK_DATA_DIR="${CODEASK_DATA_DIR:-$HOME/.codeask}"

# 3. 备份整个数据目录。不要只备份 data.db。
tar -czf "$HOME/codeask-backup-$(date +%Y%m%d-%H%M%S).tar.gz" -C "$(dirname "$CODEASK_DATA_DIR")" "$(basename "$CODEASK_DATA_DIR")"

# 4. 拉取新代码。也可以切换到明确的 release branch / tag。
git pull --ff-only

# 5. 更新依赖并重新构建前端。
uv sync
corepack pnpm --dir frontend install --frozen-lockfile
corepack pnpm --dir frontend build

# 6. 使用原数据目录启动。已有 secrets/data.key 时，可以不再导出 CODEASK_DATA_KEY。
./start.sh
```

如果离线环境只安装了系统 pnpm，可以把上面的两条前端命令替换为：

```bash
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
```

`./start.sh` 的前端构建兜底同样兼容这种环境。

升级成功后检查：

```bash
curl -s http://127.0.0.1:8000/api/healthz -H 'X-Subject-Id: alice@dev-1' | python3 -m json.tool
```

再用浏览器确认：

- 会话列表可以加载。
- Wiki 页面可以打开并预览文档。
- 设置页可以打开。
- 管理员账号可以登录。
- 已有 LLM 配置仍能正常使用。

回滚规则：

- 如果新版本还没有启动，数据库 migration 没有执行，可以直接切回旧代码。
- 如果新版本已经启动并执行了 migration，不要只回滚代码；应停止服务并恢复升级前备份的整个数据目录。
- 不承诺任意 Alembic downgrade 都能安全恢复业务数据。

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

Playwright 端到端测试当前会自动拉起一套隔离的真实服务：

- 后端：`127.0.0.1:8010`
- 前端：`127.0.0.1:4173`

这样不会复用你本地可能已经运行的 `5173 + 8000` 联调环境，也不会污染默认 `~/.codeask` 数据目录。

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

### `uv: command not found`

安装 uv，并确认当前 shell 能找到它：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv --version
```

### `corepack: command not found`

通常是 Node.js 版本不对，或安装包未包含 Corepack。请先确认：

```bash
node --version
```

项目要求 Node.js 22+。如果版本过低，先升级 Node.js；如果版本正确但没有 Corepack，可尝试：

```bash
npm install -g corepack
corepack enable
```

### `ERR_PNPM_UNSUPPORTED_ENGINE` 或前端依赖安装失败

确认 Node.js 是 22 或更高版本：

```bash
node --version
pnpm --version || corepack pnpm --version
```

如果刚切换过 Node 版本，重新启用 Corepack：

```bash
corepack enable
corepack prepare pnpm@10.12.1 --activate
```

### 启动时报 `CODEASK_DATA_KEY is not set`

首次启动时，先生成并导出 Fernet key：

```bash
export CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

首次启动成功后，CodeAsk 会把 key 缓存在 `<CODEASK_DATA_DIR>/secrets/data.key`。后续启动如果没有设置环境变量，会自动读取该缓存。

正式环境要把这个值持久保存到 secret 管理中。不要每次启动都生成新 key，否则已加密的 LLM API Key 将无法解密。

### 启动时报 `CODEASK_DATA_KEY conflicts with cached data key`

说明当前环境变量中的 key 和数据目录中的缓存 key 不一致。通常原因是：

- 用户对已有数据目录重新生成了一个 key。
- `CODEASK_DATA_DIR` 指向了另一个环境的数据目录。
- 部署系统 secret 配错。

处理方式：

1. 停止服务。
2. 确认当前 `CODEASK_DATA_DIR` 是否正确。
3. 如果要继续使用该数据目录，应使用 `<CODEASK_DATA_DIR>/secrets/data.key` 对应的 key。
4. 如果要恢复旧版本或旧环境，应恢复升级前备份的整个数据目录。

不要直接覆盖 `secrets/data.key`。

### 前端 dev server 访问不到 API

确认后端运行在 `:8000`，并且 Vite dev server 使用仓库里的代理配置启动：

```bash
CODEASK_HOST=0.0.0.0 CODEASK_PORT=8000 uv run codeask
corepack pnpm --dir frontend dev --host 0.0.0.0 --port 5173
```

### 后台看不到 opencode 进程

v1.0.4 默认使用 opencode backend。CodeAsk 服务启动时会 best-effort 拉起 shared `opencode serve`，并通过 keepalive 定时检测。如果进程表里看不到 opencode，先查询健康检查接口确认后端实际状态：

```bash
curl -fsS http://127.0.0.1:8000/api/healthz | python -m json.tool
```

重点查看：

- `agent_backend`：应为 `opencode`。如果是 `native`，说明当前环境变量或启动配置关闭了 opencode backend。
- `opencode.running`：`true` 表示后端认为 shared server 正在运行。
- `opencode.resolved_bin`：如果是 `null`，说明启动 CodeAsk 的进程 PATH 中找不到 `opencode`。可以设置 `CODEASK_OPENCODE_BIN` 为绝对路径。
- `opencode.last_error`：最近一次启动失败原因，例如命令不存在、权限不足或端口不可用。

如果 `resolved_bin` 是 `null`，先在启动 CodeAsk 的同一个 shell 中执行：

```bash
command -v opencode
opencode --version
```

如果命令存在但服务里仍解析不到，通常是 systemd、nohup、docker 或远程脚本启动时 PATH 和交互 shell 不一致。此时建议显式配置：

```bash
export CODEASK_OPENCODE_BIN="/absolute/path/to/opencode"
./start.sh
```

### 代码检索能力不完整

确认系统安装了 `ripgrep` 和 `universal-ctags`。缺少 `ctags` 时，符号检索相关能力和测试会受限。

```bash
rg --version
ctags --version
```

### 浏览器从远程机器访问不到服务

确认服务监听在 `0.0.0.0`，并检查防火墙或云服务器安全组：

```bash
CODEASK_HOST=0.0.0.0 CODEASK_PORT=8000 ./start.sh
```

开发联调时也需要让 Vite 监听 `0.0.0.0`：

```bash
corepack pnpm --dir frontend dev --host 0.0.0.0 --port 5173
```

### 端口被占用

单进程后端默认使用 `8000`，开发前端默认使用 `5173`。如果端口被占用：

```bash
CODEASK_PORT=8010 ./start.sh
```

开发联调时：

```bash
CODEASK_HOST=0.0.0.0 CODEASK_PORT=8010 uv run codeask
CODEASK_API_PROXY_TARGET=http://127.0.0.1:8010 corepack pnpm --dir frontend dev --host 0.0.0.0 --port 5173
```

### LiteLLM 启动时尝试联网

CodeAsk 已在项目级禁用 LiteLLM 启动联网拉取模型价格表。请确认环境中没有手动把 `LITELLM_LOCAL_MODEL_COST_MAP` 改为非 `True` 值。

## AI 部署验收清单

如果让 AI 或自动化脚本按本文部署，至少要完成以下检查：

- 工具链版本检查全部通过：Python 3.11+、uv、Node.js 22+、Corepack、git、rg、ctags。
- `uv sync` 成功完成。
- `corepack pnpm --dir frontend install --frozen-lockfile` 成功完成。
- `CODEASK_DATA_KEY` 已生成并导出；正式环境已持久保存。
- 首次启动后，`<CODEASK_DATA_DIR>/secrets/data.key` 已生成，且后续无 env 启动可读取缓存 key。
- `./start.sh` 能启动服务，日志显示监听地址和数据目录。
- `curl /api/healthz` 返回正常 JSON。
- 浏览器能打开正确地址：单进程为 `8000`，开发联调为 `5173`。
- 管理员账号能登录；正式环境已修改默认密码。
- 如果需要远程访问，`CODEASK_HOST=0.0.0.0`、防火墙和安全组已经配置。
- 开发验收阶段必须运行端到端测试：`corepack pnpm --dir frontend test:e2e --project=chromium`。

## 相关文档

- [README.md](./README.md)：产品介绍。
- [docs/v1.0/design/deployment-security.md](./docs/v1.0/design/deployment-security.md)：部署和安全边界。
- [docs/v1.0/design/api-data-model.md](./docs/v1.0/design/api-data-model.md)：API 和数据模型契约。
- [docs/v1.0/design/agent-runtime.md](./docs/v1.0/design/agent-runtime.md)：Agent 状态机和运行时。
