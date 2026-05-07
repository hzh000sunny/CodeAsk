# CodeAsk 文档 — v1.0.2

| 字段 | 值 |
|---|---|
| 版本 | v1.0.2 |
| 状态 | Completed |
| 主题 | LLM Agent 会话运行时优化 |
| 基线版本 | `../v1.0.1/` |
| 目标 | 将默认 Agent 会话从固定调查流水线调整为正常聊天优先、RAG 增强、工具调用由模型决策的统一运行时 |

## 版本定位

v1.0.2 是 CodeAsk 的 LLM Agent 优化专项版本。

v1.0.1 已完成独立 LLM Wiki 工作台，补齐了团队知识的维护和引用基础。v1.0.2 的重点不是继续扩展 Wiki 管理界面，而是修正 Agent 会话的默认行为：CodeAsk 首先应该是一个正常的研发 Agent，会围绕用户当前问题多轮沟通；Wiki、报告、附件和代码检索是模型可调用的增强能力，而不是后端强制执行的固定流程。

本版本采用 `v1.0.2`，语义是：

> 在 v1.0 主产品方向和 v1.0.1 Wiki 基础设施不变的前提下，修正 Agent 默认会话运行时。

## 当前记录

| 文件 | 说明 |
|---|---|
| `specs/agent-chat-runtime.md` | v1.0.2 Agent Chat Runtime 头脑风暴收敛后的设计快照 |
| `specs/claude-code-reference-notes.md` | Claude Code 源码和学习资料的参考分析，提炼适合 CodeAsk 的 harness 设计借鉴点 |
| `specs/agent-tools-from-claude-code.md` | Claude Code 工具源码模式到 CodeAsk Agent 工具体系的翻译设计 |
| `specs/agent-runtime-source-lessons.md` | 定向源码深挖后，提炼出的 CodeAsk runtime/tool/context/UI 落地约束 |
| `specs/agent-capability-roadmap.md` | v1.0.2 之后的 Agent 能力演进路线，明确与 Claude Code 的借鉴边界 |
| `specs/rag-context-budget-lessons.md` | AnythingLLM RAG 管线和 Claude Code 长上下文压缩对 v1.0.2 的落地约束 |
| `plans/agent-chat-runtime.md` | v1.0.2 Agent Chat Runtime 实施计划 |
| `prd/agent-chat.md` | v1.0.2 Agent 会话产品契约 |
| `design/agent-chat-runtime.md` | v1.0.2 Agent Chat Runtime 系统设计 |
| `plans/acceptance-checklist.md` | v1.0.2 验收清单 |
| `plans/e2e-scenarios.md` | v1.0.2 Agent Chat Runtime 端到端场景矩阵 |
| `../DEVELOPMENT_ACCEPTANCE.md` | 项目级开发验收阶段与证据基线，v1.0.2 必须遵守 |

## 当前实施状态

