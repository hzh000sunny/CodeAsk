# v1.0.2 Agent Chat Runtime 系统设计

> 状态：Completed
> 版本：v1.0.2
> 范围：后端 ChatRuntime、工具契约、SSE 事件、前端 Action Trace
>
> 会话生成问题定位报告的跨版本稳定规则见 `../../rules/problem-report.md`。

## 1. 总体架构

v1.0.2 新增独立模块：

```text
src/codeask/agent/chat_runtime/
├── context.py
├── events.py
├── prompt.py
├── retrieval.py
├── runtime.py
├── tool_contracts.py
├── tool_executor.py
├── tool_registry.py
└── tools/
```

旧模块保留：

```text
src/codeask/agent/stages/
src/codeask/agent/orchestrator.py
```

默认 `/api/sessions/{session_id}/messages` 已切换到 `ChatRuntime`。旧 `AgentOrchestrator` 作为 legacy 兼容保留，便于旧测试、评估和后续迁移参考。

## 2. ChatRuntime 职责

`ChatRuntime` 负责一轮 assistant turn 的执行：

1. 读取用户输入。
2. 加载当前会话最近 turns、上一轮关键工具行动摘要和当前会话附件摘要。
3. 调用召回服务生成 `retrieval_context`，包含特性目录、特性知识索引、候选特性、Wiki、报告、会话附件候选和代码仓库候选。
4. 组装 system prompt、recent history、tool action summary、Feature RAG Pack、会话附件候选和 current user message。
5. 把可用工具定义传给 LLM。
6. 流式转发 `text_delta`。
7. 收集模型工具调用。
8. 调用 `ToolExecutor` 执行工具。
9. 把工具结果作为 tool message 追加回模型上下文。
10. 循环直到模型停止调用工具或达到最大轮数。
11. 如果模型反复调用工具达到上限，关闭工具后再要求模型基于已有工具结果直接回答，避免把内部 `MAX_TOOL_ROUNDS` 暴露给用户。
12. 输出 `done` 或 `error`。

`ChatRuntime` 不负责判断：

- 问题属于哪个特性。
- Wiki 是否足够回答。
- 是否必须查代码。
- 是否应该生成报告。

这些判断都交给模型。

当用户在会话中触发“生成报告”时，runtime 需要把它视为独立的成文任务，而不是会话内容回填任务。生成目标必须遵守 `../../rules/problem-report.md`：

- 报告不是聊天记录副本。
- 标题必须为 `YYYY-MM-DD 问题描述`，日期取生成当天。
- `问题描述` 默认由 AI 生成，但允许用户修改。
- 正文结构给模型参考，不固定章节名。
- 证据不足时允许生成草稿，但必须明确未确认项和待补充项。
- 报告写作要求、会话关键上下文、行动轨迹摘要和已确认证据必须一起传给 AI，由 AI 自主生成标题和正文，而不是后端模板拼接。
- 同一会话只能绑定一篇来源于会话的报告；再次生成时更新原报告，不重复新增。
- 报告生成弹窗应默认选中当前会话最相关的特性；存在交叉特性时默认选最高相关项，只有确实无法判断时才让用户手动选择。
- 会话删除时不删除已生成报告，报告仅解除活跃会话绑定并保留来源追溯信息。

基础通用问答同样遵循模型决策原则。系统提示词只表达产品策略：通用编程、Linux、算法、网络、数据库、操作系统、AI、系统设计、逻辑推理和自我认知问题优先直接回答；除非用户明确要求查看项目 Wiki、附件、报告或源码，或者当前问题必须依赖项目上下文，否则不要把基础问答扩展成检索任务。运行时代码不做关键字拦截，也不把这些题型硬编码为禁止工具调用。

## 2.1 连续会话上下文装配

连续会话是 v1.0.2 的基础能力，不是上下文压缩之后才做的高级能力。每一轮模型调用前，runtime 必须从持久化数据中恢复必要上下文：

```text
session_turns 最近 N 条
+ conversation_summary（如果历史已被压缩）
+ 上一轮关键 agent_traces 摘要
+ 当前 session 附件候选
+ retrieval_context 候选证据
+ current user message
→ LLM messages
```

装配规则：

