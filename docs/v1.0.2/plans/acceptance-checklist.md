# v1.0.2 Agent Chat Runtime 验收清单

> 状态：Draft
> 版本：v1.0.2
> 范围：默认会话运行时、Agent 行动轨迹、旧 v1.0 orchestrator 兼容

## 1. 产品行为

- [x] 普通问答不会触发旧固定链路。
- [x] 默认会话不再输出 `scope_detection` / `sufficiency_judgement` 作为用户可见流程。
- [x] RAG 召回只作为候选上下文注入模型，不在后端生成“是否足够”“下一步代码调查”等结论。
- [x] Wiki 足够回答时不会由后端默认查代码。
- [x] 代码读取只在模型需要工具时发生。
- [x] 候选特性不强制绑定会话。
- [x] 模型需要补充信息时，通过 `needs_clarification` / `ask_user` 事件表达。
- [x] 报告生成仍需要用户确认，不能静默生成。

## 2. 工具与边界

- [x] 工具通过 `ToolSpec` 集中声明能力、输入 schema、只读属性、确认需求和结果预算。
- [x] 工具默认 fail-closed：默认不是只读、默认不并发、默认需要确认。
- [x] 工具调用参数由 Pydantic schema 校验。
- [x] 工具失败返回结构化 `ToolResult`，交给模型解释或追问，不直接打断整轮会话。
- [x] 仓库或版本不明确时，工具结果能返回 `needs_clarification` 或带默认版本警告。
- [x] 只读 Wiki、报告、附件、代码和策略工具已具备独立单元测试。
- [ ] 真实生产数据源的 Wiki / 报告 / 代码工具接入完整后，需要补充端到端工具调用验收。

## 3. 会话接口

- [x] `/api/sessions/{session_id}/messages` 默认调用 `ChatRuntime`。
- [x] 默认 SSE 包含 `retrieval_context`、`text_delta`、`done`。
- [x] 默认 SSE 不再包含旧固定阶段事件。
- [x] assistant 文本增量会持久化为会话历史。
- [x] `force_code_investigation` 参数保留兼容，但不再强制旧后端链路。
- [x] 旧 `AgentOrchestrator` 保留为 legacy 兼容，旧 orchestrator 集成测试继续通过。

## 4. 前端体验

- [x] 右侧面板标题为 `Agent 行动轨迹`。
- [x] 不再展示固定 stage list。
- [x] 行动轨迹只展示真实 SSE/runtime 事件。
- [x] 普通回答不会展示代码调查进度。
- [x] 工具调用、工具结果、证据、澄清事件以卡片形式展示。
- [x] 工具失败以失败状态展示，不混入普通成功事件。
- [x] 事件详情通过悬浮弹窗预览，避免撑长右侧面板。
- [x] 附件区域保留在右侧面板，不受行动轨迹替换影响。
- [x] 前端不再渲染 `范围判断`、`充分性判断`、`insufficient`、`下一步` 作为默认流程文案。

## 5. 回归验证

- [x] 后端 ChatRuntime 单元测试通过。
- [x] 后端 session SSE 集成测试通过。
- [x] 旧 orchestrator sufficient / insufficient 集成测试通过。
- [x] 前端完整测试集通过。
- [x] 前端生产构建通过。
- [ ] 手动联调真实 LLM 配置，确认普通问答、Wiki 召回、工具建议、澄清事件和行动轨迹表现。

## 6. 已知后续项

- 真实工具执行目前仍以 v1.0.2 的工具契约和独立单元测试为主，生产数据源的完整 tool registry 接入需要继续推进。
- 代码检索工具需要进一步接入真实 `AgentCodeSearchService`，而不是只停留在 runtime 工具契约层。
- 行动轨迹后续可补充工具结果原始详情的审计引用和更完整的 evidence link。
- v1.0.2 不处理多 agent、代码修改、后台任务编排和权限细粒度隔离。
