# CodeAsk

CodeAsk 是一个私有部署的研发知识工作台。它把团队内部文档、代码仓库、日志附件和已验证的问题定位报告组织成可检索、可审计、可回流的知识体系，让研发团队可以用自然语言完成问答、排障和报告沉淀。

它的核心目标是：

> 让团队知识不再卡在某个人脑子里。

CodeAsk 不是通用聊天机器人，也不是无上下文的代码补全工具。它面向真实研发协作场景：用户上传知识和日志，管理员配置模型和仓库，Agent 先检索知识库，知识不足时再进入代码调查，最后生成带证据和不确定点的回答。

## 当前状态

CodeAsk v1.0 MVP 的既定实现阶段已经完成，当前处于产品化整理和稳定阶段。

已完成阶段：

| Plan | 状态 | 主要交付 |
|---|---|---|
| `foundation` | 已完成 | FastAPI 应用骨架、配置、SQLite、Alembic、Fernet 加密、自报身份、结构化日志、健康检查 |
| `wiki-knowledge` | 已完成 | 特性、文档上传、文档切块、SQLite FTS5 检索、报告验证 / 撤销、知识库召回 |
| `code-index` | 已完成 | 全局仓库池、异步 clone / fetch、会话级 worktree、grep / read / symbols 工具、worktree 清理 |
| `agent-runtime` | 已完成 | LLM 网关、9 阶段 Agent 状态机、ToolRegistry、SSE、`agent_traces`、会话运行时 |
| `frontend-workbench` | 已完成 | React 工作台、会话 / 特性 / 设置三入口、管理员登录、LLM 配置、附件、报告入口、Markdown 渲染 |
| `metrics-eval` | 已完成 | `/api/feedback`、`/api/events`、`/api/audit-log`、审计日志、Agent eval harness、CI eval workflow |
| `deployment` | 已完成 | 后端挂载前端静态产物、`start.sh` 本地启动、CI、安全审计、本地单进程部署 |
| `admin-repo-analysis-policy` | 已完成 | 仓库编辑 / 同步语义、全局分析策略、特性分析策略、运行时 Prompt 注入 |

当前已知后置专项：

- 完整 LLM Wiki：目录上传、相对资源保存、Markdown 预览 / 编辑 / 删除 / re-index、跨文件引用解析。
- Docker / compose / 镜像发布：v1.0 deployment 只覆盖本地单进程部署，容器化作为后续 packaging 计划。
- 企业级鉴权：当前只有内置管理员保护全局配置；OIDC / LDAP / 企业 IM 登录作为 AuthProvider 扩展。
- 更强的代码智能：调用图、LSP、tree-sitter、跨仓上下文优化等作为后续工具智能阶段。

## 产品角色

| 角色 | 目标 | 当前能力 |
|---|---|---|
| 普通研发用户 / Asker | 自助提问、上传日志、查看调查过程、拿到带证据回答 | 无需登录即可使用；浏览器生成 `subject_id`；只能看到自己的会话和个人配置 |
| Maintainer | 沉淀特性知识、验证报告、维护特性关联仓库和分析策略 | 通过特性页面上传知识、查看问题报告、关联仓库、维护特性分析策略 |
| 管理员 / Admin | 配置全局模型、全局仓库、全局分析策略 | 内置管理员登录；只看到全局配置，不显示个人用户配置 |

默认管理员账号用于本地调试：

```text
username: admin
password: admin
```

正式部署必须通过环境变量覆盖默认密码：

```bash
export CODEASK_ADMIN_USERNAME="admin"
export CODEASK_ADMIN_PASSWORD="<strong-password>"
```

## 核心工作流

CodeAsk 的主链路是“知识库优先，代码调查兜底”。