- `SessionTurn.role == "user"` 转成 LLM `user`。
- `SessionTurn.role == "agent"` 转成 LLM `assistant`。
- 当较早历史超过最近窗口时，`session_conversation_summaries` 会保存 extractive 长期摘要；摘要覆盖的 turn 不再作为 recent history 注入，避免重复。
- 当前 turn 的 user message 只作为当前输入出现一次，不能在 history 中重复注入。
- 工具行动摘要只保留工具名、参数摘要、成功失败、summary、warnings、evidence refs 和“是否读取源码文件”等语义字段。
- Feature RAG Pack 位于当前用户问题之前，只包含候选摘要、snippet、轻量知识索引和引用元数据，不注入 Wiki / 报告全文。
- 每轮必须向模型注入 `feature_catalog`。它是当前系统可识别的活跃特性目录，包含 feature id、名称、描述、摘要和关联仓库摘要。后端不能只在命中特性时才提供目录，否则模型无法自行判断用户问题属于哪个特性。
- 每轮必须向模型注入 `feature_knowledge_index`。它是每个特性的轻量知识地图，来自 Wiki 标题、Wiki 路径、问题报告标题和少量关键词。即使用户问题没有命中特性名称，只要命中某个特性的 Wiki 内容，模型也应该看到这个特性可能相关。
- 特性目录和 Wiki / 报告命中需要按当前问题的相关性排序：直接命中特性名称、描述或当前问题证据的特性排在前面，其它活跃特性继续保留在候选目录中。排序只能表达召回相关性，不能在后端替模型生成结论。
- Wiki 候选上下文必须包含可执行引用：`node_id`、`document_id`、标题、路径、heading 和 snippet。模型读取 Wiki 时只能使用候选上下文或 `search_wiki` 工具结果中明确返回的 `node_id`，不能根据列表顺序、标题或路径猜测节点 id。
- 当前 session 的附件候选会进入 Feature RAG Pack，包含 attachment id、显示名、原文件名、别名、描述、类型和大小；模型可据此决定是否调用 `read_session_attachment`，但附件全文不会默认注入。
- 全局 ready 代码仓库的轻量候选会进入 Feature RAG Pack，包含 repo id、名称、来源、状态和已关联特性 id。用户点名某个仓库时，模型应先基于这些候选判断是否设置 `explicit_repo_scope=true`，而不是依赖后端固定关键词规则。
- Feature RAG Pack 会明确提示模型：调用代码工具时默认把判断相关的 `feature_id` 填入 `feature_ids`；只有用户明确要求查询某个仓库时，才设置 `explicit_repo_scope=true`。
- 完整 trace JSON 不进入模型上下文，只留在审计和 UI 展示层。
- 前端能显示历史、数据库有 turns、右侧能显示行动轨迹，都不能替代模型上下文装配验收。

v1.0.2 已落地第一版会话级 auto compact：

- 新增 `session_conversation_summaries` 持久化表。
- 当历史 turns 数量超过最近窗口时，较早 turns 会被 extractive 摘要覆盖，最近 turns 继续原文进入上下文。
- 摘要记录 `covered_turn_index`、`covered_turn_count`、`covered_trace_count`，并保留较早工具行动摘要。
- 删除会话时摘要随 session cascade 清理。
- 当前版本暂未实现 LLM 生成式结构化摘要、精确 trace id 范围和连续失败熔断，这些保留在后续 v1.0.2 收尾任务中。

曾暴露的缺陷：

```text
用户第一轮：anything llm中，是怎么通过rag处理上传的资料的
用户第二轮：你刚刚的回答，有查询代码吗
模型错误回答：这是我们第一次交流
```

根因是 runtime 第二轮没有正确带入上一轮 user / assistant / tool action summary。当前后端链路已修复：API 层会加载最近 turns 和上一轮工具行动摘要，runtime 会把它们注入 LLM messages。该修复已有 API + spy LLM 测试覆盖，但浏览器 / live E2E 仍需补齐。

最低测试要求：

- API + spy LLM 测试断言第二轮 `messages` 包含上一轮 user 和 assistant。
- API + spy LLM 测试断言第二轮 `messages` 包含上一轮工具行动摘要。
- API + spy LLM 测试断言当前 session 附件候选进入实际 `messages`，并保留重命名后的显示名、原文件名和用户描述。
- API 集成测试覆盖 `session_turns` / `agent_traces` 到 runtime messages 的转换链路。
- 浏览器 E2E 覆盖同一会话追问上一轮是否查过代码。

## 3. LLM 适配

运行时定义 `StreamingLLM` 协议：

```text
stream(messages, tools, max_tokens, temperature) -> AsyncIterator[LLMEvent]
```

生产环境通过 `GatewayStreamingLLM` 适配现有 `LLMGateway`，并将 `subject_id`、`session_id` 放入 request metadata，使 LLM 配置选择遵循当前管理员 / 用户配置规则和会话级负载均衡规则。

LLM Gateway 的生产调用统一走 LiteLLM。`protocol` 只表达消息接口协议，不表达 provider 或传输实现；页面和数据库中的 `model_name` 保持用户配置值，例如 `GLM-5.1`，网关在调用 LiteLLM 时按协议内部补 provider hint，例如 `openai/GLM-5.1`。

测试环境可以注入脚本化 LLM，验证工具循环、SSE 事件和消息持久化。

### 3.1 LLM 配置选择与基础负载均衡

v1.0.2 增加第一版进程内全局 LLM 配置池选择策略：

