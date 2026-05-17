# CodeAsk

<p align="center">
  <strong>面向研发团队的 AI 知识与问题定位工作台</strong>
</p>

<p align="center">
  用自然语言连接团队 Wiki、历史问题报告、会话附件和代码仓库，让研发排障从“问人和翻资料”变成一条可追溯、可沉淀、可复用的工作流。
</p>

<p align="center">
  <a href="./INSTALL.md">快速启动</a>
  ·
  <a href="./docs/README.md">文档中心</a>
  ·
  <a href="./docs/v1.0.4/">当前版本</a>
  ·
  <a href="./docs/future/">未来规划</a>
</p>

---

CodeAsk 不是一个普通的 LLM Wiki，也不是一个只会聊天的通用 AI 助手。

传统 LLM Wiki 擅长“基于知识库回答问题”，但研发现场往往更复杂：知识库可能缺失，日志里有新线索，历史报告里有类似故障，最终根因还要回到代码里确认。CodeAsk 的目标是把这些研发上下文组织到同一个 Agent 会话中，让模型先正常和用户沟通，再按需要检索知识、读取附件、查询代码，并把定位过程沉淀成下一次可用的团队知识。

> 一次排障，不只得到一个答案，还留下下一次能被复用的证据和经验。

## CodeAsk 解决什么问题

研发团队的知识通常散落在很多地方：

| 常见现状 | CodeAsk 的处理方式 |
|---|---|
| Wiki 有设计文档，但和真实问题、真实代码脱节 | Wiki 作为 Agent 可检索上下文进入会话，而不是静态资料库 |
| 群聊里有排障结论，但过几周很难找回 | 会话可生成结构化问题报告，验证后回流知识库 |
| 用户只有日志和现象，不知道属于哪个特性 | 模型基于特性目录、Wiki、报告和附件上下文判断范围 |
| 知识库答不出来，传统 LLM Wiki 就停止了 | Agent 可在需要时进入代码仓库检索和文件读取 |
| AI 给出结论但缺少证据 | 前端展示 Agent 行动轨迹、工具调用、证据和不确定点 |
| 同名日志、多个节点日志容易串 | 会话附件按 session 隔离，保留原文件名、显示名、别名和说明 |

## 核心能力

### 正常聊天优先的研发 Agent

CodeAsk 的会话不是一条写死的后端流水线。用户可以像使用 Agent 工具一样持续追问、补充背景、修正方向。Wiki 检索、报告检索、附件读取和代码检索都是模型可用的工具能力，由模型根据上下文决定是否调用。

### 面向特性的知识组织

团队知识以“特性”为一级边界组织。每个特性可以维护：

- Markdown Wiki 知识库
- 问题定位报告
- 关联代码仓库
- 分析策略
- 负责人和描述信息

特性删除时，相关 Wiki 不会直接丢弃，而会进入历史特性归档，保留长期知识资产。

### 独立 LLM Wiki 工作台

CodeAsk 提供独立 Wiki 页面，而不是把知识库塞进特性页的小边框里。Wiki 工作台支持：

- 特性维度目录树
- 历史特性目录
- Markdown 阅读和编辑
- 实时 Markdown 预览
- 自动保存草稿
- 版本历史
- 目录和文档拖拽排序
- Markdown 文件和目录导入
- 相对图片资源渲染
- 全局搜索

特性页仍保留轻量目录树和预览入口，上传、编辑、版本治理等完整操作跳转到 Wiki 页面完成。

### 会话附件和日志分析

每个会话拥有独立临时目录。上传的数据只属于当前会话，不会在切换会话后串到另一个会话里。

附件保留多层映射：

- 稳定附件 ID
- 原始文件名
- 当前显示名
- 历史别名
- 用户补充说明
- 物理存储路径

这让用户可以用口语化方式描述“这个节点的日志”“刚刚重命名的数据库日志”，模型仍能把名称映射到正确文件。

### 代码仓库辅助定位

当知识库和报告不足以回答问题时，CodeAsk 可以让模型基于上下文决定是否查询代码。代码仓库与特性强关联，默认不会随意扫描全局仓库；用户明确点名某个仓库时，也允许作为本轮显式范围。

当前代码能力包括：

