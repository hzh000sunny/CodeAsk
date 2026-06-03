# Wiki RAG 与源码工作区产品契约

> 版本：v1.0.5
> 状态：Release candidate（2026-06-03 文档复核）
> 适用范围：opencode 主链路下接入 OpenViking 作为 Wiki RAG 后端的第一版；代码仓 OpenViking 内容同步延后

---

## §0 Release Scope 校正（2026-06-03）

本 PRD 的早期草案把 Wiki、Report、Repo 都写入同一个 OpenViking 资源空间。M11/M12/M13/M14 落地后，v1.0.5 的 release 范围已收敛为：

- **Wiki**：按 feature 的 `wiki_workspace/current/{feature_slug}/knowledge-base` 目录导入 OpenViking，URI 为 `viking://resources/codeask/wiki/{feature_slug}`。
- **Report**：不进入 OpenViking；只维护 `problem-reports/` 文件视图，供 opencode 在 workspace 中本地 `read/grep/glob`。
- **Repo**：不进入 OpenViking；源码证据仍由 CodeAsk MCP `prepare_worktree` 暴露真实 worktree 后再读。`viking://resources/codeask/code/{repo_slug}` 仅预留层级。
- **Wiki UI 搜索**：直接走 SQL ILIKE，不再调用 OpenViking。
- **Embedding/VLM**：admin 可配置；默认 embedding 是 OpenViking local provider，不要求用户预装 Ollama 才能启动。

