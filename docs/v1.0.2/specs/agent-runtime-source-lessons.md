# Claude Code 源码深挖后的 CodeAsk Runtime 落地结论

> 日期：2026-05-07
> 状态：草稿，作为 v1.0.2 实施计划输入
> 范围：只提炼对 CodeAsk Agent Chat Runtime 有直接落地价值的源码模式

## 1. 本次深挖的边界

本次没有继续泛泛学习 Claude Code，而是带着 CodeAsk v1.0.2 的实现问题定向阅读：

- Agent loop 如何组织模型输出、工具调用、工具结果和下一轮模型输入。
- Tool contract 如何表达 schema、只读、并发、安全边界、用户交互和结果预算。
- Tool executor 如何把校验、权限、执行、错误、审计和 UI 事件串起来。
- 搜索 / 读取类工具如何控制结果大小和分页。
- `ask_user` 这类用户交互如何成为模型可调用工具，而不是后端固定兜底。
- skill / policy 如何按需加载，而不是常驻全部 prompt。

明确不纳入 v1.0.2 的部分：

- 自动代码编辑。
- Bash 任意执行。
- 多 agent / subagent。
- worktree 隔离。
- MCP 生态。
- TUI 权限交互细节。

## 2. 最重要的架构结论

Claude Code 的核心不是一条写死的阶段流，而是一个稳定的工具循环：

```text
模型输出自然语言或 tool_use
→ 后端执行 tool_use
→ tool_result 作为新的上下文消息回填
→ 模型继续基于 tool_result 回答或再次调用工具
```

这对 CodeAsk 的直接含义是：

- `ScopeDetection -> KnowledgeRetrieval -> SufficiencyJudgement -> CodeInvestigation` 不应该继续作为默认会话主链路。
- CodeAsk 需要新增独立的 `chat_runtime`，把旧状态机作为兼容能力保留。
- 默认会话入口应该进入工具化 loop，而不是进入阶段调度器。
- Wiki、报告、附件、代码读取都应该是模型可选工具，不是后端强制阶段。

## 3. Tool contract 必须成为稳定接口

Claude Code 里每个工具都具备相似的契约：工具名、schema、描述、可用性、只读、并发安全、权限检查、输入校验、结果映射、UI 渲染摘要和结果大小控制。

CodeAsk 不需要照搬 TypeScript 结构，但要保留这些边界：

```text
ToolSpec
ToolInput
ToolResult
ToolError
ToolContext
ToolExecutor
ToolRegistry
```

建议 Python 侧落地为：

```text
src/codeask/agent/chat_runtime/tool_contracts.py
src/codeask/agent/chat_runtime/tool_registry.py
src/codeask/agent/chat_runtime/tool_executor.py
src/codeask/agent/chat_runtime/tools/
```

默认值必须保守：

- 未声明 `read_only` 的工具，不能默认自由调用。
- 未声明 `concurrency_safe` 的工具，不能并发。
- 写操作默认需要确认。
- 需要用户交互的工具必须能暂停当前 turn。
- 工具错误必须返回结构化结果给模型，而不是直接让会话失败。

## 4. Tool executor 的顺序不能散落在业务工具里

Claude Code 的工具执行路径可以抽象成：

```text
找到工具
→ schema 校验
→ 工具自身输入校验
→ 权限 / 边界判断
→ 执行工具
→ 结果预算处理
→ 映射成 tool_result
→ 记录 telemetry / trace
→ 返回给模型继续推理
```

CodeAsk 应把这条顺序放进统一 `ToolExecutor`，具体工具只负责自己的业务查询或读取。这样可以避免每个工具重复处理：

- 参数错误。
- wiki node 不存在。
- session 附件越界。
- repo/ref 不明确。
- 文件路径逃逸。
- 结果过大。
- 失败事件如何给前端展示。

## 5. 工具结果是下一轮模型输入，不是 UI 文案

Claude Code 把工具结果映射成 model-facing 的 `tool_result`，UI 渲染则使用另一套摘要和进度信息。这一点很关键。

CodeAsk 也应该分三层：

| 层 | 内容 | 消费方 |
|---|---|---|
| model result | 摘要、关键片段、证据引用、警告、截断提示 | LLM |
| audit result | 完整输入、完整输出或原始结果引用、耗时、错误类型 | 后端审计 |
| trace event | 工具名、参数摘要、状态、证据、失败原因 | 前端行动轨迹 |

不能再让前端解析模型自然语言，也不能让模型看到为 UI 准备的冗余展示内容。

## 6. 搜索和读取工具要内建预算

Claude Code 的文件读取和 grep 工具都不是“读多少返回多少”：

- 读取工具支持 offset / limit。
- 搜索工具支持 limit / offset。
- 搜索默认有结果上限。
- 大文件或大结果会提示使用范围读取或分页。
- 搜索默认排除 `.git` 等版本控制目录。
- 搜索支持大小写不敏感。
- 读取同一文件同一范围时有去重思路，避免重复占用上下文。

