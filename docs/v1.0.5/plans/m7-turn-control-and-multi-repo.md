# M7 — 会话超时、停止语义与多代码仓上下文加强

> 版本：v1.0.5
> 状态：Completed
> 关联：[acceptance §4](./acceptance-checklist.md) · [m6](./m6-sync-completeness-and-events.md)
> 来源：2026-05-28 负责人使用反馈，三条产品缺陷。

---

## 0. 背景与范围

2026-05-28 在使用真实库时，负责人发现三处当前实现与产品预期不一致：

1. **超时**：一轮正在持续响应的对话被绝对墙钟切断，前端报 `Agent 运行失败：opencode turn did not finish before timeout`。
2. **停止**：用户点击 Stop 后整轮被回滚清空，但实际需求是"截断保留 + 在已发生的轨迹之上继续追加用户输入"。
3. **多代码仓**：特性绑定多个仓库时，模型默认只选一个；只有用户在会话里显式追问才扩展。

三条都属于"功能存在但语义错位"，不需要新表/新业务模块，改动集中在：

- 后端 `src/codeask/agent/opencode_compat/backend.py`（超时常量与 streaming 守护）
- 后端 `src/codeask/sessions/messages.py`（cancel 路径不再 rollback，改为持久化截断轮次）
- DB 模型 `src/codeask/db/models/session.py` + 一条 alembic 迁移（`SessionTurn` 增加 `stopped_at` 列）
- API schema `src/codeask/api/schemas/session.py`（暴露 `stopped_at` 给前端）
- 前端 turn 列表 / 会话视图（展示"已停止"角标）
- Agent prompt：`src/codeask/agent/opencode_compat/prompts.py` 与 `context.py`

### 锁定决策（2026-05-28 负责人拍板）

- **① 超时**：
  - **整体（绝对墙钟）超时延长到 3600s**（原 600s）。
  - **每事件刷新**的无进展超时设为 **600s**（原 30s）。语义：只要 600s 内有任何 event 流出就重置计时器；连续 600s 没有任何信息返回才超时。
- **② 停止**：
  - 取消旧的 `rollback_session_turn` 删表行为。
  - Cancel 时把已收集的 `assistant_chunks` 持久化为 agent 轮次，AgentTrace（已发生的 tool_call / tool_result）保留。
  - `SessionTurn` 增加 `stopped_at TIMESTAMP NULL`；非空表示这条 agent 轮次是被用户中断的。
  - **必须做好测试**：单测覆盖中断时机（中断前已经有 text_delta / 中断前只有 tool_call / 中断时还在等首个 token 三种状态），集成测试覆盖"中断→新输入→模型上下文可见前一轮截断内容"全链路。
- **③ 多代码仓**：仅做 **Step A**（prompt 加多仓约束）+ **Step B**（context bound-features 段落明列 ready repos）。**不做** Step C 的"绑定特性时自动 prepare 全部仓"——避免无谓的磁盘/同步开销。

---

## ① 会话超时：删除短墙钟，统一两层守护

### 现状

`src/codeask/agent/opencode_compat/backend.py`

```py
# :95-97
_EVENT_POLL_SECONDS = 0.5
_TURN_NO_PROGRESS_TIMEOUT_SECONDS = 30.0
_TURN_WAIT_TIMEOUT_SECONDS = 600.0
```

- `:1079` 用 `started_at` 比 `_TURN_WAIT_TIMEOUT_SECONDS`（绝对墙钟，**不看进展**），超过 600s 直接抛 `opencode turn did not finish before timeout`。
- `:1101` 在每个 `_event_belongs_to_session(...)` 命中的事件上把 `last_progress_at = time.perf_counter()`。
- `:1116` 用 `now - last_progress_at` 比 `_TURN_NO_PROGRESS_TIMEOUT_SECONDS`（无进展守护），目前阈值 30s。

### 目标行为

- 整体墙钟 = **3600s**（一轮最长 1 小时）。
- 无进展超时 = **600s**（连续 600s 没事件才认作卡死）。
- `last_progress_at` 在**每个**属于当前 session 的 event（含 `text_delta` / `tool_call` / `tool_result` / `reasoning_*` 等）上都要刷新。

