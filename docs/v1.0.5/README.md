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
    └── openviking-agpl-review.md          # OpenViking 集成边界声明（许可证承诺记录）
```

## 推荐阅读顺序

1. `prd/rag-knowledge.md` —— 产品契约
3. `design/openviking-integration.md` —— 系统设计
4. `plans/phase-0-spike.md` —— Phase 0 spike 详细计划
5. `plans/phase-1-sync-adapter.md`
6. `plans/phase-2-opencode-integration.md`
7. `plans/acceptance-checklist.md`
8. `../future/rag-knowledge-pipeline.md` —— 设计前史
9. `../future/openviking-rag-research-2026-05-20.md` —— 早期实测调研

## 当前实施进度

截至 2026-05-20，本版本仍处于 Draft：尚未启动 Phase 0 spike。OpenViking 集成边界已声明（不修改源码、不内嵌源码、不规划 SaaS），无许可证前置门槛。

## 引用

- v1.0.4 落地契约：`../v1.0.4/`
- v1.0.4 opencode_compat 模块：`src/codeask/agent/opencode_compat/`
- 设计前史：`../future/rag-knowledge-pipeline.md` 与 `../future/openviking-rag-research-2026-05-20.md`
- 参考项目本地路径：`/home/hzh/wiki/OpenViking`、`/home/hzh/wiki/OpenViking-docs`、`/home/hzh/wiki/anything-llm`、`/home/hzh/wiki/anything-llm-docs`
