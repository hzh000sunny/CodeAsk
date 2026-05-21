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
| 仪表盘可见性 | 详见 §11；admin 必须能看到 OpenViking 的所有后台活动（首次索引、增量更新、模型切换、错误重试、进程重启恢复），不允许"后端在做事但 UI 没显示" |

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
| Embedding provider | 第一版固定 `ollama`；后续可扩展为多 provider | 暂不暴露给普通用户；admin 可见 |
| Embedding 模型 | **admin 可见、可在设置页切换** | 是（admin UI） |
| VLM | 第一版默认不启用 VLM；不依赖 VLM 的资源（Markdown、代码、文本报告）质量为主 | 否 |
| Ollama URL | settings 默认 `http://127.0.0.1:11434`；admin 可读 | 否 |

`ov.conf` 由 CodeAsk 后端生成，落在 `$CODEASK_DATA_DIR/openviking/ov.conf`，不使用 `~/.openviking`。

### 7.1 Embedding 模型管理

v1.0.5 把 embedding 模型当作"运行时可切换的 admin 配置"，不是一次性写死的环境变量：

- admin 设置页提供 embedding 模型选择控件，下拉列出当前 Ollama 实例 `/api/tags` 中可用的模型
- admin 可输入自定义模型 tag（即使尚未拉取，下次同步任务执行时如果 Ollama 拉到了就生效）
- 切换模型 = 标记所有 `openviking_sync_jobs` 为 `pending` 并清空 OpenViking 当前向量索引 → 重新同步（v1.0.5 第一版采用全量重建；增量切换留给后续优化）
- 切换记录写审计：旧模型 / 新模型 / 触发时间 / 触发用户 / 重建预估时间
- 切换期间 opencode 会话仍可用，但召回质量在重建完成前会偏低；admin 面板需要可见进度
- 默认模型由 settings 决定，但 settings 只是初始值；DB 中的 admin 配置一旦设置就以 DB 为准

为什么放在 admin UI 而不是只暴露环境变量：

- embedding 模型直接影响召回质量；不同语言 / 不同领域的最佳模型不一样，应该让 admin 在生产中可对比、可切换
- 切换需要触发后台全量重建，必须有审计与可见进度，纯环境变量做不到

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

## §10 仪表盘可观察性承诺

v1.0.5 把 OpenViking 集成做成"admin 知道它在做什么"的一等公民功能，不是单纯的诊断接口。理由：

- 索引是长耗时操作（CPU 上一个代码仓可能数小时），admin 必须能看到进度、ETA 和瓶颈，不能只见"成功 / 失败"
- 增量同步是被多类事件触发的（Wiki 改 / 报告验证 / 仓库 push / 模型切换 / 启动 sweep）；只展示状态不展示触发源，admin 没法判断"为什么后台在跑"
- OpenViking / Ollama 都是独立进程，可能崩溃、重启、版本不一致；admin 必须能立刻看到恢复进度

### 10.1 admin 仪表盘必须展示

| 板块 | 内容 |
|---|---|
| 进程健康 | OpenViking running/pid/port/uptime/version；Ollama reachable/loaded model/`NUM_PARALLEL` 当前值 |
| 存储概览 | OpenViking workspace 总向量数、总文档数、磁盘占用 |
| 当前 embedding 配置 | provider/model/dimension/max_concurrent/activated_at；切换历史 |
| 进行中任务 | 每个 task：源对象、已完成 chunk / 总 chunk、failure 数、吞吐 chunk/s、ETA |
| 等待中任务 | pending 队列长度 |
| 失败任务 | failed / cancelled 列表、错误原因、手动重试入口 |
| 事件流 | 最近 N 条事件（同步触发、模型切换、Ollama 重启检测、circuit breaker 跳闸、recovery、完成事件等） |
| 性能指标 | 最近 5 分钟：throughput、avg embed latency、circuit breaker trips |
| 手动操作 | 单源重新同步、全量重建、清空 + 重建（带确认弹窗） |

### 10.2 触发同步的事件源（仪表盘事件流必须能展示）

| 事件 | 触发点 |
|---|---|
| `wiki_doc_changed` | Wiki 节点 create/update/publish/move/rename/delete |
| `report_verified` | 问题报告 verify 状态变化 |
| `report_unverified` / `report_deleted` | 同上 |
| `repo_synced` | 仓库 ready/refresh 完成 |
| `feature_changed` | 特性创建/重命名/归档 |
| `scheduled_refresh` | APScheduler 定时增量 sweep |
| `embedding_model_switched` | admin UI 切换 model |
| `manual_resync` | admin 手动触发单源 / 全量 |
| `startup_sweep` | CodeAsk 启动时对齐缺失对象 |
| `openviking_restart_detected` | OpenViking server 重启后队列恢复 |
| `ollama_recovery` | Ollama 重启后 OpenViking 重新连通 |

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
