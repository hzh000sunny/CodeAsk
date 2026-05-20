# Wiki 与代码仓 RAG 产品契约

> 版本：v1.0.5
> 状态：Draft
> 适用范围：opencode 主链路下接入 OpenViking 作为统一 RAG 后端的第一版

---

## §1 产品定位

CodeAsk v1.0.5 不改变产品定位（研发知识与问题定位工作台），也不改变 v1.0.4 opencode 主链路。本版本只补齐 Wiki 与代码仓的 RAG 能力：让模型在 opencode 会话中能基于语义检索找到 CodeAsk 派生的知识资源候选。

**CodeAsk 负责：** 主数据归属、Wiki 树、问题报告生命周期、代码仓注册与 worktree、用户认证、权限边界、审计、前端展示。

**OpenViking 负责：** 把 CodeAsk 派生的 Wiki / 报告 / 代码仓资源解析、分级摘要、向量化、检索、grep/glob 文件操作，并通过 MCP 暴露给 opencode。

**Ollama 负责：** 提供 OpenViking 所需的 embedding 模型推理（v1.0.5 本机部署）。

opencode 与 CodeAsk 的关系不变：opencode 是 Agent 执行引擎，CodeAsk 是知识平台。v1.0.5 让 opencode 多挂一个 OpenViking remote MCP。

---

## §2 核心画像

### 2.1 飞轮中的位置

| | v1.0.4 | v1.0.5 |
|---|---|---|
| Wiki 检索 | 静态 FTS5 / n-gram + `workspace/wiki` 文件零复制 | 加入 OpenViking 语义检索；`workspace/wiki` 文件挂载保留作为兜底 |
| 报告检索 | 文件 `glob/grep ./wiki/<feature>/problem-reports/` | 同上 + OpenViking 召回；verified/draft 权重在动态上下文中明确 |
| 代码仓检索 | 用户显式指定仓库 → `prepare_worktree` → opencode 原生 grep/read | OpenViking 先召回候选 repo / 路径 / 符号 → opencode 主动调用 CodeAsk `prepare_worktree` → 真实源码读取 |
| 后端 | opencode + CodeAsk MCP | opencode + CodeAsk MCP + OpenViking MCP |

### 2.2 用户体验承诺

Maintainer 和 Asker 角色不变。RAG 的引入对用户的可见变化：

- 会话中模型能更主动地引用 Wiki / 报告 / 代码候选，并附上 `viking://` 来源 URI
- Agent 行动轨迹新增 OpenViking 工具事件（`find / search / read / grep / glob`）
- admin 设置页新增 OpenViking 状态卡片（healthy / port / queue / last_sync）

普通用户不需要理解 OpenViking 概念，也不暴露"切换 RAG 后端"开关。

---

## §3 主链路

```text
用户在 opencode 会话中描述问题
  ↓
CodeAsk 组装动态上下文（沿用 v1.0.4）
  + 新增 OpenViking 资源布局提示
  + 新增 RAG 使用原则（语义先于精确，verified 强于 draft）
  ↓
opencode 自主选择工具
  ├─ 知识候选：OpenViking find/search/read
  ├─ 精确文本：OpenViking grep/glob 或 opencode 原生 grep
  ├─ 代码证据：必须先 codeask_prepare_worktree → opencode read/grep workspace 相对路径
  ├─ 会话动作：CodeAsk MCP (bind features / attachments / worktree)
  └─ 知识库写操作：仅通过 CodeAsk 现有 UI / API，不通过 MCP 暴露给模型
  ↓
opencode 给出带证据的回答
  ↓
CodeAsk 持久化 turn + 行动轨迹（含 OpenViking 工具事件）
  ↓
（可选）生成问题报告 → 审核 → 入库 → 触发 OpenViking 增量同步
```

---

## §4 产品契约

### 4.1 用户侧约定

| 约定 | 说明 |
|---|---|
| RAG 后端不暴露为 UI 选项 | v1.0.5 默认使用 OpenViking；不允许用户在前端切换 RAG 后端 |
| 知识写操作仍通过 CodeAsk UI | OpenViking 是派生索引，不是事实源；用户编辑 Wiki / 报告仍走 CodeAsk 现有界面 |
| 同步对用户透明 | Wiki / 报告 / 仓库变更触发后台同步；用户不需要手动 reindex；admin 可手动触发 |
| 不向模型暴露宿主机绝对路径 | OpenViking MCP 返回的 URI 与 CodeAsk 元数据，前端出口脱敏沿用 v1.0.4 规则 |
| Agent 行动轨迹展示 OpenViking 工具事件 | 工具名 / URI / 耗时 / 错误详情；与 v1.0.4 opencode 工具同样展示标准 |

### 4.2 产品侧承诺

