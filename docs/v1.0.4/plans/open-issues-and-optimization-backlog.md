# v1.0.4 设计与实现问题收敛清单

> 状态：Closed for v1.0.4 P0/P1 收口
> 创建日期：2026-05-16
> 范围：v1.0.4 opencode backend、LLM 配置、MCP tools、Wiki/worktree、会话流、前端行动轨迹、E2E 验收与文档一致性
> 用途：记录 v1.0.4 审查期间发现的所有未完成项和设计/实现不合理点，以及对应修复、验证和延期边界。后续版本如果继续改动 opencode backend，必须先对照本文确认不能回退这些已关闭问题。

---

## 0. 状态约定

- `[ ]` 未完成，需要实现或补验证。
- `[~]` 已有部分实现，但存在设计偏差、验收不足或文档不一致。
- `[x]` 已关闭，关闭时必须补充代码/测试/文档证据。

优先级：

- `P0`：影响 v1.0.4 主链路可靠性、用户可见行为或后续闭环判断，必须优先处理。
- `P1`：主链路可用但存在明显工程债、测试缺口或边界风险。
- `P2`：体验、诊断和长期演进项，可以在 P0/P1 收口后处理或转入 future。

---

## 1. 文档与验收口径不一致

- [x] `P0` 统一 v1.0.4 README、PRD、Design、Plan、Acceptance Checklist 的状态口径。
  - 当前问题：`README.md` 写明版本处于 `Implementing`，但部分段落描述为“已实现”；PRD 仍是 Draft；验收清单中存在大量 `[ ]` / `[~]`。
  - 要求：每个能力必须标记为 `已实现且已验收`、`已实现待 E2E`、`未实现`、`延期` 四类之一。
  - 涉及文档：
    - `docs/v1.0.4/README.md`
    - `docs/v1.0.4/prd/opencode-backend.md`
    - `docs/v1.0.4/design/opencode-backend.md`
    - `docs/v1.0.4/plans/opencode-backend.md`
    - `docs/v1.0.4/plans/acceptance-checklist.md`
  - 关闭记录：五份主文档最终统一为 `Manual Acceptance Completed` / `Release Ready` 口径；README 新增能力状态矩阵，按 `已实现且已验收`、`延期或后续版本` 显式区分，并补充 2026-05-19 opencode 完成事件闭合、长对话 UI 和特性源码调查 E2E 证据。

- [x] `P0` 在验收清单中明确：v1.0.4 未达到全部收口条件前，不得标记版本闭环。
  - 当前问题：部分模块已经写成 `[x]`，但多环境 E2E、cleanup、opencode unavailable、worktree、连续性仍未完成。
  - 要求：模块完成和版本完成分开标记，不能用局部 smoke 替代版本闭环。
  - 关闭记录：验收清单 `0. 验收原则` 已写明“所有 P0 关闭或经用户明确延期”才允许收口；README 状态矩阵把局部完成和版本未闭环分开展示。

- [x] `P1` 清理 `specs/opencode-interaction-flow.md` 中已验证、未验证和延期项的混杂状态。
  - 当前问题：Phase 0 已验证的结论、实现阶段仍未落地的项、future 项混在一起。
  - 要求：拆成 `已验证事实`、`当前实现契约`、`待实现缺口`、`future`。
  - 关闭记录：文档状态改为 `Historical Flow + Current Contract`，新增顶部 `A. 当前实现契约`，明确已验证事实、模块边界、延期项，并声明下方旧流程只作为历史推导背景，不能作为实现依据。

---

## 2. 动态上下文没有真正落地

- [x] `P0` 实现 opencode turn 级动态上下文组装器。
  - 当前问题：`OpenCodeCompat.run_turn` 传入 opencode 的 system prompt 是静态 `build_codeask_system_prompt()`；没有注入当前活跃特性列表、已绑定特性、repo 摘要、wiki manifest、附件摘要和当前 workspace 事实。
  - 要求：新增独立上下文组装边界，例如 `src/codeask/agent/opencode_compat/context.py`，每轮构造 CodeAsk context。
  - 必须包含：
    - session id、workspace 路径、当前已绑定特性。
    - 当前可见活跃特性摘要：`feature_id/name/slug/summary/wiki_path/ready_repo_count`。
    - Wiki 工作区入口和 `_manifest.json` 路径说明。
    - 可访问仓库摘要，支持用户显式点名仓库。
    - 会话附件摘要。
    - MCP 工具真实 schema 摘要。
  - 约束：后端只提供事实，不替模型判断特性或仓库边界。
  - 关闭记录：已新增 `src/codeask/agent/opencode_compat/context.py`，每轮向 system prompt 注入 session/workspace、已绑定特性、活跃特性目录、仓库目录、附件摘要、Wiki 入口和 MCP 工具摘要。
  - 验证：`uv run pytest tests/unit/test_opencode_compat_context.py tests/unit/test_opencode_compat_backend.py::test_run_turn_appends_dynamic_codeask_context_to_system_prompt -q`。

- [x] `P0` 将动态上下文同时写入 workspace `AGENTS.md` 或等价入口，保证 opencode 原生文件读取时也能看到 CodeAsk 使用规则。
  - 当前问题：`AGENTS.md` 是静态文本，缺少当前环境中的真实特性/仓库/Wiki 索引。
  - 要求：静态规则和动态事实分层，避免每次写入互相覆盖不清。
  - 关闭记录：`AGENTS.md` 保留静态规则并指向 `./CODEASK_CONTEXT.md`；每轮 `run_turn` 会重写 `CODEASK_CONTEXT.md` 为当前动态事实。
  - 验证：`test_run_turn_appends_dynamic_codeask_context_to_system_prompt` 覆盖文件写入。

- [x] `P1` 为动态上下文增加快照日志。
  - 当前问题：Agent 行为走偏时，无法确认模型实际收到哪些 CodeAsk 上下文。
  - 要求：每轮保存 context metadata 摘要，至少包含特性数量、repo 数量、wiki manifest 版本、附件数量、prompt 字符数；默认不保存敏感原文。
  - 关闭记录：`OpenCodeCompat.run_turn` 在发送 prompt 前生成 `assistant_action/codeask_context_snapshot`，只保存 `prompt_char_count`、`context_char_count`、Wiki manifest schema/view/count/exported_at 等摘要，不保存上下文原文。
  - 验证：`uv run pytest tests/unit/test_opencode_compat_backend.py::test_run_turn_appends_dynamic_codeask_context_to_system_prompt -q`。

---

## 3. MCP 工具 schema 与文档/用户自然表达不一致

- [x] `P0` 扩展 `list_features` schema，支持 `query?` 和 `limit?`。
  - 当前问题：设计文档写支持 query，但实现只支持 limit。
  - 要求：query 可按名称、slug、描述、summary 模糊过滤；不做业务判断，只返回候选。
  - 验证：`tests/unit/test_opencode_compat_mcp_feature_tools.py`。

- [x] `P0` 扩展 `get_feature_info` schema，支持 `feature_id?`、`slug?`、`name?` 三种定位方式。
  - 当前问题：实现强制 `feature_id`，但模型和普通用户经常只知道名称。
  - 要求：多个参数同时存在时优先级为 `feature_id > slug > name`；name 模糊命中多条时返回候选和 recovery hint。
  - 验证：`tests/unit/test_opencode_compat_mcp_feature_tools.py`。

- [x] `P0` 扩展 `list_feature_repos` schema，支持 `feature_id?`、`query?`、`limit?`、`include_unready?`。
  - 当前问题：用户显式指定仓库但未确认特性时，模型缺少按仓库名查候选的工具。
  - 要求：用户明确要求某仓库时，即使没有已绑定特性，也允许模型通过 query 找可见仓库候选。
  - 验证：`tests/unit/test_opencode_compat_mcp_feature_tools.py`。

