# LLM 配置 / 会话处理 链路加固

承接 [`opencode-session-resume.md`](./opencode-session-resume.md)（一会话一 id、清理/轮转后同 id 恢复，已合 main 8dd97dd）。本计划处理那次 review 暴露的 6 个设计问题，按严重度排序、逐项给出方案 + 改动点 + 风险 + 测试。

实现原则（用户要求）：**分步落地，每步独立可测、绿了再下一步，绝不引入异常错误**。建议落在一个分支 `fix/llm-session-hardening`，按下面顺序提交。

---

## P1 — config_hash 收窄到 provider 字段（消除环境抖动触发 dispose）🟠

**问题**：`initialize_session` 用整份 opencode config 的 `config_hash`（`backend.py:_config_hash`）判断 `config_changed`，而该 config 含**环境量**（openviking MCP url/port、CodeAsk MCP url/token、external_directory 路径）。openviking 重启换端口会让 `config_changed=True`，触发本不该有的 `/instance/dispose`（把正用的实例拆了重载）。实测 sess_babea 的 hash 变化正是环境量所致、provider 未变。

**方案**：把"是否需要 dispose 重载"的依据从整份 config_hash 改为**仅 provider 块**的比较。`build_opencode_config` 产出的 `config["provider"]` 正是 LLM provider 配置（key/model/baseURL/headers/npm），不含环境量。利用已持久化的 `existing.config_json`：
- `provider_changed = (existing.config_json or {}).get("provider") != config.get("provider")`
- `need_dispose = provider_changed or workspace_moved`（dispose 只为 provider 变）
- `need_write = existing.config_json != config or not opencode_json.exists()`（文件仍按整份 config 决定要不要重写，保证 opencode.json 始终是最新环境量）
- `config_changed`（用于"首轮/强制新建"分支判定 existing is None）保持不变。

无需迁移（`config_json` 已存）。

**改动**：`backend.py initialize_session` 把现有 `config_changed`/dispose 判定拆成 `need_write` 与 `need_dispose` 两个量。
**风险**：低。仅收窄 dispose 触发条件，恢复语义不变。
**测试**：新单测——provider 不变但整份 config 变（模拟 openviking 端口变）→ 复用同 id、**不** dispose、但重写 opencode.json；provider 变 → dispose。沿用现有 cleaned→resume / config-switch 用例。

---

## P2 — 恢复探针改用轻量端点 + 仅在需要时探 🟡

**问题**：每个续聊轮次都用 `list_messages`（返回**整段历史**）来判断 session 是否还在（`_external_session_is_usable`）。长对话里=每轮把全部历史拉回扔掉。

**方案**：两步收敛——
1. **改轻量端点**：opencode 有 `GET /session/{id}`（仅元信息）。新增 `http.get_session(session_id, directory)`，`_external_session_is_usable` 改用它；404/错误=不可用。
2. **仅在有疑时探**：正常 `active` 且 server 未变的会话，session 必在，无需探。`need_probe = existing.status != "active" or existing.server_url != server.base_url or existing.pid != server.pid`（即：被清理过、或后端/opencode 重启过）。不探时直接复用；万一 active+同 server 却失联（极罕见），`run_turn` 的 prompt 会自然抛 opencode 错误。

**改动**：`http.py` 加 `get_session`；`backend.py` 探针逻辑加 `need_probe` 门 + 换端点；`HttpClientLike` 协议加 `get_session`。
**风险**：低-中。"仅在需要时探"改变了探针频率——需确保被清理/重启后仍探（这正是 need_probe 覆盖的）。
**测试**：单测——active+同 server→不探直接复用；cleaned→探；server 变→探；探针 404→抛 `OpenCodeSessionResumeError`（透传）。fake http 加 `get_session` + `missing_session_ids` 复用。

---

## P3 — opencode server_data 保留策略（防无限增长）🟠

