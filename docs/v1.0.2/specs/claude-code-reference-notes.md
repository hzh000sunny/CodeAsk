# Claude Code 参考学习笔记

> 日期：2026-05-07
> 状态：Draft，等待用户审阅
> 范围：为 v1.0.2 Agent 会话运行时设计提供参考，不照搬实现

## 1. 资料范围

本次参考了 `references/claude-code/` 下两类资料：

- `claude-code/`：Claude Code 源码目录，用于理解生产级 harness 的模块边界、工具系统、上下文管理和事件处理方式。
- `learn-claude-code/`：第三方学习资料，用于理解 Claude Code 风格的 agent harness 设计原则。

参考资料只用于产品和架构学习。CodeAsk 不应复制 Claude Code 的具体实现、命名或内部代码，而应提炼适合自身垂直研发知识场景的设计模式。

## 2. 核心启发

### 2.1 Agent 产品的重点是 harness，不是后端决策树

学习资料中最关键的观点是：模型提供 agency，产品工程负责构建 harness。

对 CodeAsk 来说，这正好解释了当前 v1.0 Agent 的问题：后端固定链路试图替模型决定“先定界、再检索、再判断、再查代码”，这更像流程编排，不像正常 agent harness。

v1.0.2 应继续坚持：

```text
模型决定动作。
harness 提供上下文、工具、边界、记忆和审计。
```

### 2.2 Agent loop 应该稳定，能力通过工具扩展

学习资料的基础循环是：

```text
messages + tools → LLM → tool_use → execute tool → tool_result → messages
```

这个循环本身不应该随着能力增加而变复杂。新增能力应通过工具注册、工具 schema、工具结果处理和边界校验扩展，而不是在后端增加更多 if/else 阶段。

CodeAsk v1.0.2 应把默认运行时收敛为一个稳定的 `Agent Chat Runtime`：

- 每轮组装上下文。
- 模型选择是否调用工具。
- 后端执行工具和边界校验。
- 工具结果回到模型。
- 模型继续工具调用或自然回答。

### 2.3 工具是可组合能力，不是流程阶段

Claude Code 工具体系体现了几个生产级原则：

- 每个工具有独立 schema。
- 工具有只读 / 写入 / 需要用户交互等属性。
- 工具可以声明是否并发安全。
- 工具结果有大小上限。
- 工具错误会作为 tool result 返回给模型，而不是直接破坏整个会话。

CodeAsk 可以借鉴这些原则，把工具分成：

| 类型 | 示例 | v1.0.2 行为 |
|---|---|---|
| 只读知识工具 | `search_wiki`、`read_wiki_node`、`search_reports` | 默认可调用 |
| 只读会话工具 | `list_session_attachments`、`read_session_attachment` | 默认可调用 |
| 只读代码工具 | `search_code`、`read_code_file`、`inspect_repo_tree` | 默认可调用，但要解析 repo/ref/commit |
| 用户交互工具 | `ask_user` | 模型认为需要澄清时调用 |
| 写操作工具 | `generate_report`、`write_wiki`、`delete_wiki` | 必须用户确认或由明确 UI 动作触发 |

### 2.4 只读工具可以并发，写操作必须串行和确认

Claude Code 的工具编排会把连续的并发安全工具分批并发执行，非只读或不安全工具串行执行。

CodeAsk v1.0.2 可以先不做复杂并发，但应在工具契约里预留：

- `read_only`
- `concurrency_safe`
- `requires_confirmation`
- `requires_user_interaction`
- `max_result_size_chars`

这样后续可以自然支持：

- 并发读取多个 Wiki 文档。
- 并发搜索多个候选仓库。
- 写 Wiki、删数据、生成报告仍然串行和确认。

### 2.5 按需知识加载优于把所有规则塞进 system prompt

学习资料中的 skill loading 模型很适合 CodeAsk：

```text
系统提示中只列出可用知识/策略的名称和简述。
模型需要时再通过工具加载完整内容。
```

CodeAsk 当前有“分析策略 / Prompt 策略”，也有 Wiki 知识库。v1.0.2 不应该把所有分析策略、所有 Wiki 摘要都常驻塞进 prompt。建议改成两层：

- 常驻层：少量产品规则、可用策略列表、候选特性、轻量召回片段。
- 按需层：模型调用工具读取完整 Wiki、报告、附件、分析策略或代码。

这能降低上下文噪音，也更符合“模型决定动作”的方向。

### 2.6 上下文预算是运行时能力，不是后续优化

Claude Code 对上下文管理非常重视，包含工具结果预算、micro-compact、auto-compact、session memory 等机制。

CodeAsk v1.0.2 至少要在设计中落地三件事：

1. 工具结果必须截断和摘要。
2. 每轮轻量 RAG 只注入片段，不注入全文。
3. 长会话需要可恢复摘要，不能让历史消息和工具结果无限膨胀。

建议 v1.0.2 第一版实现：

- `tool_result` 统一最大字符数。
- Wiki/报告/代码工具结果返回摘要 + evidence refs。
- 会话历史超阈值时生成摘要消息。
- 完整原始工具结果和行动轨迹存储在审计数据中，而不是活跃上下文中。

### 2.7 计划和 Todo 是辅助状态，不是固定流程

Claude Code 风格的 Todo/Task 机制不是替模型做决策，而是帮助模型在多步任务里维持状态。

CodeAsk v1.0.2 不应把 Todo 作为所有问题的默认 UI。但可以借鉴为：