- 如果请求显式指定 `config_id`，网关按指定配置调用，不参与随机池选择。
- 如果请求显式指定的配置不可用，网关直接返回明确错误，不自动替换成其它配置。
- 如果当前 `subject_id` 存在启用的用户 LLM 配置，优先使用用户自己的配置；用户配置不占用全局配置池槽位，也不参与全局失败冷却。
- 如果用户个人 LLM 配置失败，网关不自动 fallback 到全局配置，除非后续产品明确提供用户可控的 fallback 开关。
- 如果用户没有启用的个人配置，网关从启用的全局 LLM 配置池中选择。
- 每个全局配置在最近 60 秒内最多服务 3 个不同 `session_id`。
- 同一 `session_id` 在 60 秒窗口内多次调用同一全局配置，只计为 1 个会话。
- 可用全局配置不止一个时，在未满载且未冷却的配置中随机选择。
- 全局池全部满载或被临时剔除时，网关返回 `当前资源繁忙，请稍后再试`，不偷偷突破限制。

为了避免同一会话在短时间内频繁切换模型，网关保留 5 分钟会话粘性：

- 同一 `session_id` 在 5 分钟内再次请求时，优先继续使用上次选中的全局配置。
- 即使该配置后来被其他会话占满，只要它仍启用且未处于失败冷却状态，该会话仍继续使用原配置。
- 如果该会话上次使用的全局配置已被删除、禁用或进入失败冷却，网关直接回到全局池选择下一个可用配置，不在无效配置上反复重试。
- 如果前后请求间隔超过 5 分钟，视为模型侧缓存大概率失效，可以重新进入全局池选择。

为了避免坏配置反复拖垮会话，网关还维护第一版失败冷却：

- 同一全局配置 5 分钟内出现 3 次最终失败后，临时从全局池剔除。
- 冷却时间为 10 分钟；冷却结束后自动回到候选池。
- 成功完成一次调用会清除该配置的失败记录。
- 如果某个全局配置在一次请求的初始阶段失败，且还没有输出任何模型内容，网关会在本次请求内立即排除该配置并切换到下一个可用全局配置；如果模型已经开始输出，则不跨模型续流，直接返回当前错误。
- 非供应商健康类错误不计入失败冷却，例如上下文超限、`max_tokens` 非法、工具 schema 或请求格式错误；这类错误直接返回给上层处理，不触发配置切换或剔除。
- 单次请求最多尝试 `max_retries + 1` 次模型调用，包含跨配置切换和同配置重试，避免一个请求扫完整个资源池造成放大流量。
- 如果本次请求内所有可用全局配置都在初始阶段失败，网关返回最后一次模型错误；如果没有任何候选配置可尝试，则返回 `当前资源繁忙，请稍后再试`。

这套状态第一版只存放在后端进程内存中。服务重启后清空；多进程部署时各进程独立统计。后续如果需要跨进程精确限流，应替换为 Redis / 数据库 / 专用调度服务。

### 3.2 会话标题自动生成

新建会话在用户未指定名称时使用默认标题 `新的研发会话`，但第一轮完整问答结束后，后端会用独立 LLM 请求生成一个更可读的会话标题。

标题生成不是正常 Agent 对话的一部分：

- 标题生成 prompt 不进入 `session_turns`。
- 标题生成 prompt 不进入下一轮 ChatRuntime history。
- 标题生成不写入用户可见行动轨迹。
- 标题生成失败不影响本轮回答和消息持久化。

数据模型通过 `sessions.title_source` 区分标题来源：

| 值 | 含义 |
|---|---|
| `default` | 系统默认标题，允许第一轮结束后自动生成 |
| `auto` | AI 基于第一轮用户 / 助手内容生成 |
| `manual` | 用户手动命名或历史迁移标题，后端不得自动覆盖 |

触发规则：

- 只有 `title_source = default` 且会话中刚好存在第一轮 `user + agent` 两条 turn 时才触发。
- 标题请求只接收第一轮用户提问和助手回答，不带工具完整 trace，不带完整历史，不带报告生成上下文。
- 生成结果会做基础清洗：去掉 Markdown 代码块、引号、`标题：` 前缀、多余换行和多余空白，并限制最大长度。
- 写回前再次检查 `title_source = default`，避免用户在模型返回前手动改名后被覆盖。
- 后端提供 `POST /api/sessions/{session_id}/title/generate`，用于前端在第一轮会话流结束后显式触发标题生成。该接口只读取已持久化的第一轮 user / assistant turn，返回最新 `SessionResponse`；如果标题已经是 `auto` / `manual`，或还不足一轮完整问答，则直接返回当前会话，不影响正常对话。
- 前端发送消息完成后会调用上述接口，收到 `SessionResponse` 后直接合并进会话列表缓存，实现列表标题动态渲染；同时仍立即刷新会话列表，并在短时间内补充几次延迟刷新，作为后台标题任务稍晚写回或接口失败时的兜底。会话列表标题单行显示，超出部分使用省略号。

## 4. 工具契约

工具由三部分组成：

| 组件 | 作用 |
|---|---|
| `ToolSpec` | 工具给模型看的能力说明和 schema |
| `ToolContext` | 当前 session、turn、subject、显式约束 |
| `ToolResult` | 工具执行后的结构化结果 |

