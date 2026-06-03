# M14 OpenCode 工具权限可配置化实施计划

> 版本：v1.0.5
> 状态：Completed（2026-06-03 release 复核：权限配置、前端控制台、工具错误口径修复均已落地）

> **给 agentic worker：** 实施本计划时必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按任务逐项执行。所有步骤使用 checkbox 追踪；2026-06-03 release 复核时已按落地状态勾选。涉及管理员 UI 的改动必须先触发 `frontend-design`（落地实现）或 `ui-ux-pro-max`（评审/方向）skill，严格沿用现有 OpenViking dashboard / Settings 工作台风格，不要堆叠通用 AI 审美。

**目标：** 把新建 opencode 会话时写死的工具 allow/deny 权限，改成管理员可在 UI 中配置；并为 `bash` 增加“白名单通配符”模式，让 `git`、`ls` 等检索/定位常用命令可被放行，同时保持默认安全收敛。

**架构：** opencode 每会话的 `permission` 块当前由 [config.py](/home/hzh/workspace/CodeAsk/src/codeask/agent/opencode_compat/config.py) 的常量 `READONLY_PERMISSION` 写死生成。M14 把“基础工具权限”改为来自数据库管理员配置（`system_settings` 键值表），通过注入到 `OpenCodeCompat` 的一个异步 resolver 在 `initialize_session` 时解析，沿用现有 `openviking_mcp_resolver` 的注入模式。`external_directory` 沙箱白名单和 provider 连通性测试配置仍由系统强制管理、不开放给管理员。`bash` 支持三态：`allow` / `deny` / `whitelist`（通配符放行表，其余拒绝），落到 opencode 的对象式权限（与现有 `external_directory` 同一机制）。

**技术栈：** Python 3.11、FastAPI、SQLAlchemy（`system_settings` JSON KV）、Pydantic 校验、React 19 / TypeScript 管理后台、@tanstack/react-query v5、Vitest、Playwright E2E、ruff（line-length 100）、pyright。

---

## 0. 现状与决策

### 现状（已核实）

- [config.py](/home/hzh/workspace/CodeAsk/src/codeask/agent/opencode_compat/config.py) 写死两组常量：
  - `READONLY_PERMISSION = {"bash":"deny","edit":"deny","write":"deny","read":"allow","grep":"allow","glob":"allow"}`
  - `OPENVIKING_WRITE_TOOL_DENIES = {"openviking_remember":"deny","openviking_add_resource":"deny","openviking_forget":"deny"}`
- `_build_permission()` 合并：基础只读权限 + （OV 启用时）OV 写工具拒绝 + （有 symlink 目标时）`external_directory` 对象式白名单 `{"*":"deny", <pattern>:"allow"}`。**这条已经证明 opencode 支持对象式（per-pattern）权限值**，bash 白名单复用同一机制。
- `build_opencode_config()`（config.py:140）在生成 `opencode.json` 时调用 `_build_permission(...)`。
- 会话创建链路：`OpenCodeCompat.initialize_session()`（[backend.py:140](/home/hzh/workspace/CodeAsk/src/codeask/agent/opencode_compat/backend.py)）→ `_config_input()` → `build_opencode_config(_with_profile(...))` → `_write_workspace_files()`。`config_hash` 覆盖整个 config（含 permission），权限变更后下次 `initialize_session` 会触发新的外部会话（不会污染存量进行中会话，但也**不会追溯改写正在跑的会话**）。
- `_write_provider_test_config()`（backend.py:803）另有一份写死的全 deny 权限块，仅用于 provider 连通性探测，不需要任何工具。
- `OpenCodeCompat` 已有先例的异步注入式 resolver：`openviking_mcp_resolver`（构造见 [app.py:239](/home/hzh/workspace/CodeAsk/src/codeask/app.py)，解析见 backend.py:629 `_resolve_openviking_mcp`）。M14 的权限 resolver 照搬此模式。
- 持久化基础设施：`SystemSetting`（[system_settings.py 模型](/home/hzh/workspace/CodeAsk/src/codeask/db/models/system_settings.py)，`key:str PK / value:JSON`）+ [system_settings API](/home/hzh/workspace/CodeAsk/src/codeask/api/system_settings.py)（`session_attachments_enabled` 即范例）。
- 管理员导航：[SettingsPage.tsx](/home/hzh/workspace/CodeAsk/frontend/src/components/settings/SettingsPage.tsx) 的 `adminSettingsPages`，首项 `id:"runtime"` / `label:"运行状态"` → `AdminRuntimeSettings`（[GlobalSettings.tsx:92](/home/hzh/workspace/CodeAsk/frontend/src/components/settings/GlobalSettings.tsx)）→ `OpencodeStatusPanel`；`openviking` 为末项。路由 id 联合类型在 [routing.ts](/home/hzh/workspace/CodeAsk/frontend/src/lib/wiki/routing.ts)（`SettingsAdminPageId` + `readSettingsAdminPage` 白名单）。