1. 管理员配置 LLM 账号和全局代码仓库。
2. Maintainer 创建特性，并上传文档、排障手册、设计说明等知识材料。
3. Maintainer 将全局仓库勾选关联到特性。
4. 用户进入会话页，用自然语言描述问题，可以上传日志、截图或文档片段。
5. Agent 自动判断问题相关特性。
6. Agent 优先检索知识库，包括普通文档和已验证报告。
7. 如果知识库不足，Agent 进入代码调查，通过会话级 worktree 调用 grep、读文件、符号查找等工具。
8. 前端实时展示调查进度、运行事件、范围判断、充分性判断和工具事件。
9. Agent 输出 Markdown 回答，包含结论、证据、不确定点和建议操作。
10. 用户可以对回答反馈“已解决 / 部分解决 / 没解决”，也可以生成绑定特性的报告草稿。
11. 已验证报告回流到知识库，成为后续问题的高优先级召回来源。

## 当前产品界面

前端工作台只有三个一级入口：

| 入口 | 用途 |
|---|---|
| 会话 | 会话列表、聊天流、调查进度、运行事件、附件管理、反馈、生成报告 |
| 特性 | 特性列表、特性设置、知识库上传、问题报告、关联仓库、特性分析策略 |
| 设置 | 普通用户个人设置和个人 LLM；管理员全局 LLM、仓库管理、全局分析策略 |

### 会话

已实现：

- 会话列表按当前 `subject_id` 隔离。
- 列表顶部是搜索框和新建按钮。
- 会话行三点菜单包含编辑名称、分享占位、置顶、批量操作、删除。
- 删除前有确认弹窗；批量删除支持复选框。
- 没有会话时仍可直接发送消息，前端会自动创建默认会话。
- 上传日志不要求先手工创建会话。
- 当前会话标题旁显示短 session id，例如 `sess_71b4`；点击可复制完整 ID。
- 历史会话刷新后会重新拉取 `session_turns` 和 `agent_traces`，恢复消息和调查过程。
- Markdown 回答和报告预览按 Markdown 渲染，代码块和消息支持复制。
- 会话右侧展示当前会话自己的附件，支持重命名、编辑用途说明和删除。
- 报告生成入口位于输入区操作行，需要满足基本问答条件，并且必须绑定特性。

### 特性

已实现：

- 特性列表支持搜索、新建、删除确认。
- 创建特性不要求用户填写 slug。
- 特性详情页包含：设置、知识库、问题报告、关联仓库、特性分析策略。
- 知识库当前支持基础文件上传、列表、删除；完整 LLM Wiki 目录管理后置。
- 问题报告来自会话生成，不在特性页手工创建。
- 仓库关联通过全局仓库池 checkbox 完成，不在特性页注册仓库。
- 特性分析策略支持创建、编辑、启停、删除；当前语义是 Prompt 注入策略，不是完整工具 Skill Package。

### 设置

普通用户：

- 查看自己的 Subject ID。
- 设置昵称。
- 配置个人 LLM。个人配置优先于全局配置。

管理员：

- 管理全局 LLM 配置。
- 管理全局仓库池。
- 管理全局分析策略。
- 不显示个人用户配置。

LLM 配置当前 UI 只展示：

- 配置名称
- 消息接口协议：OpenAI / Anthropic
- Base URL
- API Key
- 模型名称
- 启用 / 停用 switch

不展示：

- Max Tokens
- Temperature
- RPM
- 剩余额度
- 默认配置切换

后端默认值：

- `max_tokens = 200 * 1024`
- `temperature = 0.2`

RPM 和剩余额度字段只作为兼容字段保留，当前运行时不基于它们做调度；供应商调用失败会作为错误返回到会话。

## 技术架构

CodeAsk 是单仓项目，后端在仓库根目录，前端在 `frontend/` 子目录。

