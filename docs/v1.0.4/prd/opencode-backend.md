# OpenCode Agent Backend 产品契约

> 版本：v1.0.4
> 状态：Draft
> 适用范围：opencode 作为 CodeAsk 可选 Agent 执行引擎的第一版

---

## §1 产品定位

CodeAsk v1.0.4 引入 opencode 作为 Agent 执行引擎。此版本不改变 CodeAsk 的核心产品定位（研发知识定位平台），而是将 Agent 执行职责委托给更成熟的 coding agent。

v1.0.4 不再把 CodeAsk 自研 Agent runtime 作为新会话的可用后端。历史代码可以保留用于兼容旧会话、回滚开发或读取旧数据，但新会话的 Agent 执行主路径必须是 opencode。opencode 不可用时，应明确向用户报错，不允许静默回退到 native runtime。

**CodeAsk 负责：** 知识管理（Wiki、特性、报告、附件）、代码仓库管理（worktree、权限、版本）、会话审计（trace、turn、evidence）、用户认证与权限、前端工作台。

**OpenCode 负责：** 理解用户问题、搜索 Wiki、阅读代码、跨特性交叉分析、搜索历史报告、输出带证据引用的结论。

---

## §2 核心画像

### 2.1 产品飞轮的变化

v1.0 定义的飞轮不变，但 Agent 层的成熟度提升：

| | v1.0-v1.0.3 | v1.0.4 |
|---|---|---|
| Agent 执行 | CodeAsk 自研 runtime | opencode coding agent |
| 代码搜索 | CodeAsk `search_code` (SQL) | opencode grep (ripgrep) |
| 工具编排 | 后端固定注册表 | opencode 模型自主决策 |
| 上下文压缩 | 基础预算策略 | opencode compaction |
| 子代理 | 不支持 | opencode task/explore/plan |

### 2.2 两个角色不变

- **Maintainer**：仍通过 CodeAsk 管理特性、Wiki、报告。不受 opencode 集成影响。
- **Asker**：仍通过 CodeAsk 前端提问。Agent 后端透明切换，体验一致。

---

## §3 主链路

```text
用户创建会话
  ↓
CodeAsk 确定 Agent Backend (v1.0.4 默认 opencode)
  ↓
CodeAsk 创建会话数据目录 → 启动 opencode → 创建 opencode session
  ↓
用户发送消息
  ↓
CodeAsk 组装系统上下文（特性列表、仓库绑定、会话附件）
  → 注入到 opencode system prompt
CodeAsk 将持久化 Wiki 工作区以零复制方式挂载到会话 workspace/wiki
  ↓
opencode Agent 自主调查
  ├─ 搜索 Wiki (grep/read ./wiki/)
  ├─ 查特性信息 → CodeAsk MCP: get_feature_info
  ├─ 准备代码环境 → CodeAsk MCP: prepare_worktree
  ├─ 搜索代码 (grep/read worktree 目录)
  ├─ 参考历史报告 → grep/read ./wiki/<feature_slug>/problem-reports/
  ├─ 交叉特性分析 (再次 get_feature_info + prepare_worktree)
  └─ 确定特性绑定 → CodeAsk MCP: bind_session_features
  ↓
opencode 输出结论 (带证据引用)
  ↓
CodeAsk 持久化助理 turn + 行动轨迹
  ↓
(可选) 生成问题报告 → 审核 → 入库
```

---

## §4 产品契约

### 4.1 用户侧约定

| 约定 | 说明 |
|---|---|
| 特性和仓库是上下文事实，不是强制前置条件 | CodeAsk 会把活跃特性、描述、Wiki 目录和仓库绑定提供给模型，由模型在多轮对话中自行判断边界 |
| 用户可显式指定仓库 | 即使没有匹配到特性，用户明确要求查看某个仓库时，也允许模型请求 CodeAsk 准备该仓库；此类访问必须审计 |
| Wiki 以文件系统方式暴露 | opencode 使用 grep/read 直接搜索 `./wiki/`，v1.0.4 不依赖 CodeAsk 旧 `search_wiki` 能力 |
| Agent Backend 不暴露为 UI 选项 | v1.0.4 新会话默认使用 opencode；opencode 不可用时明确报错 |

### 4.2 产品侧承诺

| 承诺 | 说明 |
|---|---|
| 会话级隔离 | v1.0.4 主路径使用一个 shared opencode server；每个 CodeAsk 会话独立 workspace、独立 `opencode.json`、独立 opencode session、独立 MCP token 和独立审计记录 |
| Wiki 零复制访问 | CodeAsk 维护持久化 Wiki 工作区，按“特性为一级目录 + 现有 Wiki 树结构”导出；会话通过 symlink / bind mount 等零复制方式访问，不复制整库 |
| 只读执行 | opencode 默认不可 Write/Edit/Bash |
| 原生事件流展示 | 前端不复用旧 CodeAsk Agent 事件流形态，基于 opencode 返回的事件重新设计 Agent 行动轨迹 |
| 完整审计 | opencode 工具调用、MCP 调用、错误、权限拒绝和基础停止事件都要落入 CodeAsk 审计 |
| 会话可恢复 | 闲置清理后，用户再次使用时自动恢复 |
| 多轮追问 | opencode 保存完整历史，追问时保留上下文 |
| 中断可回滚 | 作为遗留增强项；主功能阶段先保证停止输出、状态清理和事件可审计 |

---

## §5 不做什么

v1.0.4 **不包含**：