CodeAsk 对应要求：

- `search_wiki` 默认只返回片段和 evidence refs。
- `read_wiki_node` 必须有 `max_chars` 和 heading 范围。
- `search_code` 必须有 limit / offset / path_glob / case_insensitive。
- `read_code_file` 必须有 start_line / line_count。
- `read_session_attachment` 必须只读摘要或片段，大日志不能全文注入。
- 所有大结果都要有 `truncated` 和 `raw_result_ref`。

## 7. `ask_user` 是工具，不是后端阶段

Claude Code 的用户提问工具本质是：模型认为需要用户选择时，调用工具，工具暂停并把用户回答作为 tool_result 返回。

CodeAsk 应这样翻译：

- 模型可以调用 `ask_user` 询问仓库、版本、特性归属、报告目标或关键环境信息。
- 一次只问一个最关键问题。
- 提供默认继续选项，例如“使用默认分支继续”。
- 用户回答后作为结构化结果进入下一轮模型输入。
- 前端渲染为轻量确认卡片或选择卡片。

这能解决旧链路里“后端判断无法继续就固定追问”的问题，让追问成为模型策略的一部分。

## 8. skill 应翻译成按需策略加载

Claude Code 的 skill 能被按需发现、加载、甚至修改当前工具权限和模型参数。CodeAsk v1.0.2 不需要 forked skill executor，但应该学习两个原则：

- 不把全部分析策略全文常驻 prompt。
- 策略是模型可读取的指导材料，不是固定流程。

CodeAsk 第一版应实现：

```text
load_analysis_policy(policy_id, scope)
```

默认上下文只列出启用策略的名称、范围和一句描述。模型需要时，再读取完整策略内容。

## 9. 上下文组装要有预算和压缩边界

Claude Code 在进入模型前会做工具结果预算、上下文压缩、历史裁剪、附件和记忆注入。CodeAsk 当前不需要完整复制，但必须在 v1.0.2 建立预算边界：

- 最近消息优先。
- 历史消息过长时生成摘要。
- Wiki / 报告召回只注入片段。
- 附件默认注入列表和摘要。
- 代码默认注入命中摘要和精确引用。
- 完整内容通过工具按需读取。

如果只说“把 RAG 和工具能力全部注入上下文”，实现会很快失控。

## 10. 并发能力先设计，不急着启用

Claude Code 会把连续的并发安全工具批量执行，但保守处理任何不确定工具。CodeAsk v1.0.2 可以先串行执行，降低实现风险，但契约必须保留：

```text
read_only
concurrency_safe
requires_confirmation
requires_user_interaction
```

后续只读工具稳定后，可以把连续的 `search_wiki`、`search_reports`、`search_code` 做并发优化。

## 11. 前端行动轨迹来自真实事件

Claude Code 的 UI 不是展示固定内部阶段，而是根据工具 use、progress、result、error 渲染。

CodeAsk 应把现有“调查进度 / 运行事件”改成“Agent 行动轨迹”：

- `retrieval_context`：本轮轻量召回。
- `tool_call`：模型实际调用工具。
- `tool_result`：工具结果摘要或失败。
- `evidence`：最终回答引用证据。
- `needs_clarification`：模型向用户澄清。
- `assistant_action`：建议生成报告或沉淀 Wiki。

UI 不再展示：

```text
范围判断
充分性判断
insufficient
下一步：code_investigation
matched feature alias
```

## 12. 对 CodeAsk 实施计划的直接约束

实施计划必须遵守以下约束：

1. 新增 `src/codeask/agent/chat_runtime/`，不要继续扩大 `orchestrator.py` 和 `agent/stages/`。
2. 先写 mock LLM 确定性测试，再接真实 LLM。
3. 先完成工具契约和执行器，再接具体 Wiki / 报告 / 附件 / 代码工具。
4. 只读工具先落地，写操作只做建议和确认，不静默执行。
5. 前端新增 `action-trace/` 组件，不继续扩写 `InvestigationPanel.tsx`。
6. 旧 SSE 事件暂时兼容，新 UI 默认消费新事件。
7. 所有工具结果必须能进入审计记录和行动轨迹。
8. v1.0.1 Wiki 工作台能力必须有回归测试保护。

## 13. 结论

Claude Code 对 CodeAsk 最有价值的不是某个具体工具实现，而是 harness 思路：

```text
稳定 agent loop
+ 明确 tool contract
+ 统一 tool executor
+ 保守边界
+ 结构化 tool result
+ 上下文预算
+ 真实行动轨迹
```

CodeAsk v1.0.2 应把这些原则翻译成面向研发知识问答和问题定位的工具化聊天运行时。
