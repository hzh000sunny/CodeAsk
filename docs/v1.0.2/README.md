# CodeAsk 文档 — v1.0.2

| 字段 | 值 |
|---|---|
| 版本 | v1.0.2 |
| 状态 | Active |
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
| `specs/model-provider-reference-lessons.md` | Claude Code、AnythingLLM、vLLM 和真实模型 stream shape 对模型服务接入、reasoning 隔离和运行事件展示的参考结论 |
| `plans/agent-chat-runtime.md` | v1.0.2 Agent Chat Runtime 实施计划 |
| `plans/problem-report-generation.md` | 会话生成问题定位报告的专项实施计划，覆盖 AI 成文、会话唯一绑定和覆盖式再生成 |
| `plans/structured-reasoning.md` | v1.0.2 结构化 reasoning 协议适配实施计划，覆盖 OpenAI-compatible / Anthropic、vLLM 网关边界和真实模型测试矩阵 |
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
- 已新增模型服务接入参考结论：结构化 reasoning 实现必须实际对照 Claude Code 的结构化 thinking、AnythingLLM 的多 provider 适配和 vLLM reasoning outputs；借鉴 provider / profile / stream normalization 分层，不照搬 AnythingLLM 的 `<think>` 文本通道。
- 已确认结构化 reasoning 的四层落地边界：后端只消费协议字段，request profile 只负责请求差异，私有 raw thinking 应在模型服务 / 网关 parser 转结构化；前端 UI Leak Guard 只做可配置显示保护，不能替代协议解析成功。
- 已完成结构化 reasoning 第一版实现：`src/codeask/llm/reasoning.py` 统一归一 OpenAI-compatible `reasoning_content/reasoning/thinking` 与 Anthropic `thinking_delta/redacted_thinking/text_delta`；`LLMClient` 只把结构化 reasoning 发为 `reasoning_delta`，不扫描正文 `<think>` 标签。
- 已完成 Reasoning Request Profile：LLM 配置新增 `reasoning_profile/reasoning_profile_json`，默认 `none`，可显式选择 `volcengine_thinking`、`vllm_enable_thinking`、`anthropic_budget_thinking` 或 `custom_json`；网关透传到 client，不按模型名硬编码。
- 已完成 reasoning 持久化隔离：`ChatRuntime` 将 `reasoning_delta` 转成 `reasoning_observed` 元数据事件，只记录字段、长度、redacted 和 `raw_reasoning_used=false`；正式回答、会话标题、问题报告和下一轮上下文只使用 `text_delta`。
- 已完成前端 UI Leak Guard 第一版：聊天流中疑似 `<think>` 泄漏只在显示层遮蔽并追加 `reasoning_leak_detected` 行动轨迹诊断，不回写数据库，不作为协议适配成功依据。
- 已完成 6 个真实 LLM 配置的 structured reasoning 冒烟验证：火山 Anthropic/OpenAI MiniMax、火山 Anthropic/OpenAI GLM、DeepSeek OpenAI/Anthropic 均能完成真实会话流；SSE、`session_turns` 和 traces 均未出现 raw `<think>` 泄漏。
- 已发现并修复 Anthropic 兼容接口的工具 schema 首包失败场景：当 provider 明确拒绝 tools schema 时，LLM client 会重试一次无工具请求，保证基础问答不被工具协议兼容性拖垮；这不是业务语义特判，不影响正常支持工具的 provider。
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
- 已完成行动轨迹调试版收敛：`llm_input` 会实时推送并持久化为模型输入审计，展示消息数、工具数、上下文长度和最近工具结果摘要；工具结果详情展示结果条数和有限预览。所有调试信息来自 Runtime 结构化事件，不为每个事件额外调用 LLM，也不展示 raw reasoning。
- 已取消会话界面的"强制代码调查"入口：前端不再提交 `force_code_investigation`，行动轨迹不会因"代码 / 源码"等关键词生成强制代码调查事件；是否调用代码工具仍由模型基于上下文和工具说明决策。报告生成和发送按钮组成右侧操作组，删除旧入口后保持原有靠右布局。
- 已修复会话页路由恢复：当前选中会话会写入 `#/sessions?session={session_id}`，浏览器刷新或切换到其它一级页面再返回时仍恢复原会话，不再默认跳回列表第一项。
- 已增加会话标题自动生成：未手动命名的新会话在第一轮完整问答后，会用独立 LLM 请求基于第一轮用户 / 助手内容生成标题；该请求不进入正常对话上下文、不写入 turns、不进入行动轨迹。用户手动重命名后标题来源变为 `manual`，后端不得自动覆盖。前端会在会话流结束后调用 `POST /api/sessions/{session_id}/title/generate`，拿到最新 `SessionResponse` 后直接合并进会话列表缓存，实现标题动态渲染；会话列表标题单行省略展示，并保留短时间补充刷新作为兜底。
- 已将会话生成问题定位报告改为异步任务模式：`POST /reports/prepare` 立即返回 `request_id/status=running`，前端轮询 `GET /reports/prepare/{request_id}` 获取草稿，避免长时间 LLM 生成经过代理或 Vite dev server 返回阶段出现 503 后丢失结果。
- 已修复会话报告重复生成的绑定规则：报告 prepare 阶段不再以前端本地 `detectedFeatureIds[0]` 或既有报告旧绑定作为默认事实，默认特性优先来自当前会话证据推断；用户在确认弹窗中显式选择并保存时才覆盖绑定。
- 已修复会话唯一报告的历史兼容：保存会话报告时会识别 `reports.session_id` 和早期 `metadata_json.session_id` 形态的历史报告，清理同一会话重复草稿及旧 Wiki 报告引用，保证一个会话只保留一篇问题报告且只出现在一个特性下。
- 已增加第一版全局 LLM 配置池负载均衡：用户个人 LLM 配置优先；没有个人配置时，从启用的全局配置中随机选择；单个全局配置最近 60 秒最多服务 3 个会话，同一会话 5 分钟内保持模型粘性，失败频繁的全局配置会临时剔除 10 分钟，初始失败会立即切换下一个可用全局配置，池满时返回 `当前资源繁忙，请稍后再试`。
- 已稳定 live Agent E2E 执行策略：当启用任一 `CODEASK_RUN_LIVE_*` 开关时，Playwright 自动强制 `workers = 1`，避免共享 LLM 配置、仓库状态和 `.tmp/playwright-e2e` 目录导致并行污染。
- 已在 2026-05-08 完成完整 live Agent E2E 套件验收：`7 passed (12.0m)`，覆盖基础问答、连续会话、特性范围代码检索、长上下文、特性上下文技术插问和管理员源码链路。
- 已修复报告草稿解析容错：模型返回被 Markdown 代码块包裹、字符串中含裸换行或 `body_markdown` 内含未转义半角双引号的 JSON-like 输出时，后端仍能提取 `title_description` 和正文，避免报告标题落到 `YYYY-MM-DD 未命名问题`、正文保存成原始 JSON 代码块。
- 当前 v1.0.2 未完成项：LLM 网关配置选择 / 切换 / 冷却的 trace 或结构化日志可观测性仍需继续增强。structured reasoning 已完成 API 真实模型验证、浏览器冒烟、全量后端测试、全量前端测试和生产构建；`frontend/e2e/agent-reasoning-protocol-live.spec.ts` 已作为后续发布流水线的可重复 live E2E 通道保留。
- 待后续版本继续：引入外部 RAG 服务、继续收敛 RAG 来源去重、上下文预算治理、生成式结构化摘要、真实 token 预算和 Claude Code 级别的 prompt cache editing。