- [x] `P0` 扩展 `prepare_worktree` schema，支持 `repo_id?`、`repo_name?`、`ref?`、`reason?`。
  - 当前问题：实现只接受 repo_id/ref；不符合“用户显式指定仓库也允许”的产品契约。
  - 要求：repo_name 模糊命中多条时不准备 worktree，返回候选；reason 写入审计。
  - 验证：`tests/unit/test_opencode_compat_mcp_worktree_tools.py`。

- [x] `P1` MCP 工具错误返回必须统一为可恢复结构。
  - 当前问题：部分参数错误直接抛 `ValueError`，模型只看到参数校验失败，缺少下一步纠错依据。
  - 要求：工具 handler 内部把可预期错误转为 `{error, summary, recovery_hint, candidates?}`。
  - 关闭记录：feature、worktree、session/attachment MCP 工具的可预期参数和仓库状态错误已返回结构化结果；底层 worktree `InvalidRefError`、bare missing 等已映射。
  - 验证：`tests/unit/test_opencode_compat_mcp_feature_tools.py`、`tests/unit/test_opencode_compat_mcp_worktree_tools.py`、`tests/unit/test_opencode_compat_mcp_session_tools.py`。

- [x] `P1` MCP tools/list 快照测试必须覆盖实际 schema，并和文档示例同步。
  - 当前问题：文档和实现漂移，后续还会重复出现工具参数失败。
  - 要求：测试失败时能直接暴露 schema 变化。
  - 关闭记录：已增加 `test_opencode_mcp_tools_list_matches_v104_contract`，固定 v1.0.4 opencode MCP 工具名称和关键参数集合；同时确认 `search_reports/read_report` 不在 opencode runtime `tools/list` 中。

---

## 4. opencode 进程生命周期和诊断不完整

- [x] `P0` 收口 opencode shared server 的启动职责。
  - 当前问题：服务 lifespan/keepalive 会启动 opencode；每次会话发送前也同步 `ensure_server()`；`initialize_session` 和 `run_turn` 内部还会再次 `ensure_server()`。
  - 要求：明确单一职责：
    - lifespan/keepalive 负责启动和重启；
    - 请求链路只等待健康或读取当前 handle；
    - 必要的懒启动只能作为诊断保护，不能造成请求长时间无反馈。
  - 关闭记录：会话消息入口不再同步调用 `ensure_server()`；请求收到后立即返回 `agent_request_received` SSE，再做 session preflight。startup/keepalive 负责拉起 shared server；真正执行 opencode 时如不可用，由 `initialize_session/run_turn` 返回分类错误事件。
  - 验证：`uv run pytest tests/integration/test_opencode_session_stream.py::test_message_stream_emits_received_event_without_starting_opencode_before_preflight -q`。

- [x] `P0` 增加 opencode 不可用的稳定错误分类。
  - 当前问题：用户可能只看到 500、network error 或通用异常。
  - 要求：至少区分：
    - `opencode_bin_missing`
    - `opencode_start_failed`
    - `opencode_health_timeout`
    - `opencode_process_exited`
    - `opencode_version_unsupported`
  - 前端必须居中弹窗展示可理解错误。
  - 关闭记录：`opencode_bin_missing`、`opencode_start_failed`、`opencode_process_exited` 已在 process manager `describe()` / 异常中分类；`opencode_health_timeout`、`opencode_version_unsupported` 已在 opencode health 等待阶段分类，并通过 SSE `error.data.code` 透传给前端。
  - 验证：`uv run pytest tests/unit/test_opencode_compat_backend.py tests/integration/test_opencode_session_stream.py tests/unit/test_opencode_compat_process.py -q`。

- [x] `P0` 处理 opencode stdout/stderr。
  - 当前问题：`Popen(stdout=PIPE, stderr=STDOUT)` 但未消费输出，长期运行有阻塞风险。
  - 要求：写入日志文件或后台 drain，不能保留无人消费的 PIPE。
  - 关闭记录：默认 `opencode serve` stdout/stderr 写入 `data/agent_sessions/opencode/logs/opencode-server.log`，shutdown 时关闭文件句柄。
  - 验证：`test_process_manager_writes_default_process_output_to_log_file`。

- [x] `P1` 启动时记录并校验 `opencode --version`。
  - 当前问题：文档声明验证 `1.14.48`，但运行时没有版本记录和 warning。
  - 要求：启动日志和诊断接口展示 configured bin、resolved bin、version、pid、port、last_error。
  - 关闭记录：`OpenCodeProcessManager.ensure_server()` 启动前解析 `opencode --version`，`describe()` 返回 configured/resolved bin、version、pid、port、last_error、last_error_code、log_file、last_health_at。
  - 验证：`uv run pytest tests/unit/test_opencode_compat_process.py::test_process_manager_describe_reports_resolved_version tests/unit/test_opencode_compat_process.py::test_process_manager_describe_reports_last_health_at -q`。

- [x] `P1` 增加 admin 诊断接口。
  - 建议接口：`GET /api/admin/opencode/status`。
  - 返回：running、pid、port、base_url、bin、version、last_error、last_health_at。
  - 关闭记录：新增 `GET /api/admin/opencode/status`，必须 admin 访问；接口只读取 process manager `describe()`，不触发 `ensure_server()`，避免诊断请求改变进程状态。
  - 验证：`uv run pytest tests/integration/test_healthz.py::test_admin_opencode_status_requires_admin_and_returns_process_status tests/integration/test_healthz.py::test_healthz_reports_opencode_status -q`。

---

## 5. LLM 调度与 opencode provider 边界不清

- [x] `P0` LLM 配置不能继续把 OpenCode 字段作为前端和 API 主语义。
  - 当前问题：v1.0.4 初版把 `opencode_provider_profile/status/tested_at/error/test_result_json` 直接放在 `llm_configs` 和表单 payload 中，后续接 Claude Code、ACP 或其它 Agent runtime 时会继续放大耦合。
  - 要求：不增加用户可见高级参数，不开放自定义 JSON；但数据模型和 API 语义要先改成 runtime-neutral。
  - 关闭记录：新增 `llm_runtime_adapters` 表，以 `(llm_config_id, runtime_backend)` 保存 profile 和手动测试状态；API 响应新增 `agent_runtime_*`，前端新增/编辑表单提交通用 `agent_runtime_profile`；历史 `opencode_provider_*` 字段保留并同步作为兼容层；列表接口优先读取 adapter 表。
  - 验证：`uv run pytest tests/integration/test_llm_configs_api.py -q`；`corepack pnpm --dir frontend exec vitest run tests/guest-llm-config.test.ts tests/sse.test.ts tests/settings-page.test.tsx`。

- [x] `P0` 明确并固化三层职责。
  - `LLMGateway`：只负责选哪条 LLM 配置、全局池随机、会话粘性、失败冷却。
  - `opencode_compat.profiles`：只负责把已选 LLM 配置映射成 opencode provider。
  - `ExternalAgentSession`：只记录当前 CodeAsk session 绑定的 opencode session/config hash/provider profile。
  - 关闭记录：opencode 会话路径只调用 `LLMGateway.select_runtime_config()` 选择配置；provider 生成仍由 `opencode_compat.profiles/config` 完成；`ExternalAgentSession` 只保存 external session、workspace、config hash 和 provider profile。
  - 验证：`tests/integration/test_opencode_session_stream.py::test_post_message_stream_uses_gateway_global_pool_for_opencode_configs`、`tests/unit/test_opencode_compat_backend.py`。