- 仓库管理和同步
- 特性关联仓库
- 代码搜索
- 文件读取
- worktree 隔离
- 版本不确定性提示
- 工具调用行动轨迹

### 问题报告回流

会话可以生成问题定位报告，但报告不是聊天记录复制。CodeAsk 会把报告写作规则、会话关键上下文、行动轨迹和证据一起交给 AI，让 AI 生成更接近正式沉淀文档的 Markdown 草稿。

报告通常覆盖：

- 问题背景
- 定位过程
- 分析思路
- 问题根因
- 解决建议
- 未确认项
- 参考资料

章节名称不强制固定，但标题必须带日期，方便后续按时间检索和排序。一个会话最多绑定一篇报告，重复生成会覆盖更新原报告。

### 管理员和个人 LLM 配置

CodeAsk 支持两层模型配置：

- 普通用户可以配置个人 LLM。
- 管理员维护全局 LLM 配置池。

当用户有个人配置时优先使用个人配置；否则从可用全局配置中选择。全局配置支持基础负载均衡、会话粘性和失败冷却，避免单个模型配置被多个会话打满或坏配置反复拖垮体验。

## 一条典型的 CodeAsk 工作流

1. 管理员配置全局 LLM、代码仓库和分析策略。
2. Maintainer 创建特性，上传 Wiki 文档，关联代码仓库。
3. 用户打开会话，描述故障现象，上传日志或截图。
4. Agent 正常回答用户问题，并在需要时检索 Wiki、报告和附件。
5. 如果已有知识不足，Agent 可以基于模型决策查询关联代码仓库。
6. 用户继续追问、补充背景、确认或纠正方向。
7. 问题逐步收敛后，用户生成问题定位报告。
8. Maintainer 验证报告，报告进入特性知识库，成为后续问答的高价值证据。

## 适合谁使用

CodeAsk 适合这些团队：

- 有多个业务特性或服务模块，需要长期维护研发知识。
- 线上问题定位依赖 Wiki、日志、历史经验和代码交叉分析。
- 希望把排障过程沉淀成结构化报告，而不是只留在群聊里。
- 需要私有化部署，不希望把内部文档、日志和代码直接交给外部 SaaS。
- 希望 AI 不只回答“通用知识”，还能够理解团队自己的上下文。

CodeAsk 暂时不适合作为：

- 企业级 IAM / 权限系统。
- 纯代码补全工具。
- 通用客服机器人。
- 只管理静态文档、不需要会话和问题定位的轻量 Wiki。

## 当前状态

当前主线是 v1.0.4，重点是引入 opencode 作为默认会话的外部 Agent 执行引擎：

- v1.0.2 已把默认会话调整为正常聊天优先，Wiki、报告、附件和代码工具由模型基于上下文决定是否使用。
- LLM Wiki 工作台已具备独立页面、目录树、导入、编辑、版本历史、相对资源渲染和特性页预览。
- 问题报告生成已从“聊天记录整理”调整为 AI 按报告规则生成正式 Markdown 草稿，并具备长报告 JSON-like 输出截断恢复能力。
- v1.0.3 已补齐统一登录、用户自动注册、admin、特性管理员、全局附件开关、审计日志和真实浏览器 E2E。
- 未登录访客仍可直接使用会话、查看特性和 Wiki；写操作由服务端权限守卫强制校验。
- v1.0.4 已新增独立 `src/codeask/agent/opencode_compat/` 模块，默认会话接入 shared `opencode serve`、会话级 workspace、Wiki 零复制挂载、remote MCP、opencode 事件流、Agent 适配方式选择/手动测试和真实浏览器 live E2E 通道。LLM 配置新增/编辑表单连接测试遵循表单语义：先测试当前草稿，保存时才把测试状态写入数据库；API 使用通用 `agent_runtime_*` 字段，历史 `opencode_provider_*` 仅作为兼容层。v1.0.4 已完成人工验收，Agent 事件返回会对宿主机绝对路径做后端出口脱敏。

仍在规划或后续专项中的能力：

- 更完整的 RAG 服务和向量召回。
- 更细粒度的企业级权限体系。
- 更强的代码智能索引。
- Docker / compose / 镜像发布。
- 更成熟的模型上下文压缩和长期记忆。

