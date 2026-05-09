# v1.0.2 Agent Chat Runtime 验收清单

> 状态：Completed
> 版本：v1.0.2
> 范围：默认 Agent 会话运行时、RAG 候选上下文、工具调用、行动轨迹、连续会话、上下文预算、旧 v1.0 orchestrator 兼容
> 项目级验收规则：见 `../../DEVELOPMENT_ACCEPTANCE.md`

## 0. 验收原则

本清单既是 v1.0.2 的功能点清单，也是版本收口门禁。后续不能只用“前端能显示”“数据库有记录”“单轮回答成功”替代 Agent 真实链路验收。

状态标记：

- `[x]` 已实现并有测试或明确手动验收记录。
- `[ ]` 未完成、未验收或已发现缺陷。
- `[~]` 部分完成，仍需补齐测试或生产接入。

v1.0.2 收口前必须满足：

- 所有核心用户路径都有自动化测试或明确 live E2E 通道。
- Agent runtime 必须有 spy LLM 测试，断言实际发给模型的 `messages`。
- 前端历史恢复、后端模型上下文恢复、行动轨迹恢复必须分别验收。
- 文档中的“已完成”必须能对应到测试、命令、会话 id 或代码路径。

## 1. 产品行为

- [x] 普通问答不会触发旧固定链路。
- [x] 默认会话不再输出 `scope_detection` / `sufficiency_judgement` 作为用户可见流程。
- [x] RAG 召回只作为候选上下文注入模型，不在后端生成“是否足够”“下一步代码调查”等结论。
- [x] Wiki 足够回答时不会由后端默认查代码。
- [x] 代码读取只在模型需要工具时发生。
- [x] 基础模型能力问答不通过代码规则强制拦截工具，而是由模型根据上下文自主决策；评测只统计偏差率。
- [x] 候选特性不强制绑定会话。
- [x] 模型需要补充信息时，通过 `needs_clarification` / `ask_user` 事件表达。
- [x] 报告生成仍需要用户确认，不能静默生成。
- [x] 会话生成的问题定位报告不再表现为聊天记录整理，而是正式 Markdown 报告；后端 `prepare_session_report_draft(...)` 由模型按报告规则直接生成标题与正文，已由单元 / 集成测试覆盖。
- [x] 生成报告时，系统必须把报告写作规则、会话关键上下文、行动轨迹摘要和已确认证据传给 AI，由 AI 自主成文；已由 `tests/unit/test_session_report_generation.py` 与 `tests/integration/test_session_report_generation.py` 覆盖。
- [x] 报告标题默认不再复用会话标题，必须满足 `YYYY-MM-DD 问题描述`。
- [x] 标题中的日期必须取生成报告当天。
- [x] 标题中的“问题描述”默认由 AI 生成，但用户允许修改。
- [x] 报告草稿解析必须能从模型返回的严格 JSON、Markdown fenced JSON、含裸换行的 JSON 字符串和固定 schema JSON-like 输出中恢复 `title_description` 与 `body_markdown`；不能因正文中的未转义半角双引号把标题保存为 `未命名问题`。
- [x] 如果模型已经返回可恢复的 `body_markdown`，后端不得把原始 JSON 或 JSON 代码块保存成报告正文。
- [x] 报告正文结构由 AI 自主组织，不固定章节名，但必须尽量覆盖背景、过程、分析、结论、建议、总结和参考资料等信息面。
- [x] 证据不足时仍允许生成草稿，但正文必须明确未确认项和待补充项。
- [x] 同一会话最多只绑定一篇报告；重复生成时更新原报告，不新增第二篇。
- [x] 删除会话不会删除已生成报告。
- [x] 生成报告弹窗会默认选中当前会话最相关的特性；只有无法判断时才要求用户手动选择。
- [x] 连续追问时，后端模型上下文必须包含上一轮用户问题、助手回答和工具行动摘要，已由 API + spy LLM 测试覆盖。
- [x] 用户追问上一轮是否查过代码时，模型上下文中必须提供可区分以下语义的工具行动摘要：
  - 是否调用代码相关工具；
  - 是否实际读取源码文件；
  - 是否基于源码证据回答。

## 2. 连续会话与模型上下文

这是 v1.0.2 当前最高优先级缺口。不能用前端历史恢复替代模型上下文验收。

- [x] `/api/sessions/{session_id}/messages` 调用 `ChatRuntime` 前，必须加载当前会话最近 turns。
- [x] 当前 turn 的 user message 不能在历史和当前输入中重复注入。
- [x] `SessionTurn.role == "user"` 必须转换为 LLM `user` message。
- [x] `SessionTurn.role == "agent"` 必须转换为 LLM `assistant` message。
- [x] 第二轮 LLM 请求必须包含上一轮 user message。
- [x] 第二轮 LLM 请求必须包含上一轮 assistant answer。
- [x] 第二轮 LLM 请求必须包含上一轮关键工具行动摘要。
- [x] 工具行动摘要只包含必要字段：工具名、参数摘要、成功失败、summary、warnings、evidence refs、是否读取源码文件。
- [x] 工具行动摘要不允许注入完整 trace JSON。
- [x] 当前会话附件候选必须进入实际 LLM messages，包含重命名后的显示名、原文件名、描述和引用名，避免模型无法把用户口语化文件名映射到真实附件。
- [x] 历史消息数量必须受配置限制，默认只取最近 N 条。
- [x] 页面刷新后继续追问，模型仍能基于历史回答；已有 live E2E 通道和真实验收记录。
- [x] 删除会话后，消息、行动轨迹和关联附件 / 存储目录必须一起清理，右侧行动轨迹必须清空；已有 API 和前端组件回归覆盖。

最低测试要求：

- [x] 新增 API + spy LLM 测试：第二轮 messages 包含上一轮 user / assistant。
- [x] 新增 API + spy LLM 测试：第二轮 messages 包含上一轮 tool action summary。
- [x] 新增 API 集成测试：DB turns -> runtime history -> LLM messages 链路。
- [x] 新增 live 浏览器 E2E 通道：同一会话追问“你刚刚的回答，有查询代码吗”。
- [x] 新增 live 浏览器 E2E 通道：刷新后继续追问“你上一轮说了什么”。

## 3. RAG 与证据上下文