- [x] `P0` 梳理同一用户 turn 发生 provider/config 切换时的会话绑定策略。
  - 当前问题：初始失败后可能切换全局配置并重新 initialize，存在旧 opencode session 绑定或上下文残留风险。
  - 要求：失败发生在 prompt 前、prompt 后、已有 text 后要分别定义行为。
  - 建议：prompt 前失败可切换；prompt 已送出但未出文本时，必须明确废弃旧 opencode session 或标记 failed binding；已有文本后不得自动切换。
  - 关闭记录：当前策略固定为：未输出可见文本前的 opencode error 可清理 sticky 并换下一个全局配置，重新 initialize 生成新的 external session binding；已输出可见文本后不自动切换，直接向前端返回错误，避免多模型拼接同一回答。
  - 验证：`test_opencode_global_pool_retries_next_config_only_before_text`、`test_opencode_global_pool_does_not_switch_after_visible_text`。

- [x] `P1` LLM 配置连接测试和会话真实运行使用同一 provider 生成逻辑。
  - 当前问题：已多次出现测试状态、provider 保存、会话运行不一致的问题。
  - 要求：测试接口、保存表单、会话运行都调用同一 profile/config builder。
  - 关闭记录：抽出 `build_opencode_provider_entry()`，会话 `opencode.json` 和 provider smoke test config 共用同一 provider entry 生成函数；差异只保留 `tool_call=True/False` 和 MCP/permission 外层配置。
  - 验证：`uv run pytest tests/unit/test_opencode_compat_foundation.py::test_provider_entry_builder_is_shared_by_session_and_probe_configs tests/unit/test_opencode_compat_backend.py::test_test_llm_config_smokes_only_selected_provider -q`。

- [x] `P1` 配置失败状态要区分“手动测试失败”和“运行时失败”。
  - 当前问题：列表状态容易被误解成单一连接状态。
  - 要求：保留 `manual_test_status` 和 `runtime_health_status` 的概念，至少在文档中明确当前字段含义。
  - 关闭记录：v1.0.4 当前数据库字段 `opencode_provider_status/tested_at/error/test_result_json` 只表示手动“测试连接”结果；运行时失败不写该字段，运行时健康由 `LLMGateway` 的内存失败计数、冷却和会话粘性处理。后续如需 UI 展示运行时健康，应新增独立字段或诊断接口，不复用手动测试字段。
  - 验证：`tests/integration/test_llm_configs_api.py` 覆盖手动测试落库；`tests/unit/test_llm_gateway.py` 覆盖运行时失败冷却与切换。

---

## 6. reasoning 处理存在字符串过滤兜底残留

- [x] `P0` 明确 reasoning 主路径为 opencode 结构化 part。
  - 当前问题：后端仍使用 `<think>` 风格内容过滤，前端也有 leak guard。
  - 要求：正常路径只从 opencode `reasoning` part 生成 `reasoning_observed`；不展示 raw reasoning。
  - 关闭记录：结构化 reasoning part 继续映射为 `reasoning_observed`；内容中泄漏的 `<think>` 不再复用该事件。

- [x] `P0` 将 `<think>` 内容过滤降级为异常防线，而不是正常适配方案。
  - 要求：
    - 事件命名明确为 `content_reasoning_leak_guard` 或等价名称；
    - trace 中标注“模型服务把 reasoning 混入 content”；
    - 不把该逻辑扩展成任意标签解析器；
    - 不让前端成为主过滤层。
  - 关闭记录：内容泄漏路径改为 `reasoning_leak_detected`，`source=content_reasoning_leak_guard`、`mode=backend_content_guard`；前端行动轨迹显示为“后端异常防线”，主链路不再在 UI 中过滤正文。
  - 验证：`uv run pytest tests/unit/test_opencode_compat_backend.py::test_run_turn_masks_late_think_tag_snapshot_without_reemitting_text -q`；`corepack pnpm --dir frontend exec vitest run tests/session-model.test.ts`。

- [x] `P1` 前端移除业务级 reasoning 标签过滤依赖。
  - 当前问题：前端 `createReasoningLeakGuard("mask_in_ui")` 仍在兜底。
  - 要求：前端只渲染后端已经规范化的可见文本和 reasoning 诊断事件。
  - 关闭记录：会话流主路径已移除前端 `mask_in_ui` 调用；`reasoning-leak-guard` 保留为独立旧工具测试，不再参与主渲染链路。
  - 验证：`corepack pnpm --dir frontend exec vitest run tests/session-workspace.test.tsx tests/session-model.test.ts tests/reasoning-leak-guard.test.ts`。

- [x] `P1` reasoning 事件降噪要稳定。
  - 当前问题：之前出现过大量“推理已隔离”事件刷屏。
  - 要求：按 message/part 聚合，默认每轮最多展示摘要，展开后看 metadata，不看 raw reasoning。
  - 关闭记录：后端按 `part_id` 记录 reasoning 已观察长度，只在首次非空或长度增长超过阈值时发送；历史 trace 接口会把同一 turn 的 `reasoning_observed` 聚合为摘要；前端只展示 redacted metadata，不展示 raw reasoning。
  - 验证：`uv run pytest tests/unit/test_opencode_compat_backend.py::test_run_turn_coalesces_repeated_reasoning_observed_events -q`；`corepack pnpm --dir frontend exec vitest run tests/session-model.test.ts`。

---

## 7. 上下文长度、模型状态和自动压缩可观察性不足

- [x] `P0` 修正 runtime context 指标来源。
  - 当前问题：初始 runtime_state 用当前用户输入字符数；后续可能用 opencode token total，两者语义混用。
  - 要求：字段明确为：
    - `context_used`
    - `context_window`
    - `context_unit = tokens | chars_estimate`
    - `context_metric_source = initial_estimate | opencode_tokens`
  - 关闭记录：初始事件标记 `chars_estimate/initial_estimate`，opencode usage 事件标记 `tokens/opencode_tokens`；旧 `context_size_chars/context_window_chars` 保留兼容。
  - 验证：`tests/unit/test_opencode_compat_backend.py::test_run_turn_emits_runtime_state_from_opencode_token_usage`、`corepack pnpm --dir frontend exec vitest run tests/session-model.test.ts tests/investigation-panel.test.tsx`。

- [x] `P1` 不再硬编码所有模型都是 200k。
  - 当前问题：`context_window = 200_000` 写死。
  - 要求：默认 200k，但 LLM 配置或 provider metadata 可覆盖；UI 显示来源。
  - 关闭记录：新增 `CODEASK_MODEL_CONTEXT_WINDOW_TOKENS` / `Settings.model_context_window_tokens`，默认仍为 200k；会话初始 runtime_state 和 opencode usage runtime_state 都使用该配置。provider metadata 级覆盖仍可在后续引入。
  - 验证：`uv run pytest tests/unit/test_opencode_compat_backend.py::test_run_turn_uses_configured_context_window_for_usage_state tests/integration/test_opencode_session_stream.py::test_post_message_stream_passes_configured_context_window_to_opencode -q`。

- [x] `P1` 补充 opencode compaction 可观察能力。
  - 当前问题：文档说借助 opencode compaction，但 CodeAsk 没有显示是否发生压缩。
  - 要求：如果 opencode 事件可识别 compaction，则记录 trace；不可识别时文档明确当前不可观察。
  - 关闭记录：当前 opencode 1.14.48 `/global/event` 主链路中未稳定暴露可直接判定 compaction 发生的结构化事件；v1.0.4 不伪造“已压缩”状态，只展示 opencode usage token runtime_state。若后续 opencode 暴露 compaction 事件，再映射为专门 trace。

---

## 7.1 Agent 事件耗时需要可观测