### opencode bash 通配符权限（可行性）

opencode 的 `permission.bash` 既支持字符串（`"allow"`/`"deny"`/`"ask"`），也支持对象式 `{ "<glob>": "allow|deny|ask", "*": "deny" }`，按命令文本匹配 glob。本仓库的 `external_directory` 已经依赖同一对象式权限解析，故 **bash 白名单形态在当前 pin 的 opencode 版本上可行**。实施第一步仍要对 pin 的 opencode 版本做一次最小冒烟（见任务 7），把“依赖未验证的上游行为”降为零。

### 决策

1. **可配置工具集（治理范围）**：`bash`、`edit`、`write`、`read`、`grep`、`glob`、`webfetch`，以及 OV 启用时的 `openviking_remember` / `openviking_add_resource` / `openviking_forget`。`codeask_*` MCP 工具是核心集成、始终放行，不进治理面。`external_directory` 沙箱白名单仍系统强制、**不**开放给管理员（安全边界，非工具开关）。
2. **默认值 = 当前行为**：缺省（DB 无配置）时，解析结果必须与今天的 `READONLY_PERMISSION`(+OV deny) 逐字节等价。即不改变全新安装的默认安全姿态；管理员显式改动后才生效。
3. **bash 三态**：`allow` / `deny` / `whitelist`。`whitelist` 落成 `{"*":"deny", <pat>:"allow", ...}`。内置一组推荐只读检索命令模板（`git *`、`git status`、`git log *`、`git diff *`、`ls *`、`cat *`、`rg *`、`find *`、`wc *`、`head *`、`tail *` 等）供一键填充，但最终值以管理员编辑为准。
4. **OV 写工具开关**：仅当 OpenViking 启用时在 UI 出现；DB 无配置时维持“deny”。允许管理员放开，但带显式风险说明（这些是写 RAG 索引的工具）。
5. **生效时机**：保存即写库；对**新建/下一次初始化**的会话生效（`config_hash` 变更驱动），不追溯正在进行的会话。UI 明确告知此语义。
6. **provider 测试配置**：`_write_provider_test_config` 保持全 deny 不变（探测无需工具），不纳入治理面。注释说明理由。
7. **无 migration**：KV 表，缺省即默认；不需要 Alembic 改动。
8. **导航调整**：`运行状态` → `OpenCode`，并把该项移到 `openviking` 正上方（把 OpenCode 与 OpenViking 两个后端分组在导航底部）。

---

## 1. 数据模型与解析层（后端核心）

权限的“单一事实来源”：`system_settings` 中新增键 `opencode_tool_permissions`，value 为规范化 JSON。

建议 JSON 形态：

```json
{
  "version": 1,
  "tools": {
    "read": "allow",
    "grep": "allow",
    "glob": "allow",
    "webfetch": "deny",
    "edit": "deny",
    "write": "deny",
    "openviking_remember": "deny",
    "openviking_add_resource": "deny",
    "openviking_forget": "deny"
  },
  "bash": {
    "mode": "deny",
    "patterns": []
  }
}
```