### 实施步骤

#### ①-1 调整常量
- 文件：`src/codeask/agent/opencode_compat/backend.py:95-97`
- 改：
  ```py
  _EVENT_POLL_SECONDS = 0.5
  _TURN_NO_PROGRESS_TIMEOUT_SECONDS = 600.0   # 原 30.0
  _TURN_WAIT_TIMEOUT_SECONDS = 3600.0          # 原 600.0
  ```
- 注：保持两层超时，不允许移除任何一条，避免极端死循环把 server 占满。

#### ①-2 校验 `last_progress_at` 覆盖面
- 文件：`backend.py:1077-1136` 的 `_stream_events_with_status_poll`。
- 现状仅在 `_event_belongs_to_session(...)` 命中时刷新；确认所有当前 session 的 event 类型都满足 `_event_belongs_to_session`，否则在那里补充。重点确认 `tool_call_start`、`tool_call_delta`、`tool_result`、`reasoning_observed`、`text_delta` 五类都能命中。
- 不需要扩大到 "任意 event"——只要保证当前 session 的事件能刷新即可。

#### ①-3 错误日志保留
- 触发 `_TURN_NO_PROGRESS_TIMEOUT_SECONDS` 时，把"卡死前已观察到的最后事件类型 + last_progress_at 距 now 的差"写进 `_synthetic_session_error_event` payload，便于定位。新增字段：`{"no_progress_seconds": int}`。
- 触发 `_TURN_WAIT_TIMEOUT_SECONDS` 时同样：`{"absolute_wait_seconds": int}`。

### 测试

- 单测（新增）：`tests/unit/test_opencode_turn_timeout.py`
  - 用 `monkeypatch.setattr(time, "perf_counter", ...)` 或注入虚拟时钟，构造三种场景：
    1. 持续 event：模拟每 50s 来一个 `text_delta`，跑 700s，**不应**触发 no-progress；3600s 内不应触发墙钟（仅在 >3600s 触发）。
    2. 中断 event：先 100s 有 text_delta，然后 700s 完全没事件 → 触发 no-progress，error payload `no_progress_seconds >= 600`。
    3. 持续小心跳但越过墙钟：每 500s 一个 event，跑到 3600s → 触发墙钟，error payload `absolute_wait_seconds >= 3600`。
  - 断言 `_synthetic_session_error_event` 的 `message` 与新增字段。
- 现有集成测试：`tests/integration/test_opencode_compat_backend.py` 或相邻文件，把模拟卡死场景的等待时间从 30s 收紧或拉长以匹配新阈值；不应回归现有"正常流跑通"用例。
- 回归：不影响 `_TURN_NO_PROGRESS_TIMEOUT_SECONDS` 旧用法的常量名（保持，避免破坏既有 import）。

---

## ② 停止：截断保留，不再 rollback

### 现状

`src/codeask/sessions/messages.py`

```py
# :470-472
except asyncio.CancelledError:
    await rollback_session_turn(request.app.state.session_factory, session_id, turn_id)
    raise

# :638-656
async def rollback_session_turn(...):
    delete AgentTrace WHERE session_id=? AND turn_id=?
    delete SessionTurn WHERE session_id=? AND id=?
```

- opencode 那一侧的停止 `backend.py:576-585 abort_turn` 行为正确，**只需改 CodeAsk 自己的清表**。
- `SessionTurn` 当前没有 `status` / `stopped_at` 字段，需 schema 改动。

### 目标行为

- 用户点击 Stop（前端调 `POST /api/sessions/{sid}/turns/{tid}/abort` → `messages.py` 流捕获 `CancelledError`）：
  1. **不删** AgentTrace；
  2. **不删** 用户 turn；
  3. 把已收集的 `assistant_chunks` 持久化为一条 `role='agent'` 的 turn，`stopped_at = now()`；若 `assistant_chunks` 为空（中断时模型尚未吐字），仍写入一条空 content 但 `stopped_at` 非空的占位 turn——前端能据此区分"中断在哪一步"；
  4. 下一轮用户输入时，构造 prompt 的逻辑天然会带入这条截断 turn，模型可以"接着"截断处继续。