```text
CodeAsk/
├── README.md
├── start.sh
├── pyproject.toml
├── uv.lock
├── alembic.ini
├── alembic/
├── src/codeask/
│   ├── api/              # REST / SSE 路由
│   ├── agent/            # Agent 状态机、Prompt、工具编排、trace
│   ├── code_index/       # 仓库、bare cache、worktree、grep、ctags、文件读取
│   ├── db/               # SQLAlchemy 模型、engine、session
│   ├── llm/              # LLM Gateway、provider adapter、配置仓库
│   ├── metrics/          # audit hook
│   └── wiki/             # 文档、报告、FTS5、检索
├── tests/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── lib/
│   │   ├── styles/
│   │   └── types/
│   ├── tests/
│   └── e2e/
└── docs/
```

后端技术栈：

- Python 3.11+
- FastAPI
- SQLAlchemy 2.0 async
- Alembic
- SQLite + FTS5
- Pydantic v2 / pydantic-settings
- cryptography / Fernet
- structlog
- APScheduler
- LiteLLM
- pytest / pytest-asyncio
- uv

前端技术栈：

- React 19
- Vite
- TypeScript
- TanStack Query
- lucide-react
- react-markdown + remark-gfm
- Zustand 依赖已引入，当前页面主要使用组件局部状态和 Query cache
- Vitest + Testing Library
- Playwright

部署形态：

- 单进程 FastAPI 应用。
- 前端构建产物存在时由后端挂载到 `/`。
- `/api/*` 始终由后端 API 处理，不被静态路由吞掉。
- 默认监听 `127.0.0.1:8000`。
- Docker packaging 后置，不属于 v1.0 必交付。

## 快速启动

### 1. 准备依赖

系统工具：

| 工具 | 用途 |
|---|---|
| `git` | clone、fetch、worktree |
| `rg` / ripgrep | 代码全文检索 |
| `ctags` / universal-ctags | 符号检索；缺失时相关测试会跳过 |

Debian / Ubuntu：

```bash
sudo apt-get install git ripgrep universal-ctags
```

macOS：

```bash
brew install git ripgrep universal-ctags
```

Python 依赖通过 uv 安装：

```bash
uv sync
```

前端依赖通过 pnpm 安装：

```bash
corepack pnpm --dir frontend install
```

### 2. 生成数据加密密钥

`CODEASK_DATA_KEY` 用于加密 LLM API Key 等敏感字段。丢失后已加密字段不可恢复。

