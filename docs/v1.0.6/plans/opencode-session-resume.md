# opencode 会话恢复：一会话一 id，永不二次新建

## 背景与问题

一个 CodeAsk 会话（`sessions` 行）对应一个 opencode 外部会话（`external_agent_sessions` 行的 `external_session_key`）。opencode 把多轮对话上下文存在自己的 `server_data`（`XDG_DATA_HOME`，落在 `agent_sessions/opencode/server_data`），**按 session id 索引**；`run_turn` 每轮只把新的 `user_message` 发给该 id，靠 opencode 自己维护历史。

现状的两个错误行为：

1. **空闲清理丢上下文**：后台每小时扫描，把 6h 未活动的会话 `cleanup_session`（删 workspace 目录 + worktree，行标 `status='cleaned'`）。下次发消息时 `initialize_session` 的复用分支被 `status=='active'` 挡掉，于是 `create_session` 建一个**全新 id**、`upsert` 覆盖旧 id —— opencode 侧仍保留着旧 id 的完整历史（`cleanup_session` 不碰 `server_data`），却被白白丢弃，模型“忘了”之前聊过什么。

2. **配置轮转丢上下文**：池化全局配置轮转（`force_new_external_session`）时同样新建 id，上下文同样丢。

目标：**一个 CodeAsk 会话 = 一个 `external_session_key` + 一个固定目录 `sessions/<id>/workspace`，只在首轮 `create_session`，之后永远复用同一个 id 恢复**。恢复不了（opencode 侧数据真丢/过期）就如实报错，绝不静默新建。

## 实测证据（直连 opencode :4101，脚本在 `~/.codeask/tmp/resume_probe/`）

| # | 结论 | 证据 |
|---|---|---|
| 1 | 上下文绑 **session id**，不绑目录 | 同目录新 id 问旧暗号→“不知道” |
| 2 | **工作目录整个 `rmtree` 重建后，同 id 仍恢复完整上下文** | 记 4173 → 删目录重建 → 同 id 答 4173 |
| 3 | 改写 opencode.json **不会**被已加载的实例重读 | 加 provider 后不 dispose，同会话/同目录新会话都拿不到 |
| 4 | **`POST /instance/dispose?directory=<dir>` 强制同目录重载配置，且上下文存活** | 改 config 未 dispose→旧配置；dispose(200)→新配置生效；再 dispose→旧记忆 7777 仍在 |
| 5 | 你那两个真实配置（deepseek-v4-pro / -flash）走 A→改配置→dispose→同 id 恢复，全程上下文不丢 | 答 9999 |
| 6 | **同 provider 只换 model 实时生效、无需 dispose**（model 是逐请求参数）；只有换 provider/apiKey/baseURL/headers 才需要 dispose | probe9 step2 未 dispose 也答 9999 |

### opencode 侧机制（源码 `packages/opencode/src/`）

- `project/instance-store.ts`：`InstanceStore` = `Map<目录, 实例>`。`load(dir)` 命中缓存就返回**配置已冻结**的实例；只有未缓存的目录才 boot、读 `opencode.json`。⇒ 改文件不重载，“同目录开新会话”也没用（事实 3）。
- `server/routes/instance/httpapi/{lifecycle,handlers/instance}.ts`：`POST /instance/dispose` → `markInstanceForDisposal` → 响应后 `store.dispose(ctx)` 销毁该目录缓存实例；下次访问重新 boot、读新 `opencode.json`（事实 4）。dispose 按**目录**生效，而 CodeAsk 每会话独占 `sessions/<id>/workspace`，互不波及。
- `config/config.ts`：全局配置 `cachedInvalidateWithTTL(..., Duration.infinity)`；per-目录配置走 `InstanceState`，随实例销毁而失效。

## 关于“每轮重写 opencode.json”（澄清疑惑）

现状 `initialize_session` 每轮**无条件** `_write_workspace_files`（backend.py:177）。结合事实 3，这**基本是白做的**：opencode 只在实例 (re)load 时读一次 opencode.json，之后缓存冻结、不监听文件；写相同内容既不触发重载也无效果。

正确模型：**opencode.json 只在「首次创建 / 配置变了 / 文件被清理删掉」三种情况才需要写**；配置变了时光写没用，必须配 dispose 才重载；常规轮次（配置没变、文件还在）根本不该重写。本计划据此把写入改成**有条件**。

## 设计

`initialize_session` 重写为下述逻辑（`run_turn` 不变，仍只发新消息）：