- [x] 轻量召回服务返回候选上下文，不生成后端流程结论。
- [x] `retrieval_context` SSE 事件会输出并持久化为行动轨迹。
- [x] 文档已明确 RAG 召回应向 `EvidenceDocument / EvidenceChunk / EvidenceRef` 收敛。
- [x] 文档已明确 `contextTexts` 和 UI `sources` 可以分离。
- [x] 文档已明确 RAG 注入只放 snippet / evidence ref，不注入全文。
- [x] 生产 `ChatRuntime` 已接入数据库版 `DatabaseRetrievalService`，每轮从真实特性、Wiki、报告和特性关联仓库组装轻量 Feature RAG Pack。
- [x] Feature RAG Pack 已进入实际 LLM messages，已有 spy LLM 测试断言模型可见 `feature_id`、关联仓库和 Wiki / 报告候选。
- [x] Feature RAG Pack 已限制候选数量和 snippet 长度，避免把 Wiki / 报告全文直接注入模型。
- [x] 每轮模型上下文必须包含 `feature_catalog`，即活跃特性目录，不能只在 query 命中特性名时才返回候选特性。
- [x] 每轮模型上下文必须包含 `feature_knowledge_index`，即每个特性的轻量 Wiki / 报告知识地图；当用户问题未命中特性名称但命中某个特性的 Wiki 内容时，模型仍能看到该特性可能相关。
- [x] `feature_catalog` 和 Wiki / 报告候选必须按当前问题相关性排序，直接命中特性或命中当前证据的特性排在前面；排序不隐藏其它候选，也不在后端替模型下结论。
- [x] Wiki 候选上下文必须向模型提供 `node_id` / `document_id` / `heading_path` 等可执行引用；模型不得依赖标题、路径或列表顺序猜测 Wiki node id。
- [x] `search_wiki` 对中英文混合长查询必须有通用降级检索，完整 query 0 命中时按词项拆分重试并去重，避免模型因连续 0 命中反复搜索。
- [x] `retrieval_context` 的替换边界已固定为 `feature_catalog`、`feature_knowledge_index`、`feature_candidates`、`wiki_hits`、`report_hits`、`attachment_candidates`、`repo_candidates`；后续外部 RAG 服务只需要实现同一结构，不应改动 runtime 决策边界。
- [x] 真实 Wiki 服务已接入默认 `ChatToolRegistry`，支持 `search_wiki` 和 `read_wiki_node`，已有真实数据库集成测试覆盖搜索、heading 读取和缺失 node 错误。
- [x] 真实问题报告服务已接入默认 `ChatToolRegistry`，支持 `search_reports` 和 `read_report`，已有真实数据库集成测试覆盖搜索、读取和缺失报告错误。
- [x] 真实附件服务已接入默认 `ChatToolRegistry`，支持 `list_session_attachments` 和 `read_session_attachment`，已有真实数据库 / 文件集成测试覆盖当前会话隔离、读取和重命名别名映射。
- [x] 当前 session 附件候选已由 `/api/sessions/{session_id}/messages` 注入 `ChatRuntime`，并由 API + spy LLM 测试覆盖上传、重命名、原文件名和描述进入模型上下文。
- [x] RAG 召回结果已按 `document_id` / `report_id` 做基础去重，避免同一 Wiki 文档或同一报告以多个节点 / 片段重复进入模型候选上下文。
- [x] RAG 召回结果还需要继续做 UI 来源治理和全链路预算治理，避免用户侧 sources 面板展示大量重复来源；后端候选注入已按稳定来源去重，工具结果进入模型前已有预算裁剪，UI 只展示摘要、引用和 trace 详情。
- [x] 模型上下文中的 RAG 片段已有预算测试，覆盖候选特性、Wiki、报告和附件候选的条数限制、snippet 截断和最终注入文本长度。

## 4. 工具契约与工具执行器

- [x] 工具通过 `ToolSpec` 集中声明能力、输入 schema、只读属性、确认需求和结果预算。
- [x] 工具默认 fail-closed：默认不是只读、默认不并发、默认需要确认。
- [x] 工具调用参数由 Pydantic schema 校验。
- [x] 工具失败返回结构化 `ToolResult`，交给模型解释或追问，不直接打断整轮会话。
- [x] 仓库或版本不明确时，工具结果能返回 `needs_clarification` 或带默认版本警告。
- [x] 工具结果超过 `ToolSpec.max_result_size_chars` 时会真实裁剪进入模型的 payload，不再只标记 `truncated=true`。
- [x] 只读 Wiki、报告、附件、代码和策略工具具备独立单元测试。
- [x] 每个生产工具都需要明确 `read_only`、`concurrency_safe`、`requires_confirmation`、`max_result_size_chars`；默认 app registry 已有回归测试覆盖。
- [x] 每个生产工具都需要在行动轨迹中输出用户可读 summary；`tool_result` SSE 和持久化 trace 已统一使用 `ToolResult.summary`。
- [x] 每个生产工具都需要区分 UI 展示摘要和模型可见结果；`tool_result` SSE 只暴露 summary / warnings / evidence_refs / version_info，模型 tool message 使用预算后的 `ToolResult`。
- [x] 每个生产工具后续需要支持 `raw_result_ref`，完整原始结果进入审计存储，不直接进入模型；超预算结果会生成 `raw_tool_result:*` 引用，并把完整原始结果写入隐藏的 `tool_result_raw` trace。

### 4.1 工具优化质量门禁

后续所有工具优化必须先证明“提升执行质量”，不能通过隐藏决策或硬编码样例制造表面成功。