- [x] `P0` 每个 Agent 事件必须记录耗时诊断。
  - 当前问题：私有环境出现会话卡在“准备运行环境 / 注入上下文”后没有后续事件时，只靠 raw opencode log 很难判断卡在 prompt 提交、event stream、模型首包还是工具调用。
  - 要求：SSE 返回给前端的事件需要带事件序号、本轮已耗时、距上一事件耗时、提交模型耗时、等待首个后端事件、等待首次响应、是否已有响应；最终完成或失败事件需要记录总耗时。
  - 关闭记录：新增会话级 `AgentTurnTiming`，`opencode_prompt_async_start/done`、`opencode_event_stream_open`、首个后端事件、首个有效响应和 `done/error` 都会写入 `timing`；DB trace 持久化非 token 增量事件和最终 `done/error`，前端行动轨迹展开详情展示耗时字段。
  - 验证：`uv run pytest tests/integration/test_opencode_session_stream.py::test_post_message_stream_uses_opencode_backend_by_setting -q`；`corepack pnpm --dir frontend exec vitest run tests/action-trace-scope.test.tsx`。

---

## 7.1.1 CodeAsk 直连 LLM 请求需要可归因

- [x] `P0` CodeAsk 自身发起的 LLM 请求必须能在日志中区分用途。
  - 当前问题：私有环境只看到 `llm_request_debug`，无法判断这是主会话、会话标题生成、报告生成还是连接测试；同一时间出现 SQLAlchemy 取消日志时，定位成本很高。
  - 要求：不改变模型请求协议，只在 debug 日志和 LLM metadata 中补充观测字段；不能把这类辅助请求写入正常会话上下文。
  - 关闭记录：`generate_single_text()` 增加 `request_purpose/request_id` metadata；会话标题生成传 `session_title_generation` 并记录 started/succeeded/cancelled；报告生成传 `session_report_prepare`。`llm_request_debug` 现在输出 `request_purpose`、`session_id`、`request_id`。
  - 验证：`uv run pytest tests/unit/test_llm_client_adapter.py::test_llm_request_debug_logs_request_purpose_and_session tests/unit/test_session_report_generation.py::test_generate_single_text_records_observability_metadata tests/integration/test_sessions_api.py::test_explicit_session_title_generation_returns_updated_session -q`。

---

## 7.1.2 长 LLM 请求不得持有无关数据库连接

- [x] `P0` 报告生成任务在等待模型期间必须释放前置读取用的 DB session。
  - 当前问题：报告生成原实现把读取 turns/traces/feature/existing report 和等待 LLM 返回放在同一个 `async with session_factory()` 中；如果任务或请求被取消，容易放大 aiosqlite 连接未归还的风险。
  - 要求：先读取生成报告所需的快照数据并关闭 DB session，再调用 LLM；失败/成功状态仍写入内存任务缓存，不改变报告保存语义。
  - 关闭记录：`_run_session_report_prepare_task()` 已拆成“读取快照 → 释放 session → 调 LLM → 更新 prepare status”。新增跟踪测试确认 LLM stream 阶段没有报告读取 session 仍处于打开状态。
  - 验证：`uv run pytest tests/integration/test_session_report_generation.py::test_prepare_session_report_releases_db_session_before_llm_stream -q`。

---

## 7.2 LLM 配置切换后 opencode binding 必须一致

- [x] `P0` 同一会话连续问答中切换 LLM 配置时不能继续使用旧 external session key。
  - 当前问题：私有环境报告中出现 `config_hash` 已更新、但 `external_session_key` 仍指向旧 opencode session 的不一致状态，随后事件流只剩“准备运行环境 / 注入上下文”，没有后续响应。
  - 分析：连续问答中超过全局 LLM sticky 时间或当前配置失败后切换到其它全局配置是预期行为；真正的问题是配置切换后 binding 必须与本轮选中的配置保持一致。当前正常 DB upsert 是同事务更新 `external_session_key/config_hash/status`，本地数据库也没有发现重复 `external_agent_sessions.session_id` 记录；但执行链路里 `initialize_session()` 已经拿到新 binding 后，`run_turn()` 仍重新从 DB 读取一次，历史数据或异常竞争会放大该不一致。
  - 关闭记录：`stream_opencode_response()` 将 `initialize_session()` 返回的 binding 直接传入 `run_turn()`；`run_turn()` 保留不传 binding 时从 store 读取的兼容路径。这样本轮 prompt、summary log、event stream 过滤都以同一个初始化结果为准。
  - 验证：`uv run pytest tests/unit/test_opencode_compat_backend.py::test_run_turn_uses_initialized_binding_after_llm_config_switch -q`；`uv run pytest tests/unit/test_opencode_compat_backend.py tests/integration/test_opencode_session_stream.py tests/unit/test_llm_gateway.py -q`。

---

## 8. 前端会话流状态仍然脆弱

- [x] `P0` 引入按 session id 管理的 stream store。
  - 当前问题：前端用单一 `activeStreamRef` 和内存 snapshot 管理正在生成的会话，切页/切会话/组件卸载仍有风险。
  - 要求：以 session id 为 key 保存：
    - streaming status
    - abort controller
    - live messages
    - live traces
    - runtime state
    - last event time
  - 关闭记录：active stream state 和 live snapshot 已按 session id 存入模块级 Map；产品层仍只允许一个会话同时生成，但消息、行动轨迹、runtime state 不再依赖单个全局 snapshot。
  - 验证：`corepack pnpm --dir frontend exec vitest run tests/session-workspace.test.tsx tests/app-shell.test.tsx`。

- [x] `P0` 切换页面不能中断后端请求。
  - 当前问题：私有环境出现切到设置页后 network error，说明前端生命周期和流请求仍可能耦合。
  - 要求：组件只订阅 stream store；页面卸载不得自动 abort，除非用户点击停止。
  - 关闭记录：组件卸载不 abort；模块级 per-session stream store 在切页后继续接收事件并恢复 UI。真实浏览器层补充停止/不可用/真实 opencode reload-continuity smoke，Vitest 覆盖切到设置页后后台继续生成。
  - 验证：`corepack pnpm --dir frontend exec vitest run tests/app-shell.test.tsx tests/session-workspace.test.tsx`；`corepack pnpm --dir frontend exec playwright test e2e/session-stop.spec.ts --project=chromium`。

- [x] `P0` 切换会话时消息、行动轨迹、模型状态必须同步切换。
  - 当前问题：曾出现标题切换但内容/轨迹停留在旧会话。
  - 要求：选中 session 变化时，优先展示该 session 的 live snapshot 或 DB turns/traces，不能混用旧 selected 状态。
  - 验证：既有 `session-workspace.test.tsx` 覆盖“另一个会话生成时切换消息和行动轨迹”，本轮模块级 snapshot 变更后已重跑通过。

- [x] `P1` 刷新浏览器后的恢复能力必须依赖后端 turns/traces，而不是只靠内存。
  - 要求：刷新后能看到已完成消息和行动轨迹；如果仍在生成，至少显示“该请求可能仍在后端运行/请刷新确认”的稳定状态。
  - 关闭记录：当前完成后的恢复路径通过 `/sessions/{id}/turns` 和 `/sessions/{id}/traces` 读取后端 DB；真实浏览器 live E2E 已在第一轮完成后刷新页面并继续第二轮追问，验证 DB 中保留 `user/agent/user/agent` 顺序。生成中刷新后的深度续流仍是后续增强项，不作为本项关闭范围。
  - 验证：`CODEASK_RUN_LIVE_OPENCODE_E2E=1 CODEASK_REALDATA_BASE_URL=http://127.0.0.1:5173 CODEASK_REAL_DATA_DIR=/home/hzh/.codeask corepack pnpm --dir frontend exec playwright test -c playwright.realdata.config.ts e2e/opencode-backend-live.spec.ts --project=chromium`；最新记录会话 `sess_b4d80f36a5122639`。

---

## 9. 前端行动轨迹仍带旧 Agent 阶段模型