工具默认 fail-closed：

```text
read_only = false
concurrency_safe = false
requires_confirmation = true
requires_user_interaction = false
```

只有明确声明为只读且不需要确认的工具，才能默认暴露给模型自由调用。

## 5. 工具执行器

`ToolExecutor` 的职责：

- 根据工具名查找 `ToolRegistry`。
- 使用 Pydantic input model 校验参数。
- 阻止未确认的确认型工具。
- 捕获工具错误并转为结构化 `ToolResult.error`。
- 保证模型拿到可继续处理的错误类型。
- 对进入模型上下文的 `ToolResult` 执行真实结果预算裁剪，不能只设置 `truncated=true`。

典型错误类型：

```text
invalid_input
not_found
out_of_scope
permission_denied
needs_feature_scope
needs_clarification
version_unknown
too_large
transient_error
internal_error
```

工具结果预算是 v1.0.2 的硬性边界。工具可以在审计存储中保留完整原始结果，但进入下一轮 LLM 的 `tool_result` 必须受 `ToolSpec.max_result_size_chars` 限制。超预算时优先保留 `summary`、`warnings`、`evidence_refs`、`version_info` 等模型决策所需字段，并压缩或删除 `items` 中的大字段。

这条边界来自当前真实问题：源码参考问题触发工具调用后，未裁剪的工具结果曾导致 LLM 请求输入达到 1221299 字符，超过 GLM-5.1 的 202752 输入上限。v1.0.2 已补齐 `ToolExecutor` 层的真实裁剪，后续还需要补 `raw_result_ref` 审计回查。

### 5.1 工具优化安全边界

工具优化的目标是让工具更稳定、更透明、更可执行、更可审计，而不是让工具替模型做业务判断。CodeAsk 的产品原则仍然是：模型基于用户问题、会话历史、RAG 候选和工具结果决定下一步动作；工具层只负责执行、校验、范围控制、结果治理和错误表达。

明确禁止的优化：

- 工具层不得做业务语义映射，例如把 `电子宠物` 自动改写成 `buddy`，把 `sqlite` 自动映射到 `schema.prisma`，把 `RAG` 自动映射到 `contextTexts` 或某个固定源码文件。
- 工具层不得按题型硬拦截工具调用，例如“基础问题禁止查 Wiki”“医疗问题禁止查代码”“SQLite 问题必须查源码”。
- 工具层不得返回后端流程结论，例如“知识足够”“无需查代码”“应该读取某个文件”。这些判断只能由模型在上下文中完成。
- 工具层不得为了减少 UI 噪音吞掉失败；失败可以折叠展示，但必须可追溯到原始 trace、参数、错误类型和恢复建议。
- 工具层不得过度压缩结果到只剩 summary；预算裁剪必须保留 `node_id`、`document_id`、`repo_id`、`path`、`line`、`snippet`、`warnings`、`error_type`、`version_info` 等模型继续推理所需字段。

允许并鼓励的优化：

- 完善可执行引用：Wiki 候选必须提供 `node_id` / `document_id` / `heading_path`，代码候选必须提供 `repo_id` / `path` / `line` / `commit`。
- 做通用检索增强：大小写不敏感、空格 / 连字符归一、中英文长查询拆词 fallback、结果去重、分页、预算裁剪。
- 做输入和权限校验：空 query、过宽通配符、非法路径、越权仓库、未确认写操作都必须 fail closed。
- 做错误可解释化：把 `internal_error` 继续细分为 `invalid_glob`、`path_not_found`、`grep_timeout`、`too_many_matches`、`out_of_scope` 等可恢复错误，并给出 recovery hint。
- 做工具调用预算和恢复提示：连续 0 命中后提示模型先用目录树或路径列表确认命名；已有足够证据时提示模型停止调用工具并回答。
- 做 UI 折叠但不隐藏：行动轨迹可以把多次搜索折叠成“搜索尝试组”，展开后仍能看到全部原始事件和失败。

每次工具优化必须同时补两类测试：

- 正向测试：证明工具更容易返回真实候选、错误更可解释、预算更稳定。
- 反向测试：证明工具没有偷偷做业务特判，例如不能把特定自然语言样例直接映射到固定路径或固定证据。

## 6. 第一批工具模块

v1.0.2 已建立以下工具模块和单元测试：

| 模块 | 工具 |
|---|---|
| `tools/wiki.py` | `search_wiki`, `read_wiki_node` |
| `tools/reports.py` | `search_reports`, `read_report` |
| `tools/attachments.py` | `list_session_attachments`, `read_session_attachment` |
| `tools/code.py` | `inspect_repo_tree`, `search_code`, `read_code_file`, `resolve_code_scope` |
| `tools/live_code.py` | 生产可用的 `list_code_repos`, `search_code`, `inspect_repo_tree`, `list_code_paths`, `read_code_file` |
| `tools/user_interaction.py` | `ask_user` |
| `tools/policies.py` | `load_analysis_policy` |
| `tools/report_actions.py` | `propose_report` |