- [ ] 工具层不得做业务语义映射：不得把 `电子宠物 -> buddy`、`sqlite -> schema.prisma`、`RAG -> contextTexts`、`AnythingLLM -> 某个固定 repo/path` 写进工具实现。
- [ ] 工具层不得按题型强制禁止或强制触发工具调用；普通问答、Wiki 检索、代码检索是否发生仍由模型基于上下文判断。
- [ ] 工具层不得输出“知识足够 / 不足”“下一步应该查代码”“应该读取某文件”等后端流程结论；工具只返回候选事实、执行结果、错误和恢复建议。
- [ ] 工具层可以做通用鲁棒性增强：大小写不敏感、分隔符归一、长 query 拆词 fallback、结果去重、分页、预算裁剪。
- [ ] 工具层可以做安全边界和输入校验：空 query、过宽通配符、非法路径、越权仓库、未确认写操作必须 fail closed。
- [ ] 工具失败必须可解释：不能只返回泛化 `internal_error`；应尽量区分 `invalid_glob`、`path_not_found`、`grep_timeout`、`too_many_matches`、`out_of_scope`、`needs_feature_scope` 等类型，并给出模型可用的 recovery hint。
- [ ] 工具结果预算裁剪必须保留关键证据字段：Wiki 的 `node_id/document_id/heading_path`，代码的 `repo_id/path/line/commit`，以及 `summary/warnings/error_type/version_info/raw_result_ref`。
- [ ] 行动轨迹可以折叠多次搜索和失败，但不得隐藏原始事件；展开后必须可追溯参数、结果、错误和 raw result。
- [ ] 每次工具优化必须新增正向测试和反向测试：正向证明质量提升，反向证明没有针对业务词、仓库名、测试样例做硬编码。

## 5. 代码工具与仓库范围

- [x] 生产默认 `ChatToolRegistry` 已接入只读代码工具。
- [x] 代码工具必须从全局 ready 仓库池收敛到“特性范围仓库池 + 用户显式仓库范围”。
- [x] `list_code_repos` 只能列出当前候选特性关联仓库或用户显式指定仓库，不能列出全部全局 ready 仓库。
- [x] 支持代码搜索。
- [x] 支持读取代码文件。
- [x] 工具达到轮次上限时，runtime 会关闭工具并要求模型基于已有结果回答。
- [x] 使用 `references/claude-code/claude-code` 从前端会话检索 `PermissionMode` 已验证代码工具链路；该仓库关联到 Claude Code 特性后的 feature-scoped live E2E 已在真实 LLM 环境执行通过。
- [x] 使用 `references/anything-llm` 从前端会话检索 `DataConnectorOption` 已验证代码工具链路；已补充该仓库关联到 AnythingLLM 特性后的 feature-scoped live E2E 通道。
- [x] 仓库范围推断必须由模型基于 Feature RAG Pack 选择一个或多个候选特性，再从这些特性关联仓库中检索。
- [x] Feature RAG Pack 必须包含足够模型判断的信息：特性目录、特性知识索引、特性名、描述、Wiki / 报告候选摘要和关联仓库摘要。
- [x] 多候选特性时，代码工具可访问这些特性关联仓库的并集。
- [x] 用户明确要求通过某个仓库查询时，该仓库可作为本轮显式范围，即使没有关联特性。
- [x] 没有候选特性范围且没有显式仓库时，代码工具必须返回 `needs_feature_scope`，不得 fallback 到全局仓库。
- [x] repo_id / repo_name 命中全局仓库但不属于候选特性关联仓库，且用户没有明确指定该仓库时，代码工具必须返回 `out_of_scope`。
- [x] 显式仓库范围的工具结果和行动轨迹必须标注 `explicit_user_repo`。
- [x] 代码版本选择仍需增强：无法确认版本时默认当前代码，但必须标注不确定性；默认 HEAD 读取会返回 `version_info.status=current_checkout` 和版本未确认 warning。
- [x] 用户追问“上一轮是否查代码”时，必须区分 list repos、search code、read code file 三种行为；已有摘要单测和 live 连续会话验收。
- [x] 源码工具结果必须有预算测试，避免 grep / read file 返回过大内容；生产代码工具 `ToolSpec.max_result_size_chars` 已显式声明并由工具执行器预算测试覆盖。

### 5.1 代码检索工具反特判验收

后续增强代码工具时，必须遵守以下边界：

- [x] 工具层不得根据用户自然语言做业务语义映射，例如 `电子宠物 -> buddy`；已新增回归用例，`list_code_paths(query="电子宠物")` 不会自动命中 `src/buddy`。
- [x] 工具层不得根据特定仓库名称 hardcode 返回固定路径；代码工具只基于已解析仓库、scope 参数和文件系统路径返回结果。
- [x] 工具层不得为了某个测试样例返回固定文件或固定证据；新增 `list_code_paths` 只做大小写不敏感路径匹配。
- [x] 工具层不得自动补业务同义词；同义词选择必须由模型基于 prompt 和上下文决定。
- [x] 工具层可以新增通用目录树能力，例如 `inspect_repo_tree`；生产 `ChatToolRegistry` 已接入 feature-scoped 版本。
- [x] 工具层可以新增通用路径 / 文件名搜索能力，例如 `list_code_paths`；已接入生产 Chat Runtime 工具注册。
- [x] 工具层可以增强 `search_code` 的通用搜索模式，例如 `literal`、`regex`、`any_terms`、`all_terms`。
- [x] 工具层可以对空 query、过短 query、`*`、目录读取等无效输入返回结构化 `invalid_input`；`search_code` 已拦截空 query 和单独通配符。
- [x] 工具层可以对搜索结果做聚合、去重、预算裁剪和截断提示；工具执行器会统一裁剪超预算结果并保留 raw reference。
- [x] 代码功能是否存在的强否定结论，不能仅基于若干次 `search_code` 0 命中；0 命中结果会提示模型先用 `list_code_paths` 或 `inspect_repo_tree` 确认目录和命名。
- [x] 新增回归用例：`claude code里面有实现tui界面的电子宠物功能吗`，必须验证不能通过工具 hardcode 通过；当前后端用例验证中文业务词不会被工具层映射到 `buddy` 路径。

## 6. 会话 API、SSE 与持久化