详细版本状态见 [docs/v1.0.4/README.md](./docs/v1.0.4/README.md) 和 [docs/future/](./docs/future/)。

## 快速启动

完整安装、配置、开发联调和验证命令见 [INSTALL.md](./INSTALL.md)。如果是在一台新机器上部署，请先按 `INSTALL.md` 完成 Python、uv、Node.js、Corepack 或 pnpm、ripgrep 和 ctags 的工具链检查。

最短本地启动路径：

```bash
uv sync
corepack pnpm --dir frontend install --frozen-lockfile
export CODEASK_DATA_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
./start.sh
```

如果环境没有 Corepack，可以把 `corepack pnpm` 替换成系统 `pnpm`。`start.sh` 的自动前端构建兜底会优先使用 `corepack pnpm`，如果 Corepack 不可用再使用系统 `pnpm`。

离线拷贝代码升级时需要注意：`start.sh` 只会在 `frontend/dist/index.html` 不存在时自动构建前端。如果目标环境已有旧 `frontend/dist`，请先执行 `corepack pnpm --dir frontend build` 或等价 `pnpm --dir frontend build`，否则后端会正常启动，但浏览器看到的仍可能是旧页面。

访问地址取决于启动方式：

| 场景 | 打开地址 | 说明 |
|---|---|---|
| 单进程启动 | `http://127.0.0.1:8000` | `./start.sh` 启动后端；当前端构建产物存在时，后端会把前端静态页面挂载到 `/` |
| 前端开发联调 | `http://127.0.0.1:5173` | Vite dev server 负责前端页面，并把 `/api/*` 代理到后端 `http://127.0.0.1:8000` |

如果你在开发模式下同时启动了后端和 Vite，请访问 `5173`，不要把后端 API 端口 `8000` 当成前端开发页面地址。

本地调试管理员账号：

```text
username: admin
password: admin
```

正式部署必须覆盖默认管理员密码：

```bash
export CODEASK_ADMIN_USERNAME="admin"
export CODEASK_ADMIN_PASSWORD="<strong-password>"
```

## 项目结构

```text
CodeAsk/
├── src/codeask/      # 后端：FastAPI、Agent、LLM、Wiki、会话、代码索引
├── frontend/         # 前端：React 工作台
├── tests/            # 后端测试
├── docs/             # 产品、设计、计划、规则和未来规划
├── INSTALL.md        # 安装、配置、本地开发和验证
├── start.sh          # 本地启动入口
└── pyproject.toml
```

## 文档入口

- [INSTALL.md](./INSTALL.md)：安装、配置、启动和测试。
- [docs/README.md](./docs/README.md)：文档中心和版本入口。
- [docs/rules/](./docs/rules/)：跨版本产品和交互规则。
- [docs/future/](./docs/future/)：未来能力规划。
- [docs/v1.0/](./docs/v1.0/)：MVP 基线设计。
- [docs/v1.0.1/](./docs/v1.0.1/)：LLM Wiki 专项。
- [docs/v1.0.2/](./docs/v1.0.2/)：Agent 会话运行时优化。
- [docs/v1.0.3/](./docs/v1.0.3/)：鉴权、访问控制和特性管理员。
- [docs/v1.0.4/](./docs/v1.0.4/)：OpenCode Agent Backend 对接。

## 开源参考

CodeAsk 的实现是面向自身产品定位的独立设计，但在部分版本设计中参考了优秀开源项目的思路，并结合研发知识库、问题报告和特性边界进行了取舍。

| 版本 | 参考项目 | 参考点 |
|---|---|---|
| v1.0.2 | [anthropics/claude-code](https://github.com/anthropics/claude-code) | 参考了 Claude Code 在工具调用、长上下文处理、行动轨迹和面向代码任务的 Agent 运行时组织方式。 |
| v1.0.2 | [affaan-m/everything-claude-code](https://github.com/affaan-m/everything-claude-code) | 参考了社区对 Claude Code 架构和使用模式的整理，用于辅助理解工具编排、权限边界和交互体验。 |
| v1.0.4 | [anomalyco/opencode](https://github.com/anomalyco/opencode) | 基于 opencode 1.14.48 实测接入 shared server、workspace 级配置、remote MCP、事件流和工具权限边界。 |

## License

License 尚未确定。