当前生产 `ChatToolRegistry` 已接入只读代码工具：

- `list_code_repos`：只列当前特性范围内仓库或用户显式指定仓库，不再暴露完整全局 ready 仓库池。
- `search_code`：基于模型选择的候选特性解析允许仓库，使用 session-scoped worktree 和 ripgrep 检索；支持 `literal`、`regex`、`any_terms`、`all_terms` 通用搜索模式。
- `inspect_repo_tree`：读取允许仓库内的目录树，帮助模型在搜索词不确定时先确认代码结构。
- `list_code_paths`：按路径名列出允许仓库中的文件和目录，用于模型在搜索词不确定时做通用导航；工具层不补业务同义词，也不做自然语言语义映射。
- `read_code_file`：只读取当前候选特性关联仓库内的文件片段。

代码检索的产品边界是 **Feature-Scoped Code Access**：模型负责根据足够的特性 RAG 信息选择一个或多个相关特性，后端默认只开放这些特性关联仓库的并集。用户明确要求通过某个仓库查询时，该仓库可作为本轮显式代码范围，即使它没有关联特性。全局仓库池只用于管理员配置、特性关联和显式仓库解析，不作为默认 Agent 模糊检索范围。详细规则见 `../specs/feature-scoped-code-access.md`。

为了让模型能自己判断特性，每轮上下文必须提供轻量 Feature RAG Pack：特性目录、特性知识索引、特性名、别名、描述、Wiki / 报告候选摘要、会话附件线索、关联仓库摘要和版本提示。后端不能只返回空 feature id，也不能用全局仓库名称匹配替代特性判断。

代码工具默认读取仓库 `HEAD` 时会在工具结果中返回版本不确定提醒。后续还需要把真实 Wiki、报告、附件等服务继续接入默认 app registry。

第一版已落地：

- `DatabaseRetrievalService` 接入生产 app，替代空的 `LightweightRetrievalService`。
- `ChatRuntime` 已把 Feature RAG Pack 注入实际 LLM messages，并有 spy LLM 测试覆盖。
- `DatabaseRetrievalService` 已补齐 `feature_catalog` 和 `feature_knowledge_index`：模型每轮都能看到活跃特性目录和由 Wiki / 报告构建的轻量知识地图。
- 当前内置 RAG 只是临时实现，外部 RAG 服务引入后应替换 `RetrievalService.retrieve(...)` 的实现，保持 `retrieval_context` 输出结构稳定。
- 真实 Wiki 只读工具已接入生产 `ChatToolRegistry`，支持 `search_wiki` 和 `read_wiki_node`。
- `search_wiki` 已补齐长查询降级检索：完整查询 0 命中时，会按通用词项拆分重试并去重，避免中英文混合长短语导致模型连续收到 0 命中后反复搜索。
- 真实问题报告只读工具已接入生产 `ChatToolRegistry`，支持 `search_reports` 和 `read_report`。
- 真实会话附件只读工具已接入生产 `ChatToolRegistry`，支持 `list_session_attachments` 和 `read_session_attachment`，并按当前 session 隔离。
- 当前 session 附件候选已接入 `DatabaseRetrievalService` 和 `/api/sessions/{session_id}/messages`，会在模型上下文中提供轻量索引，不需要模型先盲猜附件 id。
- `DatabaseRetrievalService` 已对底层 Wiki / 报告命中做基础来源去重：优先按 `document_id` / `report_id` 合并，缺失稳定 id 时才按 `kind + node_id` 回退，避免同一来源以多个片段重复塞入模型上下文。
- `tools/live_code.py` 已支持 `feature_ids` 和 `explicit_repo_scope`。
- 代码工具结果的 `version_info.scope_source` 会随 `tool_result` SSE 事件透传。
- 超预算工具结果会生成 `raw_tool_result:*` 引用；模型只收到预算后的结果，完整原始结果写入隐藏的 `tool_result_raw` 审计 trace，不进入 SSE 可见列表。
- 已有集成测试覆盖无范围拒绝、显式仓库允许、特性关联允许和范围外拒绝。

## 7. SSE 事件

默认会话 SSE 支持：

```text
retrieval_context
text_delta
tool_call
tool_result
evidence
assistant_action
needs_clarification
done
error
```

legacy SSE 事件仍保留类型兼容：

```text
stage_transition
wiki_scope_resolution
scope_detection
sufficiency_judgement
ask_user
```

前端默认面板不再把 legacy stage 当作固定流程渲染。

新版 runtime 的 `retrieval_context`、`tool_call`、`tool_result`、`needs_clarification`、`assistant_action`、`error` 会同步写入 `agent_traces`。刷新页面或切换会话后，前端通过 `/api/sessions/{session_id}/traces` 恢复行动轨迹，不依赖仅存在于流式过程中的临时状态。

## 8. 前端 Action Trace

前端新增：