- [x] `/api/sessions/{session_id}/messages` 默认调用 `ChatRuntime`。
- [x] 默认 SSE 包含 `retrieval_context`、`text_delta`、`done`。
- [x] 默认 SSE 不再包含旧固定阶段事件。
- [x] assistant 文本增量会持久化为会话历史。
- [x] `retrieval_context`、`tool_call`、`tool_result` 等新版 runtime 事件会持久化为会话行动轨迹。
- [x] `force_code_investigation` 参数保留兼容，但不再强制旧后端链路。
- [x] 旧 `AgentOrchestrator` 保留为 legacy 兼容，旧 orchestrator 集成测试继续通过。
- [x] 下一轮 `ChatRuntime` 调用必须从持久化 turns 读取历史。
- [x] 下一轮 `ChatRuntime` 调用必须从持久化 traces 读取上一轮工具行动摘要。
- [x] SSE 错误事件必须在前端以明确错误提示展示，不能静默失败；运行时 `error` 事件会写入错误气泡并显示顶部提示，已有前端组件测试覆盖。
- [x] 删除会话失败时必须有错误提示；删除成功后必须清理右侧行动轨迹。
- [x] 会话生成中必须支持用户主动中断。
- [x] `POST /api/sessions/{session_id}/reports/prepare` 必须启动异步草稿任务并立即返回 `request_id/status=running`，不能长时间等待 LLM 响应。
- [x] `GET /api/sessions/{session_id}/reports/prepare/{request_id}` 必须按会话隔离返回任务状态；成功时返回 AI 生成的标题草稿、正文草稿、建议特性和已存在的会话报告 id（如有），失败时返回明确错误。
- [x] 前端生成报告必须先打开“正在准备报告”过程弹窗，再轮询任务状态；成功进入确认弹窗，失败走页面中央阻断式错误弹窗。
- [x] 报告草稿异步任务必须有 request id 回传和状态恢复能力，避免长 POST 经过代理或公网 dev server 在返回阶段出现 503 后让用户丢失草稿。
- [x] `POST /api/sessions/{session_id}/reports` 必须按“upsert 会话报告”语义工作：同一 session 首次创建，再次生成时更新原报告。
- [x] 前端发送消息前必须生成 `client_turn_id` 并传给后端；停止发生在 SSE header 或事件返回前，也能使用该 id 调用显式 abort API。
- [x] 中断后必须回滚到本次 user turn 发送前的状态：
  - 删除本次 user turn；
  - 删除本次 partial assistant turn；
  - 删除本次 turn 产生的 agent traces；
  - 删除或标记本次未完成的临时工具结果；
  - 保留本次发送前的历史消息、附件和行动轨迹。
- [x] abort 删除父 user turn 后，即使后端流迟到完成，也不得持久化 assistant turn 或迟到 trace。
- [x] 自动化测试必须覆盖迟到 assistant turn 场景：父 user turn 已被 rollback 后，`persist_agent_turn(..., parent_turn_id=...)` 不写入历史。
- [x] 中断不能影响上一轮已经完成的 turns 和 traces。
- [x] 中断后前端输入框必须恢复可输入状态，并给出清晰状态提示。
- [x] 自动化验收必须覆盖：无服务端 `turn_id` header / SSE 事件时，前端仍能按 `client_turn_id` 调用 `POST /api/sessions/{session_id}/turns/{turn_id}/abort` 并清空本轮消息和行动轨迹。

## 7. 前端体验

- [x] 右侧面板标题为 `Agent 行动轨迹`。
- [x] 不再展示固定 stage list。
- [x] 行动轨迹只展示真实 SSE/runtime 事件。
- [x] 普通回答不会展示代码调查进度。
- [x] 工具调用、工具结果、证据、澄清事件以卡片形式展示。
- [x] 工具失败以失败状态展示，不混入普通成功事件。
- [x] 事件详情通过悬浮弹窗预览，避免撑长右侧面板。
- [x] 附件区域保留在右侧面板，不受行动轨迹替换影响。
- [x] 前端不再渲染 `范围判断`、`充分性判断`、`insufficient`、`下一步` 作为默认流程文案。
- [x] 前端可刷新恢复历史消息和行动轨迹。
- [x] 前端刷新恢复不能作为模型上下文恢复的替代验收；已通过 API + spy LLM 测试和 live E2E 分别覆盖前端恢复与模型上下文恢复。
- [x] 失败提示需要统一：Agent 会话流错误、删除失败、Wiki 导入 / 删除 / 重命名、设置保存等路径已在前端使用明确错误提示；后续新增 UI 必须沿用“成功轻量提醒、失败明确弹窗或错误框”。
- [x] 用户追问上一轮行动时，前端必须保留足够的历史和 trace 可供后端加载；行动轨迹按 turn 保留，后端从持久化 traces 装配工具行动摘要。
- [x] 同一会话发送新消息时，`Agent 行动轨迹` 不得清空历史事件。
- [x] `Agent 行动轨迹` 应按 turn 分组展示；当前运行中的 turn 追加流式事件，历史 turn 保留并可折叠。
- [x] 切换会话时加载目标会话自己的行动轨迹；删除会话后清空右侧行动轨迹。
- [x] 未手动命名的新会话在第一轮完整问答后，应通过独立 LLM 请求自动生成标题；该请求不进入 `session_turns`，不污染正常 Agent 上下文，不写入用户可见行动轨迹。
- [x] 用户手动重命名后，`title_source` 必须变为 `manual`，自动标题生成不得覆盖用户标题。
- [x] 标题自动生成失败不影响正常回答、消息持久化和会话继续使用。
- [x] 后端必须提供 `POST /api/sessions/{session_id}/title/generate`，允许前端在第一轮完整问答落库后显式生成标题，并返回最新 `SessionResponse`。
- [x] 显式标题生成接口必须只读取已持久化的第一轮 user / assistant turn；不能把标题 prompt 写入 turns、行动轨迹或正常 Agent 上下文。
- [x] 前端收到显式标题生成接口返回后，必须直接合并进会话列表缓存，让标题动态渲染，而不是只能依赖用户刷新页面。
- [x] 会话流结束后，前端必须立即刷新会话列表，并在标题独立生成可能稍晚完成的窗口内再次刷新，避免列表停留在 `新的研发会话`。
- [x] 会话列表标题默认只显示一行，超出宽度用省略号展示。
- [x] 生成报告确认弹窗打开时，若已能推断出主要特性，应默认选中该特性。
- [x] 生成报告确认弹窗应展示 AI 生成的默认标题，用户可以修改“问题描述”部分后再保存。
- [x] 如果该会话已经生成过报告，再次生成时 UI 文案应明确是“更新当前报告”，而不是暗示会新建第二篇。
- [x] 行动轨迹卡片默认保持简洁，但点击或展开后必须显示更完整的信息：
  - 工具名；
  - 参数摘要；
  - 成功 / 失败状态；
  - summary；
  - warnings；
  - evidence refs；
  - repo / ref / commit / path / line；
  - truncated / raw_result_ref；
  - 错误类型和错误消息。
