# 依赖与技术选型

> 本文档属于 v1.0 SDD，统一锁定**组件层**（库 / 工具链）选型，避免实现阶段每个模块各自拍脑袋导致栈分裂。
>
> **应用层自研**——状态机、定界、充分性判断、报告飞轮、A2/A3 透明、Maintainer dashboard 等核心产品逻辑不复用第三方应用。理由见 §11。
>
> 当 SDD 与 PRD 冲突时，以 PRD 为准。PRD §4.3 显式不锁的事（LLM 供应商 / 索引技术 / DB 选型 / clone 实现），本文给推荐方案 + 替换通道。

## 1. 选型原则

| 原则 | 含义 |
|---|---|
| **低部署门槛优先**（PRD §4.4.1） | 一切依赖都要兼容"30 秒上手"承诺：单进程、零外部服务、SQLite 即可跑 |
| **显式优于魔法** | 拒绝过度抽象的框架（LangChain / LlamaIndex 类）——Agent 状态机要可读可调试 |
| **标准库 / 主流方案优先** | 不为节省 100 行代码引入小众依赖；社区 + 文档质量是重要分母 |
| **复用必须有锚点** | 每条依赖说明为什么用 + 不用什么替代品 + 何时该换 |
| **PRD 不锁的留替换通道** | LLM 供应商 / 索引引擎 / DB 都通过抽象接口接入，换实现不改业务 |

## 2. 后端组件

### 2.1 核心 Web 栈

| 用途 | 推荐 | 不用 | 备注 |
|---|---|---|---|
| Python 版本 | **3.11+** | 3.10 及以下 | match / TaskGroup / 更好的错误信息 |
| Web 框架 | **FastAPI** | Flask / Django / Starlette 直用 | 已在 `deployment-security.md` §2 锁定；Pydantic v2 一等公民 |
| ASGI 服务器 | **uvicorn**（生产可加 `--workers` 或 `gunicorn -k uvicorn.workers.UvicornWorker`） | hypercorn | 标准品 |
| 数据校验 | **Pydantic v2** | dataclasses + 手写校验 | FastAPI 原生 |
| HTTP 客户端 | **httpx**（同步 + 异步） | requests / aiohttp 各一份 | 一个库覆盖两个场景 |
| 后台任务 | **APScheduler** | Celery / RQ / dramatiq | 已在 `deployment-security.md` §7 锁定；私有部署不引入 broker |

### 2.2 数据库与迁移

| 用途 | 推荐 | 不用 | 备注 |
|---|---|---|---|
| 默认 DB | **SQLite**（WAL 模式） | Postgres（强行要求服务化） | 已在多处锁定；满足"30 秒部署"承诺 |
| ORM | **SQLAlchemy 2.0**（async 风格） | SQLModel / Tortoise / 裸 SQL | 与 Pydantic 解耦边界更清；SQLModel 把 ORM 和 schema 绑死，长期会疼 |
| 迁移 | **Alembic** | 手写 SQL / Django migration | SQLAlchemy 标配 |
| 全文检索 | **SQLite FTS5 + n-gram tokenizer**（自定义） | Tantivy / Elasticsearch / Meilisearch | 已在 `wiki-search.md` 锁定；中文 n-gram 兜底由代码层实现 |

**Postgres 替换通道**：SQLAlchemy URL 切换即可，业务代码不改；前提是迁移到 PG 时把 FTS5 替换为 `tsvector` 或 PG 的 trigram。

### 2.3 LLM 调用

| 用途 | 推荐 | 不用 | 备注 |
|---|---|---|---|
| 多供应商 | **LiteLLM**（薄抽象 + 100+ provider） 或 **直接 httpx + 三家 SDK** | LangChain / LlamaIndex 的 LLM wrapper | 见下方权衡 |
| Prompt 管理 | **Python 模板字符串 / Jinja2** | LangChain PromptTemplate / Guidance | 显式优于魔法 |
| Agent 编排 | **自研状态机**（详见 `agent-runtime.md`） | LangGraph / CrewAI / AutoGen | A2/A3 透明 + 状态机 9 阶段都需要可控；框架带来的抽象会反过来阻碍 |
| Token 计数 | **tiktoken**（OpenAI 系） + **anthropic SDK 自带** | 自己估算 | 成本统计需要 |
| 流式输出 | **SSE**（FastAPI `StreamingResponse`） | WebSocket | 单向流足够；浏览器原生 EventSource 兼容 |