```text
frontend/src/components/session/action-trace/
├── ActionTracePanel.tsx
├── ActionTraceEvent.tsx
├── ClarificationEvent.tsx
├── EvidenceEvent.tsx
├── RetrievalEvent.tsx
├── ToolCallEvent.tsx
├── ToolResultEvent.tsx
└── action-trace-model.ts
```

设计原则：

- `action-trace-model.ts` 负责把 SSE 转成可渲染事件。
- 组件只负责展示，按事件类型拆分。
- 右侧面板标题为 `Agent 行动轨迹`。
- 事件详情用悬浮弹窗，避免面板被长 JSON 撑开。
- 工具结果显示成功、失败和证据，不直接展示原始 JSON。
- 代码工具结果会展示范围来源、特性 id、仓库、ref 和 commit，让用户能区分 `feature_scope` 与 `explicit_user_repo`。
- 附件区域保留在同一右侧面板中。
- `Agent 行动轨迹` 是会话级时间线，不是单轮进度条。同一会话发送新消息时不得清空历史轨迹；新事件应追加到当前 turn 分组。
- 行动轨迹按 turn 分组，最近 turn 默认展开，历史 turn 可折叠。
- 卡片默认简洁，点击后展示完整诊断信息，包括参数摘要、summary、warnings、evidence refs、repo/ref/commit/path/line、truncated、raw_result_ref、error_type 和 error message。
- 长字段在详情中支持就地复制，复制成功或失败都在入口旁给出轻量反馈，不把提示挤到页面头部。
- 详情内容使用抽屉、弹窗或固定高度滚动区域，不能用长 JSON 撑开右侧面板。
- 输入框快捷键：`Enter` 发送，`Ctrl + Enter` 和 `Shift + Enter` 换行；中文输入 composition 期间不能误发送。

## 8.1 生成中断与回滚

会话生成过程中必须支持用户主动中断。中断不是简单停止前端流式显示，而是要回滚本轮已产生的持久化副作用。

当前实现：

- 前端发送消息前生成 `client_turn_id`，随 `POST /api/sessions/{session_id}/messages` 提交；后端优先使用该 id 创建本轮 user turn，并通过 `X-CodeAsk-Turn-Id` 和 SSE `turn_id` 回传。
- 前端通过 `AbortController` 中断当前 `/api/sessions/{session_id}/messages` SSE。
- 前端立即回滚本轮本地 user message、partial assistant message 和本轮临时行动轨迹。
- 后端在 StreamingResponse 收到 `asyncio.CancelledError` 时，删除本次 user turn 和本次 turn 产生的 `agent_traces`。
- 前端停止时会调用 `POST /api/sessions/{session_id}/turns/{turn_id}/abort` 做显式持久化回滚；即使用户在 header 或第一条 SSE 事件返回前停止，也能使用前端预生成的 `client_turn_id` 删除本轮 user turn 和行动轨迹。
- assistant turn 持久化前必须检查父 user turn 仍然存在；如果 abort 已删除父 user turn，迟到完成的 assistant 内容不得写入 `session_turns`。
- trace 持久化前也必须检查父 user turn 仍然存在；如果 abort 已删除父 user turn，后续迟到 trace 不得重新污染行动轨迹。
- assistant turn 仅在收到 `done` 且有完整内容后持久化，因此中断时不会留下 partial assistant turn。

已实现的回滚接口：

```text
POST /api/sessions/{session_id}/messages
→ 请求体包含 client_turn_id
→ 返回 X-CodeAsk-Turn-Id

POST /api/sessions/{session_id}/turns/{turn_id}/abort
→ 回滚该 turn 的持久化副作用
```

后续如需要跨设备中断、后台任务管理或多连接恢复，再扩展为可取消后台运行任务的 abort API。

回滚范围：

```text
删除本次 user turn
删除本次 partial assistant turn
删除本次 turn 产生的 agent_traces
删除或标记本次未完成 tool result
保留本次发送前历史 turns / traces / attachments
```

中断后前端应恢复到本轮发送前状态：聊天消息不保留半条回答，行动轨迹不保留本轮半截事件，输入框恢复可输入，并显示中断完成或失败提示。

曾暴露的缺陷：

```text
用户：换一种
生成过程中点击停止
UI 看起来已回滚
下一轮问：我刚刚让你介绍了几种宠物
模型仍感知到“换一种”
```

根因是后端运行流可能在 abort 删除 user turn 后迟到完成，并把 assistant turn 作为新的 `turn_xxx` 写入历史；同时迟到 trace 也可能继续进入行动轨迹。修复要求是：所有迟到写入都必须以父 user turn 仍存在为前置条件，父 turn 不存在时直接丢弃，不进入模型上下文、聊天历史或行动轨迹。

## 9. RAG 与上下文预算

v1.0.2 的 RAG 优化参考 AnythingLLM 的资料处理链路，但只保留适合 CodeAsk 的部分：