- [x] 行动轨迹详情不得用长 JSON 直接撑开布局；应使用抽屉、弹窗或固定高度滚动详情区。
- [x] 代码工具结果行动轨迹已展示范围来源、特性 id、仓库、ref 和 commit；已有前端测试覆盖 `feature_scope` 与 `explicit_user_repo` 展示。
- [x] 输入框快捷键必须符合：
  - `Enter` 直接发送；
  - `Ctrl + Enter` 换行；
  - `Shift + Enter` 换行。
- [x] 生成中输入框应显示中断入口；中断后输入框内容和会话状态应回滚到本轮发送前。

## 8. 上下文预算与压缩

- [x] 单个工具结果进入模型前已经有预算裁剪。
- [x] 文档已纳入 AnythingLLM RAG 管线和 Claude Code 长上下文压缩启发。
- [x] 文档已明确 CodeAsk 不直接照搬 Claude Code 算法，而是实现领域化上下文预算。
- [x] 文档已明确并实现第一版 `compaction.py`：
  - `estimate_context_size(...)`
  - `micro_compact_tool_results(...)`
  - `reactive compact retry`
  - `build_active_context(...)`
- [x] `compaction.py` 已实现 Claude Code 风格的阈值体系：
  - context window；
  - summary output reserve；
  - autocompact buffer；
  - warning / error buffer；
  - blocking limit；
  - keep recent tool results。
- [x] 每轮模型调用前会先估算 active context，低于阈值不压缩，高于阈值才压缩旧工具结果。
- [x] 累计多轮工具结果导致上下文膨胀时，旧工具结果会被替换成摘要，保留 summary、warnings、evidence refs、version_info、error_type 等语义字段。
- [x] 供应商返回 `input length` / `prompt too long` / `context length` 类错误时，runtime 会执行一次更严格的 reactive compact 并重试。
- [x] 已新增回归测试，覆盖“单个工具结果不超限但累计工具上下文超限”的场景。
- [x] 已新增回归测试，覆盖上下文超限错误后的 reactive compact retry。
- [x] 已新增单元测试，覆盖低于阈值不压缩和旧工具结果压缩后保留语义摘要。
- [x] 会话级 `conversation_summary` 已实现第一版：历史超过最近窗口时生成 extractive 持久化摘要，并在下一轮注入 LLM messages。
- [x] 旧工具结果 micro-compact 已实现第一版。
- [x] 历史 auto-compact 已实现第一版：较早 turns 被摘要覆盖，最近 turns 保留原文。
- [x] 压缩后身份、任务状态、已确认事实、证据、附件、仓库 / 版本、未解决问题的再注入已建立摘要通道；当前 extractive 摘要会保留历史 turns 和工具行动事实。
- [x] 长会话多轮工具调用后仍能继续回答已有后端回归测试；真实浏览器 / live LLM 长上下文 E2E 通道已补齐。

### 8.1 第二层：会话级 Auto Compact 待办

这是 `compaction.py` 第一版之后的下一层能力，必须作为独立任务实现，不能用当前 micro-compact 替代。

- [x] 建立 `conversation_summary` 持久化模型或等价存储：`session_conversation_summaries`。
- [x] summary 必须记录覆盖的 turn index 范围和 trace id 范围；当前记录 `covered_turn_index`、`covered_turn_count`、`covered_trace_count`，并在摘要正文中保留工具行动事实。
- [x] summary 必须保留当前用户目标、已确认事实、证据、附件、仓库 / 分支 / commit、未解决问题；当前从历史 turns 和工具行动摘要 extractive 保留。
- [x] summary 必须区分事实、推断和未确认信息；当前摘要声明为 extractive 历史事实，不把摘要内容伪装成新判断。
- [x] summary 必须保留工具行动事实，尤其是：
  - 是否调用 `list_code_repos`；
  - 是否调用 `search_code`；
  - 是否实际调用 `read_code_file`；
  - 工具失败类型和失败原因；
  - 代码证据使用的 repo / ref / commit 状态。
- [x] 实现 summary 生成 prompt 和解析逻辑；当前采用 extractive 摘要构造器，明确事实来源、覆盖范围、工具行动事实和使用要求。
- [x] 实现 active context builder：
  - system prompt；
  - conversation_summary；
  - recent turns；
  - 上一轮 tool action summary；
  - retrieval_context；
  - current user message。
- [x] active context builder 必须避免当前 user message 重复注入。
- [x] active context builder 必须避免 summary 覆盖范围和 recent turns 大量重复；摘要覆盖的 turns 不再作为 recent history 注入。
- [x] 超过 auto compact 阈值时生成或更新 summary；当前阈值为历史消息数量超过最近窗口。
- [x] 低于 auto compact 阈值时不能生成 summary。
- [x] compact 后 active context 必须低于阈值；当前按最近消息窗口收敛，旧 turns 由 summary 覆盖，工具结果另有字符预算裁剪。
- [x] compact 失败必须有连续失败熔断，默认最多 3 次；已有回归测试覆盖摘要构造失败时复用旧摘要并累计 failure。
- [x] 删除会话时必须清理 summary。
- [x] 刷新页面后继续追问，模型上下文必须能加载 summary 和 recent turns；后端上下文装配已支持，浏览器 long-context live E2E 待补。
- [x] summary 后用户追问“刚刚是否查过代码”，模型仍能正确区分列仓库、搜索代码和读取源码；summary 保留工具行动摘要，已有 spy LLM 场景覆盖长期摘要注入。
- [x] summary 后用户追问“上一轮说了什么”，模型不能回答成第一次交流；已新增 long-context live E2E 通道覆盖刷新后追问。
- [x] 新增后端 spy LLM 测试，断言 summary 进入实际 LLM messages。
- [x] 新增长历史触发 auto compact 的集成测试。
- [x] 新增 compact 失败熔断测试。
- [x] 新增真实浏览器 / live LLM Feature-Scoped Code Access 通道：`frontend/e2e/agent-feature-scoped-code-live.spec.ts`，覆盖创建特性、关联仓库、模型选择特性范围、代码工具结果 `scope_source=feature_scope`。
- [x] 新增真实浏览器 / live LLM 长上下文 E2E 通道：`frontend/e2e/agent-long-context-live.spec.ts`。

## 9. 基础模型能力评测