```
workspace = prepare_workspace(session_id)        # 目录路径稳定；缺则建（覆盖清理后重建）
existing  = get_by_session_id_or_none(session_id)
config        = build_opencode_config(...)
config_hash   = _config_hash(config)

# 是否需要写 opencode.json：首次 / 配置变 / 文件缺失
config_changed   = existing is None or existing.config_hash != config_hash
opencode_json    = workspace.workspace_dir / "opencode.json"
need_write       = config_changed or not opencode_json.exists()
if need_write:
    _write_workspace_files(workspace.workspace_dir, config)

# 有旧 id 且非显式强制新建 → 恢复同 id
if existing is not None and existing.external_session_key and not force_new_external_session:
    usable, reason = await _external_session_is_usable(            # 探针：该 id 在 server_data 还在吗
        client, session_id=existing.external_session_key, directory=workspace.workspace_dir
    )
    if not usable:
        raise OpenCodeSessionResumeError(reason)  # 透传 opencode 实际报错，不新建（reason 即探针捕获的原始错误）
    if config_changed or existing.workspace_dir != str(workspace.workspace_dir):
        await client.dispose_instance(directory=workspace.workspace_dir)   # 让下一轮 prompt 重载新配置
    return await self._session_store.update_server_binding(
        session_id=session_id, server_url=..., port=..., pid=...,
        config_hash=config_hash, config_json=config,                      # 持久化新配置指纹
        workspace_dir=str(workspace.workspace_dir),
    )

# 无旧 id（首轮）或显式强制新建 → 建新
external_session_key = await client.create_session(directory=workspace.workspace_dir)
return await self._session_store.upsert(ExternalAgentSessionCreate(... external_session_key ...))
```

关键点：
- **去掉 `status=='active'` 与 `config_hash==` 这两道把恢复挡掉的门**。`cleaned` 会话照样恢复。
- **探针先于 dispose**：探针只查“session id 是否还在”（`list_messages`，与 provider 配置无关），用当前缓存实例即可；探不到=历史真丢/过期→报错。
- **dispose 只在配置变（或目录搬迁）时调**：覆盖换 provider/key/baseURL/headers（事实 4/6）；只换 model 时多调一次无害。
- **`force_new_external_session` 仅保留为显式“重置会话”用途**，不再由配置轮转触发。

### 报错语义（已确认）

恢复探针失败时，**透传 opencode 的实际报错**——不自造“历史已过期”之类话术。`_external_session_is_usable` 捕获 `list_messages` 的原始异常文本作为 `reason`，`OpenCodeSessionResumeError(reason)` 只承载该原文，上层照原样呈现，**不静默新建**。逃生口：上层可在用户显式选择时传 `force_new_external_session=True` 就地重开（本计划不做前端按钮，仅保留后端能力）。

## 逐文件改动

1. **`src/codeask/agent/opencode_compat/http.py`**：新增 `dispose_instance(self, *, directory: str) -> None` → `POST /instance/dispose?directory=...`，非 2xx 容忍（记 warn，不抛）。
2. **`src/codeask/agent/opencode_compat/backend.py`**：
   - `HttpClientLike` 协议加 `dispose_instance`。
   - `SessionStoreLike.update_server_binding` 协议加可选 `config_hash`/`config_json`/`workspace_dir`。
   - 新增 `OpenCodeSessionResumeError`（带 session_id / external_session_key / reason）。
   - 重写 `initialize_session`（上节逻辑）：条件写 opencode.json、去门、探针、按需 dispose、恢复同 id。
3. **`src/codeask/agent/opencode_compat/sessions.py`**：`update_server_binding` 增可选 `config_hash`/`config_json`/`workspace_dir`，给了就更新（不给保持原值）。
4. **`src/codeask/sessions/messages.py`**：轮转不再传 `force_new_external_session`（line ~371）；捕获 `OpenCodeSessionResumeError` → 对应错误事件/HTTP。
5. **清理任务不变**：`cleanup_session` 仍删 workspace+worktree、标 `cleaned`（`server_data` 本就不删）；与“恢复”天然兼容。

## 验证

- 单测：`initialize_session` 四条路径——首轮建新 / 配置不变复用（不写不 dispose）/ 配置变复用（写+dispose）/ 探针失败报错；`force_new` 仍建新；`dispose_instance` 调用。
- 既有单测迁移：原本断言“cleaned→新建”的用例改为“cleaned→同 id 恢复”。
- 本地实测（去代理重启后端）：① 正常多轮；② 手动把会话标 `cleaned` + 删目录 → 再发消息确认同 id 恢复、上下文在；③ 用 v4-pro/v4-flash 两配置切换 → 确认上下文不丢、新模型生效；④ 制造一个 server_data 缺失的 id → 确认报错而非新建。

## 已确认
- 报错路径：透传 opencode 实际报错，不静默新建；后端保留 `force_new` 逃生口（暂不加前端按钮）。
- opencode.json 改为有条件写（首次/配置变/文件缺失），不再每轮白写。
