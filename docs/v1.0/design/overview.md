# CodeAsk 总览设计

> 本文档属于 v1.0 SDD（系统设计文档），描述 CodeAsk **怎么实现**。
>
> 产品契约（为谁 / 为什么 / 做什么 / 不做什么）见同版本 `prd/codeask.md`。**当 SDD 与 PRD 冲突时，以 PRD 为准。**

## 1. 项目定位

CodeAsk 是一个让团队成员自助查到答案、让资深工程师把脑中知识低成本沉淀下来的私有部署研发问答系统。

它面向需要私有部署的研发团队，把团队的代码、文档和已验证经验组织为可检索的知识库，让 AI 基于团队的真实知识——既让提问者随时拿到带证据的可信回答，也让贡献者不必反复口头回答同一问题。

系统要支持：

- 基于团队知识库回答问题（文档 / 规范 / 排障手册 / 已验证报告）。
- 知识库不够时进入代码层深入分析（grep / 读文件 / 符号检索）。
- 复杂查询（含日志排障）作为同一主链路上的"复杂度更深"分支处理。
- 给出回答时附证据（文档章节、文件行号、commit）；不确定时坦白。
- 让人工验证过的报告回流为知识库高优先级文档。

详见 `prd/codeask.md` §1。

## 2. 主链路

CodeAsk 主链路是**知识库优先 → 代码深入**的两层结构。完整描述见 `prd/codeask.md` §3，本节只列实现侧的关键约束。

| 复杂度 | 走向 |
|---|---|
| 简单问答 | 知识库层就结束（命中文档 → 合成回答） |
| 复杂问答 | 知识库不够 → 进代码层（worktree + grep / read_file） |
| 日志排障 | 复杂问答的特例（query 是日志 + 现象） |

**关键判断**：

- 已验证报告作为知识库内的**高优先级文档**存在，**不是单独一层**。
- "知识库够不够"由 Agent 自动判断（详见 `agent-runtime.md`）。
- 用户提问不需要选场景或类型，Agent 自动定界到特性（详见 `wiki-search.md`）。
- 代码层访问按会话隔离，使用 git worktree（详见 `code-index.md`）。

## 3. 通用框架原则

CodeAsk 不绑定 Java、Node.js、Python、Go 或任何特定框架。通用能力放在核心层，语言和平台特定能力通过插件式 Analyzer 或索引器扩展。

核心层保持通用：

- 会话与 Agent 状态机。
- 特性自动定界。
- 知识库（含已验证报告）与代码的检索优先级。
- 工具调用协议。
- 证据模型。
- 报告验证闭环。
- 仓库、commit、worktree 管理。
- `grep_code`、`read_file`、`search_wiki` 等通用工具。

可插拔增强层：

- `GenericLogAnalyzer`：一期内置的通用日志线索提取器。
- 语言 Analyzer：Java stack trace、Python traceback、Node.js stack、Go panic 等。
- 平台 Analyzer：Kubernetes、Nginx、数据库错误、云日志格式等。
- 代码符号索引器：一期以 universal-ctags 为主，后续可接 tree-sitter、LSP、调用图。

## 4. 总体架构

一期采用单进程 FastAPI 应用，前端作为独立 React/Vite 项目构建后由后端挂载静态资源——**单仓 + 单产物部署**，落地 PRD §4.4.1 "30 秒部署"承诺。

### 4.1 逻辑架构

```text
Web 研发工作台
  ├─ 会话问答
  ├─ 调查进度面板
  ├─ 证据引用
  ├─ 版本确认
  ├─ Wiki / 报告管理
  ├─ Maintainer dashboard
  └─ 全局配置

FastAPI API 网关
  ├─ REST API
  ├─ SSE 流
  ├─（一期无鉴权，详见 deployment-security.md）
  └─ 定时任务

Agent 编排器
  ├─ 自动定界
  ├─ 知识库检索 + 充分性判断（含报告高优先级合并）
  ├─ 代码调查
  ├─ 用户追问（ask_user）
  ├─ 证据归并
  └─ 答案 / 报告合成

工具系统
  ├─ wiki tools（含 search_reports）
  ├─ code tools
  ├─ log tools
  └─ ask_user

支撑服务
  ├─ Wiki 与知识检索（报告作为高优先级文档）
  ├─ 代码索引与仓库管理（全局仓库池 + 会话级 worktree）
  ├─ LLM 网关
  ├─ 会话与附件存储
  └─ 报告验证闭环
```

