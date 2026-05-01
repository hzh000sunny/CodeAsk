# CodeAsk

CodeAsk 是一个私有部署的研发问答系统，帮助团队把内部文档、代码和已验证的工程经验组织成可检索的知识库，并基于这些真实知识提供带证据的可信回答。

它面向需要私有部署的研发团队，解决“知识卡在某个人脑子里”的问题：提问者可以自助获得答案，资深工程师也可以把反复回答的问题低成本沉淀下来，减少重复打断。

## 当前状态

CodeAsk 目前已完成 v1.0 MVP 的 metrics-eval 阶段，正在进行 deployment 阶段。v1.0 的 deployment 只包含本地单进程部署、前端静态挂载、CI 和安全审计；Docker / compose / 镜像发布后置为独立计划。

产品需求、系统设计和实现计划位于 `docs/v1.0/`。当前已完成：

- `foundation`：后端应用骨架、配置、存储布局、数据库、Alembic 迁移、加密、自报身份中间件、结构化日志和健康检查。
- `wiki-knowledge`：特性、文档上传与切块、SQLite FTS5 检索、已验证报告、报告验证 / 撤销闭环，以及 `/api/features`、`/api/documents`、`/api/reports`。
- `code-index`：全局仓库池、异步 clone、会话级 worktree、`/api/repos`、`/api/code/grep`、`/api/code/read`、`/api/code/symbols`，以及 24 小时闲置 worktree 清理。
- `agent-runtime`：LLM 配置、会话、Skill、9 阶段 Agent 状态机、LLM Gateway、ToolRegistry、SSE 事件、agent_traces 轨迹记录，以及 `/api/llm-configs`、`/api/skills`、`/api/sessions`。
- `frontend-workbench`：React 工作台、会话界面、特性页面、设置页、管理员登录、个人 / 全局 LLM 配置隔离、会话附件管理、报告生成入口和 Playwright smoke。
- `metrics-eval`：反馈表、前端事件表、审计日志表、`/api/feedback`、`/api/events`、`/api/audit-log`、跨计划 audit hook、Agent eval harness 和 GitHub Actions eval workflow。

当前阶段是 `deployment`。完整 LLM Wiki 目录管理和 Docker packaging 都已明确后置为独立专项。

## 产品目标

CodeAsk 的核心目标是：

> 让团队知识不再卡在某个人脑子里。

它服务于两类同等重要的用户：

- Maintainer：负责模块、系统或特性的资深工程师，把文档、经验、排障结论沉淀进知识库。
- Asker：新人、跨模块协作者、oncall 工程师等，通过自然语言提问获得带证据的回答。

CodeAsk 不是通用代码助手，也不是无知识库支撑的零样本代码理解工具。它的重点是基于团队自己的文档、代码和已验证经验回答问题。

## 核心工作流

CodeAsk 采用“知识库优先，代码深入分析兜底”的主链路：

1. 用户创建特性，作为知识和代码检索的边界。
2. Maintainer 上传文档、规范、排障手册等知识材料。
3. 团队注册代码仓库，并把仓库关联到对应特性。
4. Asker 用自然语言提问，不需要选择场景或问题类型。
5. Agent 自动判断问题属于哪个特性。
6. 系统优先检索知识库，包括已验证报告和普通文档。
7. 如果知识库不足以回答，Agent 进入代码层，通过独立 worktree、grep、文件读取、符号查找等工具分析代码。
8. 系统生成带证据的回答，引用文档、代码片段和 commit 信息。
9. 有价值的问答可以沉淀为报告草稿，经人工验证后进入知识库，成为后续检索的高优先级内容。

## v1.0 MVP 范围

v1.0 MVP 包含：

- 私有部署
- 普通用户无登录直接使用
- 基于自报身份的会话归属
- 内置管理员登录保护全局 LLM 配置和全局仓库写操作
- SQLite 本地存储
- 基础知识库文档上传、管理与检索
- 已验证报告作为高优先级知识
- 全局代码仓库池
- 特性与仓库关联
- 会话级 git worktree 隔离
- Agent 自动定界到特性
- Agent 自动判断知识库是否足够
- 代码工具调用，包括 grep、读取文件、符号查找
- 带证据的答案生成
- 报告草稿与人工验证闭环
- 单机部署

v1.0 MVP 暂不包含：