- [x] `P0` 移除或弱化旧阶段流水线 UI。
  - 当前问题：`input_analysis/scope_detection/knowledge_retrieval/sufficiency_judgement/code_investigation` 是旧 native runtime 阶段，不是 opencode 原生事件。
  - 要求：v1.0.4 行动轨迹以 opencode 原始事件映射为准，不用旧阶段解释新事件。
  - 关闭记录：v1.0.4 新事件优先走 `actionTraceFromAgentEvent` 的 opencode/runtime/tool/MCP/reasoning 映射；旧 `scope_detection/wiki_scope_resolution/sufficiency_judgement` 仅保留在 legacy fallback 中用于历史 trace 兼容，不参与 opencode 主链路解释。
  - 验证：`corepack pnpm --dir frontend exec vitest run tests/session-model.test.ts tests/session-workspace.test.tsx`。

- [x] `P0` 重新定义 opencode 行动轨迹事件类型。
  - 建议分组：
    - runtime status：starting/running/retrying/idle/error
    - model usage：model/context/reasoning observed
    - opencode tool：grep/read/glob/list/task
    - CodeAsk MCP：list_features/get_feature_info/list_feature_repos/prepare_worktree/bind_session_features/attachments
    - filesystem evidence：wiki path/report path/repo path
    - error：可展开错误详情
  - 关闭记录：前端行动轨迹当前以 `runtime_status`、`diagnostic`、`warning`、`tool_call`、`tool_result`、`evidence`、`error` 分组展示 opencode 和 CodeAsk MCP 事件；busy、reasoning、leak、context/runtime state 已有专门映射。
  - 验证：`frontend/tests/session-model.test.ts`、`frontend/tests/investigation-panel.test.tsx`、`frontend/tests/session-workspace.test.tsx`。

- [x] `P1` `opencode_busy` 事件要去重且自动消失。
  - 当前问题：之前会话第一轮出现多个 busy 事件。
  - 要求：同一 turn 只显示一个“opencode running/initializing”状态；非 busy 事件到来后转为正常事件。
  - 关闭记录：前端 `appendRuntimeInsight` 按 turn 去重 `opencode_busy`，任意真实 runtime/tool/text/error/done insight 到来后移除 running 状态；历史 trace 恢复时不把 persisted busy 当成长期卡片。
  - 验证：`corepack pnpm --dir frontend exec vitest run tests/session-model.test.ts tests/session-workspace.test.tsx`。

- [x] `P0` opencode 已返回 assistant 终止型 finish 时必须闭合 CodeAsk turn。
  - 当前问题：真实会话 `sess_535ecc82d996ff15` 中，opencode raw event 已有完整助手正文和 `message.updated finish=stop`，但 CodeAsk 先处理 finish 分支并 `continue`，没有把该事件映射为 `done`；后续如果 `session.status idle` 没有被当前流稳定消费，前端会一直显示正在生成，DB 中也不会写入 agent turn。
  - 要求：assistant `message.updated.finish=stop` 等终止型完成事件是可独立闭合本轮的协议事件；收到后必须清理本轮 message 缓存，返回 `done`，并停止继续等待后续 idle 事件。`finish=tool-calls` 不是终止，它表示模型请求工具调用，必须继续等待工具结果和最终回答。该处理只解决协议完成语义，不参与模型决策。
  - 关闭记录：`OpenCodeCompat.run_turn` 在 `_opencode_message_finish(...)` 返回非 `tool-calls/tool_calls` finish 后 yield `done` 并 break；`tool-calls/tool_calls` 分支只清理当前消息缓存并继续消费后续事件；保留已有 `session.status idle` 作为兼容路径，但不再作为唯一完成条件。
  - 验证：`uv run pytest tests/unit/test_opencode_compat_backend.py::test_run_turn_finishes_on_assistant_message_finish_without_idle_status tests/unit/test_opencode_compat_backend.py::test_run_turn_does_not_finish_on_tool_calls_finish -q`；`uv run pytest tests/unit/test_opencode_compat_backend.py -q`。

- [x] `P1` opencode 原生 `task` 事件不能裸展示为未知工具。
  - 当前问题：用户在行动轨迹中看到“准备使用 task”，无法判断这是 CodeAsk 工具、MCP 工具还是 opencode 自身行为。
  - 要求：前端按 opencode 语义显示为子任务/子 Agent 事件，并在展开详情里展示 description、subagent_type 等模型传入的任务摘要；同一 `tool_call_id` 的 repeated running 事件要去重。
  - 关闭记录：`task` 显示为 `opencode 子任务`；`toolCallDetail` 提取 `description/subagent_type`；`appendRuntimeInsight` 按 `turnId + tool_call_id` 去重 repeated running tool call。
  - 验证：`corepack pnpm --dir frontend exec vitest run tests/action-trace-scope.test.tsx tests/session-model.test.ts`。

---

## 10. worktree、workspace 和会话清理未闭环

- [x] `P0` 实现 `OpenCodeCompat.cleanup_session(session_id)`。
  - 当前问题：文档标记 cleanup_session 未完成；删除会话只删除 session storage 和 opencode workspace，不精确清理 repo worktree。
  - 要求：
    - 清理 `data/agent_sessions/opencode/sessions/<session_id>`，并兼容清理旧版 `data/agent_sessions/opencode/<session_id>`；
    - 清理 `data/repos/*/worktrees/<session_id>`；
    - 不关闭 shared opencode server；
    - 写入日志和可观测结果。
  - 关闭记录：`cleanup_session` 删除会话 workspace、旧版 legacy workspace 和 `data/repos/*/worktrees/<session_id>`，不调用 process manager。
  - 验证：`test_cleanup_session_removes_workspace_and_repo_worktrees`。

- [x] `P0` 删除单个会话和批量删除必须调用统一 cleanup 入口。
  - 当前问题：删除逻辑散在 API 和 attachment storage helper 中。
  - 要求：避免只删 workspace、不删 worktree，或只删 DB、不删文件。
  - 关闭记录：`DELETE /sessions/{id}` 和 `/sessions/bulk-delete` 均调用 `_cleanup_opencode_session_resources`。
  - 验证：`test_delete_session_calls_opencode_cleanup`、`test_bulk_delete_sessions_calls_opencode_cleanup_for_owned_sessions`。

- [x] `P1` 实现单会话 idle cleanup，不影响 shared server。
  - 当前问题：验收清单标记未完成。
  - 要求：超时清理会话级临时资源，保留必要 DB 记录和审计。
  - 关闭记录：新增 `opencode_session_idle_cleanup` APScheduler job，按 `CODEASK_OPENCODE_SESSION_IDLE_TTL_SECONDS` 找到 `external_agent_sessions.status=active` 且超时的绑定；清理 session workspace 和 `data/repos/*/worktrees/<session_id>`，随后把绑定标记为 `cleaned`。shared `opencode serve` 不参与单会话清理。
  - 验证：`uv run pytest tests/integration/test_healthz.py::test_lifespan_starts_and_keeps_opencode_server_alive tests/unit/test_opencode_compat_cleanup.py tests/integration/test_opencode_external_sessions.py::test_external_agent_session_store_lists_idle_and_marks_cleaned tests/unit/test_opencode_compat_backend.py::test_initialize_session_recreates_cleaned_external_binding -q`。

- [x] `P1` 清理动作必须有测试。
  - 要求：覆盖单删、批量删、idle cleanup、worktree 存在/不存在、symlink 被删等场景。
  - 关闭记录：单删、批量删、session workspace、repo worktree、idle cleanup 和 cleaned binding 重建均已有测试；Wiki symlink 删除恢复由 workspace 测试覆盖。
  - 验证：`uv run pytest tests/unit/test_opencode_compat_cleanup.py tests/unit/test_opencode_compat_backend.py::test_cleanup_session_removes_workspace_and_repo_worktrees tests/integration/test_opencode_session_stream.py::test_delete_session_calls_opencode_cleanup tests/integration/test_opencode_session_stream.py::test_bulk_delete_sessions_calls_opencode_cleanup_for_owned_sessions -q`。

