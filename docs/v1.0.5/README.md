# CodeAsk 文档 — v1.0.5

| 字段 | 值 |
|---|---|
| 版本 | v1.0.5 |
| 起始日期 | 2026-05-20 |
| 状态 | Draft |
| 主题 | Wiki 与代码仓 RAG —— 接入 OpenViking 作为统一上下文数据库 |
| 基线版本 | `../v1.0.4/` |
| 目标 | 让 opencode 在会话中能基于 OpenViking 语义检索 Wiki / 问题报告 / 代码仓候选；CodeAsk 继续掌握主数据、权限、审计和 worktree |

## 版本定位

v1.0.4 已经让 opencode 成为 CodeAsk 默认会话的 Agent 执行引擎，CodeAsk 负责知识平台层。v1.0.5 在此基础上补齐 RAG：把 Wiki、问题报告和代码仓变成 OpenViking 资源，让 opencode 通过 OpenViking MCP 的 `find / search / read / list / grep / glob` 找到候选，再用 CodeAsk MCP `prepare_worktree` 准备真实源码读取环境。

本版本采用 `v1.0.5`，语义是：

> 在 v1.0.4 opencode 主链路不变的前提下，把 Wiki 和代码仓 RAG 升级到 OpenViking 统一后端。

不改变 CodeAsk 的产品定位、Feature/Wiki/Report/Repo 主数据归属、登录鉴权与权限边界。

## 与 v1.0.4 的关系

v1.0.4 完成：

- shared `opencode serve` 进程管理
- 会话级 workspace、`opencode.json`、MCP token
- 持久化 Wiki 文件工作区 + 会话 `workspace/wiki` 零复制 symlink
- CodeAsk MCP 工具：特性 / 仓库 / worktree / 附件 / 会话特性绑定
- LLM Adapter 与 opencode provider profile

v1.0.5 新增：

- 新增 `src/codeask/rag/openviking/` 独立兼容模块
- 启动管理 OpenViking server（参考 v1.0.4 `opencode_compat/process.py` 模式）
- 把 CodeAsk Wiki / 问题报告 / 代码仓增量同步到 OpenViking `viking://resources/codeask/...`
- opencode 同时挂 CodeAsk MCP 和 OpenViking remote MCP，会话动态上下文增加 OpenViking 资源布局提示
- admin 诊断面板新增 OpenViking 状态卡片
- Wiki 现有 FTS5 / n-gram 检索作为兜底保留，但不再是 opencode 主链路 RAG 入口

v1.0.5 不做：

- 不引入 AnythingLLM 运行时；只参考其文档处理、向量缓存、来源去重和同步队列模式
- 不引入 LangChain 作为 CodeAsk 主依赖；OpenViking 自带的 LangChain 集成只作参考
- 不重写 CodeAsk Wiki / 报告 / 仓库主数据模型
- 不让 opencode 通过 OpenViking MCP 导入 CodeAsk 本地路径，避免宿主机绝对路径外泄
- 不让 RAG 后端替模型做“是否需要继续查代码”“知识是否足够”等流程结论
- 不在 v1.0.5 接入 Claude Code backend（保留到后续版本）

## 关键决策

| 维度 | 选择 | 备注 |
|---|---|---|
| RAG 后端 | OpenViking 统一后端 | Wiki、问题报告、代码仓都进入同一 `viking://resources/codeask/` 资源空间 |
| Embedding provider | 本机 Ollama | OpenViking `embedder.provider = ollama`，模型由 Phase 0 实测决定（候选 `bge-m3` / `nomic-embed-text` / `mxbai-embed-large`） |
| OpenViking 进程 | CodeAsk 后端管理 | 参考 v1.0.4 shared opencode serve：启动拉起 + keepalive + admin 诊断；Ollama 进程不归 CodeAsk 管 |
| AGPL 边界 | 边界承诺已记录，无前置门槛 | CodeAsk 不修改 OpenViking 源码、不内嵌源码、当前不规划 SaaS；详见 `specs/openviking-agpl-review.md` |
| 数据目录 | `$CODEASK_DATA_DIR/openviking/{ov.conf,workspace,models,logs}` | 不使用用户默认 `~/.openviking` |
| 处理参考 | anything-llm | chunk header、vector cache、sync queue、source dedup、worker SSE 进度等模式 |
| 退化策略 | OpenViking 不可用时返回明确错误，不静默回退 | 与 v1.0.4 opencode 不可用同样的失败语义 |

## 目录结构