- 多租户 SaaS
- 企业级登录与权限系统
- 自动修 PR
- IDE 插件
- 实时监控或告警系统
- 外部向量数据库作为核心依赖
- 与 ELK、Loki、Splunk 等日志平台的直接对接
- 完整 LLM Wiki 目录上传、相对资源保存、在线预览 / 编辑 / re-index 工作流
- Docker / compose / 镜像发布

## 技术方向

后端计划采用：

- Python 3.11+
- FastAPI
- SQLAlchemy 2.0 async
- Alembic
- SQLite + FTS5
- Pydantic v2
- pydantic-settings
- cryptography / Fernet
- structlog
- pytest / pytest-asyncio
- uv

前端当前实现采用：

- React 19
- Vite
- TypeScript
- Tailwind CSS v4
- lucide-react
- TanStack Query
- TanStack Router 依赖已引入；当前工作台导航仍由 `AppShell` 内部状态驱动
- Zustand
- Vitest
- Playwright

部署目标是单进程、单端口、低依赖，优先满足小团队私有部署和 30 秒启动体验。

## 当前仓库结构

当前仓库已经包含文档、foundation 后端地基、wiki-knowledge 后端知识库能力、code-index 代码索引能力、agent-runtime 后端问答运行时和 frontend React 工作台：

```text
CodeAsk/
├── README.md
├── start.sh
├── pyproject.toml
├── uv.lock
├── alembic.ini
├── alembic/
├── src/
│   └── codeask/
│       ├── api/
│       ├── agent/
│       ├── code_index/
│       ├── db/
│       ├── llm/
│       └── wiki/
├── tests/
├── frontend/
├── docs/
│   ├── README.md
│   ├── STRUCTURE.md
│   └── v1.0/
│       ├── README.md
│       ├── prd/
│       │   └── codeask.md
│       ├── design/
│       ├── plans/
│       └── specs/
└── .claude/
```

后续 deployment 计划完成后，还会补充如下目录：

```text
CodeAsk/
└── .github/
```

## 文档入口

推荐阅读顺序：

1. `docs/README.md`：文档版本入口
2. `docs/STRUCTURE.md`：文档结构与版本规则
3. `docs/v1.0/prd/codeask.md`：产品需求文档，定义产品契约
4. `docs/v1.0/design/overview.md`：系统设计总览
5. `docs/v1.0/plans/roadmap.md`：v1.0 实施路线图
6. `docs/v1.0/plans/foundation.md`：已完成的后端地基计划
7. `docs/v1.0/plans/wiki-knowledge.md`：已完成的知识库计划
8. `docs/v1.0/plans/code-index.md`：已完成的代码索引计划
9. `docs/v1.0/plans/agent-runtime.md`：已完成的 Agent 运行时计划
10. `docs/v1.0/plans/agent-runtime-handoff.md`：交给前端、metrics-eval、deployment 的运行时契约

在 v1.0 中，PRD 是产品契约。如果 PRD 与 SDD 冲突，以 PRD 为准，SDD 应同步更新。

## 实施路线

v1.0 实现被拆成七个 plan：

| # | Plan | 状态 | 说明 |
|---|---|---|---|
| 1 | `foundation` | 已完成 | 后端应用骨架、配置、存储、数据库、迁移、加密、身份、日志、健康检查 |
| 2 | `wiki-knowledge` | 已完成 | 特性、文档、文档切块、报告、FTS 检索、知识库召回 |
| 3 | `code-index` | 已完成 | 仓库注册、异步 clone、worktree、grep、文件读取、符号索引 |
| 4 | `agent-runtime` | 已完成 | LLM 网关、会话、Agent 状态机、工具调用、SSE、轨迹记录、运行时 API |
| 5 | `frontend-workbench` | 已完成 | React 工作台、会话界面、特性页面、设置页面、管理员入口、LLM 配置、附件和报告入口 |
| 6 | `metrics-eval` | 已完成 | 反馈、前端事件、审计日志、Agent eval、质量门禁 |
| 7 | `deployment` | 进行中 | 前端静态挂载、`start.sh` 本地启动、CI、安全检查和发布 smoke test |

当前阶段执行文件为 `docs/v1.0/plans/deployment.md`。

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

如果 `frontend/dist/index.html` 不存在，`start.sh` 会在 `corepack pnpm` 可用时自动构建前端；如果本机没有前端工具链，后端仍会启动，`/api/*` 可用，同时终端会提示你如何手动构建前端。

健康检查：

```bash
curl -s http://127.0.0.1:8000/api/healthz -H 'X-Subject-Id: alice@dev-1' | python -m json.tool
```