- [x] 基础模型能力题库已加入 `evals/basic_qa/cases/seed_001.jsonl`。
- [x] 题库覆盖 11 类 32 个问题：
  - 编程基础；
  - Linux / Shell；
  - 算法与数据结构；
  - 计算机网络；
  - 数据库；
  - 操作系统；
  - AI / 机器学习；
  - 系统设计 / 产品；
  - 逻辑推理；
  - Agent 自我认知；
  - 上下文依赖。
- [x] 预期为模型直答优先，允许少量 Wiki / 代码工具决策偏差，上限 10%。
- [x] 评测不允许在运行时代码中加入关键词拦截或强制禁止工具调用。
- [x] 使用管理员账号和真实 GLM-5.1 配置，在同一个会话 `sess_edf3fda647d77a83` 完成 30 题实测：30 个 user turn、30 个 agent turn、Wiki/代码工具触发偏差 0、错误 0；当前完整题库已扩展为 11 类 32 题。
- [x] 需要补充上下文依赖型基础题，例如“你刚刚提到哪个是不可变的”“把上一轮总结成一句话”。
- [x] 需要覆盖特性上下文中的插入式技术问答：会话围绕 AnythingLLM / RAG 展开时，用户中途问 `lancedb 和 sqlitedb 有什么区别`，模型应保持当前主题语境并优先直接回答；允许少量工具决策偏差，但不应频繁触发代码检索，也不应要求用户显式指定仓库。

## 10. E2E 验收

E2E 端到端测试是每个开发验收阶段的基本要求。本阶段验收必须覆盖真实前端、真实后端、浏览器刷新后的历史恢复、Agent 工具调用链路、连续追问和模型上下文恢复。

完整场景矩阵见 `e2e-scenarios.md`。新增或修改核心用户路径时，必须同步更新该文件中的场景、前置条件、步骤和验收标准。

- [x] 手动联调真实 LLM 配置，确认普通问答、源码仓库工具调用、刷新恢复、删除清理和行动轨迹表现。
- [x] 使用真实 GLM-5.1 配置验证 `anything llm中，是怎么通过rag处理上传的资料的`，修复工具结果预算后会话 `sess_8d591f3142d5f1b4` 正常完成，未再出现 input length 超限。
- [x] 后端 API + spy LLM 验证同一会话继续追问 `你刚刚的回答，有查询代码吗` 时，LLM messages 包含上一轮历史和工具行动摘要。
- [x] 已新增连续会话 live E2E 测试通道：`frontend/e2e/agent-conversation-continuity-live.spec.ts`。
- [x] 真实浏览器 / live LLM 继续追问 `你刚刚的回答，有查询代码吗` 已通过，会话 `sess_096f8685b5997d38`。
- [x] 刷新页面后继续追问上一轮内容已通过，会话 `sess_096f8685b5997d38`。
- [x] 保留 live E2E 测试通道：`frontend/e2e/admin-agent-source-live.spec.ts`，用于显式开启真实 LLM、管理员登录、源码仓库注册、前端会话、行动轨迹、刷新恢复的全链路验证。
- [x] 保留 Feature-Scoped Code Access live E2E 测试通道：`frontend/e2e/agent-feature-scoped-code-live.spec.ts`，用于显式开启真实 LLM、管理员登录、创建特性、注册并关联源码仓库、验证代码工具范围来源为 `feature_scope`。
- [x] 2026-05-07 使用真实 GLM-5.1 / OpenAI 协议配置执行 `frontend/e2e/agent-feature-scoped-code-live.spec.ts`，结果 `1 passed (57.8s)`；LLM Gateway 统一走 LiteLLM，配置中的模型名保持 `GLM-5.1`，内部调用按需补 `openai/` provider hint；历史 `openai_compatible` 也遵循同一协议语义。
- [x] 2026-05-07 删除 OpenAI 协议直连实现后，使用真实 GLM-5.1 / OpenAI 协议配置执行 `frontend/e2e/agent-feature-scoped-code-live.spec.ts` 和 `frontend/e2e/agent-long-context-live.spec.ts`，结果 `3 passed (2.4m)`。
- [x] 2026-05-07 修复显式仓库名匹配：`claude code` 可匹配已注册的 `claude-code` 仓库，避免模型因一次仓库关键词 0 命中就泛化回答；真实 GLM-5.1 / OpenAI 协议执行 `frontend/e2e/admin-agent-source-live.spec.ts`，结果 `1 passed (1.4m)`。
- [x] 2026-05-07 补齐模型可见仓库候选：`retrieval_context` 会向模型注入全局 ready 仓库轻量列表，模型可基于 repo id / name / source / linked feature ids 自行判断显式仓库范围；工具层仓库名归一匹配仅作为容错，不作为业务特判。
- [x] 保留基础问答 live E2E 测试通道：`frontend/e2e/basic-model-qa-live.spec.ts`，用于显式开启真实 LLM、管理员登录、同一会话代表性题集问答、工具触发偏差率统计和会话历史持久化校验；完整 32 题题库保留在 `evals/basic_qa/cases/seed_001.jsonl`。
- [x] 保留连续会话 live E2E 测试通道：`frontend/e2e/agent-conversation-continuity-live.spec.ts`，用于显式开启真实 LLM、管理员登录、源码仓库注册、同一会话二轮追问、刷新后继续追问的全链路验证。
- [x] 新增特性上下文技术插问 live E2E 测试通道：`frontend/e2e/agent-contextual-technical-qa-live.spec.ts`，用于显式开启真实 LLM、管理员登录、创建 AnythingLLM 特性并关联仓库、按真实会话问题顺序验证 RAG 主题问答、`lancedb 和 sqlitedb 有什么区别` 插入式直接回答、回到 RAG 语境追问以及最后明确源码确认。
- [x] live Agent E2E 在共享同一套 LLM 配置、仓库状态和 `.tmp/playwright-e2e` 数据目录时默认串行执行；`frontend/playwright.config.ts` 会在任一 `CODEASK_RUN_LIVE_*` 开关启用时强制 `workers = 1`。
- [x] 2026-05-08 已执行整套 live Agent E2E：`7 passed (12.0m)`，覆盖基础问答、连续会话、特性上下文技术插问、Feature-Scoped Code Access、长上下文和管理员源码链路。
- [x] 会话页刷新和跨一级页面返回时保持当前选中会话：选中 session 写入 `#/sessions?session={session_id}`，已有 `tests/session-workspace.test.tsx` 覆盖刷新恢复和离开再返回恢复。
- [x] 会话标题自动生成已有后端集成测试覆盖：默认标题会在第一轮完整问答后生成，标题生成 LLM 请求不写入 turns，用户手动标题不会被覆盖。
- [x] 会话标题自动生成已有后端显式接口测试覆盖：`POST /api/sessions/{session_id}/title/generate` 会基于已持久化第一轮问答返回更新后的 `SessionResponse`。
- [x] 会话标题自动生成已有前端刷新和动态合并测试覆盖：会话流结束后会立即刷新列表、调用显式标题生成接口，并把返回的 session 合并进可见列表缓存。
- [x] 会话列表单行省略已有前端组件回归：标题文本使用独立 `.item-title-text`，由 CSS `text-overflow: ellipsis` 控制。
- [x] 会话生成问题报告的重复生成 / 改绑路径已有后端集成测试覆盖：prepare 默认特性优先取当前会话证据推断，保存时按一会话一报告 upsert，历史 `metadata_json.session_id` 重复报告和旧 Wiki 报告引用会被清理。
- [x] 报告草稿解析回归测试覆盖真实失败形态：`body_markdown` 中包含未转义半角双引号时，仍能提取 AI 生成的标题描述和 Markdown 正文。