| 承诺 | 说明 |
|---|---|
| 资源映射稳定 | `viking://resources/codeask/features/<feature_slug>/...` 是稳定契约；slug 重命名需要走 CodeAsk 主数据，并触发同步 |
| verified 强于 draft | 动态上下文中明确告诉模型：verified 报告才能作为强证据；draft 只作为弱背景 |
| 代码证据走 worktree | OpenViking 返回 repo/path/symbol 候选只是"可能在哪里"；最终代码证据必须来自 CodeAsk `prepare_worktree` 准备的 session worktree |
| OpenViking 不可用时明确报错 | 与 v1.0.4 opencode 不可用同等失败语义；不静默回退到旧 FTS5 链路 |
| 会话级隔离不变 | OpenViking session_id 不直接复用 CodeAsk session_id；MCP 调用通过会话级 bearer token 校验，沿用 v1.0.4 `mcp/auth.py` 模式 |
| 审计完整 | OpenViking 工具调用、CodeAsk 同步任务、permission 拒绝、错误事件都进入审计 |
| 增量同步 | Wiki / 报告 / 仓库变更后通过同步状态表追踪；失败有重试上限和 cooldown |

---

## §5 不做什么

v1.0.5 **不包含**：

- 不让 OpenViking 接管 CodeAsk Feature / Wiki / Report / Repo / Session 主数据
- 不让模型通过 OpenViking MCP `add_resource` 导入 CodeAsk 本地路径
- 不暴露 OpenViking `forget` MCP 工具给 opencode（避免误删）；强制只读子集
- 不在 v1.0.5 引入 LangChain 作为 CodeAsk 主依赖
- 不在 v1.0.5 同时启用 AnythingLLM 作为对比后端运行时
- 不让 RAG 替模型判断"知识够不够"或"是否需要继续查代码"
- 不重写 v1.0.4 的 opencode_compat 模块；只通过新增 `src/codeask/rag/openviking/` 模块协作
- 不在 v1.0.5 接入 Claude Code backend
- 不让 OpenViking 自动写回 CodeAsk DB

---

## §6 资源契约

### 6.1 OpenViking URI 结构

CodeAsk 派生资源统一在 `viking://resources/codeask/` 命名空间下：

```text
viking://resources/codeask/
├── features/
│   ├── <feature_slug>/
│   │   ├── README.md                       # 特性入口（描述、Wiki 入口、关联仓库列表）
│   │   ├── knowledge-base/                 # Wiki 正式文档
│   │   │   └── ...
│   │   ├── problem-reports/
│   │   │   ├── verified/                   # 已验证报告（强证据）
│   │   │   └── drafts/                     # 草稿报告（弱背景）
│   │   └── repos.md                        # 该特性关联仓库说明
│   └── ...
├── repos/
│   ├── <repo_slug>/                        # 单个代码仓的 RAG 资源
│   └── ...
└── global/
    ├── feature-index.md                    # 全特性目录
    ├── repo-index.md                       # 全仓库目录
    └── report-index.md                     # 全报告索引
```

规则：

- `<feature_slug>` 与 CodeAsk Feature 主数据保持一致；重命名需触发同步
- `<repo_slug>` 取 `repos.slug`；若 slug 缺失退化为 `<repo_id>`
- `knowledge-base/` 与 `problem-reports/` 的目录树与 v1.0.4 `wiki_workspace` 一致，但增加分级摘要 L0 / L1 / L2
- v1.0.5 不在第一版导入 session 附件；附件检索仍通过 CodeAsk MCP `list/read_session_attachment`

### 6.2 MCP 工具暴露策略

| OpenViking 原生工具 | v1.0.5 是否暴露给 opencode | 备注 |
|---|---|---|
| `find` | 是 | 全局向量召回 |
| `search` | 是 | 带会话上下文的深度召回 |
| `read` | 是 | 读取 `viking://` URI |
| `list` | 是 | 列目录 |
| `grep` | 是 | 精确文本搜索 |
| `glob` | 是 | 路径模式匹配 |
| `health` | 是 | 健康检查（opencode 不强制使用） |
| `add_resource` | **否** | CodeAsk 后台同步专用，不通过 opencode 暴露 |
| `remember` | **否** | OpenViking memory，v1.0.5 不接入 |
| `forget` | **否** | 危险删除，不暴露给模型 |

OpenViking MCP 直接接入 opencode `opencode.json` 的 `mcp` 配置，使用 OpenViking server `/mcp` endpoint；CodeAsk 不重新封装为 `search_wiki` / `search_code`。

### 6.3 代码证据路径

模型必须遵守：

1. OpenViking 返回的代码候选只代表"可能在哪里"
2. 要读取真实源码必须先调用 `codeask_prepare_worktree`
3. worktree 就绪后用 opencode 原生 `read/grep/glob` 读 workspace 相对路径
4. OpenViking `read(uri)` 适用于 OpenViking 维护的 abstract / overview / chunk / skeleton，**不**等于源码事实

---

## §7 LLM 与 Embedding 配置契约