### 实施步骤

#### ②-1 Schema 改动

- 文件：`src/codeask/db/models/session.py:91-109`
  - 在 `SessionTurn` 中新增：
    ```py
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ```
- 新 alembic 迁移：`alembic/versions/20260528_0032_session_turn_stopped_at.py`
  - `revision = "0032"`，`down_revision = "0031"`。
  - `upgrade`: `op.add_column("session_turns", sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True))`。
  - `downgrade`: `op.drop_column("session_turns", "stopped_at")`（这条迁移可逆）。

#### ②-2 API schema 同步

- 文件：`src/codeask/api/schemas/session.py:43-53`
  - `SessionTurnResponse` 增加 `stopped_at: datetime | None = None`。
- 不需要新接口；既有 `GET /api/sessions/{sid}/turns` 自动透出该字段。

#### ②-3 持久化"截断 agent 轮次"

- 文件：`src/codeask/sessions/messages.py:470-472`
  - 把 cancel 分支替换为：
    ```py
    except asyncio.CancelledError:
        partial = "".join(assistant_chunks).strip()
        await persist_stopped_agent_turn(
            request,
            session_id,
            content=partial,
            parent_turn_id=turn_id,
        )
        raise
    ```
- 新函数 `persist_stopped_agent_turn`：复用既有 `persist_agent_turn` 写入逻辑（同文件附近），但在写入时把 `stopped_at = datetime.now(timezone.utc)` 一并落库；如果 `partial == ""`，也要写一条（标记中断时机）。
- **删除** `rollback_session_turn` 函数及其唯一调用点。如果有其它路径在用（grep 验证），先确认无引用再删；若有路径同样需要"保留语义"，统一改为 stopped。

#### ②-4 前端展示

- 文件（候选）：
  - `frontend/src/components/session/SessionTurns.tsx`（或同目录下的轮次卡片组件，按当前结构找）。
  - turn list/卡片：检测到 `turn.role === "agent" && turn.stopped_at` 时显示一个灰色 chip："已停止"，hover tooltip 显示 stopped 时间。
  - 若 content 为空且 stopped_at 非空：显示占位文案"用户在模型回复前停止了这一轮"。
- 不需要新接口；类型 `frontend/src/types/api.ts` 的 `SessionTurnResponse` 同步加 `stopped_at: string | null`。

#### ②-5 Abort 触发链路确认（无须改代码，只验证）

- `frontend → POST /api/sessions/{sid}/turns/{tid}/abort` → `src/codeask/api/sessions.py:552-558` → `app.state.opencode_compat.abort_turn(session_id)` → `backend.py:576-585` 调 `client.abort_session`。
- opencode 关闭流后，`messages.py:395-465` 的 `async for event in compat.run_turn(...)` 抛 `CancelledError` → 进入 ②-3 改后的 except 分支。
- 验证步骤见测试 ②-T2。

### 测试（**必须做齐**）

#### ②-T1 单测：持久化截断 turn 三态
- 文件：`tests/unit/test_session_turn_stopped.py`（新增）。
- 用例：
  1. `assistant_chunks = ["hello ", "wor"]` 时中断 → DB 中 agent turn `content="hello wor"`、`stopped_at` 非空。
  2. `assistant_chunks = []`、尚有 tool_call trace 时中断 → agent turn `content=""`、`stopped_at` 非空；AgentTrace 行**保留**（断言行数没掉）。
  3. `assistant_chunks = []`、无 trace 时中断 → 仍写一条 `content=""` 的 agent turn 占位。