```text
v1.0.5/
├── README.md
├── prd/
│   └── rag-knowledge.md                   # 产品契约
├── design/
│   └── openviking-integration.md          # 系统设计
├── plans/
│   ├── phase-0-spike.md                   # Phase 0 可行性 spike 详细计划
│   ├── phase-1-sync-adapter.md            # Phase 1 同步适配器实现计划（框架）
│   ├── phase-2-opencode-integration.md    # Phase 2 opencode 主链路接入计划（框架）
│   └── acceptance-checklist.md            # 多环境 E2E 与收口验收清单
└── specs/
    ├── openviking-agpl-review.md          # OpenViking 集成边界声明（许可证承诺记录）
    ├── ollama-installation.md             # Ollama 安装实测记录（Phase 0）
    └── openviking-server-bootstrap.md     # OpenViking server 首次启动实测记录（Phase 0）
```

## 推荐阅读顺序

1. `prd/rag-knowledge.md` —— 产品契约
2. `design/openviking-integration.md` —— 系统设计
3. `plans/phase-0-spike.md` —— Phase 0 spike 详细计划
4. `specs/ollama-installation.md` —— Ollama 安装实测记录
5. `specs/openviking-server-bootstrap.md` —— OpenViking server 首次启动实测记录
6. `plans/phase-1-sync-adapter.md`
7. `plans/phase-2-opencode-integration.md`
8. `plans/acceptance-checklist.md`
9. `../future/rag-knowledge-pipeline.md` —— 设计前史
10. `../future/openviking-rag-research-2026-05-20.md` —— 早期实测调研

## 当前实施进度

- 2026-05-20：v1.0.5 文档骨架建立；OpenViking 集成边界已声明（不修改源码、不内嵌源码、不规划 SaaS），无许可证前置门槛。
- 2026-05-20：Phase 0 spike 启动；本机 Ollama 0.24.0 + OpenViking 0.3.17 + MCP 10 tools 全部验证通过；实测记录见 `specs/ollama-installation.md` 与 `specs/openviking-server-bootstrap.md`。
- 2026-05-21：embedding 模型选定 `bge-m3`（中文 wiki 优先，admin UI 可切换；PRD §7.1、SDD §3.3 已补）。
- 2026-05-21：发现 CPU 上 Ollama embedding 并发雪崩（默认 max_concurrent=10 → 单 chunk 88s），收敛为 `max_concurrent=1` 顺序处理，单 chunk 稳定 ~3s。
- 2026-05-21：Phase 0 收口。核心链路全通（Ollama / OpenViking / MCP / Embedding / 中文 find / 批量异步 import 入队）；CPU 性能瓶颈量化为已知约束写入 SDD；完整召回基线推到 Phase 2 live E2E。详见 `plans/phase-0-spike.md` §10。
- 2026-05-21：补 admin 仪表盘契约。PRD §10、SDD §13、Phase 1 §7 全部完成。约定："admin 必须能看到 OpenViking 的所有后台活动"，含首次索引 / 增量更新 / 模型切换 / 进程重启恢复 / 错误重试。新增 `openviking_dashboard_events` 表与三个前端组件（Health / SyncJobs / EventStream）。
- 2026-05-21：补调优面板。约定："admin 必须能通过仪表盘动态调参 + 看当前指标"。PRD §10.4–§10.5 定义调优闭环与可调参数清单（OpenViking + Ollama + CodeAsk 三层），含部署规格推荐表。SDD §3.4 新增 `OpenVikingTuningSetting` 表；§13.6 定义调优面板组件。**只展示当前事实指标，不做改前改后自动对比**——避免误把外部因素归因到 admin 调参，也减少实现复杂度。Phase 1 §7.1.4 加 7 个 tuning API。Ollama 参数由 CodeAsk 给推荐 + 复制 systemd snippet，不替 admin 跑 sudo；CodeAsk 探测实际生效。
- 下一步：进入 Phase 1（OpenViking Sync Adapter）实现阶段。

## 引用

- v1.0.4 落地契约：`../v1.0.4/`
- v1.0.4 opencode_compat 模块：`src/codeask/agent/opencode_compat/`
- 设计前史：`../future/rag-knowledge-pipeline.md` 与 `../future/openviking-rag-research-2026-05-20.md`
- 参考项目本地路径：`/home/hzh/wiki/OpenViking`、`/home/hzh/wiki/OpenViking-docs`、`/home/hzh/wiki/anything-llm`、`/home/hzh/wiki/anything-llm-docs`