### 前端联调

开发前端时可以单独启动 Vite dev server：

```bash
cd frontend
corepack pnpm install
corepack pnpm dev
```

前端开发服务器监听 `http://127.0.0.1:5173`，并把 `/api/*` 代理到后端 `:8000`。后端仍按上面的 `./start.sh` 启动。

### 常用测试

```bash
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run pyright src/codeask
corepack pnpm --dir frontend test:run
corepack pnpm --dir frontend build
```

## Python 依赖源

项目已在 `pyproject.toml` 配置 uv 默认包索引：

```toml
[[tool.uv.index]]
name = "tuna"
url = "https://pypi.tuna.tsinghua.edu.cn/simple/"
default = true
```

因此新环境中直接执行 `uv sync` 即会使用清华 TUNA PyPI 镜像源，不需要额外追加 `--default-index`。如需临时改回官方 PyPI，可用命令行参数或本机用户级 uv 配置覆盖。

## 文档解析依赖

后端解析上传文档时使用以下库（已通过 `uv sync` 安装，无需手工配置）：

| 文件类型 | 解析库 |
|---|---|
| Markdown / 文本 | `markdown-it-py` |
| PDF | `pypdfium2` |
| DOCX | `python-docx` |

未来扩展类型（Excel 等）参考 `docs/v1.0/design/dependencies.md` §2.5。

## 代码索引系统依赖

代码索引子系统会调用本机标准工具。以下命令需要能在 `$PATH` 中找到：

| 工具 | 用途 | 建议版本 |
|---|---|---|
| `git` | bare clone、worktree add/remove、rev-parse | 2.30+ |
| `rg`（ripgrep） | 代码全文检索，支撑 `/api/code/grep` | 13+ |
| `ctags`（universal-ctags） | 符号查找，支撑 `/api/code/symbols` | universal-ctags 5.9+，不是 Exuberant Ctags |

Debian / Ubuntu 可安装：

```bash
apt-get install git ripgrep universal-ctags
```

macOS 可安装：

```bash
brew install git ripgrep universal-ctags
```

当前测试环境如果缺少 `ctags`，符号相关测试会跳过；安装 `universal-ctags` 后会自动执行。后续容器化包装计划会把这些系统工具打进镜像，但不属于 v1.0 deployment。

## 配置项

| 环境变量 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `CODEASK_DATA_KEY` | 是 | — | Fernet key，base64-url-safe 32 bytes。用于加密敏感字段；丢失后已加密字段不可恢复。 |
| `CODEASK_DATA_DIR` | 否 | `~/.codeask` | SQLite、上传文件、worktree、日志等本地数据根目录。 |
| `CODEASK_HOST` | 否 | `127.0.0.1` | 默认只监听本机，一期无鉴权时不要随意改成公网监听。 |
| `CODEASK_PORT` | 否 | `8000` | HTTP 服务端口。 |
| `CODEASK_LOG_LEVEL` | 否 | `INFO` | 可设为 `DEBUG` / `INFO` / `WARNING` / `ERROR`。 |
| `CODEASK_DATABASE_URL` | 否 | 基于 `CODEASK_DATA_DIR` 派生 | 默认是本地 SQLite；通常只在测试或迁移数据库时覆盖。 |
| `CODEASK_FRONTEND_DIST` | 否 | `<repo>/frontend/dist` | 前端构建产物目录；存在 `index.html` 时由后端挂载到 `/`。 |

## 开发约定

后续按 plan 文件逐步实现，每个任务保持小步提交，并优先遵循对应 plan 中的测试步骤和验收标准。

常用检查命令：

```bash
uv sync
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run pyright src/codeask
```

## 新会话接手

新会话或新环境接手时，建议先确认本地 `main` 已同步到 `origin/main`，然后直接执行：

```bash
uv sync
uv run pytest -q
```

项目级 `pyproject.toml` 已配置清华 TUNA PyPI 镜像源，`uv sync` 默认会使用该镜像。

下一阶段从 `docs/v1.0/plans/deployment.md` 开始。新会话接手时建议按顺序快速重读：

1. `README.md`
2. `docs/v1.0/plans/roadmap.md`
3. `docs/v1.0/specs/frontend-workbench-handoff.md`
4. `docs/v1.0/plans/metrics-eval.md`
5. `docs/v1.0/plans/deployment.md`
6. `docs/v1.0/design/` 下与部署、安全、API、前端和 Agent 运行时相关的设计文档

## License

License 尚未确定。