**LiteLLM vs 直连**：

- **LiteLLM**：开箱即用 100+ provider，含 OpenAI-compatible / Anthropic / 本地（Ollama / vLLM）。dep 略重但维护活跃。
- **直连**：只支持 OpenAI / Anthropic / 一种本地模型时，三个 SDK 加起来比 LiteLLM 还简单；但 PRD §4.3 明确不锁供应商 + 私有部署用户的供应商五花八门。
- **建议**：MVP 用 **LiteLLM**——避开"用户用了 deepseek-coder 我们没适配"的支持成本；如果后续发现 LiteLLM 在某些场景失控（比如 stream chunking 异常），再剥离到自家 provider 抽象。

**显式不引入 LangChain / LlamaIndex**：

- Agent 控制流我们已经设计成显式 9 阶段状态机（`agent-runtime.md`），框架会反向约束；
- 框架升级频繁，私有部署用户跟不上；
- 调试 prompt 时多一层抽象 = 多一倍痛苦。

### 2.4 工具链（代码 / 文件）

| 用途 | 推荐 | 不用 | 备注 |
|---|---|---|---|
| Git 操作 | **subprocess + git CLI**（参数数组传参） | pygit2 / GitPython | 已在 `code-index.md` 锁定；libgit2 的 worktree API 缺陷较多 |
| 全文搜索（代码） | **ripgrep**（`rg --json`） | Python 自实现 / ack | 已锁定 |
| 符号定位 | **universal-ctags** | tree-sitter（一期）/ LSP | 已锁定；tree-sitter 是 future replacement |
| 文件读取 | **stdlib + 路径白名单** | aiofiles | 简单足够 |

### 2.5 文档解析

| 用途 | 推荐 | 备注 |
|---|---|---|
| Markdown | **markdown-it-py** | 比 mistune / python-markdown 更接近 CommonMark |
| PDF | **pypdfium2** | Apache 协议；pdfplumber 也可，按性能取舍 |
| DOCX | **python-docx** | 标准品 |
| Excel（如需） | **openpyxl** | 若有团队上传 .xlsx |

### 2.6 安全 / 加密

| 用途 | 推荐 | 备注 |
|---|---|---|
| 字段加密（API Key） | **cryptography (Fernet)** | 由 `CODEASK_DATA_KEY` 环境变量提供主密钥，详见 `deployment-security.md` §5 |
| 密码哈希（未来鉴权） | **bcrypt** 或 **argon2-cffi** | 一期不需要 |
| 路径校验 | **stdlib pathlib + 自家校验函数** | 防 `../` 越狱 |

### 2.7 日志 / 观测

| 用途 | 推荐 | 备注 |
|---|---|---|
| 结构化日志 | **structlog** | JSON 输出方便后续接 ELK |
| 请求 trace | **starlette middleware 自实现 trace_id** | OpenTelemetry 一期不上 |
| Agent 轨迹 | **写 DB（`agent_traces` 表）** | 详见 `agent-runtime.md` §13；**不写日志文件** |

## 3. 前端组件

### 3.1 核心栈

| 用途 | 推荐 | 不用 | 备注 |
|---|---|---|---|
| 框架 | **React 19**（含 useTransition / Server Components 兼容） | Vue / Svelte / Solid | 生态决定；与组件库丰富度匹配 |
| 构建工具 | **Vite** | webpack / CRA | 标准品 |
| 类型系统 | **TypeScript 严格模式** | JS / Flow | 必须 |
| 包管理 | **pnpm** | npm / yarn | 私有部署友好（hardlink + 离线模式） |

### 3.2 UI 与样式

| 用途 | 推荐 | 不用 | 备注 |
|---|---|---|---|
| 组件库 | **shadcn/ui**（Radix + Tailwind，复制式） | MUI / Mantine / Ant Design | 见下方权衡 |
| 样式 | **Tailwind CSS v4** | CSS-in-JS（emotion / styled） | 与 shadcn 一体；私有部署无运行时开销 |
| 图标 | **lucide-react** | heroicons / phosphor | shadcn 默认 |
| 字体 | **系统字体栈** + 等宽 JetBrains Mono / Fira Code 自托管 | Google Fonts CDN | 私有部署不依赖外部 CDN |

**shadcn/ui vs MUI / Ant**：