因此本文后续历史段落若出现“Report/Repo 入 OpenViking”或“UI 搜索 OpenViking-first”的旧措辞，以本节和 [acceptance-checklist §0.1](../plans/acceptance-checklist.md#01-release-readiness2026-06-03) 为准。

## §1 产品定位

CodeAsk v1.0.5 不改变产品定位（研发知识与问题定位工作台），也不改变 v1.0.4 opencode 主链路。本版本补齐 Wiki RAG 能力：让模型在 opencode 会话中能基于语义检索找到 CodeAsk 派生的 Wiki 候选；源码证据仍通过 CodeAsk worktree 机制取得。

**CodeAsk 负责：** 主数据归属、Wiki 树、问题报告生命周期、代码仓注册与 worktree、用户认证、权限边界、审计、前端展示。

**OpenViking 负责：** 把 CodeAsk 派生的 Wiki `knowledge-base/` 目录解析、分级摘要、向量化、检索、grep/glob 文件操作，并通过 MCP 暴露给 opencode。

**Embedding provider 负责：** 提供 OpenViking 所需的 embedding 模型推理。v1.0.5 默认使用 OpenViking local provider；admin 可切换到 Ollama 或第三方 provider。

opencode 与 CodeAsk 的关系不变：opencode 是 Agent 执行引擎，CodeAsk 是知识平台。v1.0.5 让 opencode 多挂一个 OpenViking remote MCP。

---

## §2 核心画像

### 2.1 飞轮中的位置

| | v1.0.4 | v1.0.5 |
|---|---|---|
| opencode 会话内 Wiki 检索 | `workspace/wiki` 零复制 symlink；opencode 用 native `read/grep/glob` 直接读 Markdown | 同上 **+ OpenViking 语义召回作为增强**；OpenViking 不可用时退回 v1.0.4 行为 |
| 浏览器 Wiki UI 搜索框 | `/api/wiki/search` 走 `NativeWikiSearchService` (SQL `ILIKE`)；另有 legacy `/api/documents/search` 走 FTS5（前端不调用） | `/api/wiki/search` 继续走 SQL `ILIKE`；不调用 OpenViking |
| 报告检索 | 文件 `glob/grep ./wiki/<feature>/problem-reports/` + legacy FTS5 `reports_fts`（前端不调用） | 文件 `glob/grep ./wiki/<feature>/problem-reports/`；Report 不进入 OpenViking |
| 代码仓检索 | 用户显式指定仓库 → `prepare_worktree` → opencode 原生 grep/read | 同 v1.0.4 主链路；模型需要源码证据时必须调用 CodeAsk `prepare_worktree` 后读真实 worktree。OpenViking code 资源层级预留，内容同步延后 |
| 后端 | opencode + CodeAsk MCP；存在 legacy `agent_backend=native` 路径（默认未启用，含 FTS5 工具） | **native 路径搬入 `agent/native_backend/` 隔离保留、不接入请求链路**，`agent_backend` 收敛为 `Literal["opencode"]`；opencode + CodeAsk MCP + OpenViking MCP（OpenViking 是会话内语义检索的唯一入口；CodeAsk MCP 不暴露 FTS / 向量工具）；将来若重启自研 Agent，RAG 接 OpenViking、不回退 FTS5 |
| FTS5 / n-gram 索引 | 三张虚表 + `WikiIndexer` + `WikiSearchService`，仅 legacy 上传路径写入；UI 不调；编辑发布后不重建（drift） | **完全废弃**：alembic drop 三张虚表；删除 `wiki/{search,indexer,tokenizer}.py`；`api/documents_compat.py` `/search` 端点删除，上传路径不再 chunk |

### 2.2 用户体验承诺

Maintainer 和 Asker 角色不变。RAG 的引入对用户的可见变化：

- 会话中模型能更主动地引用 Wiki 候选，并附上 `viking://resources/codeask/wiki/...` 来源 URI
- Agent 行动轨迹新增 OpenViking 工具事件（`find / search / read / grep / glob`）
- admin 设置页新增 OpenViking 仪表盘（健康 / 同步任务进度 / 事件流 / 调优面板，详见 §10）

普通用户不需要理解 OpenViking 概念，也不暴露"切换 RAG 后端"开关。

---

## §3 主链路

v1.0.5 的 OpenViking 链路只服务 opencode 会话内的 Agent 召回；浏览器 Wiki UI 搜索框保持 SQL ILIKE。

### 3.1 opencode 会话 RAG

```text
用户在 opencode 会话中描述问题
  ↓
CodeAsk 组装动态上下文（沿用 v1.0.4）
  + 新增 OpenViking 资源布局提示（仅 OpenViking 可用时注入）
  + 新增 RAG 使用原则（语义先于精确，verified 强于 draft）
  ↓
opencode 自主选择工具
  ├─ OpenViking 可用：知识候选用 OpenViking find/search/read；精确文本可用 OpenViking grep/glob 或 opencode 原生 grep
  ├─ OpenViking 不可用：opencode 用 native read/grep/glob 在 workspace/wiki/ symlink 上检索（v1.0.4 行为）
  ├─ 代码证据：必须先 codeask_prepare_worktree → opencode read/grep workspace 相对路径
  ├─ 会话动作：CodeAsk MCP (bind features / attachments / worktree)
  └─ 知识库写操作：仅通过 CodeAsk 现有 UI / API，不通过 MCP 暴露给模型
  ↓
opencode 给出带证据的回答
  ↓
CodeAsk 持久化 turn + 行动轨迹（含 OpenViking 工具事件，若有）
  ↓
（可选）生成问题报告 → 审核 → 更新 problem-reports 文件视图（不进入 OpenViking）
```

### 3.2 浏览器 Wiki UI 搜索框

```text
用户在 Wiki 页面搜索框输入 q
  ↓
前端 GET /api/wiki/search?q=...&feature_id=...&current_feature_id=...
  ↓
后端：NativeWikiSearchService SQL ILIKE 全表扫描（v1.0.4 行为）
  ↓
统一分组（current_feature / other_current_features / history_features / current_feature_reports）返回前端
```

OpenViking 不参与 UI 搜索。这样 UI 搜索不受 embedding 队列、模型切换、OpenViking 降级或索引重建影响。

### 3.3 Wiki 写路径 → OpenViking 增量同步触发器

| 写操作 | 触发 | OpenViking 行为 |
|---|---|---|
| `POST /api/documents` 上传 Markdown / 文本 / PDF | LegacyWikiSyncService 写 `wiki_documents` 后 | 投影对应 feature 的 `knowledge-base/`，enqueue `source_type=wiki_feature` |
| `POST /api/wiki/documents/{node_id}/publish` | 新 version 写入 + `current_version_id` 更新后 | 写时增量投影对应 md，enqueue `source_type=wiki_feature` |
| `POST /api/wiki/documents/{node_id}/rollback` | `current_version_id` 切换后 | 写时增量投影对应 md，enqueue `source_type=wiki_feature` |
| `PUT /api/wiki/documents/{node_id}/draft` 草稿 | 写 `wiki_document_drafts` | ❌ 不投影正文、不入 OpenViking |
| wiki node 软删 / feature 删除 | DB 提交后 | 删除对应磁盘 md / feature 子树；若 OpenViking 中存在远端 feature，enqueue delete，对 running upsert 采用 deferred delete |
| Report verify / unverify / reject / delete | Report 状态变更后 | 只更新 `problem-reports/` 文件视图；❌ 不入 OpenViking |

---

## §4 产品契约

### 4.1 用户侧约定

| 约定 | 说明 |
|---|---|
| RAG 后端不暴露为 UI 选项 | v1.0.5 默认使用 OpenViking；不允许用户在前端切换 RAG 后端 |
| 知识写操作仍通过 CodeAsk UI | OpenViking 是派生索引，不是事实源；用户编辑 Wiki / 报告仍走 CodeAsk 现有界面 |
| 同步对用户透明 | Wiki 变更触发后台同步；用户不需要手动 reindex；admin 可手动触发。Report/Repo 不进入本版本 OpenViking 同步范围 |
| 不向模型暴露宿主机绝对路径 | OpenViking MCP 返回的 URI 与 CodeAsk 元数据，前端出口脱敏沿用 v1.0.4 规则 |
| Agent 行动轨迹展示 OpenViking 工具事件 | 工具名 / URI / 耗时 / 错误详情；与 v1.0.4 opencode 工具同样展示标准 |

### 4.2 产品侧承诺

| 承诺 | 说明 |
|---|---|
| 资源映射稳定 | `viking://resources/codeask/wiki/{feature_slug}` 是本版本稳定契约；slug 重命名需要走 CodeAsk 主数据，并触发同步 |
| verified 强于 draft | 动态上下文中明确告诉模型：verified 报告才能作为强证据；draft 只作为弱背景 |
| 代码证据走 worktree | OpenViking 返回 repo/path/symbol 候选只是"可能在哪里"；最终代码证据必须来自 CodeAsk `prepare_worktree` 准备的 session worktree |
| OpenViking 是增强、不是 hard dep | OpenViking 不可用时 graceful degradation：Wiki UI 搜索框退回 SQL ILIKE 兜底；opencode 会话退回 native `read/grep/glob`；admin 仪表盘标 degraded 但用户路径保持可用，不弹窗中断（详见 §8） |
| 会话级隔离不变 | OpenViking session_id 不直接复用 CodeAsk session_id；MCP 调用通过会话级 bearer token 校验，沿用 v1.0.4 `mcp/auth.py` 模式 |
| 审计完整 | OpenViking 工具调用、CodeAsk 同步任务、permission 拒绝、错误事件都进入审计 |
| 增量同步 | Wiki 变更后通过同步状态表追踪；失败有重试上限和 cooldown。Report/Repo 同步延后 |
| 仪表盘可见性 | 详见 §10；admin 必须能看到 OpenViking 的所有后台活动（首次索引、增量更新、模型切换、错误重试、进程重启恢复），不允许"后端在做事但 UI 没显示" |

---

## §5 不做什么

v1.0.5 **不包含**：

- 不让 OpenViking 接管 CodeAsk Feature / Wiki / Report / Repo / Session 主数据
- 不在 v1.0.5 把 Report 或代码仓内容导入 OpenViking
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
├── wiki/
│   ├── <feature_slug>/                     # 导入自 wiki_workspace/current/<feature_slug>/knowledge-base
│   │   └── ...
│   └── ...
└── code/
    └── <repo_slug>/                        # 预留；v1.0.5 不导入代码仓内容
```

规则：

- `<feature_slug>` 与 CodeAsk Feature 主数据保持一致；重命名需触发同步
- `<repo_slug>` 取 `repos.slug`；若 slug 缺失退化为 `<repo_id>`；本版本仅预留，不作为 OpenViking 内容源
- OpenViking 只导入 `knowledge-base/`，不导入 `<feature>/README.md` 或 `problem-reports/`
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
| OpenViking server URL / token | CodeAsk 后端自动管理；admin 可在 OpenViking 仪表盘查看状态 | 否 |
| Embedding provider | 默认 `local`，可切换 Ollama / OpenAI-compatible / 云端 provider | 暂不暴露给普通用户；admin 可见 |
| Embedding 模型 | **admin 可见、可在设置页切换** | 是（admin UI） |
| VLM | 默认不启用；admin 可配置 provider/model/base URL/API key；保存只重启 OpenViking，不清索引 | 是（admin UI） |
| Ollama URL | 仅当 embedding provider 为 Ollama，或 VLM 使用 Ollama-compatible 模型时才参与健康检查 | 是（admin UI） |

`ov.conf` 由 CodeAsk 后端生成，落在 `$CODEASK_DATA_DIR/openviking/ov.conf`，不使用 `~/.openviking`。

### 7.0 Operator 前置职责

v1.0.5 区分两类生命周期：

| 组件 | 谁负责安装与启停 | CodeAsk 行为 |
|---|---|---|
| OpenViking server | **CodeAsk 后端** | 启动时自动拉起、keepalive 守护、admin 仪表盘可见 |
| 默认 local embedding | OpenViking + CodeAsk 依赖 | CodeAsk 通过 `openviking[local-embed]` 安装运行依赖；GGUF 模型由 OpenViking 首次使用时懒下载 |
| Ollama 进程 + embedding 模型（可选） | **Operator（部署者）** | 仅当 admin 切到 Ollama provider，CodeAsk 才探测 `/api/tags`；不会自动 `ollama pull`，不会改 Ollama systemd unit |

默认 local provider 下，Operator 不需要先安装 Ollama。若 admin 选择 Ollama provider，则需要完成：

1. 安装 Ollama（默认走 `install.sh`，实测命令见 [`../specs/ollama-installation.md`](../specs/ollama-installation.md) §3）
2. 拉取目标 embedding 模型（例如 `bge-m3`；admin UI 切换前应保证目标模型已在 `/api/tags`）
3. 保证 `http://127.0.0.1:11434/api/tags` 同机可达（默认 Ollama 即如此；跨机部署需要 operator 自行处理 `OLLAMA_HOST` 与防火墙）

CodeAsk 启动时的探测行为（详见 [`../design/openviking-integration.md`](../design/openviking-integration.md) §9 错误矩阵）：

- active embedding provider 不是 Ollama，且 VLM 没有使用 Ollama-compatible 模型 → 不探测 Ollama，不把 Ollama 缺失算作 degraded。
- active provider 是 Ollama 时，Ollama 不可达 → `embedding_unhealthy`，admin 仪表盘报错；OpenViking 同步任务退避。
- active provider 是 Ollama 且目标模型不在 `/api/tags` → `embedding_model_missing`，提示 operator 手动 `ollama pull <model>`。
- 任何情况下，CodeAsk 都**不会**自动执行 `ollama pull`、不会改 Ollama 配置。

INSTALL.md 的"Ollama 与 RAG embedding（v1.0.5）"段是给 operator 的安装清单；本节是其在产品契约中的对应承诺。

### 7.1 Embedding 模型管理

v1.0.5 把 embedding 模型当作"运行时可切换的 admin 配置"，不是一次性写死的环境变量：

- admin 设置页提供 embedding provider 下拉、模型、维度、并发、API base/API key 等字段；provider 校验跟随 OpenViking `EmbeddingModelConfig`
- Ollama provider 下可探测 `/api/tags` 中可用的模型；local provider 展示缓存状态 / 首次启动会下载
- “测试”只写用户数据目录下临时 `ov.conf` 并运行 OpenViking doctor，不保存 DB、不覆盖正式 `ov.conf`、不重启、不清索引、不重排 sync jobs
- 保存 embedding 配置 = 标记 `openviking_sync_jobs` 为 `pending` 并清空 OpenViking 当前向量索引 → 重新同步（v1.0.5 第一版采用全量重建；增量切换留给后续优化）
- 切换记录写审计：旧模型 / 新模型 / 触发时间 / 触发用户 / 重建预估时间
- 切换期间 opencode 会话仍可用，但召回质量在重建完成前会偏低；admin 面板需要可见进度
- 默认模型由 settings 决定，但 settings 只是初始值；DB 中的 admin 配置一旦设置就以 DB 为准

为什么放在 admin UI 而不是只暴露环境变量：

- embedding 模型直接影响召回质量；不同语言 / 不同领域的最佳模型不一样，应该让 admin 在生产中可对比、可切换
- 切换需要触发后台全量重建，必须有审计与可见进度，纯环境变量做不到

---

## §8 失败语义

总原则：**OpenViking 是增强功能，不可用时 graceful degrade，不阻断用户路径**。admin 仪表盘必须把降级状态显式标出，但不要用居中弹窗打断普通用户。

| 场景 | 用户路径行为 | admin 仪表盘 |
|---|---|---|
| OpenViking server 未启动 / 启动失败 | Wiki UI 搜索框走 SQL ILIKE 兜底；opencode 会话走 native `read/grep/glob` 在 `workspace/wiki/` symlink 上检索（v1.0.4 行为） | `degraded`，原因 `server_unavailable`，含最近 N 条启动错误 |
| active provider 不是 Ollama，且 VLM 不依赖 Ollama | 无影响 | 不显示 Ollama 故障，不计入 degraded |
| Ollama 不可用（仅 active provider / VLM 需要时） | OpenViking 后续 embedding 调用退避；已索引数据继续可查；用户路径同上兜底 | `embedding_unhealthy`；同步任务退避（不消耗 retry 配额） |
| Ollama 可达但目标模型不在 `/api/tags`（仅 active provider / VLM 需要时） | 同上 | `embedding_model_missing`，提示 operator `ollama pull <model>` |
| OpenViking MCP 调用单次失败 | 工具返回 error 给 opencode，模型自行回退到 native grep；不立刻判定 OpenViking 整体不可用 | 行动轨迹展示错误详情；事件流记录单次 MCP 失败 |
| 同步任务失败 | 不影响用户路径（被同步内容尚未进入 OpenViking，但 SQL ILIKE 兜底覆盖） | 状态机记录 `failed`，受 `maxRepeatFailures` 限制；admin 可手动重试 |
| 代码仓导入超阈值 | 同上 | 通过 `--ignore-dirs / --include / --exclude` 配置；超时进入失败状态 |
| OpenViking 版本与已验证版本不一致 | 无影响 | warning |

显式不弹窗的反例：opencode 调 OpenViking MCP 单次失败不弹窗（模型自己处理）；OpenViking 整体不可用不弹窗（用户走兜底）。仅当**用户行为依赖 admin 干预**（如长期 `embedding_model_missing` 导致同步队列堆积）才在 admin UI 内提示。

### 8.1 UI 搜索框不走 OpenViking

2026-06-01 起，`/api/wiki/search` 直接走 SQL ILIKE，不再调用 OpenViking。理由：UI 搜索是精确检索/导航工具，不应受 embedding 队列、模型切换、OpenViking 降级或索引重建影响。OpenViking 只服务 opencode / LLM RAG 召回。

---

## §9 验收标准

### 9.1 功能验收

- [x] Phase 0 spike 通过：OpenViking server 在 CodeAsk `uv` 环境中可启动、健康检查、停止、重启
- [x] CodeAsk 后端在 startup 拉起 OpenViking server 并注册 keepalive；运行期不再 `uvx`
- [x] admin 诊断接口 `GET /api/admin/openviking/status` 可读 running / pid / port / version / queue / last_health_at / last_error
- [x] 真实 Feature Wiki 同步到 `viking://resources/codeask/wiki/{feature_slug}` 后可 `find/search/read/grep/glob`
- [x] Report 不进入 OpenViking；`problem-reports/` 文件视图由 opencode 本地 read/grep/glob 使用
- [ ] 真实代码仓同步到 `viking://resources/codeask/code/{repo_slug}` 并可被 `search` 命中。延后到后续版本，不阻塞 v1.0.5 RC
- [x] opencode 在同一会话同时使用 CodeAsk MCP 和 OpenViking MCP 不串
- [x] 模型需要代码证据时调用 `codeask_prepare_worktree` → opencode 读取真实文件；OpenViking URI 不作为源码事实
- [x] OpenViking 不可用时 graceful degrade：Wiki UI 搜索框仍走 SQL ILIKE；opencode 会话用 native `read/grep/glob`；admin 仪表盘显示 `degraded` 但不弹窗打断普通用户
- [x] Wiki 写路径通过 `wiki_workspace/current/{feature_slug}/knowledge-base` 投影和 `wiki_feature` sync job 入队；草稿不入 OpenViking；Report 不入 OpenViking
- [x] `agent_backend=native` legacy 路径已搬入 `agent/native_backend/` 隔离：不在请求链路；`settings.agent_backend` 为 `Literal["opencode"]`；`native_backend` 可 import，冒烟测试通过；模块内无 FTS5 依赖
- [x] FTS5 / n-gram 已删除：`docs_fts` / `docs_ngram_fts` / `reports_fts` 虚表通过 alembic drop；`wiki/{search,indexer,tokenizer}.py` 与 `api/documents_compat.py:/search` 端点删除
- [x] 同步状态表能记录每条同步任务的 source / uri / status / hash / last_synced_at / error

### 9.2 非功能验收

- [x] OpenViking 进程崩溃不影响 CodeAsk 主进程；孤儿进程 / 动态端口深度 hardening 记录为后续长跑项
- [x] CodeAsk 重启后 OpenViking 索引、同步状态可恢复；定时 sweep 会继续对账
- [x] MCP 调用具备会话级 token 校验
- [x] 工具事件返回前端前完成路径脱敏（沿用 v1.0.4 出口脱敏规则）
- [x] 同步任务失败有重试上限和 cooldown，避免坏配置反复跑
- [x] Phase 0 实测耗时基线已记录；当前按 feature 目录同步，耗时受 embedding 队列和模型 provider 影响，admin 指标展示队列和 ETA
- [x] 集成边界承诺落地：CodeAsk 仓库不出现 OpenViking 源码、不修改 OpenViking 源码、OpenViking 以独立进程运行；README/INSTALL 包含 OpenViking 引用

### 9.3 端到端验收

详见 [`plans/acceptance-checklist.md`](../plans/acceptance-checklist.md)，最低覆盖：

- 临时空库 `start.sh` 跑通
- 真实数据只读
- 真实数据可写沙箱（同步增量）
- 真实 LLM / opencode + OpenViking + Ollama
- OpenViking 不可用降级提示
- 升级部署（旧 v1.0.4 数据库 → v1.0.5 schema）

---

## §10 仪表盘可观察性承诺

v1.0.5 把 OpenViking 集成做成"admin 知道它在做什么"的一等公民功能，不是单纯的诊断接口。理由：

- 索引是长耗时操作（CPU 上一个代码仓可能数小时），admin 必须能看到进度、ETA 和瓶颈，不能只见"成功 / 失败"
- 增量同步是被多类事件触发的（Wiki 改 / 特性删除 / 模型切换 / 启动 sweep / 定时远端对账）；只展示状态不展示触发源，admin 没法判断"为什么后台在跑"
- OpenViking 是独立进程；Ollama 只是可选 embedding provider 之一。admin 必须能看到当前 provider、OpenViking 真实 PID / 版本、恢复进度和索引队列状态。

### 10.1 admin 仪表盘必须展示

| 板块 | 内容 |
|---|---|
| 进程健康 | OpenViking running/pid/port/uptime/version；当前 embedding provider/model readiness；Ollama 仅在选择 Ollama provider 时展示 reachable/loaded model/`NUM_PARALLEL` |
| 存储概览 | OpenViking workspace 总向量数、总文档数、磁盘占用 |
| 当前 embedding 配置 | provider/model/dimension/max_concurrent/activated_at；切换历史 |
| 进行中任务 | 每个 task：源对象、已完成 chunk / 总 chunk、failure 数、吞吐 chunk/s、ETA |
| 等待中任务 | pending 队列长度 |
| 失败任务 | failed / cancelled 列表、错误原因、手动重试入口 |
| 事件流 | 最近 N 条事件（Wiki 同步触发、report 文件视图更新、模型切换、可选 provider 恢复检测、circuit breaker 跳闸、完成事件等） |
| 性能指标 | 最近 5 分钟：throughput、avg embed latency、circuit breaker trips |
| 手动操作 | 单源重新同步、全量重建、清空 + 重建（带确认弹窗） |

### 10.2 触发同步的事件源（仪表盘事件流必须能展示）

| 事件 | 触发点 |
|---|---|
| `wiki_feature_changed` | Wiki 节点 create/update/publish/move/rename/delete 后，对应 feature 的 `knowledge-base/` 目录需要同步 |
| `report_projection_changed` | 问题报告 verify/unverify/reject/delete 或引用关系变化后，只更新 `problem-reports/` 文件视图，不进入 OpenViking |
| `repo_synced` / `repo_refresh_summary` | 仓库 ready/refresh 完成；仅表示 CodeAsk repo 状态，不表示代码内容进入 OpenViking |
| `scheduled_refresh_summary` | APScheduler 定时增量 sweep 完成，含 scanned/enqueued/skipped/remote_stale/delete 信息 |
| `embedding_model_switched` | admin UI 切换 model |
| `manual_resync` | admin 手动触发单源 / 全量 |
| `startup_sweep` | CodeAsk 启动时对齐缺失对象 |
| `openviking_restart_detected` | OpenViking server 重启后队列恢复 |
| `ollama_recovery` / provider-specific recovery | 仅当前配置需要外部 provider 时记录恢复事件 |

每条事件至少携带：`event_type / source_object_id / source_type / triggered_by / triggered_at / outcome`。

### 10.3 不在第一版要求的

- 实时 WebSocket 推送（v1.0.5 用 polling，2–5 s 间隔；后续优化）
- Prometheus / 外部 metrics 导出（OpenViking 自己提供 `/metrics`，CodeAsk 仪表盘第一版不接）
- 历史趋势图表（折线 / 热力图等）
- 跨多 OpenViking 实例聚合

### 10.4 参数调优闭环

仪表盘不只是"看"，还要能调。admin 在不熟悉部署环境时，必须能通过观察指标动态调整参数，而不是只能在 settings.py 改完重启全栈。

调优闭环：

```text
admin 进入仪表盘
  ↓
观察当前指标（throughput / avg embed latency / ETA / circuit breaker trips）
  ↓
判断瓶颈，调整参数（OpenViking max_concurrent / Ollama NUM_PARALLEL / ...）
  ↓
系统自动 restart 相应进程（OpenViking 30 s，Ollama 由 admin 在 shell 跑）
  ↓
仪表盘 metrics 卡片自然刷新到新数据（5 分钟滚动窗口）
  ↓
admin 自己判断是否改善；不满意 → 回滚 / 再调
```

**只展示当前事实数据，不做改前改后自动对比。** 理由：

- 系统强行算 delta 可能误导：可能改善真的来自这次调整，也可能来自外部因素（其它 sync 任务完成、Ollama 模型从冷启动转热等）；admin 自己心里判断更准
- 减少实现复杂度（没有 sleep + 异步 snapshot + 配对事件渲染）
- 减少前端复杂度（事件流就是单条事件按时间倒序，不需要"成对渲染"逻辑）

历史变更走 `GET /api/admin/openviking/tuning/history` 拉，admin 想看趋势就翻历史。

### 10.5 可调参数清单

#### 10.5.1 OpenViking 端（CodeAsk admin UI 直接管理）

| 参数 | 含义 | 调整时机 |
|---|---|---|
| `embedding.max_concurrent` | OpenViking 客户端 asyncio.Semaphore 上限 | embedding 是 CPU/GPU/远程网关时各不同；spike 实测 CPU=1，GPU=2-4，云端=5-10 |
| `embedding.circuit_breaker.failure_threshold` | 连续失败多少次跳闸 | 默认 5；网络抖动多可调大 |
| `embedding.circuit_breaker.reset_timeout` | 半开重试间隔（秒） | 默认 60；Ollama 频繁卡顿可调小 |
| `embedding.max_retries` | 单 chunk embed 最大重试次数 | 默认 3 |
| `embedding.max_input_tokens` | 单 chunk 输入上限 | 默认 4096；大型代码文件可调大避免切碎 |

改完 → 写 DB → 重写 ov.conf → restart OpenViking → 不重建已有索引 → ~30 s 服务中断。

#### 10.5.2 Ollama 端（CodeAsk 提供建议，admin 自己改 systemd）

| 参数 | 含义 | 推荐值 |
|---|---|---|
| `OLLAMA_NUM_PARALLEL` | Ollama 同时处理几个 embed 请求 | 见 10.5.4 推荐表 |
| `OLLAMA_NUM_THREAD` | 每次推理用几核做 BLAS | 见 10.5.4 推荐表 |

第一版 admin UI 提供"复制 systemd snippet"按钮 + 给出 `systemctl edit ollama && systemctl restart ollama` 命令，**不**替 admin 跑 sudo。CodeAsk 进程不需要 root 权限。

#### 10.5.3 CodeAsk 端（settings + 内存）

| 参数 | 含义 | 调整时机 |
|---|---|---|
| `openviking_sync_workers` | CodeAsk 同步引擎并发 worker 数 | 影响多个 sync_jobs 是否并发派发到 OpenViking |
| `openviking_progress_sweep_interval_seconds` | 进度轮询间隔 | 默认 5；任务多可调大降低 OpenViking 负载 |
| `openviking_scheduled_refresh_hours` | 全量 hash 比对周期 | 默认 24 |

CodeAsk 端参数调整是轻量的（restart sync scheduler，不动 OpenViking），秒级生效。

#### 10.5.4 部署规格推荐表

| 主机规格 | OpenViking max_concurrent | Ollama NUM_PARALLEL | Ollama NUM_THREAD | CodeAsk sync_workers |
|---|---|---|---|---|
| 笔记本 / 小机（4–8 核 CPU） | 1 | 1 | auto | 2 |
| 单 socket 服务器（16–32 核 CPU） | 2 | 2 | 16 | 2 |
| 中型服务器（32–64 核 CPU） | 4 | 4 | 16 | 3 |
| 多 socket 大机（64–128 核 CPU） | 8 | 8 | 16，绑 NUMA | 4 |
| 单 GPU 主机 | 4 | 4 | auto | 3 |
| 云端 embedding 网关（OpenAI / 火山 / DashScope） | 8 | n/a | n/a | 4 |

仪表盘"调优面板"会把当前规格自动识别（CPU 核数 + GPU 检测 + provider）+ 推荐值预填，admin 可手动覆盖。

### 10.6 与其它仪表盘的关系

- v1.0.4 已有 admin opencode 状态卡片；OpenViking 仪表盘**独立**放置，不嵌入 opencode 卡片
- 会话页 Agent 行动轨迹只展示 opencode 调 OpenViking MCP 的工具事件（`find/search/read/grep/glob`）；**不**展示后台同步事件，避免污染会话视图
- 同步事件只在 admin 仪表盘可见

---

## §11 文档维护

本文档是 v1.0.5 产品契约。

- 版本演进遵循 `../STRUCTURE.md`
- PRD 与 SDD 冲突以 PRD 为准；冲突时同步更新 SDD
- 产品契约修订需在本文件追加变更小节，并同步更新 `design/openviking-integration.md` 和 `plans/`