```bash
export CODEASK_DATA_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

### 3. 启动单进程服务

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

注意：v1.0 普通用户无登录即可使用，只有全局配置由管理员登录保护。把 `CODEASK_HOST` 设为 `0.0.0.0` 前，应确认部署环境位于可信内网或已有外层访问控制。

健康检查：

```bash
curl -s http://127.0.0.1:8000/api/healthz -H 'X-Subject-Id: alice@dev-1' | python -m json.tool
```

### 4. 前端开发联调

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

项目已在 `pyproject.toml` 配置 uv 默认包索引为清华 TUNA：

```toml
[[tool.uv.index]]
name = "tuna"
url = "https://pypi.tuna.tsinghua.edu.cn/simple/"
default = true
```

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

## API 概览

当前主要 API：

| 分组 | 接口 |
|---|---|
| Auth | `GET /api/auth/me`、`POST /api/auth/admin/login`、`POST /api/auth/logout` |
| Sessions | `GET/POST /api/sessions`、`PATCH/DELETE /api/sessions/{id}`、`POST /api/sessions/bulk-delete` |
| Session Runtime | `POST /api/sessions/{id}/messages`、`GET /api/sessions/{id}/turns`、`GET /api/sessions/{id}/traces` |
| Attachments | `GET/POST /api/sessions/{id}/attachments`、`PATCH/DELETE /api/sessions/{id}/attachments/{attachment_id}` |
| Reports | `POST /api/sessions/{id}/reports`、`GET/POST /api/reports`、`PUT /api/reports/{id}`、`POST /api/reports/{id}/verify`、`POST /api/reports/{id}/unverify` |
| Features | `GET/POST /api/features`、`GET/PUT/DELETE /api/features/{id}` |
| Documents | `GET/POST /api/documents`、`GET /api/documents/search`、`GET/DELETE /api/documents/{id}` |
| Repos | `GET/POST /api/repos`、`GET/PATCH/DELETE /api/repos/{id}`、`POST /api/repos/{id}/refresh` |
| Feature Repos | `GET /api/features/{feature_id}/repos`、`POST/DELETE /api/features/{feature_id}/repos/{repo_id}` |
| Code Tools | `POST /api/code/grep`、`POST /api/code/read`、`POST /api/code/symbols` |
| LLM Configs | `GET/POST /api/me/llm-configs`、`PATCH/DELETE /api/me/llm-configs/{id}`、管理员同路径前缀 `/api/admin/llm-configs` |
| Analysis Policies | `GET/POST /api/skills`、`GET/PATCH/DELETE /api/skills/{id}`；产品语义是分析策略 |
| Metrics | `POST /api/feedback`、`POST /api/events`、`GET /api/audit-log` |
| Health | `GET /api/healthz` |

消息接口 `POST /api/sessions/{id}/messages` 返回 SSE 流，事件类型：

```text
stage_transition
text_delta
tool_call
tool_result
evidence
scope_detection
sufficiency_judgement
ask_user
done
error
```

## 安全边界

v1.0 的安全模型是“小团队私有部署 + 内置管理员保护全局配置”：

- 普通用户无登录直接使用，浏览器本地生成 `subject_id`。
- 会话列表按 `subject_id` 隔离。
- 管理员登录使用 HttpOnly cookie。
- 全局 LLM 配置、全局仓库写操作、全局分析策略写操作要求管理员。
- LLM API Key 使用 Fernet 加密存储，GET 响应只返回 mask 后的 key。
- 上传文件和代码读取做路径校验，防止目录穿越。
- git / rg / ctags 调用使用参数数组，不使用 shell 拼接。
- LiteLLM 启动联网拉取模型价格表已在项目级禁用，避免私有部署依赖 GitHub 网络。

这不是企业级权限系统。需要真实账号体系时，应通过后续 AuthProvider 扩展对接 OIDC / LDAP / 企业 IM。

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

## 文档入口

推荐阅读顺序：

1. `docs/README.md`：文档版本入口。
2. `docs/STRUCTURE.md`：文档结构与版本规则。
3. `docs/v1.0/README.md`：v1.0 元信息、目录和实现状态。
4. `docs/v1.0/prd/codeask.md`：产品需求文档，定义产品契约。
5. `docs/v1.0/design/overview.md`：系统设计总览。
6. `docs/v1.0/design/frontend-workbench.md`：前端工作台交互设计。
7. `docs/v1.0/design/api-data-model.md`：API 和数据模型契约。
8. `docs/v1.0/design/agent-runtime.md`：Agent 状态机和运行时。
9. `docs/v1.0/design/deployment-security.md`：部署、安全、鉴权边界。
10. `docs/v1.0/plans/roadmap.md`：v1.0 实施路线图和验收。
11. `docs/v1.0/specs/frontend-workbench-handoff.md`：当前前端工作台实际交接边界。

文档优先级：

```text
PRD > SDD > Plans > Specs
```

如果 PRD 与 SDD 冲突，以 PRD 为准，SDD 应同步更新。Plan 文件中早期 task 片段如果与当前 handoff 或代码现状冲突，以 handoff、SDD 和代码为准。

## 新会话接手

接手项目时建议先运行：

```bash
uv sync
corepack pnpm --dir frontend install
uv run pytest -q
corepack pnpm --dir frontend test:run --maxWorkers=1 --minWorkers=1
```

然后阅读：

1. `README.md`
2. `docs/v1.0/README.md`
3. `docs/v1.0/plans/roadmap.md`
4. `docs/v1.0/specs/frontend-workbench-handoff.md`
5. `docs/v1.0/design/api-data-model.md`
6. `docs/v1.0/design/agent-runtime.md`
7. `docs/v1.0/design/deployment-security.md`

## License

License 尚未确定。