- **不让 opencode 执行任意 shell** — Bash 权限为 deny
- **不让 opencode 修改代码** — Write/Edit 权限为 deny
- **不实现 Claude Code Backend** — 后移到 v1.0.5 或后续版本
- **不实现前端 Agent Backend 选择开关** — v1.0.4 新会话默认走 opencode 独立兼容模块，用户无需理解 backend 差异
- **不让 opencode 直接操作 CodeAsk DB** — 所有 DB 操作通过 MCP tools 代理
- **不使用 CodeAsk 旧 Wiki 搜索作为主路径** — Wiki 主路径是 opencode grep/read `./wiki/`
- **不在 opencode 不可用时静默回退 native** — 必须明确提示 Agent 执行引擎不可用
- **不复制整份 Wiki 到每个会话目录** — Wiki 访问必须零复制或近零复制

---

## §6 opencode 兼容选择规则

| CodeAsk LLM 配置 | 兼容模块 | 说明 |
|---|---|---|
| `openai` | opencode | 通过 opencode provider 配置注入 |
| `openai_compatible` | opencode | 通过 opencode provider + baseURL 适配 |
| `anthropic` | opencode | 使用 opencode 的 Anthropic provider |
| 其他未知协议 | error | v1.0.4 不回退 native；提示当前协议暂不支持 opencode |

**关键原则：**
- 用户不可见 backend 切换，不使用 "agent_backend" 概念作为 UI 选项
- 如果 opencode 不支持某个 provider，明确报错，不自动回退
- 每个会话创建时记录使用的 opencode 版本、provider 和模型
- CodeAsk 与 opencode 需要声明已验证版本关系；用户后续提供目标 opencode 版本后，v1.0.4 文档和测试都以该版本为准

---

## §6.1 Wiki 文件工作区契约

CodeAsk 维护一个持久化 Wiki 文件工作区，用于给 opencode 提供稳定、可 grep/read 的文件系统视图。

```text
<CODEASK_DATA_DIR>/wiki_workspace/current/
├── <feature-name-or-slug>/
│   ├── index.md
│   ├── <wiki-tree-dir>/
│   ├── <doc>.md
│   └── <doc>.assets/
└── _manifest.json
```

规则：

- 一级目录必须是特性维度，和当前特性 Wiki 树结构保持一致。
- Markdown 文件和静态资源保持相对引用关系，保证 opencode 读到路径后能继续读取相关资源。
- `index.md` 是模型进入某个特性 Wiki 的推荐入口；`_manifest.json` 记录特性、标题、路径、更新时间和来源 ID。
- 会话目录中的 `workspace/wiki` 通过 symlink、bind mount 或等价零复制方式指向持久化 Wiki 工作区。
- 不允许每个会话复制整份 Wiki。
- 如果未来接入 RAG，新增 MCP 工具提供 RAG 查询；grep/read `./wiki/` 仍作为基础能力保留。

---

## §6.2 前端事件流契约

v1.0.4 前端需要适配 opencode 原生事件，不保留旧 CodeAsk Agent 事件流形态，除非某些 UI 组件复用确有必要。

前端至少需要展示：

- opencode backend、session、turn 和模型信息。
- 文本增量。
- opencode 内置工具事件：grep/read/glob/list/task 等。
- CodeAsk MCP 工具事件：工具名、参数、结果摘要、错误详情。
- 中断、回滚、重试、资源繁忙、opencode 不可用等运行状态。
- 每个事件卡片可展开查看完整参数和错误信息。

---

## §7 验收标准

### 7.1 功能验收

- [ ] opencode 不可用时不会回退 native，而是弹出明确错误提示
- [ ] CodeAsk 后端启动时 best-effort 拉起一个 shared `opencode serve` 常驻进程，并通过 keepalive 定时检测；如果进程退出，后台自动重新拉起
- [ ] 会话创建后，生成独立 workspace、`opencode.json`、opencode session 和 MCP token
- [ ] 所有 opencode 请求都携带 `directory=<workspace>`，不能依赖 server 当前工作目录
- [ ] 会话数据目录结构正确（workspace/wiki, attachments, config, logs, state）
- [ ] CodeAsk 持久化 Wiki 工作区存在，特性为一级目录，结构与特性 Wiki 树一致
- [ ] 会话 `workspace/wiki` 零复制指向持久化 Wiki 工作区，不复制整库
- [ ] opencode 可通过 MCP 调用 CodeAsk 的 opencode 专用 tools
- [ ] opencode 可 grep/read wiki 目录中的 markdown 文件
- [ ] opencode 调用 prepare_worktree 后，代码目录出现在 workspace 中
- [ ] 用户显式指定仓库时，即使没有匹配到特性，也可通过 MCP 准备该仓库并记录审计
- [ ] opencode 调用 bind_session_features 后，DB 中写入绑定记录
- [ ] 多轮追问在同一 opencode session 中继续
- [ ] 用户停止后，前端停止输出且状态清理；深度 `abort + revert` 回滚列为遗留增强项
- [ ] 30 分钟闲置后，会话级临时资源和 worktree 可清理；shared opencode server 不因单个会话闲置被杀
- [ ] shared opencode server 崩溃或重启后，会话可通过持久化 workspace 和 opencode session 信息恢复

### 7.2 非功能验收

- [ ] 一个 shared opencode server 支持至少 10 个活跃 CodeAsk 会话，workspace、provider、MCP token 和事件流不串
- [ ] opencode 进程崩溃不影响 CodeAsk 主进程
- [ ] 每个 MCP 调用写入 audit log
- [ ] 每个 opencode 工具调用映射为新版 Agent 行动轨迹事件
- [ ] 前端失败提示使用居中弹窗，成功提示使用低密度居中浮层

### 7.3 端到端验收

E2E 测试场景按 [opencode-interaction-flow.md](../specs/opencode-interaction-flow.md) §9 的场景矩阵执行。