```text
上传 / Wiki / 报告 / 附件 / 代码
→ 标准化 EvidenceDocument
→ Markdown / 日志 / 代码感知切分
→ EvidenceChunk + metadata
→ feature / session / repo namespace
→ 相似度召回 + 可选 rerank
→ retrieval_context 候选证据
→ 模型决定回答、追问或调用工具
```

`retrieval_context` 只提供候选证据，不给出后端流程结论。每个 hit 只允许包含标题、路径、来源类型、片段、分数、证据引用和截断状态，不注入全文。

当前 `retrieval_context` 的稳定输出结构如下，后续外部 RAG 服务必须兼容这个边界：

```json
{
  "feature_catalog": [],
  "feature_knowledge_index": [],
  "feature_candidates": [],
  "wiki_hits": [],
  "report_hits": [],
  "attachment_candidates": [],
  "repo_candidates": []
}
```

字段职责：

- `feature_catalog`：活跃特性目录，必须每轮提供，帮助模型理解可选业务范围。
- `feature_knowledge_index`：每个特性的轻量 Wiki / 报告知识地图，包含标题、路径和关键词，不包含全文。
- `feature_candidates`：与当前问题直接命中的候选特性。
- `wiki_hits` / `report_hits`：当前问题直接召回的证据片段。
- `attachment_candidates`：当前会话附件索引。
- `repo_candidates`：可供模型识别显式仓库范围的 ready 仓库候选。

这层结构是外部 RAG 服务的替换入口。CodeAsk 后端 runtime 只消费该结构并注入模型上下文，不在工具层做业务语义判断。

长会话上下文预算参考 Claude Code 的分层压缩思路：

1. **工具结果预算**：单个 tool result 进入模型前必须被裁剪到预算内。
2. **轮次级 micro-compact**：每次调用模型前先估算 active context，只有超过阈值才把旧工具结果转摘要，只保留最近 N 个关键原文片段。
3. **Reactive compact**：如果供应商仍返回 `input length` / `prompt too long` / `context length` 类错误，运行时使用更严格的工具结果保留策略强制压缩一次并重试；重试仍失败才把错误返回前端。
4. **会话级 auto-compact**：历史超过阈值后生成 `conversation_summary`，保留当前任务、已确认事实、证据、附件、仓库/版本和未解决问题。
5. **审计保留**：完整 turns、traces、attachments 和原始工具结果不删除，只是不全部进入活跃上下文。

v1.0.2 已新增 `src/codeask/agent/chat_runtime/compaction.py`。它参考 Claude Code 的阈值模型，而不是随意写固定数字：

| CodeAsk 参数 | Claude Code 对应思路 | 当前说明 |
|---|---|---|
| `context_window_chars` | model context window | 默认 `200000`，表示 CodeAsk 运行时估算的模型总上下文窗口，不等同于 LLM API 的 `max_tokens` |
| `auto_compact_threshold_ratio` | auto compact trigger ratio | 默认 `0.85`；达到约 `170000` 字符时触发自动压缩 |
| `summary_output_reserve_chars` | `MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20000` | 为压缩摘要 / 回答预留空间 |
| `autocompact_buffer_chars` | `AUTOCOMPACT_BUFFER_TOKENS = 13000` | 保留为兼容和后续 blocking limit 参考；当前自动压缩阈值以 `context_window_chars * auto_compact_threshold_ratio` 为准 |
| `warning_buffer_chars` | `WARNING_THRESHOLD_BUFFER_TOKENS = 20000` | 预留 warning 阈值，后续供 UI / trace 使用 |
| `error_buffer_chars` | `ERROR_THRESHOLD_BUFFER_TOKENS = 20000` | 预留 error 阈值，后续供 UI / trace 使用 |
| `manual_compact_buffer_chars` | `MANUAL_COMPACT_BUFFER_TOKENS = 3000` | blocking limit 的保留空间 |
| `keep_recent_tool_results` | micro compact keep recent | 默认保留最近 3 个工具结果原文 |

这里必须区分两个概念：

- `max_tokens` 是供应商 API 的单次回答输出预算，继续沿用后端默认值，配置页不展示。
- `context_window_chars` 是 CodeAsk runtime 用于上下文装配和压缩判断的总窗口近似值，默认按 200k 字符估算。

Claude Code 使用 token 计数；CodeAsk 当前还没有 provider-neutral token counter，所以 v1.0.2 使用 LLM message 序列化字符数作为近似执行单位。这个选择是工程上的临时适配，不改变目标方向：后续应把 LLM gateway 的真实 usage、模型 context window 配置和 tokenizer 估算接入 `ContextBudgetPolicy`。

本阶段已实现工具结果 micro-compact、prompt-too-long reactive compact，以及第一版会话级 `conversation_summary` / 历史摘要持久化。当前 `conversation_summary` 仍是 extractive 摘要，后续需要继续补 LLM 生成式结构化摘要、真实 token accounting、手动 compact UI、失败熔断和 Claude Code 级别的 prompt cache editing。

第一版预算比例建议：