LLM 配置池与基础负载均衡验收：

配置来源选择：

- [x] 用户存在启用的个人 LLM 配置时，优先使用用户配置，不占用全局配置池槽位。
- [x] 用户个人 LLM 配置失败时，不自动 fallback 到全局配置；错误直接返回，除非后续产品明确允许用户开启 fallback。
- [x] 用户个人配置不参与全局会话限额、失败冷却和随机池选择。
- [x] 请求显式指定 `config_id` 时，不参与全局池随机选择、会话限额、会话粘性和失败切换。
- [x] 请求显式指定 `config_id` 且配置不可用时，按明确错误返回，不自动替换成其它配置。
- [x] 用户没有个人配置时，从启用的全局 LLM 配置池中选择。

会话统计和粘性：

- [x] 单个全局配置最近 60 秒最多服务 3 个不同会话。
- [x] 同一 `session_id` 在 60 秒窗口内多次调用同一全局配置，只计为 1 个会话，不按请求次数累计。
- [x] 全局配置池全部满载或处于失败冷却时，返回 `当前资源繁忙，请稍后再试`。
- [x] 同一会话 5 分钟内继续使用上次选中的全局配置，即使该配置随后被其他会话占满。
- [x] 同一会话上次使用的全局配置被删除、禁用或进入失败冷却时，直接切换下一个可用配置。
- [x] 同一会话前后间隔超过 5 分钟后，可以重新进入全局池选择。
- [x] 会话内 LLM 调用必须传 `session_id`，否则无法参与会话粘性和按会话限额统计；当前 ChatRuntime、旧 Orchestrator 和报告生成链路均会传递 `session_id`。
- [x] 非会话型 LLM 调用如果没有 `session_id`，不参与会话粘性和会话数统计；后续若要限制非会话任务，需要单独设计任务级限流。

失败切换和冷却恢复：

- [x] 非供应商健康类错误不得计入 LLM 配置失败冷却，例如上下文超限、max_tokens 非法、tool schema / 请求格式错误；这类错误直接返回给上层处理，不触发配置切换或剔除。
- [x] 同一全局配置 5 分钟内出现 3 次最终失败后，临时剔除 10 分钟；冷却结束后自动回池。
- [x] 冷却期间配置不会被 sticky 选择命中，也不会进入全局候选池。
- [x] 冷却到期后失败记录清空，重新按健康配置参与随机池。
- [x] 全局配置在一次请求的初始阶段失败且尚未输出内容时，立即排除该配置并切换下一个可用全局配置；已开始输出后不跨模型续流。
- [x] 本次请求内所有可用全局配置都在初始阶段失败时，返回最后一次模型错误；如果没有任何候选配置可尝试，返回 `当前资源繁忙，请稍后再试`。
- [x] 单次请求最多尝试 `max_retries + 1` 次模型调用，包含跨配置切换和同配置重试，避免一个请求扫完整个资源池造成放大流量。

UI 与可观测性：

- [ ] LLM 资源繁忙错误在会话 UI 中显示为明确失败提示，不允许静默失败或只在行动轨迹中出现。
- [ ] 资源繁忙不应该持久化成一条看似正常的 AI 回答。
- [ ] 后续应在 trace / log 中记录配置选择、切换、失败、冷却原因和尝试过的配置 id，便于排查资源池问题。
- [x] 单元测试覆盖上述选择、限额、粘性、初始失败切换、失败冷却和关键边界行为：`uv run pytest tests/unit/test_llm_gateway.py -q`。

源码工具 live E2E 显式运行方式：

```bash
CODEASK_RUN_LIVE_AGENT_E2E=1 \
CODEASK_LIVE_AGENT_LLM_API_KEY='<api-key>' \
CODEASK_LIVE_AGENT_LLM_BASE_URL='https://ark.cn-beijing.volces.com/api/coding/v3' \
CODEASK_LIVE_AGENT_LLM_MODEL='GLM-5.1' \
corepack pnpm --dir frontend test:e2e e2e/admin-agent-source-live.spec.ts
```

Feature-Scoped Code Access live E2E 显式运行方式：

```bash
CODEASK_RUN_LIVE_FEATURE_SCOPED_CODE_E2E=1 \
CODEASK_LIVE_AGENT_LLM_API_KEY='<api-key>' \
CODEASK_LIVE_AGENT_LLM_BASE_URL='https://ark.cn-beijing.volces.com/api/coding/v3' \
CODEASK_LIVE_AGENT_LLM_MODEL='GLM-5.1' \
corepack pnpm --dir frontend test:e2e e2e/agent-feature-scoped-code-live.spec.ts
```

基础问答基线显式运行方式：

```bash
CODEASK_RUN_LIVE_BASIC_QA_E2E=1 \
CODEASK_LIVE_AGENT_LLM_API_KEY='<api-key>' \
CODEASK_LIVE_AGENT_LLM_BASE_URL='https://ark.cn-beijing.volces.com/api/coding/v3' \
CODEASK_LIVE_AGENT_LLM_MODEL='GLM-5.1' \
corepack pnpm --dir frontend test:e2e e2e/basic-model-qa-live.spec.ts
```