---

## 11. local dir 与 git 仓库兼容边界需要补强

- [x] `P0` `list_feature_repos` 返回 repo source/status/error/last_synced_at。
  - 当前问题：模型只知道 ready 仓库或 repo not ready，无法解释 local dir/git 同步状态。
  - 要求：让模型能向用户说明为什么当前不能读代码。
  - 验证：`tests/unit/test_opencode_compat_mcp_feature_tools.py`。

- [x] `P0` `prepare_worktree` 对 local_dir/git 的错误恢复提示要明确。
  - 当前问题：local dir 没同步、clone 失败、bare missing 时只暴露底层错误。
  - 要求：返回结构化错误：
    - `repo_not_ready`
    - `repo_clone_failed`
    - `bare_repo_missing`
    - `invalid_ref`
  - 关闭记录：`repo_not_ready`、`repo_clone_failed`、`bare_repo_missing`、`invalid_ref` 已结构化返回。
  - 验证：`tests/unit/test_opencode_compat_mcp_worktree_tools.py`。

- [x] `P1` 增加 local_dir 真实 E2E。
  - 要求：注册 local dir repo，刷新到 ready，opencode 通过 prepare_worktree 读取文件。
  - 关闭记录：新增集成 E2E 覆盖 plain local dir repo：创建真实本地目录，注册 `Repo.SOURCE_LOCAL_DIR`，调用 `RepoCloner.run_clone` 刷新 ready，绑定 external opencode session，随后通过 MCP `codeask_prepare_worktree` 准备 worktree，并验证 `workspace/repos/<repo>/server/app.py` 可读。
  - 验证：`uv run pytest tests/integration/test_opencode_mcp_app_integration.py::test_opencode_mcp_prepare_worktree_supports_plain_local_dir_repo -q`。

---

## 12. Wiki / 报告文件工作区仍需真实场景验证

- [x] `P0` 验证 opencode 能通过 `glob/grep/read ./wiki/` 回答真实 Wiki 问题。
  - 当前问题：live smoke 只验证 symlink 存在，不验证模型实际使用 wiki 文件。
  - 关闭记录：真实浏览器会话 `sess_9c60f250bb43a87f` 第一轮自然语言提问后，模型自主调用 `glob/grep/read` 读取 Wiki 文件并回答。

- [x] `P0` 验证问题报告通过文件目录访问，不再通过 `search_reports/read_report`。
  - 要求：MCP tools/list 中不出现报告检索工具；模型使用 `./wiki/<feature_slug>/problem-reports/verified/`。
  - 关闭记录：`WikiWorkspaceExporter` 已把 verified/draft 报告导出为 `problem-reports/verified/` 和 `problem-reports/drafts/` 文件；opencode MCP `tools/list` 契约快照确认没有 `search_reports/read_report`。
  - 验证：`uv run pytest tests/integration/test_opencode_wiki_workspace.py tests/integration/test_opencode_mcp_app_integration.py -q`。

- [x] `P1` Wiki workspace 导出要记录 manifest 版本/更新时间。
  - 当前问题：模型能看到文件，但 CodeAsk 不容易审计“当时看到的是哪版 Wiki”。
  - 关闭记录：`WikiWorkspaceExporter.export_current()` 在根目录生成 `_manifest.json`，包含 `schema_version`、`view_mode=live`、`exported_at`、feature/document/report count 和每个特性的文件路径摘要。
  - 验证：`uv run pytest tests/integration/test_opencode_wiki_workspace.py::test_wiki_workspace_exporter_materializes_current_wiki_and_reports -q`。

- [x] `P1` 明确 live view 风险。
  - 当前问题：会话进行中 Wiki 变更会影响后续读取。
  - 要求：文档写明 v1.0.4 是 live view；snapshot 是 future。
  - 关闭记录：`docs/v1.0.4/design/opencode-backend.md` 明确 v1.0.4 Wiki 工作区是 live view；后续会话级 snapshot 是 future。

---

## 13. 停止生成能力未完成验收

- [x] `P0` 停止生成必须做真实浏览器 E2E。
  - 当前问题：验收清单标记未完成。
  - 要求：发送长回答，点击停止，前端回到可输入，行动轨迹记录 stop/abort，DB 不保留未完成 user turn。
  - 关闭记录：新增真实浏览器用例 `frontend/e2e/session-stop.spec.ts`，验证流式回答中点击“停止”后触发 abort 请求，用户问题、助手临时回答和临时行动轨迹均从 UI 回滚。
  - 验证：`corepack pnpm --dir frontend exec playwright test e2e/session-stop.spec.ts --project=chromium`。

- [x] `P1` 明确 `abort` 与 `abort + revert` 的边界。
  - 当前问题：文档说深度回滚延期，但用户曾发现上下文残留问题。
  - 要求：当前版本如果不做 deep revert，必须文档明确“停止只保证 CodeAsk DB/UI 清理，不保证 opencode 内部上下文深度回滚”；如果要保证，则必须实现 revert 并 E2E 验证。
  - 关闭记录：验收清单已明确 v1.0.4 不要求完整 `abort + revert` 深度回滚；当前 E2E 验证范围是停止输出、前端临时状态回滚、CodeAsk DB 不保留未完成 turn。opencode 内部 session revert 列为后续增强。

---

## 14. 会话连续性与恢复未完整验证

- [x] `P0` 多轮追问 E2E。
  - 场景：第一轮回答后，第二轮问“你刚刚查阅了哪些资料？”
  - 通过标准：回答能基于上一轮工具/文件证据，不回答成第一次交流。
  - 关闭记录：真实浏览器 opencode live smoke 已扩展为刷新后继续发送第二轮追问，并验证最终 DB 中存在 `user/agent/user/agent` 四个 turn；自然语言 Wiki→代码三轮会话 `sess_9c60f250bb43a87f` 已验证跨轮引用。
  - 验证：`CODEASK_RUN_LIVE_OPENCODE_E2E=1 ... e2e/opencode-backend-live.spec.ts`。

- [x] `P0` 刷新浏览器后继续追问 E2E。
  - 通过标准：消息、行动轨迹和上下文仍可恢复。
  - 关闭记录：`opencode-backend-live.spec.ts` 在第一轮完成后进入会话页、刷新浏览器，再发送第二轮追问；最新验证会话 `sess_b4d80f36a5122639`。
  - 验证：`CODEASK_RUN_LIVE_OPENCODE_E2E=1 CODEASK_REALDATA_BASE_URL=http://127.0.0.1:5173 CODEASK_REAL_DATA_DIR=/home/hzh/.codeask corepack pnpm --dir frontend exec playwright test -c playwright.realdata.config.ts e2e/opencode-backend-live.spec.ts --project=chromium`。

- [x] `P1` shared server 重启后继续会话 E2E。
  - 通过标准：opencode server 换 pid/port 后，原 session 可继续；workspace、provider、MCP token 不串。
  - 关闭记录：Phase 0 已用真实 opencode 验证同一数据目录和 workspace 下 server 重启后可读取原 session message 并继续第二轮 prompt；本轮新增自动化回归，模拟 shared server handle 从 `4100/pid=123` 切到 `4101/pid=456`，再次初始化同一 CodeAsk session 时复用原 external opencode session，不重新创建 session，只更新绑定中的 server url/port/pid。
  - 验证：`uv run pytest tests/unit/test_opencode_compat_backend.py::test_initialize_session_reuses_external_session_after_shared_server_restart -q`；真实记录见 `../specs/opencode-1.14.48-phase0-spike.md`。

---