- 已完成默认会话入口迁移：`/api/sessions/{session_id}/messages` 默认走 `ChatRuntime`。
- 已完成前端右侧面板迁移：固定“调查进度”替换为 `Agent 行动轨迹`。
- 已保留 v1.0 `AgentOrchestrator` 作为 legacy 兼容，旧 sufficient / insufficient 集成测试继续通过。
- 已完成运行时事件、工具契约、工具执行器、上下文组装、数据库召回和第一批工具模块的单元测试。
- 已接入生产 Feature RAG Pack：`DatabaseRetrievalService` 会从真实特性、Wiki、报告和特性关联仓库组装轻量候选上下文，并注入实际 LLM messages。
- 已补齐每轮结构化 RAG 上下文：模型会看到 `feature_catalog` 活跃特性目录和 `feature_knowledge_index` 特性知识索引；即使问题没有直接命中特性名称，也能通过 Wiki 标题、路径和关键词判断特性相关性。
- 已保留外部 RAG 服务替换入口：后续可替换 `RetrievalService.retrieve(...)` 实现，只要继续输出 `feature_catalog`、`feature_knowledge_index`、`feature_candidates`、`wiki_hits`、`report_hits`、`attachment_candidates`、`repo_candidates`。
- 已接入生产 Wiki 只读工具：默认 Agent 会话可以搜索 Wiki，并按 node / heading 读取真实 Wiki 片段。
- 已接入生产问题报告只读工具：默认 Agent 会话可以搜索已验证问题报告，并读取指定报告正文与元数据。
- 已接入生产会话附件只读工具：默认 Agent 会话可以列出当前会话附件，并读取指定附件片段；工具结果包含原文件名、显示名、别名和描述，避免同名日志串联错误。
- 已将当前会话附件候选注入实际 LLM messages：用户上传、重命名或描述的日志会在本轮上下文中作为“会话附件候选”出现，模型可据此决定是否调用附件读取工具；附件仍按 session 隔离，不跨会话共享。
- 已完成 RAG 候选基础去重和注入预算测试：同一 Wiki 文档或同一问题报告即使被底层搜索返回多个片段，也只向模型注入一次基础来源；候选特性、Wiki、报告和附件进入 LLM messages 前会限制条数和片段长度。
- 已接入生产只读代码工具：仓库列表、代码搜索、目录树、路径列表和代码文件读取；代码访问已收敛为“特性范围仓库池 + 用户显式仓库范围”，默认不再暴露全局 ready 仓库池。
- 已补齐工具结果真实预算裁剪，避免超大工具结果只标记 `truncated=true` 却仍完整进入下一轮 LLM 上下文。
- 已将 AnythingLLM 的 RAG 上传资料管线和 Claude Code 的长上下文压缩经验纳入 v1.0.2 设计输入。
- 已完成真实 LLM 前端端到端验收：使用 `references/claude-code/claude-code` 和 `references/anything-llm` 验证源码仓库检索、刷新恢复和删除清理；这些参考仓库后续必须通过对应特性关联后再进入默认代码检索范围。
- 已实现第一版上下文预算与压缩：参考 Claude Code 的阈值体系，每轮先估算 active context，超过阈值才压缩旧工具结果；供应商返回上下文超限错误时执行一次 reactive compact retry；较早会话 turns 超过最近窗口时，会写入 `session_conversation_summaries` 并在后续轮次注入长期摘要。
- 已新增 live E2E 测试文件：`frontend/e2e/admin-agent-source-live.spec.ts`。该用例默认跳过，显式设置 `CODEASK_RUN_LIVE_AGENT_E2E=1` 后才会触发真实 LLM 调用。
- 已新增并执行 Feature-Scoped Code Access live E2E 通道：`frontend/e2e/agent-feature-scoped-code-live.spec.ts`。该用例默认跳过，显式设置 `CODEASK_RUN_LIVE_FEATURE_SCOPED_CODE_E2E=1` 后验证“创建特性、关联仓库、模型选择特性范围、代码工具结果标注 feature_scope”的完整浏览器链路；2026-05-07 使用真实 GLM-5.1 / OpenAI 协议配置执行通过。
- 已新增长上下文 live E2E 通道：`frontend/e2e/agent-long-context-live.spec.ts`。该用例默认跳过，显式设置 `CODEASK_RUN_LIVE_AGENT_LONG_CONTEXT_E2E=1` 后验证基础问答、上下文依赖追问、刷新后追问和长期摘要恢复。
- 已修复连续会话后端上下文装配缺陷：同一会话第二轮追问时，runtime 会加载最近 turns 和上一轮工具行动摘要，注入本轮 LLM messages。
- 已新增连续会话 live E2E 通道：`frontend/e2e/agent-conversation-continuity-live.spec.ts`。该用例默认跳过，显式设置 `CODEASK_RUN_LIVE_AGENT_CONTINUITY_E2E=1` 后验证“先查 anything-llm，再追问是否查询代码，再刷新后追问上一轮”的真实用户路径。
- 已通过真实浏览器 + GLM-5.1 连续会话验收：会话 `sess_096f8685b5997d38` 第一轮调用 `list_code_repos` / `search_code` / `read_code_file`，第二轮能正确回答刚刚查询了代码，刷新后第三轮仍能复述上一轮内容。
- 已新增特性上下文技术插问 live E2E 通道：`frontend/e2e/agent-contextual-technical-qa-live.spec.ts`。该用例默认跳过，显式设置 `CODEASK_RUN_LIVE_CONTEXTUAL_TECH_QA_E2E=1` 后验证会话围绕 AnythingLLM / RAG 展开时，中途询问 `lancedb 和 sqlitedb 有什么区别` 能保持当前主题语境并优先直接回答，允许少量工具决策偏差，但不应频繁触发代码检索或要求用户显式指定仓库。
- 已将项目级验收规则从“E2E 基线”扩展为“开发验收阶段与证据基线”：后续不能用前端历史恢复替代模型上下文恢复，不能用行动轨迹展示替代模型可追问工具行动。
- 已新增基础问答评测库 `evals/basic_qa/cases/seed_001.jsonl`，当前覆盖 11 类 32 个通用模型能力问题；`frontend/e2e/basic-model-qa-live.spec.ts` 使用“每类取 1 题”的代表性 live 子集，完整题库保留给离线评测和周期性回归。
- 已完成会话体验 Task 14：行动轨迹同会话多轮保留并按 turn 分组，详情弹窗展示结构化诊断字段，长字段支持就地复制并给出轻量提示，生成中可停止并回滚本轮消息 / traces，输入框支持 `Enter` 发送、`Ctrl + Enter` / `Shift + Enter` 换行。
- 已稳定 live Agent E2E 执行策略：当启用任一 `CODEASK_RUN_LIVE_*` 开关时，Playwright 自动强制 `workers = 1`，避免共享 LLM 配置、仓库状态和 `.tmp/playwright-e2e` 目录导致并行污染。
- 已在 2026-05-08 完成完整 live Agent E2E 套件验收：`7 passed (12.0m)`，覆盖基础问答、连续会话、特性范围代码检索、长上下文、特性上下文技术插问和管理员源码链路。
- 待后续继续：引入外部 RAG 服务、继续收敛 RAG 来源去重、上下文预算治理和会话级 auto compact。