- shadcn 是"复制粘贴"模型——组件代码进我们仓库，不是 npm 黑盒。**改样式不打架**、bundle 小、Tailwind 原生。对 PRD §8.4"oncall 凌晨 2 点要看清"那种密集信息布局尤其合适（Tailwind utility 调对比度比 MUI 主题改起来快得多）。
- MUI / Ant 设计语言强——会拽着我们走它的设计；CodeAsk 要"研发工作台"风格不是"管理后台"风格。

### 3.3 数据 / 状态

| 用途 | 推荐 | 不用 | 备注 |
|---|---|---|---|
| 服务端状态 | **TanStack Query**（v5） | SWR / Redux Toolkit Query | 缓存 + invalidate 模型最自然 |
| 客户端状态 | **Zustand** | Redux / Recoil / Jotai | 用到再上；很多页面 useState 够了 |
| 表单 | **react-hook-form** + **zod** | Formik | 与 TS 类型对齐 |
| 路由 | **TanStack Router** 或 **React Router v7** | Next.js | 一期是 SPA；路由器二选一 |

### 3.4 SSE / 流式

| 用途 | 推荐 | 不用 | 备注 |
|---|---|---|---|
| SSE 客户端 | **microsoft/fetch-event-source** | 原生 EventSource | 原生不支持自定义 header / POST，未来加鉴权会卡 |

### 3.5 渲染

| 用途 | 推荐 | 不用 | 备注 |
|---|---|---|---|
| Markdown 渲染（回答 / 文档展示） | **react-markdown** + remark-gfm + rehype-raw（按需） | mdx-js（重） / 自写 parser | 标准 |
| 代码高亮 | **shiki**（VS Code 同款 grammar） | highlight.js / prism | 高亮质量明显领先；可 SSR |
| 数学（如需） | **KaTeX** | MathJax | 轻 |
| 图表（dashboard） | **Recharts** | ECharts / D3 直用 | 一期 dashboard 折线图 / 柱图够用，不需要 D3 灵活度 |
| 文档编辑器（如需 in-app 编辑） | **TipTap** | CodeMirror / Slate / Lexical | TipTap 适合富文本，CodeMirror 适合代码 |

**编辑器一期是否要 in-app**：PRD 没要求 in-app 编辑——上传 + 拖目录就行。**一期不引入 TipTap**，等 MVP+ 评估"录入摩擦最大瓶颈是不是缺编辑器"再决定。

## 4. 测试

| 用途 | 推荐 | 备注 |
|---|---|---|
| 后端单元 / 集成 | **pytest** + **pytest-asyncio** + **pytest-httpx** | 已在 `testing-eval.md` 体现 |
| 后端 LLM mock | **MockLLMClient** 自实现（`testing-eval.md` §3） | LiteLLM 自带 mock 但太粗 |
| 前端组件 | **Vitest** + **Testing Library** | jest 退役 |
| 端到端 | **Playwright** | Cypress | Playwright 更稳、跨浏览器 |
| Agent eval 运行 | **自家 runner**（详见 `testing-eval.md` §4.5） | 不引入 ragas / promptfoo | 锁定到 case schema 即可 |

## 5. 部署

| 用途 | 推荐 | 备注 |
|---|---|---|
| 单机部署 | **`start.sh`**（systemd unit 可选） | 最低门槛 |
| Docker | **多阶段构建 + alpine-based**（最终镜像 ~150MB） | 含 git / ripgrep / universal-ctags |
| Compose | **docker-compose.yml**（单服务） | 默认无 PG / Redis / Elasticsearch |
| 包发布 | **uv** 管 Python deps，**pnpm** 管前端 deps | uv 比 pip / poetry 快、lockfile 干净 |

**为什么不用 K8s helm chart**：PRD §4.4.1"30 秒部署"承诺。Helm 进来等于把"小团队私有部署"门槛拉高一截。可作为社区适配，不进官方默认路径。

## 6. 工程工具

| 用途 | 推荐 |
|---|---|
| Python lint | **ruff**（含 lint + format，替 flake8 + black + isort） |
| Python type check | **mypy** 或 **pyright**（pyright 更快，VS Code 无缝） |
| TS lint | **eslint** + **typescript-eslint** |
| TS format | **prettier** |
| Pre-commit | **pre-commit** + ruff / prettier hook |
| CI | **GitHub Actions**（开源仓库） / **Drone / Gitea Actions**（私有部署友好） |