## 15. 真实 E2E 覆盖不足

- [x] `P0` 补充真实浏览器自然语言场景，禁止使用内部实现提示词。
  - 当前问题：过去测试里出现“请先判断特性和仓库”“不要查代码”等普通用户不会说的话。
  - 要求：测试问题必须模拟普通用户自然表达。
  - 关闭记录：`sess_9c60f250bb43a87f` 使用普通用户话术完成三轮链路，没有显式要求特性判断、仓库判断或工具调用。

- [x] `P0` 增加 Wiki → 代码调查多轮 E2E。
  - 示例流程：
    1. “anything llm 是怎么处理召回的？”
    2. “源码里对应是怎么实现的？”
    3. “结合源码重新解释一下。”
  - 通过标准：第一轮优先读 Wiki；第二轮准备 worktree 并 grep/read；第三轮能结合源码证据。
  - 关闭记录：`sess_9c60f250bb43a87f` 第一轮工具为 `codeask_list_features`、`codeask_get_feature_info`、`codeask_bind_session_features`、`glob/grep/read`；第二轮工具为 `codeask_list_feature_repos`、`codeask_prepare_worktree`、`grep/read`；第三轮不再重复准备 worktree，直接结合前两轮上下文回答。

- [x] `P0` 增加 opencode unavailable E2E。
  - 要求：临时环境中配置不存在的 opencode bin，发送消息后居中错误弹窗，CodeAsk 服务不崩。
  - 关闭记录：后端已有 bin missing / health timeout / version unsupported 分类测试；新增真实浏览器用例验证 SSE error 中的 `opencode_bin_missing` 会显示在居中失败弹窗中。
  - 验证：`corepack pnpm --dir frontend exec playwright test e2e/opencode-unavailable.spec.ts --project=chromium`。

- [x] `P0` 增加升级部署 E2E。
  - 要求：从 v1.0.3 数据目录升级到当前代码，执行 `uv sync`、前端 build、`start.sh`，确认 migration、data key、特性、Wiki、LLM、repo 不丢。
  - 关闭记录：使用临时数据目录先执行 `alembic upgrade 0025` 模拟 v1.0.3 末尾数据库，再通过当前 `start.sh` 启动服务；启动阶段自动迁移到 `0028`，`/api/healthz` 正常，opencode shared server 正常拉起。
  - 验证命令记录：`CODEASK_DATA_DIR=<tmp> CODEASK_DATA_KEY=<key> uv run alembic upgrade 0025` 后，`CODEASK_DATA_DIR=<tmp> CODEASK_PORT=8021 CODEASK_OPENCODE_PORT_RANGE=4321-4321 ./start.sh`；结果 `before=0025 after=0028`。

- [x] `P1` 增加 all LLM config live smoke 的运行记录归档。
  - 当前已有测试入口，但后续每次 provider/profile 变更都必须重新跑并记录配置数量和结果。
  - 关闭记录：验收清单 1.4 已记录 2026-05-16 live smoke 命令和结果；当前数据库 9 条配置全部通过。

---

## 16. 旧 native runtime 边界仍需收敛

- [x] `P0` 确认 v1.0.4 新会话不会静默回退 native runtime。
  - 当前设计允许 `agent_backend=native` 作为诊断配置，但产品契约要求默认 opencode，不可用时明确报错。
  - 要求：文档写清 `native` 只用于测试/诊断；生产新会话不自动 fallback。
  - 关闭记录：默认设置为 `agent_backend=opencode`；opencode 初始化或运行失败时 SSE 返回 `error` 并结束，不调用 native runtime。`native` 仅在显式诊断配置下启用。
  - 验证：`tests/integration/test_opencode_session_stream.py::test_post_message_stream_opencode_exception_returns_error_event`、`::test_post_message_stream_opencode_error_does_not_persist_agent_turn`。

- [x] `P1` 清理前端旧 native 事件概念对 opencode UI 的影响。
  - 当前问题：`scope_detection`、`sufficiency_judgement` 等旧事件逻辑仍存在前端模型。
  - 要求：兼容旧历史 trace 可以保留，但 v1.0.4 新事件不应依赖旧阶段。
  - 关闭记录：opencode/runtime/tool/MCP/reasoning 事件走 `actionTraceFromAgentEvent` 新映射；旧 `scope_detection`、`sufficiency_judgement` 等只保留在 legacy fallback 中用于历史 trace 兼容，不参与 v1.0.4 opencode 主链路解释。
  - 验证：`corepack pnpm --dir frontend exec vitest run tests/session-model.test.ts tests/investigation-panel.test.tsx`。

---

## 17. 安全和权限边界需要补验证

- [x] `P1` 验证 opencode Bash/Edit/Write deny 在真实浏览器场景中生效。
  - 当前 Phase 0 有验证，但版本收口 E2E 需要保留记录。
  - 关闭记录：配置层继续由 `opencode.json` 快照测试确认 Bash/Edit/Write 默认 deny；新增真实浏览器 deterministic SSE 用例，模拟 opencode 返回 Bash/Edit/Write permission denied tool_result，验证前端行动轨迹显示三个失败卡片和 `permission_denied` 错误细节。
  - 验证：`uv run pytest tests/unit/test_opencode_compat_foundation.py::test_build_opencode_config_contains_provider_mcp_and_readonly_permissions -q`；`corepack pnpm --dir frontend exec playwright test e2e/opencode-permission-deny.spec.ts --project=chromium`。

- [x] `P1` 验证 MCP token 跨 session 不可用。
  - 要求：自动化测试和至少一次集成路径证明。
  - 关闭记录：已有 MCP server/route 单测覆盖跨 session token 拒绝；本轮新增 FastAPI app 集成测试，使用 `sess_allowed` token 请求 `sess_other` endpoint，返回 `401 invalid mcp token`。
  - 验证：`uv run pytest tests/integration/test_opencode_mcp_app_integration.py::test_opencode_mcp_rejects_cross_session_token_at_app_boundary -q`。

- [x] `P1` 验证 external_directory allowlist 不越权。
  - 当前允许 wiki workspace 和 session worktree symlink target。
  - 要求：opencode 不能读取 CodeAsk 数据目录中未授权路径。
  - 关闭记录：`build_opencode_config` 默认 deny Bash/Edit/Write；`external_directory` 固定为 `* = deny`，只允许当前 session 的 wiki symlink target 和 worktree target pattern，不把整个 CodeAsk data dir 暴露给 opencode。
  - 验证：`uv run pytest tests/unit/test_opencode_compat_foundation.py::test_build_opencode_config_contains_provider_mcp_and_readonly_permissions tests/unit/test_opencode_compat_foundation.py::test_build_config_allows_codeask_external_symlink_targets -q`。

---

## 18. UI / 产品体验未收口点

- [x] `P1` LLM 配置新增/编辑连接测试状态继续保留真实落库语义。
  - 当前刚修过，后续重构 provider/profile 时不得退化成前端临时状态。
  - 关闭记录：新增/编辑表单测试结果作为隐藏表单状态，保存时随配置字段一起提交；列表只显示数据库返回状态。本轮 provider entry 重构后重跑设置页测试，未破坏该语义。
  - 验证：`corepack pnpm --dir frontend exec vitest run tests/settings-page.test.tsx`。

- [x] `P1` 错误弹窗统一居中展示。
  - 当前要求：失败必须弹窗；成功低密度居中浮层；不能顶部一闪而过或隐藏在容器内。
  - 关闭记录：`AppFeedbackProvider` 继续使用居中 success toast 和 blocking error dialog；opencode unavailable 真实浏览器用例验证 SSE error 会显示为居中失败弹窗。
  - 验证：`corepack pnpm --dir frontend exec vitest run tests/app-feedback.test.tsx`；`corepack pnpm --dir frontend exec playwright test e2e/opencode-unavailable.spec.ts --project=chromium`。