## 已确认方向

- 默认会话回归正常 Agent 聊天，不再让每条用户消息强制走完整调查闭环。
- 默认会话必须支持正常多轮追问；模型下一轮必须能看到必要历史和上一轮工具行动摘要。
- 每轮默认执行轻量 Wiki / 报告 / 特性候选召回，并作为上下文注入模型。
- RAG 召回只提供候选证据，不产生“范围判断”“充分性判断”“下一步代码调查”等后端流程结论。
- 模型基于上下文和工具能力决定下一步动作：回答、追问、查 Wiki、读报告、读附件或查代码。
- 代码读取是默认只读能力；真正需要处理的是仓库范围和代码版本不明确时的追问或不确定性标注。
- 特性是候选上下文，不是用户提问前必须绑定的条件。
- 会话 UI 的右侧调查区改为可折叠 Agent 行动轨迹，只展示真实发生的动作和证据。
- 报告生成、写入 Wiki、删除 Wiki 等写操作仍然需要用户确认或明确 UI 动作。

## 推荐阅读顺序

1. `specs/agent-chat-runtime.md`
2. `prd/agent-chat.md`
3. `design/agent-chat-runtime.md`
4. `plans/agent-chat-runtime.md`
5. `plans/acceptance-checklist.md`
6. `plans/e2e-scenarios.md`
7. `specs/claude-code-reference-notes.md`
8. `specs/agent-tools-from-claude-code.md`
9. `specs/agent-runtime-source-lessons.md`
10. `specs/rag-context-budget-lessons.md`
11. `specs/agent-capability-roadmap.md`
12. `../v1.0.1/README.md`
13. `../v1.0/design/agent-runtime.md`
14. `../v1.0/design/llm-gateway.md`
15. `../v1.0/design/wiki-search.md`
16. `../v1.0/design/frontend-workbench.md`