### 4.2 仓库结构

CodeAsk 是单仓 monorepo，但**不引入**专用 monorepo 工具（nx / turborepo / pnpm workspace）——backend（uv）和 frontend（pnpm）工具链不同，各自独立项目，CI 各跑各的。

```text
CodeAsk/
├── README.md                       # 项目入口（30 秒部署说明）
├── start.sh                        # 单脚本：build 前端 → 起 backend
├── docs/                           # PRD / SDD / Plans（版本树见 ../STRUCTURE.md）
│
├── pyproject.toml                  # Backend 在仓库根（Python 惯例）
├── uv.lock
├── .python-version
├── alembic.ini
├── alembic/                        # DB 迁移
├── src/codeask/                    # Backend 包
│   ├── api/                        # REST / SSE 路由
│   ├── db/                         # SQLAlchemy 模型 + 引擎
│   ├── agent/                      # 9 阶段状态机（详见 design/agent-runtime.md）
│   ├── wiki/                       # 知识库 / 检索（详见 design/wiki-search.md）
│   ├── code_index/                 # 仓库 / worktree（详见 design/code-index.md）
│   ├── llm/                        # LLM 网关（详见 design/llm-gateway.md）
│   ├── tools/                      # Tool 实现（详见 design/tools.md）
│   └── ...                         # settings / crypto / identity / storage / logging_config
├── tests/                          # Backend 测试（pytest + pytest-asyncio）
│
├── frontend/                       # Frontend 子项目（独立工具链）
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── vite.config.ts              # dev 时把 /api/* 反代到 :8000
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── components.json             # shadcn/ui CLI 配置
│   ├── index.html
│   ├── public/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── routes/                 # 路由（TanStack Router 或 React Router v7）
│   │   ├── pages/                  # 会话工作台 / Dashboard / Wiki / 配置
│   │   ├── components/
│   │   │   └── ui/                 # shadcn/ui 复制过来的组件
│   │   ├── hooks/
│   │   ├── lib/                    # SSE client / API client / utils
│   │   └── stores/                 # Zustand
│   ├── tests/                      # Vitest + Testing Library
│   ├── e2e/                        # Playwright
│   └── dist/                       # 构建产物（.gitignore；backend StaticFiles 挂载）
│
├── docker/
│   ├── Dockerfile                  # 多阶段：node build 前端 → python install backend → 合一镜像
│   └── docker-compose.yml
│
└── .github/workflows/
    ├── backend.yml                 # uv sync + ruff + pyright + pytest
    └── frontend.yml                # pnpm install + tsc + vitest + playwright
```

### 4.3 关键决策（仓库结构层）

| 决策 | 选择 | Why |
|---|---|---|
| 前后端是否同仓 | 同仓 | 单产物部署；backend `StaticFiles` 挂载前端构建产物 |
| 是否用 monorepo 工具 | 不用 | 一期只有一对前后端；nx / turborepo 是过度设计 |
| backend 在根 vs `backend/` 子目录 | 在根 | Python `pyproject.toml` 在根是绝大多数项目惯例 |
| frontend 在 `frontend/` 子目录 | 是 | 工具链与 backend 不同，必须分目录隔离 |
| 前端 dev 与 backend 联调 | Vite proxy | 前端 5173 / backend 8000；`/api/*` 反代；上线时 backend 挂 `frontend/dist/` |
| 部署形态 | 单进程 + 单端口 | 落地 PRD §4.4.1 "30 秒部署"——零反向代理、零外部服务 |
| Docker 镜像 | 多阶段单镜像 | node build 前端 → python install backend → 合一；详见 07 deployment 子计划 |

## 5. 组件边界