**问题**：`cleanup_session` 只删 workspace+worktree，**从不动 server_data**；全仓库无 server_data 裁剪。一会话一 id 永久恢复后，对话历史只增不减。

**方案**：加**二级清理 = 过期销毁**（一级=现有 6h idle → cleanup_session 删目录、标 cleaned、**仍可恢复**）：
- 新 setting `opencode_session_history_retention_days`（默认 30，`ge=1`）。
- 二级 job（复用 cleanup 调度，更长周期）找 `updated_at < now - retention_days` 的 binding：
  - 调 opencode `DELETE /session/{id}`（新增 `http.remove_session(session_id, directory)`）永久删 server_data；
  - **保留** `external_agent_sessions` 行、把 `status` 置为新状态 **`expired`**（不是删行）。
- 之后用户若再对该会话发消息：`initialize_session` 见 `existing.status == "expired"` → **抛"会话已过期"错误，不探针、不新建、不被 force_new 复活**。用户要继续=新建会话（旧 transcript 仍在 `session_turns`/UI 可见，只是这条会话不能再续）。**彻底删除即终态过期**，符合"删了就不该再无声新建"。
- 与"恢复探针失败"区分：探针失败=透传 opencode 原始错误（opencode 意外丢了）；`expired`=CodeAsk 主动销毁，给明确文案"会话已过期（超过 N 天未活动，历史已清理，请新建会话）"。

**改动**：`settings.py` 加配置；**迁移**：`external_agent_sessions` 的 status CheckConstraint 增 `expired`（alembic batch 重建表）；`db/models` 同步；`sessions.py` 加 `list_expired_session_ids(before)` + `mark_expired(session_id)`；`http.py` 加 `remove_session`；`backend.py initialize_session` 增 `expired` 分支（抛 `OpenCodeSessionExpiredError`）；`app.py` 加二级 job；`cleanup.py` 加 `expire_idle_sessions` helper；`messages.py` 捕获并呈现过期错误。
**风险**：中。①`DELETE /session/{id}` 需带 `directory`，而二级时 workspace 目录早被一级删了——**实现时必须先验证 DELETE 在目录不存在时的行为**（opencode 按目录路径 hash 定位 project，可能仍能删；若不行，删前临时 `mkdir` 该路径）。②`expired` 是终态、不可恢复——只对确实超长闲置者执行，默认 30 天。
**测试**：单测 `expire_idle_sessions`（找出过期、调 remove、标 expired、失败隔离）；http `remove_session`；`initialize_session` 见 expired → 抛 `OpenCodeSessionExpiredError`（不新建、不探针）；集成——标 binding 远古 updated_at → 跑二级 → opencode DELETE 被调 + 行标 expired + 再发消息得过期错误。**实现期补 live 验证**：真实 opencode DELETE 后 `GET` 返 404。

---

## P4 — runtime_fields_changed 纳入 reasoning_profile 🟡

**问题**：`api_service.py:137-152` 判定"哪些字段变要重置连通测试状态"漏了 `reasoning_profile`/`reasoning_profile_json`。改 reasoning 后连通状态仍显示旧"ok"。

**方案**：把 reasoning 两字段加入 `runtime_fields_changed`。
**改动**：`api_service.py` 一处。
**风险**：极低。
**测试**：单测——仅改 reasoning_profile → 连通状态被重置为 unknown。

---

## P5 — 每轮选中的 config/model 落到 turn 级元数据（可观测性）🟡 ✅ 复核后发现已满足，无需改动

**复核结论**：`messages.py:_opencode_runtime_state_event` 产出的 `runtime_state` 事件**已携带** `config_id`/`model_name`/`provider_id`/`scope`/`is_global_pool`，且经 `persist_runtime_event_trace` **按 turn_id 落库**；池化轮转时每次尝试都会重发该事件。即"哪条配置/哪个模型答的这轮"已在 turn 级 trace 可查。**本项不动代码**。原方案如下（已无需执行）：