#### ②-T2 集成：abort → 续问 → 模型看到截断
- 文件：`tests/integration/test_opencode_abort_continuation.py`（新增）或合入既有 sessions 集成。
- 步骤：
  1. POST 一条会让模型多次工具调用的 user turn。
  2. 等到 sse 流出现至少一条 `tool_call` 后，触发 `POST /turns/{tid}/abort`。
  3. 断言：
     - GET `/api/sessions/{sid}/turns` 返回 user turn + 一条 `stopped_at` 非空的 agent turn。
     - GET `/api/sessions/{sid}/traces` 返回中断前所有 tool_call/tool_result。
  4. 再 POST 一条新 user turn "继续之前的工作"。
  5. 断言模型上下文窗口构造（看 `chat_runtime/prompt.py` 渲染产物，或直接断言传给 opencode 的 messages 列表）**包含**前一轮的截断内容。

#### ②-T3 前端 vitest
- 文件：`frontend/tests/session-turn-stopped.test.tsx`（新增）。
- mount turn 列表 fixture：一条 `stopped_at` 非空的 agent turn → 渲染含"已停止"标签；hover 显示时间；content 为空时显示占位文案。

#### ②-T4 e2e（可选，开关默认跳过）
- 真实启动后端 + DeepSeek-pro 跑一遍 abort 流，确认全链路不报错、turn 保留、二轮接续。开关 `CODEASK_RUN_LIVE_ABORT_E2E=1`，加在 `frontend/e2e/`。
- 不做强制门禁（live 容易抖），但 plan 完成后跑一次记录结果。

---

## ③ 多代码仓上下文：Step A（prompt）+ Step B（context 表）

### 现状

- `src/codeask/agent/opencode_compat/prompts.py:5-72` 的 system prompt 提到 repository 时是单数；没有"特性可能绑定多仓"的指导。
- `src/codeask/agent/opencode_compat/context.py:63-72` 的 "Bound features" 块只列出 wiki_path，未展开该 feature 名下的 ready repo 列表。
- 仓库表（:92-106）虽然每行有 `feature_ids`，但模型要做反向连接（feature → 全部 repos）信号弱。

### Step A — Prompt 加多仓约束

- 文件：`src/codeask/agent/opencode_compat/prompts.py`
- 在现有 escalation 段（约第 44-49 行的"Escalate to repository reading only when..."）**之后**插入一段独立指引（新段落，保留前后段不动）：

  ```
  - When the bound feature(s) have multiple ready repositories, treat the
    feature as a multi-repo system. For questions about cross-repo
    interactions, end-to-end flows, component boundaries, or how parts of
    the same feature talk to each other, prepare and inspect ALL linked
    ready repositories instead of picking only the most obvious one. Only
    narrow to a single repository when the user explicitly named one or the
    question is clearly scoped to a single component.
  ```

- 测试：
  - 单测断言 `build_codeask_system_prompt()` 返回值包含 `"multi-repo system"` 与 `"ALL linked ready repositories"`。
  - 加在既有 prompts 单测里（如无则新增 `tests/unit/test_opencode_prompts.py`）。

### Step B — Context Bound-features 段落明列 ready repos

- 文件：`src/codeask/agent/opencode_compat/context.py:41-72`
- 现状 `_load_bound_features(...)` 返回 dict 没有 `ready_repos`；要扩成包含 `ready_repos: list[{repo_id, name}]`（顺序固定，按 repo_id 升序）。
- 渲染段落（`:63-72`）改为：

  ```
  - <feature_name> (id=..., slug=..., source=..., wiki=...)
      Linked ready repos: [<repo_id_1>:<name_1>, <repo_id_2>:<name_2>, ...]
  ```

  若 `ready_repos` 为空：保持原行，并追加 `Linked ready repos: (none)`。

- 数据来源：与 `_load_repositories` / `_load_active_features` 走同一份 join（repo↔feature 关联表）。复用现有查询，只在 bound-features 路径上多 fetch 一次每个 feature 的 ready repo 列表（按 `repo.status='ready'` 过滤）。如果性能担心，可在 `_load_active_features` 已有的 ready_repo_count 旁加 `ready_repo_list`（同一 join 多 `array_agg`/Python 端聚合）。

### 测试