- 当用户明确要求“帮我定位根因”“做完整分析”“生成报告”时，模型可以生成轻量调查清单。
- 清单是行动轨迹的一部分，而不是后端状态机。
- 同一时间最多一个进行中的调查动作，避免 UI 上出现多个并行状态混乱。

这比固定的“范围判断 / 知识检索 / 代码调查”更自然。

### 2.8 Ask User 是工具，而不是后端兜底弹窗

Claude Code 的用户提问工具把“需要用户选择或补充”建模为工具调用。

CodeAsk v1.0.2 应借鉴这个边界：

- 模型判断需要澄清时调用 `ask_user` 或自然语言追问。
- 前端可以根据结构化 `needs_clarification` 或 `ask_user` 事件展示轻量确认 UI。
- 后端不应该自己在固定阶段里弹“请确认特性”，除非模型或用户动作触发了需要确认的流程。

这能解决“用户不知道特性却被要求绑定”的问题。

## 3. 对 CodeAsk v1.0.2 的具体补充

### 3.1 Runtime 模块边界

建议实施计划中把后端拆成以下模块：

```text
src/codeask/agent/chat_runtime/
├── runtime.py              # 主 agent loop
├── context_assembler.py    # 上下文组装
├── retrieval_context.py    # 轻量 Wiki/报告/特性召回
├── prompt_policy.py        # 产品规则和工具说明
├── tool_registry.py        # 工具注册和 schema
├── tool_executor.py        # 工具执行、错误处理、结果预算
├── tool_contracts.py       # read_only / concurrency_safe / confirmation 等契约
├── trace_recorder.py       # 行动轨迹和证据记录
└── compaction.py           # 会话摘要和工具结果压缩
```

这能避免继续把 Agent 逻辑堆在旧状态机文件里。

### 3.2 工具契约字段

建议每个工具至少定义：

```text
name
description
input_schema
read_only
concurrency_safe
requires_confirmation
requires_user_interaction
max_result_size_chars
result_renderer
error_mapper
```

这不是为了追求抽象，而是为了让前端行动轨迹、后端执行边界和测试可以稳定依赖工具元数据。

### 3.3 工具错误模型

建议统一错误类型：

```text
invalid_input
not_found
out_of_scope
permission_denied
needs_clarification
version_unknown
too_large
transient_error
internal_error
```

工具错误应回到模型上下文，让模型决定追问还是给出有限结论。

### 3.4 行动轨迹的粒度

Claude Code 的 TUI 会展示工具调用和结果摘要。CodeAsk 前端也应以“行动事实”为粒度：

- `retrieval_context`：本轮轻量召回了什么。
- `tool_call`：模型调用了哪个工具、参数摘要是什么。
- `tool_result`：工具返回了什么摘要、是否截断、是否有警告。
- `evidence`：最终回答引用了哪些证据。
- `needs_clarification`：模型需要用户补充什么。

行动轨迹不应展示“后端判断下一步”，也不应展示空阶段。

### 3.5 会话记忆和压缩

CodeAsk v1.0.2 第一版不需要完整实现 Claude Code 级别的 session memory，但必须有基础策略：

- 每个会话维护 `conversation_summary`。
- 工具结果超过阈值只保留摘要进入活跃上下文。
- 原始工具结果进入审计存储，可在 UI 中展开查看。
- 当历史消息超过阈值时，生成摘要并替换旧历史进入模型上下文。

这对“用户和 AI 在不停沟通中逐步完善背景”非常关键。

## 4. 不建议 v1.0.2 直接借鉴的内容

以下能力在 Claude Code 中很有价值，但不适合作为 CodeAsk v1.0.2 的第一优先级：

| 能力 | 不纳入原因 |
|---|---|
| 多 agent 团队协作 | 当前核心问题是默认会话运行时错误，先修主循环 |
| worktree 隔离执行 | CodeAsk 当前是只读代码调查，不做代码修改 |
| 后台长任务 | 可以后续用于长时间索引/测试，但 v1.0.2 先保证同步工具链路稳定 |
| MCP 完整生态 | 当前先做好内置 Wiki/报告/附件/代码工具 |
| 自动记忆整理 | 需要更成熟的数据治理，先做会话摘要和工具结果预算 |
| 计划模式显式切换 | 用户不应该理解模式差异，v1.0.2 以自然聊天为主 |

## 5. 需要回补到 v1.0.2 主设计的点

`specs/agent-chat-runtime.md` 已经覆盖大方向，但结合 Claude Code 学习后建议进一步强化：

1. 明确 CodeAsk 是研发知识 agent harness，不是后端流程编排器。
2. 在工具模型中加入 `read_only`、`concurrency_safe`、`requires_confirmation`、`max_result_size_chars` 等字段。
3. 在上下文预算中明确“工具结果摘要进入上下文，原始结果进入审计存储”。
4. 在行动轨迹中明确 tool call / tool result / evidence / clarification 的最小事件粒度。
5. 在实施计划中优先做 mock LLM 的 agent loop 测试，再接真实 LLM。
6. 把旧状态机迁移为历史设计，不继续在其上打补丁。

## 6. 结论

Claude Code 对 CodeAsk v1.0.2 最大的启发是：不要把 Agent 做成后端规则流水线。真正应该建设的是一个领域 harness：

```text
工具清晰
上下文干净
知识按需
边界可靠
行动可审计
模型做决定
```

CodeAsk 的差异在于，它不是通用 coding agent，而是研发知识工作台。因此 v1.0.2 不需要复制 Claude Code 的全部能力，而应把这些 harness 原则落到 Wiki、报告、附件、特性和代码只读调查这条产品主线上。

