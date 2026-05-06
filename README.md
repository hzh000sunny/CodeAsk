# CodeAsk

**面向研发团队的私有知识工作台。**

CodeAsk 把团队内部文档、代码仓库、日志附件和已验证的问题定位报告组织到同一条问题分析链路里。研发同学可以用自然语言提问，系统会先检索团队知识，再在知识不足时进入代码调查，最后输出带证据、带不确定点、可回流沉淀的 Markdown 结论。

> 让研发知识不再只存在于某个人的经验里。

CodeAsk 不是通用聊天机器人，也不是简单的代码补全工具。它更像一个懂你团队上下文的研发助手：能读知识库，能看日志，能查代码，能把一次问题定位沉淀成下一次可复用的知识。

## 为什么需要 CodeAsk

研发团队的排障经验通常分散在很多地方：

- Wiki 里有设计文档，但和真实代码、线上日志脱节。
- 群聊里有排障结论，但过几周很难再找到。
- 老同事知道某个模块的坑，但新人只能反复问人。
- AI 工具可以回答问题，但缺少团队私有上下文，也无法证明答案来自哪里。

CodeAsk 的目标是把这些碎片重新连起来。它让一次问题分析不只得到答案，还能留下证据、过程和可验证的报告，并在验证后自动成为后续问答的高价值知识来源。

## 核心能力

| 能力 | 说明 |
|---|---|
| 知识库优先问答 | 优先检索特性文档、排障手册、历史报告，避免每次都从代码开始猜。 |
| 代码调查兜底 | 当知识库不足时，Agent 会进入会话级代码调查，调用 grep、读文件、符号检索等工具补齐证据。 |
| 会话级附件 | 每个会话有独立临时目录，日志、截图、文档片段互不串扰；同名日志也能通过元数据区分。 |
| 调查过程可见 | 前端展示范围判断、充分性判断、阶段进度、工具事件和运行轨迹，避免黑盒回答。 |
| Markdown 回答 | 回答和报告预览按 Markdown 渲染，代码块和消息内容支持复制。 |
| 问题报告回流 | 任意会话可以生成绑定特性的报告草稿；验证后的报告会回流知识库。 |
| 特性工作台 | 按特性维护知识库、关联仓库、问题报告和分析策略。 |
| 独立 Wiki 工作台 | 提供独立一级 `Wiki` 页面，支持目录树、阅读态、编辑态、版本历史、导入队列、报告投影和全局搜索。 |
| Wiki 目录排序 | 普通目录和 Markdown 文档支持树内上移 / 下移、同级重排，以及拖入目录整理。 |
| Wiki 修复通道 | owner/admin 可对节点子树执行手动 reindex repair，用于修复正式文档派生状态。 |
| 私有 LLM 配置 | 普通用户可配置个人模型；管理员可维护全局模型、仓库和分析策略。 |

## 典型工作流

1. 管理员配置全局 LLM 和代码仓库池。
2. Maintainer 创建特性，上传设计文档、排障手册、FAQ 等知识材料。
3. Maintainer 将全局仓库关联到特性，并配置必要的分析策略。
4. 用户在会话里描述问题，上传日志或补充材料。
5. Agent 判断问题范围，优先检索知识库和已验证报告。
6. 知识不足时，Agent 进入代码调查，通过隔离 worktree 读取相关代码。
7. 前端实时展示调查进度和运行事件。
8. Agent 输出带证据的 Markdown 回答。
9. 用户可反馈解决情况，也可以生成问题定位报告。
10. Maintainer 验证报告后，报告进入知识库，成为后续问答的高优先级材料。

## 产品界面

CodeAsk 的工作台保持三个一级入口，避免把配置、知识库和会话混在一起。

| 入口 | 主要功能 |
|---|---|
| 会话 | 会话列表、聊天流、调查进度、运行事件、附件管理、反馈、生成报告。 |
| 特性 | 特性列表、特性设置、知识库上传、问题报告、关联仓库、特性分析策略。 |
| 设置 | 普通用户个人设置和个人 LLM；管理员全局 LLM、仓库管理、全局分析策略。 |

### 会话

- 会话按当前用户 `subject_id` 隔离。
- 没有会话时也可以直接发送消息，前端会自动创建默认会话。
- 会话标题旁展示短 session id，点击可复制完整 ID。
- 附件只属于当前会话，支持重命名、用途说明和删除。
- 生成报告前会做基础条件检查，并要求绑定特性。

### 特性