## 已确认方向

- 默认会话回归正常 Agent 聊天，不再让每条用户消息强制走完整调查闭环。
- 默认会话必须支持正常多轮追问；模型下一轮必须能看到必要历史和上一轮工具行动摘要。
- 每轮默认执行轻量 Wiki / 报告 / 特性候选召回，并作为上下文注入模型。
- RAG 召回只提供候选证据，不产生“范围判断”“充分性判断”“下一步代码调查”等后端流程结论。
- 模型基于上下文和工具能力决定下一步动作：回答、追问、查 Wiki、读报告、读附件或查代码。
- 代码读取是默认只读能力；真正需要处理的是仓库范围和代码版本不明确时的追问或不确定性标注。
- 特性是候选上下文，不是用户提问前必须绑定的条件。
- 会话 UI 的右侧调查区改为可折叠 Agent 行动轨迹，只展示真实发生的动作和证据。
- Agent 行动轨迹允许扩展公开分析摘要，例如本轮注入了哪些候选、选择了哪些证据、下一步为何读取 Wiki / 报告 / 代码；这些摘要必须来自可见上下文、工具事件和证据链，不能使用或展示 raw reasoning。
- 前端可做受控 UI Leak Guard 防止上游 raw thinking 直接暴露，但它不得回写数据库、不得污染下一轮上下文，也不得作为 structured reasoning 协议适配成功的证据。
- 报告生成、写入 Wiki、删除 Wiki 等写操作仍然需要用户确认或明确 UI 动作。

## 推荐阅读顺序

1. `specs/agent-chat-runtime.md`
2. `prd/agent-chat.md`
3. `design/agent-chat-runtime.md`
4. `plans/agent-chat-runtime.md`
5. `plans/structured-reasoning.md`
6. `plans/acceptance-checklist.md`
7. `plans/e2e-scenarios.md`
8. `specs/model-provider-reference-lessons.md`
9. `specs/claude-code-reference-notes.md`
10. `specs/agent-tools-from-claude-code.md`
11. `specs/agent-runtime-source-lessons.md`
12. `specs/rag-context-budget-lessons.md`
13. `specs/agent-capability-roadmap.md`
14. `../v1.0.1/README.md`
15. `../v1.0/design/agent-runtime.md`
16. `../v1.0/design/llm-gateway.md`
17. `../v1.0/design/wiki-search.md`
18. `../v1.0/design/frontend-workbench.md`