- [x] `P1` 会话数据区模型名称和上下文进度必须和流式 runtime_state 同步。
  - 要求：生成中持续刷新；完成后保留最终状态。
  - 关闭记录：前端 `runtimeStateFromEvent` 以 `runtime_state` SSE/trace 为来源，显示模型名称和 `context_used/context_window`；本轮 context window 改为后端配置驱动后，session model 测试继续覆盖 runtime state 映射和显示单位。
  - 验证：`corepack pnpm --dir frontend exec vitest run tests/session-model.test.ts`。

- [x] `P1` 设置页 admin 子页面必须支持刷新恢复。
  - 当前问题：设置页内部 admin 子页面曾只保存在组件本地状态，刷新浏览器后总是回到默认“运行状态”。
  - 要求：子页面状态进入 URL 或等价路由状态；刷新、复制链接、App 重新挂载后仍停留在同一子页面。
  - 关闭记录：设置页使用 `#/settings?page=<page>` 记录 admin 子页面；`SettingsPage` 由 `AppShell` 路由状态驱动，不再自行保存 `adminPageId`。
  - 验证：`corepack pnpm --dir frontend exec vitest run tests/settings-page.test.tsx tests/wiki-routing.test.ts`；开发服务器真实浏览器输出 `browser-settings-subpage-refresh: PASS`；生产构建 + `start.sh` 临时空库真实浏览器输出 `temp-start-admin-settings: PASS`。

- [x] `P2` 增加 opencode backend 状态可视化。
  - 内容：版本、pid、port、健康状态、最后错误、当前活动 session 数。
  - 关闭记录：新增设置页 admin 面板“opencode 后端状态”，读取 `GET /api/admin/opencode/status`，展示 running、version、pid、port、active session count、last health、bin、log file 和 last error。后端接口增加 `active_session_count`，只读状态，不触发进程启动。
  - 验证：`uv run pytest tests/integration/test_healthz.py::test_admin_opencode_status_requires_admin_and_returns_process_status -q`；`corepack pnpm --dir frontend exec vitest run tests/settings-page.test.tsx tests/investigation-panel.test.tsx`。

---

## 19. Agent 事件接口暴露宿主机绝对路径

- [x] `P0` 后端返回给前端的 Agent 事件必须做路径脱敏。
  - 当前问题：opencode `read` / `grep` / MCP tool 事件中可能出现宿主机绝对路径；即使前端展示层过滤，浏览器 Network 中仍可看到原始路径。
  - 要求：只处理返回给前端的 SSE 和历史 traces API；不能修改数据库 trace、raw opencode JSONL、工具执行参数、模型上下文和报告生成链路。
  - 关闭记录：新增 `src/codeask/sessions/trace_redaction.py`，SSE 非 `text_delta/done` Agent 事件返回前使用脱敏副本；`/api/sessions/{session_id}/traces` 返回前对 payload 副本脱敏。当前会话目录内路径显示为会话相对路径，外部宿主机绝对路径显示为 `[外部绝对路径已隐藏]`。
  - 2026-05-19 回归补充：覆盖新目录结构 `agent_sessions/opencode/sessions/<session_id>/...`，尤其是 opencode `read` 的 `tool_call.arguments_summary.filePath`、`tool_result.summary/message/path`。后端 SSE 和历史 traces API 都只返回 `workspace/...` 相对路径；前端展示层保留同样的兜底脱敏。
  - 2026-05-19 slashless 路径补充：真实会话 `sess_535ecc82d996ff15` 暴露 opencode 完成事件会把 `/home/hzh/...` 变成 `home/hzh/...` 后写入 `summary/message`；旧正则会从中间 `/hzh/...` 匹配，导致前端看到 `homeworkspace/...`。已修正后端和前端正则边界，slashless agent session path 会完整转换为 `workspace/...`。
  - 验证：`uv run pytest tests/unit/test_session_trace_redaction.py tests/integration/test_opencode_session_stream.py -q`；`corepack pnpm --dir frontend exec vitest run tests/action-trace-scope.test.tsx`；相关 ruff/eslint/tsc 检查通过。

---

## 20. 会话消息换行和上下文指标刷新

- [x] `P0` 用户气泡必须保留用户输入中的换行。
  - 当前问题：用户消息和助手消息共用 Markdown 渲染，普通换行在气泡中被 Markdown 折叠为空格，导致用户实际发送的多行内容和界面展示不一致。
  - 关闭记录：用户消息改为纯文本节点渲染，样式使用 `white-space: pre-wrap`；助手消息继续使用 Markdown 渲染。
  - 验证：`corepack pnpm --dir frontend exec vitest run tests/message-stream.test.tsx`；`CODEASK_RUN_LIVE_SESSION_LONG_UI_E2E=1 ... playwright test -c playwright.realdata.config.ts e2e/session-long-ui-live.spec.ts --project=chromium`。

- [x] `P0` 模型上下文指标不能在每轮开始时被初始估算清零。
  - 当前问题：每轮开始后端都会发送基于当前用户输入长度的 `initial_estimate` runtime_state；前端直接覆盖已有 runtime state，导致界面显示从 `0k / 200k` 或很小数值重新开始。
  - 关闭记录：新增 `mergeRuntimeState`，当已有更大的 `opencode_tokens` 观测值时，新的 `initial_estimate` 只更新模型/配置元信息，不回退上下文用量；实时 SSE 和历史 trace 回放共用该逻辑。
  - 验证：`corepack pnpm --dir frontend exec vitest run tests/session-model.test.ts`；真实浏览器长对话会话 `sess_ff0d65dc59be064c` 中逐轮观察到 `initial_estimate` 小值和持续增长的 `opencode_tokens`，前端未回退显示为 `0k / 200k`。

---

## 21. 建议执行顺序

### P0 收口批次 A：契约一致性

- [x] 更新 v1.0.4 文档状态矩阵。
- [x] 修正 MCP schema 与文档一致。
- [x] 实现动态上下文组装。
- [x] 新增 MCP schema 快照测试。

### P0 收口批次 B：运行时稳定性

- [x] 收口 opencode 进程生命周期。
- [x] 增加 opencode 不可用错误分类。
- [x] 处理 stdout/stderr。
- [x] 明确 LLM config/provider/session binding 切换策略。

### P0 收口批次 C：前端流和真实事件

- [x] 引入 session stream store。
- [x] 取消旧阶段 UI 对 opencode 主链路的误导。
- [x] 修正 context metrics 字段语义。
- [x] reasoning 主路径切回结构化 part，字符串过滤仅作为异常防线。

### P0 收口批次 D：清理与 E2E

- [x] 实现 cleanup_session/worktree 清理。
- [x] 补 Wiki → 代码调查自然语言 E2E。
- [x] 补停止生成 E2E。
- [x] 补升级部署 E2E。

---

## 22. v1.0.4 关闭前必须重新确认

- [x] PRD、Design、Plan、Acceptance Checklist、本文档状态一致。
- [x] 所有 P0 已关闭，或被用户明确同意延期并迁移到 future/下一版本。
- [x] 每个 P0 关闭项都有自动化测试或真实浏览器 E2E 记录。
- [x] opencode 版本、LLM 配置数量、测试 session id、数据目录、测试命令均已记录。
- [x] 不存在“文档写完成，但验收矩阵未完成”的状态。
- [x] 2026-05-18 用户已确认人工验收和验证完成。
- [x] 2026-05-19 补充 opencode 完成事件闭合、`finish=tool-calls` 边界、`task` 子任务展示、长对话 UI、特性源码调查和路径脱敏回归；自动化与真实浏览器 E2E 均已记录。
- [x] 本次先推送 `main`，暂不推送 `v1.0.4` 分支。