- 特性列表支持搜索、新建和删除。
- 特性详情页包含设置、知识库、问题报告、关联仓库、分析策略。
- 特性页知识库是轻量预览入口：左侧只展示当前特性的目录树，默认展开 `知识库` 根目录，下层目录可展开 / 收起。
- 特性页知识库右侧只保留 Markdown 正文预览，不显示文档名头部，也不显示特性级报告计数。
- 问题报告来自会话生成，不在特性页手工创建。
- 仓库通过全局仓库池勾选关联，不在特性页重复注册。

### 设置

- 普通用户可以维护昵称和个人 LLM 配置。
- 个人 LLM 优先于全局 LLM。
- 管理员只看到全局配置，包括全局 LLM、仓库池和全局分析策略。
- 全局敏感信息只对管理员开放，LLM API Key 加密存储且只返回脱敏值。

## 快速启动

完整安装、配置、开发联调和验证命令见 [INSTALL.md](./INSTALL.md)。

本地体验的最短路径：

```bash
uv sync
corepack pnpm --dir frontend install
export CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
./start.sh
```

默认访问地址：

```text
http://127.0.0.1:8000
```

内置管理员账号仅用于本地调试：

```text
username: admin
password: admin
```

正式部署必须覆盖默认管理员密码：

```bash
export CODEASK_ADMIN_USERNAME="admin"
export CODEASK_ADMIN_PASSWORD="<strong-password>"
```

## 部署和安全边界

CodeAsk 当前定位是“小团队私有部署 + 内置管理员保护全局配置”：

- 普通用户无需登录即可使用，浏览器本地生成 `subject_id`。
- 会话、附件和个人配置按 `subject_id` 隔离。
- 管理员登录使用 HttpOnly cookie。
- 全局 LLM 配置、全局仓库写操作、全局分析策略写操作要求管理员。
- LLM API Key 使用 Fernet 加密存储。
- 上传文件、代码读取和 git 工具调用都做路径和参数边界控制。
- LiteLLM 启动联网拉取模型价格表已在项目级禁用，适合私有内网部署。

这不是企业级权限系统。需要真实账号体系时，应通过后续 AuthProvider 扩展对接 OIDC、LDAP 或企业 IM。

## 技术概览

CodeAsk 是单仓项目：后端在仓库根目录，前端在 `frontend/`。

```text
CodeAsk/
├── src/codeask/        # FastAPI、Agent、LLM、Wiki、代码索引、会话服务
├── frontend/           # React 工作台
├── tests/              # 后端测试
├── docs/               # PRD、SDD、计划和过程文档
├── INSTALL.md          # 安装、配置、本地开发和验证
├── start.sh            # 本地单进程启动入口
└── pyproject.toml
```

后端：

- Python 3.11+
- FastAPI
- SQLAlchemy 2.0 async
- Alembic
- SQLite + FTS5
- Pydantic v2
- LiteLLM
- APScheduler
- pytest

前端：

- React 19
- Vite
- TypeScript
- TanStack Query
- lucide-react
- react-markdown + remark-gfm
- Vitest + Testing Library
- Playwright

部署形态：

- 本地单进程 FastAPI 应用。
- 前端构建产物存在时由后端挂载到 `/`。
- `/api/*` 始终由后端 API 处理。
- Docker / compose / 镜像发布后置到后续 packaging 计划。

## 产品边界

当前版本已经具备“知识库 + 代码调查 + 会话工作台 + 报告回流”的主链路。下面这些能力属于后续专项，不应该误解为当前已完整覆盖：

- 更完善的 LLM Wiki 治理：来源连接器、来源定时刷新、批量修复入口、索引演进和更细的权限治理。
- 企业级鉴权：OIDC / LDAP / 企业 IM 登录、组织空间、权限组。
- 更强代码智能：调用图、LSP、tree-sitter、跨仓上下文优化。
- 容器化交付：Docker、compose、镜像发布和升级脚本。

## 文档入口

推荐阅读顺序：

1. [INSTALL.md](./INSTALL.md)：安装、配置、本地开发和验证。
2. [docs/README.md](./docs/README.md)：文档版本入口。
3. [docs/v1.0/prd/codeask.md](./docs/v1.0/prd/codeask.md)：产品需求文档，定义产品契约。
4. [docs/v1.0/design/overview.md](./docs/v1.0/design/overview.md)：系统设计总览。
5. [docs/v1.0/design/frontend-workbench.md](./docs/v1.0/design/frontend-workbench.md)：前端工作台设计。
6. [docs/v1.0/design/api-data-model.md](./docs/v1.0/design/api-data-model.md)：API 和数据模型契约。
7. [docs/v1.0/design/agent-runtime.md](./docs/v1.0/design/agent-runtime.md)：Agent 状态机和运行时。

文档优先级：

```text
PRD > SDD > Plans > Specs
```

如果 PRD 与 SDD 冲突，以 PRD 为准，SDD 应同步更新。

## License

License 尚未确定。