**问题**：会话不绑定具体配置，池化下相邻轮次可能不同模型作答而前端无显式标识；"哪条配置/哪个模型答的这轮"只散在 runtime trace。

**方案**：现有 `_opencode_runtime_state_event(selection, ...)` 已携带 provider_id；扩展为同时带 `config_id` + `model_name`，并确保写进该轮的持久化 trace（`persist_runtime_event_trace` 已落库）。前端可选地在该轮展示（本计划只保证后端可查，不强制改 UI）。
**改动**：`messages.py` `_opencode_runtime_state_event`（加字段）；确认 trace 持久化包含之。
**风险**：低。纯增字段。
**测试**：单测/集成——一轮对话后 trace 含 selected config_id + model。

---

## P6 — 池化故障转移逻辑收口（去重）🔴 ⛔ 本轮延后（用户决定暂不做）

**问题**：同一套"池化选择 + 健康追踪 + 失败排除并切下一个"算法实现了两遍：
- LiteLLM 辅助链路 `gateway.stream`（`gateway.py:184-280`，自带 inline attempt/exclude/reselect）。
- opencode 主链路 `messages.py`（`while True` + `_retry_next_opencode_global_config` + `retrying_with_next_config`）。
共享状态（`_global_usage`）但控制流各写各的，策略一改要同步两处。

**方案（保守，不强行合并执行循环）**：把**轮转决策**抽成 gateway 上的单一对象 `RuntimeConfigRotation`：
- `start() -> selection | busy`
- `on_failure(selection, error_data) -> next_selection | None`（内部：判 `_counts_against_config_health` → `record_failure` + `clear_sticky` → 加 excluded → `_select_config` 下一个；返回 None=停止轮转）
两条链路都消费它：`gateway.stream` 的 inline 块（212-245）和 `messages.py` 的 `_retry_next_opencode_global_config` 都改为调用同一对象。**两个执行循环（inline event stream vs initialize+run_turn+SSE）保持独立**，只把"策略"收进一处。

**风险**：高——`gateway.stream` 是 title/report/连通测试的命脉，行为必须 1:1 不变。
**收敛判据**：若抽象后两个调用点没有明显变简洁、或行为难以保证一致，**则降级**为只抽取决策谓词（共享一个 `should_rotate_and_next(...)` 纯函数），不动循环骨架。
**测试**：必须全程保持 `gateway` 池化重试与 `messages` 池化重试的现有单测/集成全绿；不新增行为，只重构。先跑基线记录两条路径的现有测试，再重构，逐一对比。

---

## 实施顺序与验证总纲

本轮范围 **P1–P5**（P6 延后）。顺序：
1. **P4**（最小、独立）→ 2. **P1**（直接关联上次改动，低风险）→ 3. **P2**（探针）→ 4. **P5**（trace 字段）→ 5. **P3**（保留策略 = 过期销毁，含 live 验证 DELETE 行为）。

每步：`ruff check` + 该步相关 `pytest` 绿，再进下一步。全部完成后：
- 全量 `pytest`（opencode/session/llm 全套）绿；
- 去代理重启后端 + live E2E 复跑（清理后恢复、配置切换、**新增**：过期删除后新建、openviking 端口变不触发 dispose）；
- 不提交、不 push，交付审阅后再按指示合并。

## 待确认
- P3：过期处理已定为 **opencode DELETE + 标 `status=expired`（保留行）→ 再发消息报"会话已过期"、不新建**（用户已确认）。仅剩**默认保留天数**：建议 **30 天**，可调。
- P6：两条链路均在用（A=标题/报告的 LiteLLM 一次性调用，B=主对话；你当前 2 配置无默认=池化，两条的轮转都会跑到）。是否接受"保守收口（抽策略对象，保留两个执行循环），必要时降级为共享谓词"？鉴于 A 低频、P6 风险最高，**也可选择不做 P6、只保留其余 5 项**。
- 是否就按 P4→P1→P2→P5→P3→P6 顺序、单分支分步提交。