- [x] 在 `src/codeask/agent/opencode_compat/` 新增 `permissions.py`（纯函数 + dataclass，无 IO）：
  - [x] `@dataclass(frozen=True) OpencodeToolPermissions`：`tools: dict[str,str]`、`bash_mode: Literal["allow","deny","whitelist"]`、`bash_patterns: tuple[str,...]`。
  - [x] `DEFAULT_TOOL_PERMISSIONS`：与现有 `READONLY_PERMISSION`（不含 bash）一致 + OV 写工具 deny + `webfetch:"deny"`。给出 `default()` classmethod 返回与今日行为等价的实例（bash_mode="deny"）。
  - [x] `GOVERNED_TOOLS`（顺序固定，供 UI 目录）与 `OPENVIKING_WRITE_TOOLS` 子集常量。
  - [x] `BASH_WHITELIST_SUGGESTIONS`：推荐只读命令模板元组。
  - [x] `from_stored(value: object) -> OpencodeToolPermissions`：宽松解析 DB JSON，未知键忽略、缺失键回落默认、非法 mode/值回落默认；保证永不抛错（DB 脏数据不能拖垮会话创建）。
  - [x] `to_stored(self) -> dict`：规范化序列化（用于 PATCH 落库）。
  - [x] `to_permission_block(self, *, openviking_enabled: bool) -> dict[str,object]`：产出 opencode `permission` 子块（不含 `external_directory`）。bash：`allow`/`deny` → 字符串；`whitelist` → `{"*":"deny", **{p:"allow" for p in patterns}}`（空 patterns 时退化为 `"deny"` 并记一条 warning 级日志）。OV 未启用时**剔除** `openviking_*` 键（与现状一致：只有 OV 启用才注入这些 deny）。
- [x] 校验函数 `validate_bash_patterns(patterns) -> list[str]`：去空白、去重、保序；单条长度上限（如 ≤200）、总条数上限（如 ≤64）；拒绝含换行/控制字符的条目。超限抛 `ValueError`（API 转 400）。

## 2. 改造权限构建（config.py）

- [x] `_build_permission()` 增加可选参数 `tool_permissions: OpencodeToolPermissions | None = None`：
  - `None` → 维持现有 `READONLY_PERMISSION`(+OV deny) 行为（向后兼容、便于单测与 provider test 复用）。
  - 提供时 → 用 `tool_permissions.to_permission_block(openviking_enabled=...)` 替换基础块，再叠加 `external_directory`（保持原逻辑、原顺序）。
- [x] `build_opencode_config()` 与 `OpenCodeConfigInput` 增加 `tool_permissions: OpencodeToolPermissions | None = None` 字段；`with_openviking` 与 backend 的 `_with_profile`（backend.py:772）透传该字段（注意 `_with_profile` 是手写逐字段拷贝，**必须补这一字段**，否则会丢失）。
- [x] 保持 `READONLY_PERMISSION` / `OPENVIKING_WRITE_TOOL_DENIES` 常量不删（默认路径仍用），避免大范围连锁改动。

## 3. resolver 注入（backend.py + app.py）

- [x] `OpenCodeCompat.__init__` 增加 `tool_permissions_resolver: Callable[[], Awaitable[OpencodeToolPermissions]] | None = None`（无 session 入参——权限是全局配置，非每会话）。
- [x] 新增 `async def _resolve_tool_permissions(self) -> OpencodeToolPermissions`：resolver 为 None 时返回 `OpencodeToolPermissions.default()`；否则 await resolver，异常时 log + 回落 default（绝不阻断会话创建）。
- [x] `initialize_session()`：在构造 `config_input` 后、`build_opencode_config` 前解析一次，传入 `tool_permissions`。确认 `_config_input` / `_with_profile` 链路把该字段带到 `build_opencode_config`。
- [x] [app.py](/home/hzh/workspace/CodeAsk/src/codeask/app.py) 在构造 `OpenCodeCompat`（app.py:221）处注入 resolver：`async def resolve_tool_permissions() -> OpencodeToolPermissions: return await load_opencode_tool_permissions(factory)`，其中 loader 读 `system_settings` 的 `opencode_tool_permissions` 键并 `OpencodeToolPermissions.from_stored(...)`。
- [x] loader 放在新 API 模块或一个小的 `opencode_compat/permissions_store.py`（接受 `session_factory`），与 openviking 的 `_resolve_openviking_mcp_config` 风格一致。

## 4. 管理 API（新增 opencode_admin.py）

镜像 [openviking_admin.py](/home/hzh/workspace/CodeAsk/src/codeask/api/openviking_admin.py) 的结构，新建 `src/codeask/api/opencode_admin.py`，`require_admin` 守卫。