- 单测（context 渲染）：`tests/unit/test_opencode_context.py`（若不存在则新建）
  - 构造一个 feature 绑定到当前 session，且该 feature 有 2 个 ready repo + 1 个 not-ready repo。
  - 断言渲染产物含 `Linked ready repos:` 行，含两个 ready 仓的 id+name，不含 not-ready 那个。
- 单测（prompt 含约束句）：见 Step A 测试。
- 集成（可选）：用一个绑定多仓的 feature 跑 agent live，观察模型是否会对**多个**仓库 prepare_worktree。**模型行为不能 100% 锁定**——本项不作硬性回归门禁，仅记录两次跑分（Step A+B 上线前 vs 后），看是否有改善。

---

## 验收口径回填（实现完成后回写 acceptance-checklist.md）

本 plan 不增加新 acceptance 行，而是修正既有口径：

- §3.2 line57/58 等 stop 相关旧描述若有"中断回滚整轮"语义，统一改为"中断截断保留"；如无对应行则不动。
- §4 Phase 2 / opencode 接入相关用例若假设"超时 = 600s 墙钟"，在测试代码层面调整阈值并写入回归记录。
- 新增 §4.x（待定行号）一条："会话 stop 后已生成的 agent 轮次保留，下一轮模型上下文包含截断内容" + "多代码仓绑定特性时模型对全部 ready 仓做证据准备"。具体行号在 plan 实现后由开发回写。

已回写到 `acceptance-checklist.md` §4.1（M7 会话控制与多仓上下文）。

---

## 质量门禁（每项退出条件）

- `uv run pyright src/codeask evals` = 0；`uv run pytest -q` 绿；`uv run ruff check src tests evals` 与 `ruff format --check` 绿。
- `corepack pnpm exec tsc --noEmit`、`corepack pnpm exec eslint --max-warnings=0 .`、`corepack pnpm exec vitest run` 绿。
- alembic：`uv run alembic upgrade head` + `uv run alembic downgrade -1` + `uv run alembic upgrade head` 在真实库备份上跑通；0032 → 0031 → 0032 可逆。
- live（如开关启用）：abort e2e 跑过一次留记录；多代码仓 prompt 跑过一次留对照记录。

---

## 不在本 plan 范围

- 旧 `rollback_session_turn` 函数若被其它路径（非 messages.py）调用，统一改为 stopped 语义——若 grep 未发现其它调用点，可直接删；若有，开发判断同步改造或保留并改名。
- 前端 turn 列表"已停止"标签的视觉风格细节（颜色、文案措辞）：以现有设计语言为准，不在 plan 内强约束。
- 多代码仓的 Step C（绑定 feature 时自动 prepare 全部 ready repo）：先观察 A+B 实测效果，必要时再单独立项。
- 会话级 stop 的"撤销/清理被截断的轮次"按钮——若产品需要，单独评估。
- `_TURN_NO_PROGRESS_TIMEOUT_SECONDS` 与 `_TURN_WAIT_TIMEOUT_SECONDS` 是否暴露为配置项：本 plan 维持硬编码常量；若多负责人/多部署形态需要配置化，单独再起。

---

## 完整开发 Checklist（开发执行视角，可直接逐项勾）

### ① 超时
- [x] `backend.py:95-97` 常量改：`_TURN_NO_PROGRESS_TIMEOUT_SECONDS = 600.0`、`_TURN_WAIT_TIMEOUT_SECONDS = 3600.0`
- [x] grep 确认 `last_progress_at` 在当前 session event / status 观测上刷新；现有 `_event_belongs_to_session` 覆盖 `properties.sessionID` 与 `properties.part.sessionID`
- [x] no-progress 触发分支补 `no_progress_seconds` 字段进 `_synthetic_session_error_event`
- [x] 绝对墙钟触发分支补 `absolute_wait_seconds` 字段
- [x] 新增单测 `tests/unit/test_opencode_turn_timeout.py`：no-progress、absolute wait 与默认阈值契约
- [x] 调整依赖旧错误 payload 的 opencode backend 单测
- [x] pyright / pytest / ruff 绿（收口验证见完成记录）