连续会话显式运行方式：

```bash
CODEASK_RUN_LIVE_AGENT_CONTINUITY_E2E=1 \
CODEASK_LIVE_AGENT_LLM_API_KEY='<api-key>' \
CODEASK_LIVE_AGENT_LLM_BASE_URL='https://ark.cn-beijing.volces.com/api/coding/v3' \
CODEASK_LIVE_AGENT_LLM_MODEL='GLM-5.1' \
corepack pnpm --dir frontend test:e2e e2e/agent-conversation-continuity-live.spec.ts
```

后续每个开发阶段新增或修改核心用户路径时，都必须在对应版本的验收清单中补充 E2E 项，并说明是否已执行。

## 11. 回归验证命令

当前已执行过的验证：

- [x] `uv run pytest -q`
- [x] `uv run pytest tests/integration/test_evals_runner_smoke.py tests/integration/test_basic_qa_baseline.py -q`
- [x] `corepack pnpm --dir frontend test:run`
- [x] `corepack pnpm --dir frontend build`
- [x] 本次改动文件的 `uv run ruff check ...`
- [x] `git diff --check`
- [x] `uv run pytest tests/integration/test_session_report_generation.py -q`
- [x] `uv run pytest tests/unit/test_session_report_generation.py tests/integration/test_session_report_generation.py -q`
- [x] `uv run ruff check src/codeask/sessions/report_generation.py tests/unit/test_session_report_generation.py`
- [x] `corepack pnpm --dir frontend exec vitest run tests/session-workspace.test.tsx tests/app-shell.test.tsx tests/wiki-routing.test.ts`
- [x] `corepack pnpm --dir frontend exec tsc --noEmit`

后续修复连续会话缺陷后，至少需要重新执行：

```bash
uv run pytest tests/unit/chat_runtime tests/integration/test_agent_chat_runtime.py tests/integration/test_agent_chat_runtime_sse.py -q
uv run pytest tests/integration/test_sessions_api.py tests/integration/test_basic_qa_baseline.py -q
corepack pnpm --dir frontend test:run
corepack pnpm --dir frontend build
git diff --check
```

如果新增 live E2E，需要补充显式运行命令和实际会话 id。

连续会话 live 验收记录：

```text
会话 id：sess_096f8685b5997d38
模型：GLM-5.1
第一轮：搜索 anything-llm 仓库中的 processSingleFile，并说明它和 RAG 上传资料处理的关系。
第一轮工具：list_code_repos、search_code、search_code、read_code_file
第二轮：你刚刚的回答，有查询代码吗？如果有，请区分是列出仓库、搜索代码还是读取源码文件。
第二轮结果：通过，模型正确说明上一轮使用了 list_code_repos、search_code 和 read_code_file。
刷新后第三轮：刷新后继续追问：你上一轮说了什么？
第三轮结果：通过，模型能复述上一轮关于代码工具使用情况的回答。
```

## 12. v1.0.2 收口阻塞项

以下项未完成前，v1.0.2 不能标记为完成：

- [x] 修复连续会话模型上下文缺失。
- [x] 修复上一轮工具行动摘要不能被模型追问的问题。
- [x] 为连续会话补 API + spy LLM 测试。
- [x] 为工具行动可追问补 API + spy LLM 测试。
- [x] 为刷新后继续追问补 live 浏览器 E2E 通道。
- [x] 为 `anything llm` RAG 问题的二轮追问补 live E2E 通道。
- [x] 明确生产 Wiki / 报告 / 附件工具的接入范围：本版本已接入只读 `search/read/list` 能力；写入、编辑、删除仍走明确 UI 动作或后续确认型工具。
- [x] `compaction.py` 第一版已作为本版本必须项实现；会话级 `conversation_summary` 和历史 auto-compact 已完成 extractive 基线，生成式结构化摘要、真实 token 预算和失败熔断仍是后续项。
- [x] 修复会话页刷新 / 离开再返回后选中会话丢失的问题。
- [x] 修复问题报告重复生成时默认绑定沿用旧错误特性的问题。
- [x] 修复同一会话历史重复报告在旧特性问题报告列表中残留的问题。
- [x] 修复 AI 已生成标题但报告保存为 `YYYY-MM-DD 未命名问题` 的解析容错问题。
- [ ] LLM 资源繁忙错误在会话 UI 中显示为明确失败提示，不允许静默失败或只在行动轨迹中出现。
- [ ] 资源繁忙不应该持久化成一条看似正常的 AI 回答。
- [ ] LLM 网关应在 trace 或结构化日志中记录配置选择、切换、失败、冷却原因和尝试过的配置 id，便于排查资源池问题。
- [x] 升级兼容规则已落入 `docs/rules/upgrade-compatibility.md`，安装文档包含从旧版本升级、备份、回滚和 `CODEASK_DATA_KEY` 缓存说明。
- [x] 首次启动提供 `CODEASK_DATA_KEY` 时，服务会把 key 写入 `<CODEASK_DATA_DIR>/secrets/data.key`。
- [x] 二次启动未设置 `CODEASK_DATA_KEY` 时，服务可以从 `<CODEASK_DATA_DIR>/secrets/data.key` 读取 key。
- [x] 当环境变量 key 和缓存 key 不一致时，服务拒绝启动，避免破坏已有加密数据。
- [x] `start.sh` 不再在存在缓存 key 的情况下要求用户重复导出 `CODEASK_DATA_KEY`。
- [x] 数据 key 缓存逻辑具备单元 / 集成测试，覆盖首次写入、二次读取、冲突拒绝和缺失失败。

## 13. 非目标与后续项

- v1.0.2 不处理多 agent。
- v1.0.2 不处理代码修改、提交和 PR。
- v1.0.2 不处理后台任务编排。
- v1.0.2 不处理完整权限细粒度隔离。
- 完整向量库重构、复杂 reranker、历史特性向量迁移放到后续版本。
- Claude Code 级别的 prompt cache editing 不纳入 v1.0.2。
- 用户手动 compact UI 不纳入 v1.0.2。
- 自动升级工具、显式 `doctor / backup / migrate / version` 命令和前后端 build revision 校验不纳入 v1.0.2，后续版本单独规划。