- [x] `GET /admin/opencode/permissions` → 返回当前配置 + 目录元数据：
  ```json
  {
    "tools": {...}, "bash": {"mode":"...","patterns":[...]},
    "catalog": {
      "tools": [{"key":"read","label":"读取文件","group":"file","openviking":false}, ...],
      "bash_suggestions": ["git status","ls *", ...]
    },
    "openviking_enabled": true,
    "defaults": {...}
  }
  ```
  - `openviking_enabled` 取自 `request.app.state.settings.openviking_enabled`，前端据此决定是否渲染 OV 写工具行。
- [x] `PUT /admin/opencode/permissions`（整体覆盖式更新，payload 经 Pydantic + `validate_bash_patterns` 校验）：
  - 规范化后 `to_stored()` 落 `SystemSetting`（key=`opencode_tool_permissions`），upsert，`write_audit(entity_type="system_setting", action="opencode_permissions.update", ...)`。
  - 返回与 GET 同形的最新值。
  - 校验失败 → 400（含可读信息）。
- [x] 在 [app.py:480](/home/hzh/workspace/CodeAsk/src/codeask/app.py) 附近 `include_router(opencode_admin_router, prefix="/api")`。
- [x] Pydantic 模型：`mode` 用 `Literal`；tool 值用 `Literal["allow","deny"]`；只接受治理集内的 key（未知 key 拒绝或忽略，二选一并写测试固定行为）。

## 5. 前端类型与 API 客户端

- [x] `frontend/src/types/api.ts`：新增 `OpencodeToolPermissionValue = "allow"|"deny"`、`OpencodeBashMode`、`OpencodePermissionsResponse`（含 `catalog`/`defaults`/`openviking_enabled`）、`OpencodePermissionsUpdateRequest`。
- [x] 新增 `frontend/src/lib/api-opencode.ts`（或并入既有 api 模块）：`getOpencodePermissions()`、`updateOpencodePermissions(payload)`。复用现有 fetch 封装与错误处理。

## 6. 管理员 UI（先触发设计 skill）

> 设计方向：沿用 OpenViking dashboard 的“工作台卡片”语言——`.surface` 容器、`section-title` + lucide 图标、紧凑栅格、36px 控件、按钮 `.button-secondary/-primary`、`SwitchControl`、`requestConfirm` 危险确认；不要大段说明文字。新页面 = 「OpenCode」，上半部分保留现有 `OpencodeStatusPanel`（运行健康），下半部分新增「工具权限」卡片。

### 6.1 导航与页面装配
- [x] [SettingsPage.tsx](/home/hzh/workspace/CodeAsk/frontend/src/components/settings/SettingsPage.tsx)：
  - [x] 把 `runtime` 项 `label` 改为 `"OpenCode"`，`description` 改为如「opencode 后端状态与工具权限」，图标可保留 `Activity` 或换 `Terminal`。
  - [x] 在 `adminSettingsPages` 数组里把该项移动到 `openviking` 项**正上方**（保持其余顺序）。
  - [x] 同步更新 `pageDescriptions["runtime"]`。
  - [x] （决策点）是否把路由 id `"runtime"` 改名为 `"opencode"`：**推荐保留 id 不变**（避免改 routing.ts 联合类型/白名单与潜在深链回归），仅改展示 label。若改名，则同步 [routing.ts](/home/hzh/workspace/CodeAsk/frontend/src/lib/wiki/routing.ts) 的 `SettingsAdminPageId` 与 `readSettingsAdminPage`。
- [x] `AdminRuntimeSettings`（GlobalSettings.tsx:92）：在 `OpencodeStatusPanel` 下追加新组件 `<OpencodeToolPermissionsPanel />`。

### 6.2 工具权限面板（新组件）
- [x] 新建 `frontend/src/components/settings/OpencodeToolPermissionsPanel.tsx`：
  - [x] `useQuery(["admin-opencode-permissions"], getOpencodePermissions)` 拉取；本地表单 state，`useMutation` 提交（`isPending` 态、成功/失败 toast 走 `AppFeedback`）。
  - [x] 每个治理工具一行：工具名 + 简述 + allow/deny 控件（`SwitchControl` 或分段按钮，二态）。OV 写工具仅当 `openviking_enabled` 渲染，并带风险提示样式（danger 调性）。
  - [x] `bash` 行特殊：三态分段控件（允许 / 拒绝 / 白名单）。选「白名单」时展开 pattern 编辑区——chips 或可增删的输入行；提供「填入推荐命令」按钮（来自 `catalog.bash_suggestions`）。空白名单给出内联提示「等价于拒绝」。
  - [x] 「保存」`.button-primary`：`requestConfirm` 二次确认（说明“对新建会话生效，不影响进行中的会话”）。「恢复默认」`.button-secondary`：用 `defaults` 重置表单（仅本地，保存后才落库）。
  - [x] 表单 dirty 检测：未改动时禁用保存。