## 7. 显式不引入的依赖（Anti-list）

| 不用 | 理由 |
|---|---|
| **LangChain / LlamaIndex / Haystack** | Agent 状态机已显式设计，引入框架反向约束；版本冲突地狱 |
| **Streamlit / Gradio** | 不是生产多用户应用方案 |
| **向量数据库（Pinecone / Weaviate / Milvus / Qdrant）** | PRD §6.2 MVP Anti-Goal "不做向量检索作为核心依赖"；FTS5 + n-gram + 精确信号召回够 |
| **Embedding 模型推理（local sentence-transformers）** | 同上；未来如需，叠加在 SQLite + sqlite-vec 上即可 |
| **Redis / RabbitMQ / Kafka** | 单进程 + APScheduler + SQLite 队列足够；引入 broker 等于把"30 秒部署"承诺干掉 |
| **Postgres**（默认） | 同上；作为切换通道留 |
| **Elasticsearch / Meilisearch** | 同上 |
| **Kubernetes Helm chart 作为默认部署形态** | 同上 |
| **Sourcegraph 作为代码检索引擎** | 重；ripgrep + worktree + ctags 更贴合"会话级隔离"模型 |
| **AnythingLLM / Dify / FastGPT 作为底座** | 数据模型不匹配（无飞轮 / 无 A2/A3 / 无自报身份），改造成本 > 自研 |

## 8. 未来扩展的依赖位

PRD §4.4.2 + §6.2 锁定的扩展通道，对应的依赖**今天不加**但**接口预留**：

| 扩展场景 | 触发条件 | 候选依赖 |
|---|---|---|
| 鉴权 | 团队需要真鉴权 | `authlib`（OIDC / OAuth2.1）/ `python-ldap` / 各家社交 SSO SDK；通过 `AuthProvider` 接入（详见 `deployment-security.md` §4） |
| 向量检索叠加 | FTS5 + n-gram 召回不够（线上数据证明） | `sqlite-vec`（轻）/ `pgvector`（如果已切 PG）/ Qdrant local |
| 代码 LSP | ctags 不够 | 各语言 LSP server + `pylsp-jsonrpc` 或 `multilspy` |
| 调用图 | 跨文件 / 跨服务影响分析 | tree-sitter + 自研静态分析 |
| 实时监控对接 | PRD §6.1 永久 Anti-Goal——不做 | — |

## 9. 依赖审计与升级

- **每季度一次**审计 `pyproject.toml` / `package.json` 依赖：是否有废弃 / 是否有 CVE / 是否有更优替代
- 重大依赖升级（Python / Node / FastAPI / React 大版本）走单独 PR + 完整 eval + 集成测试
- LiteLLM / shadcn/ui 等高频更新依赖锁版本——不跟随 latest

## 10. 与 PRD 的对齐

本文落地 PRD §4.3 不锁的事 + §4.4.1 部署门槛 + §6.2 MVP Anti-Goal，主要承诺：

- §1 / §7 把"低部署门槛优先"贯彻到每条依赖（无 broker / 无外部 DB / 无 K8s 默认）
- §2.3 LLM 多供应商通过 LiteLLM 落地 PRD §4.3 不锁供应商承诺；同时显式拒绝 LangChain 类框架，与 `agent-runtime.md` 9 阶段状态机自研一致
- §7 Anti-list 与 PRD §6.2 MVP Anti-Goal 列表逐条对齐
- §8 扩展通道与 PRD §4.4.2 鉴权扩展约束 + §7.3 次要假设（向量叠加 / LSP）一致

## 11. 为什么应用层自研

简短答复（详细讨论见 conversation 记录）：

CodeAsk 产品独特价值集中在**飞轮机制 + A2/A3 透明 + 自报身份 + commit 绑定证据**四件事上。市面候选（AnythingLLM / Dify / Sourcegraph / Bloop / llm-wiki）的数据模型都不贴这套设计——选它们做底座意味着持续跟人家的会话模型 / 报告流转 / 检索哲学打架，最后改的代码比自研还多，且把"30 秒部署"承诺拆了。

**该复用的是组件**（FastAPI、SQLite、ripgrep、ctags、shadcn/ui、TanStack Query、shiki……），**不该复用的是应用骨架**。本文 §2-§6 列的是前者，§7 列的是后者。
