# CodeAsk

CodeAsk 是一个私有部署的研发问答系统，帮助团队把内部文档、代码和已验证的工程经验组织成可检索的知识库，并基于这些真实知识提供带证据的可信回答。

它面向需要私有部署的研发团队，解决“知识卡在某个人脑子里”的问题：提问者可以自助获得答案，资深工程师也可以把反复回答的问题低成本沉淀下来，减少重复打断。

## 当前状态

CodeAsk 目前处于 v1.0 MVP 的后端增量实现阶段。

产品需求、系统设计和实现计划位于 `docs/v1.0/`。当前已完成：

- `foundation`：后端应用骨架、配置、存储布局、数据库、Alembic 迁移、加密、自报身份中间件、结构化日志和健康检查。
- `wiki-knowledge`：特性、文档上传与切块、SQLite FTS5 检索、已验证报告、报告验证 / 撤销闭环，以及 `/api/features`、`/api/documents`、`/api/reports`。
- `code-index`：全局仓库池、异步 clone、会话级 worktree、`/api/repos`、`/api/code/grep`、`/api/code/read`、`/api/code/symbols`，以及 24 小时闲置 worktree 清理。

下一阶段是 `agent-runtime`：会话、LLM 网关、Agent 状态机、工具调用、SSE 和轨迹记录。

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
- 一期无登录、无鉴权
- 基于自报身份的会话归属
- SQLite 本地存储
- 知识库文档管理与检索
- 已验证报告作为高优先级知识
- 全局代码仓库池
- 特性与仓库关联
- 会话级 git worktree 隔离
- Agent 自动定界到特性
- Agent 自动判断知识库是否足够
- 代码工具调用，包括 grep、读取文件、符号查找
- 带证据的答案生成
- 报告草稿与人工验证闭环
- Maintainer dashboard
- 单机部署与 Docker 部署

v1.0 MVP 暂不包含：

- 多租户 SaaS
- 登录与权限系统
- 自动修 PR
- IDE 插件
- 实时监控或告警系统
- 外部向量数据库作为核心依赖
- 与 ELK、Loki、Splunk 等日志平台的直接对接

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

前端计划采用：

- React 19
- Vite
- TypeScript
- Tailwind CSS v4
- shadcn/ui
- TanStack Query
- TanStack Router 或 React Router
- Zustand
- Vitest
- Playwright

部署目标是单进程、单端口、低依赖，优先满足小团队私有部署和 30 秒启动体验。

## 当前仓库结构

当前仓库已经包含文档、foundation 后端地基、wiki-knowledge 后端知识库能力和 code-index 代码索引能力：

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
│       ├── code_index/
│       ├── db/
│       └── wiki/
├── tests/
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

后续前端、部署和 CI 计划完成后，还会补充如下目录：

```text
CodeAsk/
├── frontend/
├── docker/
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

在 v1.0 中，PRD 是产品契约。如果 PRD 与 SDD 冲突，以 PRD 为准，SDD 应同步更新。

## 实施路线

v1.0 实现被拆成七个 plan：

| # | Plan | 状态 | 说明 |
|---|---|---|---|
| 1 | `foundation` | 已完成 | 后端应用骨架、配置、存储、数据库、迁移、加密、身份、日志、健康检查 |
| 2 | `wiki-knowledge` | 已完成 | 特性、文档、文档切块、报告、FTS 检索、知识库召回 |
| 3 | `code-index` | 已完成 | 仓库注册、异步 clone、worktree、grep、文件读取、符号索引 |
| 4 | `agent-runtime` | 下一阶段 | LLM 网关、会话、Agent 状态机、工具调用、SSE、轨迹记录 |
| 5 | `frontend-workbench` | 未开始 | React 工作台、会话界面、证据展示、配置页面、Maintainer dashboard |
| 6 | `metrics-eval` | 未开始 | 反馈、前端事件、审计日志、Agent eval、质量门禁 |
| 7 | `deployment` | 未开始 | 前端静态挂载、Docker、docker-compose、CI、安全检查和发布 smoke test |

下一阶段应从 `docs/v1.0/plans/agent-runtime.md` 开始。

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

健康检查：

```bash
curl -s http://127.0.0.1:8000/api/healthz -H 'X-Subject-Id: alice@dev-1' | python -m json.tool
```

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

当前测试环境如果缺少 `ctags`，符号相关测试会跳过；安装 `universal-ctags` 后会自动执行。后续 Docker 镜像会在 `deployment` 阶段内置这些工具。

## 配置项

| 环境变量 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `CODEASK_DATA_KEY` | 是 | — | Fernet key，base64-url-safe 32 bytes。用于加密敏感字段；丢失后已加密字段不可恢复。 |
| `CODEASK_DATA_DIR` | 否 | `~/.codeask` | SQLite、上传文件、worktree、日志等本地数据根目录。 |
| `CODEASK_HOST` | 否 | `127.0.0.1` | 默认只监听本机，一期无鉴权时不要随意改成公网监听。 |
| `CODEASK_PORT` | 否 | `8000` | HTTP 服务端口。 |
| `CODEASK_LOG_LEVEL` | 否 | `INFO` | 可设为 `DEBUG` / `INFO` / `WARNING` / `ERROR`。 |
| `CODEASK_DATABASE_URL` | 否 | 基于 `CODEASK_DATA_DIR` 派生 | 默认是本地 SQLite；通常只在测试或迁移数据库时覆盖。 |

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

## License

License 尚未确定。