- [x] `frontend/src/styles/globals.css`：新增本面板所需类，复用既有 token（边框 #e4e9f2/#d0d5dd、文字 ramp、success/error 配色、7–8px 圆角、36px 控件、字重 650–750）。保持栅格对齐，避免之前 OpenViking 字段提示破坏对齐的同类问题。

## 7. 测试

### 7.1 后端单元（pytest）
- [x] `tests/unit/test_opencode_permissions.py`：
  - [x] `default()` 产出与现有 `READONLY_PERMISSION`(+OV deny) 等价的 permission block（OV 启用/未启用两种）。
  - [x] `from_stored` 宽松解析：缺键回落、未知键忽略、非法 mode/值回落、`None`/非 dict 输入返回 default。
  - [x] `to_permission_block`：bash allow/deny/whitelist 三态正确；whitelist 空 patterns 退化为 deny；OV 未启用时不含 `openviking_*` 键。
  - [x] `validate_bash_patterns`：去重保序、超长/超量/含控制字符抛错。
- [x] `tests/unit/test_opencode_compat_backend.py` / config 测试：`build_opencode_config` 传入自定义 `tool_permissions` 时 `permission` 块正确，且 `external_directory` 仍叠加；`_with_profile` 透传不丢字段。

### 7.2 后端集成（pytest，httpx ASGI）
- [x] `tests/integration/test_opencode_admin_api.py`：
  - [x] GET 默认返回（无 DB 配置）= defaults，且含 catalog/openviking_enabled。
  - [x] PUT 合法 payload → 落库 + 审计 + 回读一致。
  - [x] PUT bash whitelist → 回读 patterns 规范化。
  - [x] PUT 非法（超量 patterns / 非法 mode / 越权工具 key）→ 400。
  - [x] 非管理员 → 403。
- [x] resolver 端到端：构造带 resolver 的 `OpenCodeCompat`（或直接测 loader），DB 写入配置后 `initialize_session` 产出的 `opencode.json` permission 反映配置（可在现有 backend 集成测试夹具上加用例）。

### 7.3 前端（Vitest）
- [x] `frontend/tests/opencode-permissions.test.tsx`：渲染面板、mock GET、切换工具态与 bash 三态、白名单增删与「填入推荐」、保存调用 `updateOpencodePermissions` 且 payload 正确、OV 未启用时不渲染 OV 写工具行、dirty 禁用逻辑。
- [x] `frontend/tests/settings-page.test.tsx`：导航项 label=「OpenCode」、位于 OpenViking 之上；进入该页渲染状态面板 + 权限面板。

### 7.4 E2E（Playwright，按现有约定）
- [x] 管理员进入 OpenCode 页 → 把 bash 设为白名单并填入 `git *`/`ls *` → 保存成功 toast → 回读保持。

## 8. 文档与验收

- [x] 更新 [acceptance-checklist.md](/home/hzh/workspace/CodeAsk/docs/v1.0.5/plans/acceptance-checklist.md)：新增 M14 验收条目（导航重命名+排序、每工具 allow/deny 可配、bash 白名单生效于新会话、默认行为不变、非管理员 403、生效语义提示）。
- [x] 自测记录：`uv run pytest`（新单测+集成）、`ruff`/`pyright` clean；前端 `lint`/`build`/相关 vitest 绿；说明“对进行中会话不追溯”这一已知语义。

---

## 风险与边界