```text
system / policy: 10-15%
conversation summary: 10-20%
recent turns: 20-30%
retrieval snippets: 20-30%
tool results: 20-30%
response reserve: 固定预留
```

这不是用户可见规则，而是 runtime 组装上下文时的工程约束。详细参考 `specs/rag-context-budget-lessons.md`。

当前已补充 RAG 注入预算回归测试：即使召回服务返回超过上限的候选特性、Wiki、报告和附件候选，进入 LLM messages 的 Feature RAG Pack 仍会限制条数、截断 snippet，并保持整体文本在小预算范围内。

## 10. 当前验证

已验证：

- `uv run pytest -q`
- `uv run pytest tests/integration/test_evals_runner_smoke.py tests/integration/test_basic_qa_baseline.py -q`
- `corepack pnpm --dir frontend test:run`
- `corepack pnpm --dir frontend build`
- `corepack pnpm --dir frontend test:e2e`
- 本次改动文件的 `uv run ruff check ...`
- `git diff --check`
- 真实 GLM-5.1 基础问答基线：完整题库保留在 `evals/basic_qa/cases/seed_001.jsonl`，当前覆盖 11 类 32 题；管理员账号、同一个会话 `sess_edf3fda647d77a83` 已完成 30 题实测，工具触发偏差 0、错误 0。
- 真实 GLM-5.1 参考仓库问答：`anything llm中，是怎么通过rag处理上传的资料的` 在修复工具结果预算后完成回答，无 input length 超限，测试会话 `sess_8d591f3142d5f1b4`。
- 真实 GLM-5.1 连续会话：`sess_096f8685b5997d38` 第一轮查询 anything-llm 的 `processSingleFile`，调用 `list_code_repos`、`search_code`、`read_code_file`；第二轮追问“你刚刚的回答，有查询代码吗”能正确区分列仓库、搜索代码和读取源码；刷新后第三轮仍能复述上一轮内容。
- 真实 GLM-5.1 Feature-Scoped Code Access：`frontend/e2e/agent-feature-scoped-code-live.spec.ts` 已在浏览器 E2E 中执行通过，覆盖管理员登录、创建特性、注册并关联 `references/claude-code/claude-code` 仓库、模型选择特性范围、代码工具结果 `scope_source=feature_scope`。
- 浏览器手动 E2E：前端会话读取 `references/claude-code/claude-code`，搜索 `PermissionMode`，刷新后恢复消息和行动轨迹，删除后清空行动轨迹。
- 浏览器手动 E2E：前端会话读取 `references/anything-llm`，搜索 `DataConnectorOption`，刷新后恢复消息和行动轨迹，删除后清空行动轨迹。
- 已沉淀 live Playwright 通道：`frontend/e2e/admin-agent-source-live.spec.ts`。默认跳过；设置 `CODEASK_RUN_LIVE_AGENT_E2E=1` 后，可在真实 LLM 配置下验证管理员登录、源码仓库注册、前端会话、工具调用、刷新恢复。
- 已沉淀基础问答 live Playwright 通道：`frontend/e2e/basic-model-qa-live.spec.ts`。默认跳过；设置 `CODEASK_RUN_LIVE_BASIC_QA_E2E=1` 后，按“每类取 1 题”的代表性 live 子集验证模型直答优先，并统计 Wiki/代码工具触发偏差；完整 32 题题库继续保留在 `evals/basic_qa/cases/seed_001.jsonl`。
- live Agent E2E 共享同一套 LLM 配置、仓库状态和 `.tmp/playwright-e2e` 数据目录时，Playwright 会强制 `workers = 1` 串行执行，避免并行污染导致空响应或上下文串扰。
- 2026-05-08 已用真实 GLM-5.1 / OpenAI 协议配置跑完 live Agent E2E 套件：`7 passed (12.0m)`，覆盖基础问答、连续会话、特性上下文技术插问、Feature-Scoped Code Access、长上下文和管理员源码链路。
- 已新增后端上下文预算回归：累计工具结果超过 active context 阈值时触发 micro-compact；供应商返回 input length / prompt too long / context length 错误时触发 reactive compact retry；低于阈值时不压缩。

说明：全仓库 `ruff check src tests` 仍存在历史格式问题，未纳入本次 Agent runtime 修复范围。本次验证只对改动文件执行 ruff。

## 11. 后续设计方向

1. 把真实 Wiki / 报告 / 附件 service 接入默认 `ChatToolRegistry`。
2. 将工具结果原始内容落审计存储，并通过 `raw_result_ref` 回查。
3. 为 `needs_clarification` 建立前端待答复状态，而不是只追加 assistant 文本。
4. 增加真实 LLM 端到端评测：普通问答、Wiki 足够回答、Wiki 不足但不确定仓库、代码读取后回答。
5. 在 `compaction.py` 第一版基础上继续实现会话级 `conversation_summary`、历史 auto-compact、真实 token accounting 和手动 compact UI。
6. 继续压缩旧 `session-model.ts` 中 legacy stage helper，避免长期保留两套模型。