### ② 停止
- [x] `db/models/session.py` `SessionTurn` 增加 `stopped_at: Mapped[datetime | None]`
- [x] alembic `20260528_0032_session_turn_stopped_at.py`：`revision="0032"`、`down_revision="0031"`；`upgrade` add_column nullable，`downgrade` drop_column
- [x] `api/schemas/session.py` `SessionTurnResponse` 加 `stopped_at: datetime | None = None`
- [x] `sessions/messages.py` 新增 `persist_stopped_agent_turn`：写入时设 `stopped_at`；空 partial 也写占位
- [x] `sessions/messages.py` cancel 分支：去掉 `rollback_session_turn`，改调 `persist_stopped_agent_turn`
- [x] grep `rollback_session_turn` 无活代码引用；旧函数已删除，API abort 端点不再删 turn / trace
- [x] 前端 `types/api.ts` `SessionTurnResponse` 加 `stopped_at`
- [x] 前端 turn 列表组件加"已停止"chip + 空 content 占位文案
- [x] 单测 `tests/unit/test_session_turn_stopped.py`：①-T1 三状态
- [x] 集成合入 `tests/integration/test_sessions_api.py`：stopped 保留、abort endpoint 不清表、迟到回答/迟到 trace 防写入
- [x] vitest `frontend/tests/message-stream.test.tsx` + `session-workspace.test.tsx`：渲染与 Stop 本地保留断言
- [ ] （可选）e2e `CODEASK_RUN_LIVE_ABORT_E2E=1`：手动跑一次记录到 plan
- [x] alembic upgrade/downgrade/upgrade 在临时数据目录跑通
- [x] pyright / pytest / tsc / vitest / eslint 绿（收口验证见完成记录）

### ③ 多代码仓
- [x] `prompts.py` escalation 段后插入"multi-repo system + ALL linked ready repositories"段
- [x] `context.py` `_load_bound_features` 扩 `ready_repos: list[dict]`（id、name），按 repo_id 升序
- [x] `context.py` bound-features 渲染段插入 `Linked ready repos: [...]` 行；空时 `(none)`
- [x] 单测 `tests/unit/test_opencode_compat_foundation.py`：prompt 含关键句
- [x] 单测 `tests/unit/test_opencode_compat_context.py`：bound feature 含两个 ready repo + 一个 not-ready → 渲染含两个 ready
- [ ] （可选）live 跑分对照：A+B 上线前后各跑一次多仓特性的 agent 问询，记录在本 plan
- [x] pyright / pytest / ruff 绿（收口验证见完成记录）

### 收口
- [x] 更新 `acceptance-checklist.md` 中受影响的口径（stop 截断保留、超时阈值、多代码仓 ready repos）
- [x] 本 plan 状态从 Planned → Completed，回填"完成记录"小节
- [ ] 不要 push tag；docs 改动单独一个 commit；功能/迁移/测试可合并一个 commit

---

## 完成记录

- 代码范围：超时阈值与诊断字段、Stop 截断保留、`SessionTurn.stopped_at` 迁移/API/前端展示、多代码仓 prompt/context ready repo 列表。
- 测试覆盖：
  - `tests/unit/test_opencode_turn_timeout.py`
  - `tests/unit/test_session_turn_stopped.py`
  - `tests/integration/test_sessions_api.py` 中 stopped / abort / late write 回归
  - `tests/unit/test_opencode_compat_foundation.py`
  - `tests/unit/test_opencode_compat_context.py`
  - `frontend/tests/message-stream.test.tsx`
  - `frontend/tests/session-workspace.test.tsx`
- 收口命令：
  - `uv run pyright src/codeask evals`
  - `uv run pytest -q`
  - `uv run ruff check src tests evals`
  - `uv run ruff format --check src tests evals`
  - `corepack pnpm --dir frontend exec tsc --noEmit`
  - `corepack pnpm --dir frontend exec eslint src tests e2e --max-warnings=0`
  - `corepack pnpm --dir frontend exec vitest run`
  - `CODEASK_DATA_DIR=$PWD/.tmp/alembic-m7 CODEASK_DATA_KEY=<generated> uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