- **opencode 上游行为依赖**：bash 对象式权限按 pin 版本验证一次（任务 7.2 的 e2e/集成已覆盖落盘，建议补一条对真实 opencode 的最小冒烟或在实施首步手验 `opencode.json` 被接受）。已有 `external_directory` 对象式权限佐证可行。
- **安全姿态**：默认仍全收敛；放开 bash/写工具是管理员显式动作，UI 用 danger 调性 + 二次确认；`external_directory` 沙箱不开放，防止绕过 symlink 边界。
- **DB 脏数据**：`from_stored` 与 resolver 双重兜底回落默认，任何解析异常都不得阻断会话创建。
- **生效时机**：仅对新建/下次初始化会话生效；不提供“热重载进行中会话”，UI 必须说明，避免管理员误判。

---

## 实施记录（2026-06-03，分支 `m14-opencode-tool-permissions`）

本里程碑由 Claude 在用户显式委派下前后端一并实施。

**范围追加（用户决策）：** 用户在动工后要求重做整个 OpenCode 页（原仅一个状态面板，风险低）。落地为 **「Agent Control Console」** 整页重设计，沿用现有 admin 工作台设计语言、不引入冲突主题：状态 hero（运行态脉冲环 + 单色信号灯，`prefers-reduced-motion` 降级）、等宽 tabular chips 仪表读数、路径行、工具权限矩阵（分组 + allow/deny 分段控件）、bash 终端式白名单编辑器（mac 三色点 + `$` 提示符 + 命令通配符 chips + 填入推荐）。先触发 `frontend-design` skill。

**已落地文件：**
- 后端：`agent/opencode_compat/permissions.py`（新）、`config.py`、`backend.py`（resolver 注入）、`api/opencode_admin.py`（新，GET/PUT + loader）、`app.py`（注入 + 注册路由）。
- 前端：`lib/api-opencode.ts`（类型 + 客户端）、`components/settings/OpencodeStatusPanel.tsx`（重写）、`OpencodeToolPermissionsPanel.tsx`（新）、`GlobalSettings.tsx`（组合）、`SettingsPage.tsx`（导航重命名 + 移位）、`styles/globals.css`（Console 样式块）。
- 测试：`tests/unit/test_opencode_permissions.py`（17）、`tests/integration/test_opencode_admin_api.py`（7）、`frontend/tests/opencode-permissions.test.tsx`（5）、`settings-page.test.tsx`（导航 + 面板断言）、`e2e/opencode-tool-permissions.spec.ts`（非 live，绿）。

**决策落点：** 路由 id 保留 `runtime`（仅改 label，避免 routing.ts 改动）；`webfetch` 纳入治理且默认 deny（仅管理员显式保存后生效，None 路径仍逐字节等价旧行为）；`_write_provider_test_config` 全 deny 保持不变。

**门禁：** 后端 `ruff` / `pyright` clean；前端 `lint` / `tsc` / `build` clean；前端 vitest 264 全绿；新 E2E 通过。bash 对象式权限可行性已由真实 opencode E2E（保存 → 落盘 → 刷新保持）坐实。

## 补充完成记录（2026-06-03，工具错误口径修复）

架构复检发现 MCP 工具存在“transport completed，但 structured output 内含 `{error: ...}`”的业务失败形态。已补齐：

- `agent/opencode_compat/tool_output.py` 抽出结构化 output 解析、错误提取和摘要生成，`events.py` 与 `backend.py` 复用同一套逻辑。
- CodeAsk MCP / OpenViking MCP 的结构化业务失败会统一表现为 MCP `isError=true`、前端 `tool_result.ok=false`、持久化摘要 `ok=false`。
- 保留内置 opencode 工具（bash/read/grep 等）的普通 JSON output，不因非 CodeAsk/OpenViking 工具里的 `error` 数据键误判失败。
- 终态 `tool_result` 也按 part id 去重，避免重复 summary。
- 验证：`test_opencode_compat_mcp_server.py`、`test_opencode_compat_http_events.py`、`test_opencode_compat_backend.py`、`test_opencode_mcp_app_integration.py`、`test_opencode_compat_mcp_worktree_tools.py` 等相关测试通过；ruff / pyright clean；DeepSeek live E2E 覆盖 `prepare_worktree` 成功、失败、恢复路径。

---

## 协作分工提醒

按 v1.0.5 既定分工：本计划由开发实施 + 自测，Claude 负责架构/评审/最终验收，不代写实现代码（前端例外仅在被显式委派时）。提交需用户显式要求；提交信息以 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` 结尾。