v1.0.5 在 CodeAsk 现有 LLM 配置体系之外引入 embedding 配置：

| 配置项 | 来源 | 是否暴露给用户 |
|---|---|---|
| OpenViking server URL / token | CodeAsk 后端自动管理；admin 可在诊断面板查看状态 | 否 |
| Embedding provider | 第一版固定 `ollama`；模型由全局 settings 配置 | 暂不暴露在普通用户视图；admin 可在 settings 调整 |
| VLM | 第一版默认不启用 VLM；不依赖 VLM 的资源（Markdown、代码、文本报告）质量为主 | 否 |
| Ollama URL / 模型 tag | `OPENVIKING_EMBED_OLLAMA_BASE_URL` / `OPENVIKING_EMBED_MODEL` 等环境变量；admin 可读 | 否 |

`ov.conf` 由 CodeAsk 后端生成，落在 `$CODEASK_DATA_DIR/openviking/ov.conf`，不使用 `~/.openviking`。

---

## §8 失败语义

| 场景 | 行为 | 用户可见 |
|---|---|---|
| OpenViking server 未启动 / 启动失败 | 健康检查失败；不静默回退 | 居中弹窗：知识检索后端不可用，请检查 OpenViking 或 Ollama |
| Ollama 不可用 | OpenViking embedding 失败；后台同步任务记录错误并退避 | 同上 |
| OpenViking MCP 调用失败 | 该工具返回 error 给 opencode，模型自行处理 | 行动轨迹展示错误详情 |
| 同步任务失败 | 状态机记录 `failed`，受 `maxRepeatFailures` 限制；admin 可手动重试 | admin 面板可见 |
| 代码仓导入超阈值 | 通过 `--ignore-dirs / --include / --exclude` 配置；超时进入失败状态 | admin 可见任务状态 |
| OpenViking 版本与已验证版本不一致 | 启动时记录 warning；admin 面板提示 | 管理员可见 |

---

## §9 验收标准

### 9.1 功能验收

- [ ] Phase 0 spike 通过：OpenViking server 在 CodeAsk `uv` 环境中可启动、健康检查、停止、重启
- [ ] OpenViking 集成边界声明（不修改源码、不内嵌源码）已落到 `specs/openviking-agpl-review.md`，README/INSTALL 披露完成
- [ ] CodeAsk 后端在 startup 拉起 OpenViking server 并注册 keepalive
- [ ] admin 诊断接口 `GET /api/admin/openviking/status` 可读 running / pid / port / version / queue / last_health_at / last_error
- [ ] 真实 Feature Wiki 同步到 `viking://resources/codeask/features/<slug>/knowledge-base/` 后可 `find/search/read/grep/glob`
- [ ] 真实 verified report 同步到 `problem-reports/verified/` 并可被 `find` 命中
- [ ] 真实代码仓同步到 `viking://resources/codeask/repos/<slug>/` 并可被 `search` 命中
- [ ] opencode 在同一会话同时使用 CodeAsk MCP 和 OpenViking MCP 不串
- [ ] OpenViking 召回代码候选 → 模型调用 `codeask_prepare_worktree` → opencode 读取真实文件
- [ ] OpenViking 不可用时，会话以明确错误结束，不静默回退到旧 FTS5 主链路
- [ ] 同步状态表能记录每条同步任务的 source / uri / status / hash / last_synced_at / error

### 9.2 非功能验收

- [ ] OpenViking 进程崩溃不影响 CodeAsk 主进程
- [ ] CodeAsk 重启后 OpenViking 索引、同步状态可恢复
- [ ] MCP 调用具备会话级 token 校验
- [ ] 工具事件返回前端前完成路径脱敏（沿用 v1.0.4 出口脱敏规则）
- [ ] 同步任务失败有重试上限和 cooldown，避免坏配置反复跑
- [ ] Phase 0 实测耗时基线：Wiki 单文档同步 < N 秒（具体 N 在 spike 中确定）
- [ ] 集成边界承诺落地：CodeAsk 仓库不出现 OpenViking 源码、不修改 OpenViking 源码、OpenViking 以独立进程运行；README/INSTALL 包含 OpenViking 引用与许可证披露

### 9.3 端到端验收

详见 [`plans/acceptance-checklist.md`](../plans/acceptance-checklist.md)，最低覆盖：

- 临时空库 `start.sh` 跑通
- 真实数据只读
- 真实数据可写沙箱（同步增量）
- 真实 LLM / opencode + OpenViking + Ollama
- OpenViking 不可用降级提示
- 升级部署（旧 v1.0.4 数据库 → v1.0.5 schema）

---

## §10 文档维护

本文档是 v1.0.5 产品契约。

- 版本演进遵循 `../STRUCTURE.md`
- PRD 与 SDD 冲突以 PRD 为准；冲突时同步更新 SDD
- 产品契约修订需在本文件追加变更小节，并同步更新 `design/openviking-integration.md` 和 `plans/`