| 组件 | 职责 | 不负责 |
|---|---|---|
| Agent 运行时 | 状态机、提示组装、工具调用、终止条件、事件输出 | 直接读数据库或文件 |
| 工具系统 | Agent 与外部世界的唯一交互通道 | 决定业务流程 |
| Wiki 检索 | 文档、特性、报告检索与摘要（含报告高优先级合并） | 代码仓库检索 |
| 代码索引 | 仓库注册、worktree、grep、文件读取、符号索引 | 解释业务语义 |
| 证据与报告 | 结构化证据、报告生成、验证、入库 | 任意替代人工验证 |
| LLM 网关 | 模型协议、流式、工具调用解码、重试 | 业务状态机 |
| 前端工作台 | 用户输入、调查可视化、证据展示、配置管理 | 后端推理逻辑 |

## 6. 文档地图

本版本（v1.0）所有 SDD 在 `design/` 目录下；同版本 PRD 在 `prd/codeask.md`，是产品契约的权威来源。

| 文档 | 内容 |
|---|---|
| `overview.md` | 项目定位、主链路、整体架构、组件边界（本文件） |
| `debugging-workflow.md` | 日志排障作为复杂查询特例的处理流程 |
| `agent-runtime.md` | Agent 状态机、工具循环、Prompt 分层、SSE |
| `evidence-report.md` | 证据链、回答结构、报告闭环、验证闸门 |
| `tools.md` | Tool Protocol、工具清单、JSON Schema、错误处理 |
| `wiki-search.md` | 特性、文档、报告、多路召回、FTS5、n-gram、回源引用 |
| `code-index.md` | 全局仓库池、会话级 worktree、commit/ref、grep、ctags |
| `session-input.md` | 会话、输入、附件、上下文、版本确认 |
| `frontend-workbench.md` | 研发工作台页面与交互 |
| `api-data-model.md` | REST/SSE API、SQLite schema、目录布局 |
| `llm-gateway.md` | OpenAI / Anthropic / OpenAI-compatible 通用协议、流式、工具调用、模型配置 |
| `deployment-security.md` | 私有部署、一期无鉴权与未来扩展通道、清理任务、安全边界 |
| `testing-eval.md` | 单测、集成测试、Agent eval、CI |

## 7. 关键决策

| 决策 | 选择 |
|---|---|
| 产品形态 | 私有部署研发问答系统（Maintainer 沉淀知识 + Asker 自助提问，飞轮两端同等重要） |
| 一期主链路 | 知识库优先 → 代码深入；日志排障作为复杂查询特例 |
| 技术栈支持 | 核心通用，语言能力插件化 |
| 输入方式 | 自然语言提问，可附日志 / 截图 / 文件；不需选场景或类型 |
| 外部日志平台 | 后续扩展，一期不直接接入 |
| 代码版本策略 | 可先默认分支预查；最终报告必须绑定明确 commit |
| 检索优先级 | 知识库（含已验证报告高优先级）→ 代码 |
| 知识污染防护 | 报告人工验证后才进入高优先级检索 |
| LLM 协议 | 一期直接支持 OpenAI、Anthropic 和 OpenAI-compatible，Agent 只依赖内部通用接口 |
| 鉴权 | 一期完全无鉴权（私有部署 + 127.0.0.1）；未来通过前后端 `AuthProvider` 扩展通道对接 OIDC / LDAP / 企业 IM 等 |
| 报告验证 | 一期任何人都能验证（"特性 owner" 是命名上的角色，靠社会契约约束） |
| 部署形态 | 小团队私有部署，默认本机监听 |
| 数据库 | SQLite + FTS5，一期零中间件；Wiki 检索采用多路召回，不依赖向量数据库 |

## 8. 与 PRD 的对齐

本文已按 `prd/codeask.md` §9 对齐表更新，主要变化：

- 删除 P0 / P1 / P2 / P3 阶段优先级（旧 §2 整节移除）
- 主链路从"已验证报告 → 知识库 → 代码"三层简化为"知识库（含报告）→ 代码"两层
- Agent 编排器中"报告检索 / 知识库检索"合并为"知识库检索 + 充分性判断"
- 鉴权从"master token"改为"一期无鉴权 + 前后端 AuthProvider 扩展通道"
- 报告验证从"特性 owner 强制"改为"任意人可验证 + 社会契约约束"
- §4 拆出 §4.1 逻辑架构 / §4.2 仓库结构 / §4.3 关键决策（仓库层），承接 PRD §4.4.1 "30 秒部署"承诺——单仓 + backend 在根 + `frontend/` 子目录 + 单产物部署

详细对齐表见 `prd/codeask.md` §9。
