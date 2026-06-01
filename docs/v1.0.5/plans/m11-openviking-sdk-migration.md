# M11 — CodeAsk 后端 OpenViking 调用：手搓 HTTP → 官方 SDK 客户端

> 版本：v1.0.5
> 状态：方向已二次收敛（2026-06-01，嵌入式被运行时证伪后改定 HTTP 客户端；随后实测单篇 `add_resource` 目录化，改为按 feature wiki 目录导入），开发中。
> 一句话：**CodeAsk 后端改用官方 SDK `AsyncHTTPClient`，但 OpenViking 写入范围收窄为 feature 级 Wiki 目录；UI Wiki 搜索只走 SQL ILIKE，report 不再进入 OpenViking。`openviking-server` 原样不动，opencode 不受影响。**
> 关联：[openviking-integration 设计](../design/openviking-integration.md) · [m9 运行时拉起](./m9-openviking-runtime-provisioning.md)

---

## 0. 为什么是 HTTP 客户端而不是嵌入式（2026-06-01 重定调依据，务必先读）

最初定的是用进程内嵌入式 `AsyncOpenViking(path=workspace)`。落地前的 V1/V2 运行时验证**在初始化阶段就被 OpenViking 自己的硬锁挡死**——不是 bug、是设计。

**开发 2026-06-01 验证记录（保留为证据）**：
- **前置发现**：`AsyncOpenViking(path=workspace)` 只覆盖 storage workspace，SDK 仍从 `OPENVIKING_CONFIG_FILE` / 默认路径读 `ov.conf`。未设置 `OPENVIKING_CONFIG_FILE` 时初始化即报 `FileNotFoundError: OpenViking configuration file not found`。
- **撞锁**：用临时 data dir 生成 `openviking/ov.conf`，启动 `openviking-server --config <tmp>/openviking/ov.conf` 后，再用 `OPENVIKING_CONFIG_FILE=<same ov.conf>` 构造 `AsyncOpenViking(path=<same workspace>)`，初始化失败：
  - `openviking.utils.process_lock.DataDirectoryLocked`
  - 原文：`Another OpenViking process (...) is already using the data directory '...'. Running multiple OpenViking instances on the same data directory causes silent storage contention and data corruption.`

**架构 review 对源码的核实**（非转述）：
- `AsyncOpenViking` → LocalClient → `service/core.py:244` `Core.initialize()` 一进来就 `acquire_data_dir_lock(workspace)`。
- `utils/process_lock.py` 在 workspace 写 `.openviking.pid`（持锁进程 PID）；另一个 OpenViking 进程再 init 同一 workspace 即抛 `DataDirectoryLocked`，**无法绕过**。
- 锁的原因（docstring 原文）：两进程同 data dir 会 silent **AGFS / VectorDB corruption**（向量层内存缓存 `_meta_data_cache` 不能跨进程协调；AGFS 落盘锁能协调、向量内存层不能）。错误信息本身给出的多消费方解法就是 **HTTP mode（单 server）**。

**结论**：在「server 给 opencode + CodeAsk 用 SDK + 共享同一 workspace」拓扑下，嵌入式三者互斥、无合规路径（停 server / 换 workspace / CodeAsk 自封 MCP 均已被否或断功能）。故改用官方 SDK 的 **HTTP 客户端** `AsyncHTTPClient`：它连已起着的 server，**不自取数据目录锁**，server / opencode 零影响。

**坦诚边界**：`AsyncHTTPClient` 内部仍是 `httpx` 打同样的 `/api/v1/*` 端点——本质还是 HTTP。本里程碑换的不是传输方式，而是**把手搓的 httpx 调用换成官方维护的 SDK 客户端类**（官方请求/响应模型、鉴权/配置/重试，删掉自拼 JSON / multipart 的定制代码，随上游升级）。价值在代码质量与可维护性，不是架构升级——这点负责人在嵌入式被证伪后知情选定。

---

## 1. 范围（就这么大）

本版本 CodeAsk 后端对 OpenViking 的自有调用只有这几类，全在 `rag/openviking/client.py:OpenVikingClient`：

| 现状（手搓 httpx） | 用途 | 改成（官方 SDK `AsyncHTTPClient`） | 端点 |
|---|---|---|---|
| `add_wiki_feature`（新增，目录 `add_resource`） | 写一个 feature 的整棵 Wiki knowledge-base | `add_resource(path=<wiki_workspace/current/{slug}/knowledge-base>, to=<wiki feature uri>)` | `/api/v1/resources` |
| `delete_resource`（`DELETE /fs`） | 删除已下线的 feature wiki 根 | `rm(uri, recursive)` | `DELETE /fs` |
| `find`（`POST /search/find`） | LLM / opencode 语义召回 | `find(query, target_uri, limit, score_threshold)`（同名同参，返回 `FindResult`） | `/api/v1/search/find` |
| `task_status`（`GET /tasks`） | 同步任务状态查询 | `get_task(task_id)` | `GET /tasks` |

**不在范围**：
- `openviking-server` 的拉起 / 生命周期 / 健康探针 / 配置——CodeAsk 已实现，本里程碑不碰。
- opencode 的 `/mcp` 接线——不动。server 保持 full capability，不做任何"只读 / 限工具 / 禁 worker"改造。
- 代码仓 → OpenViking（旧 M11，已延后）。
- report → OpenViking：本轮明确取消。report 仍留在 CodeAsk DB / Wiki UI 中，OpenViking 只接 Wiki knowledge-base。
- UI Wiki 搜索：`GET /api/wiki/search` 不再 OpenViking-first，改回纯 `NativeWikiSearchService` SQL ILIKE。OpenViking 只服务 LLM/RAG 召回。

## 1.1 OpenViking 资源层级（2026-06-01 二次收敛）

资源根分两类，先把层级定清楚；本轮只实现 `wiki/`，`code/` 预留给后续 repo 同步：

```text
viking://resources/codeask/
  wiki/
    opencode/
      ...来自 ~/.codeask/wiki_workspace/current/opencode/knowledge-base
    anything-llm/
      ...来自 ~/.codeask/wiki_workspace/current/anything-llm/knowledge-base
    openviking/
      ...来自 ~/.codeask/wiki_workspace/current/openviking/knowledge-base

  code/
    <repo_slug>/
      ...后续代码仓同步使用，本轮不实现
```

写入规则：
- 不再逐篇 `wiki_doc` 写 OpenViking。实测 `add_resource(path=单个 md, to=leaf uri)` 会把目标目录化，产生 `.path.ovlock`，没有可读可检索的真实文件节点。
- 直接使用现成工作区目录：`~/.codeask/wiki_workspace/current/{feature_slug}/knowledge-base`。该目录由现有 Wiki workspace exporter 同步维护，发布/导入后会更新；不再构造临时目录。
- 每个 feature 的 knowledge-base 目录用一次 `add_resource(path=..., to="viking://resources/codeask/wiki/{feature_slug}")` 导入。

增量语义（2026-06-01 官方资料核实）：
- CodeAsk 的同步任务粒度是 feature 目录：失败重试仍会重新调用 `add_resource(path=<knowledge-base dir>, to=<wiki feature uri>)`，不会在 CodeAsk 自己拆成单文件 retry job。
- OpenViking 服务端对同一个 `to` URI 的再次 `add_resource` 是增量/diff 更新路径，不是简单从零全量覆盖。官方资源文档说明：目标 URI 已存在时会保留临时树用于后续 diff comparison。
- `reindex(uri, mode="vectors_only")` 用于已有内容的语义/向量产物重建；官方系统文档说明它是 non-destructive，使用 rebuild/upsert behavior，不要求先 drop vector collection。
- 因此：本轮坚持 feature 目录导入，不再回退到逐篇 md 写入；失败或变更后的补偿以“再次提交同一 feature 目录”作为 CodeAsk 侧重试方式，具体差异处理交给 OpenViking。

`watch_interval` 能力：
- OpenViking 官方文档确认存在 Watch Task 机制：资源增量更新通过 watch task 实现；设置 `watch_interval > 0` 后，到期会自动重新触发 `add_resource`。
- MCP/CLI 层已有 `add_resource --watch-interval` / watch task 相关入口。当前已安装 SDK 的 `AsyncHTTPClient.add_resource` 签名未暴露 `watch_interval` 参数（本地核实签名为 `path/to/parent/reason/instruction/wait/timeout/strict/.../preserve_structure/telemetry`）。
- 本轮不启用自动 watch/interval 同步，仍由 CodeAsk 的显式 sweep / run_pending 驱动。原因：需要先确认 HTTP SDK 暴露方式或改走受支持端点/CLI/MCP；同时要定义取消 watch、更新 watch 间隔、重启后恢复、UI 可观测性等运维语义。该项记录为后续实现，不阻塞本轮。

后续自动同步计划（当前迁移与 E2E 验收完成后再做）：
- 优先实现 **CodeAsk 定时 sweep + add_resource**，作为 Wiki 内容同步的主方案，而不是先接 OpenViking watch task。定时任务扫描 `active + current` features，计算 `~/.codeask/wiki_workspace/current/{slug}/knowledge-base` 的内容 hash；hash 变化才入队 `wiki_feature` job，再调用同一个 `add_resource(path=目录, to=viking://resources/codeask/wiki/{slug})`。官方资料确认同一 `to` 的再次 `add_resource` 是 incremental update，适合作为内容同步入口。
- `reindex(uri)` 不作为内容同步方案。官方资料明确它只处理 OpenViking 中已有内容，不导入新文件；后续可作为 admin 手动按钮、embedding 配置变更后的批处理、或低频索引维护任务。
- OpenViking 自带 `watch_interval` 仍保留为另一路后续候选方案；等 HTTP SDK/REST/CLI/MCP 的稳定接入方式与 watch task 运维语义确认后，再评估是否替代或补充 CodeAsk 定时 sweep。

召回提示词规则：
- 无法确定 feature 时，优先从 `viking://resources/codeask/wiki` 做广义召回。
- 已能确定 feature 时，再收窄到 `viking://resources/codeask/wiki/{feature_slug}` 二次召回。
- 代码仓目录后续使用 `viking://resources/codeask/code/{repo_slug}`，本轮不要求模型调用。

---

## 2. 用哪个 SDK 入口

`openviking.__all__ = [SyncOpenViking, AsyncOpenViking, SyncHTTPClient, AsyncHTTPClient]`。
- 用 **`from openviking import AsyncHTTPClient`**（实体在 `openviking_cli.client.http`）。CodeAsk 是 async FastAPI，用异步版。
- **不用** `AsyncOpenViking`（嵌入式）——见 §0，撞数据目录锁。

构造（对源码 `http.py:137`）：
```python
from openviking import AsyncHTTPClient
client = AsyncHTTPClient(
    url=base_url,            # 现 OpenVikingClient 的 base_url
    account="codeask",       # 替代手设的 X-OpenViking-Account
    user="codeask",          # 替代 X-OpenViking-User
    agent_id="codeask",      # 替代 X-OpenViking-Agent
    timeout=...,             # 沿用现有超时
    # 如需额外头：extra_headers={...}
)
await client.initialize()
```
方法对应：写→`write` / `add_resource`；删→`rm`；搜→`find`；任务→`get_task`。

---

## 3. 实现（开发）

- **B1**：`OpenVikingClient` 内部从手搓 httpx 改为持有一个 `AsyncHTTPClient`，按事件循环缓存并初始化。
  - 公开方法调整为目录导入语义（`add_wiki_feature` / `delete_resource` / `find` / `task_status`）。`add_text_resource` 的单篇文本语义不再用于活同步路径。
  - `find` → SDK `find`，把 `FindResult` 映射回现有 `OpenVikingSearchHit`（uri / score / context_type / level / abstract / overview / content）。
  - `delete_resource` → `rm(uri, recursive=True)`，保留现状 not_found 不抛的语义。
  - `task_status` → `get_task(task_id)`。
  - `add_wiki_feature` → SDK `add_resource(path=<现成 knowledge-base 目录>, to=wiki_feature_uri(slug), wait=False, strict=False, preserve_structure=True)`。目录来自 `settings.data_dir/wiki_workspace/current/{slug}/knowledge-base`。
  - 指标 / 错误事件：包裹 SDK 调用计时。**breaker 事件必须重接到 SDK 异常**（2026-06-01 review 发现旧 httpx `Response` 那套 `_raise_for_status`/`_emit_breaker_event` 已成死代码、信号哑火）：SDK 失败抛 `openviking_cli.exceptions.OpenVikingError` 子类，带 `.code`/`.message`/`.details`。在 4 个 SDK 调用外层 `except OpenVikingError as exc`，`if exc.code in {"UNAVAILABLE", "RESOURCE_EXHAUSTED"}` → `emit_event("openviking_breaker_tripped", ...)` 再 re-raise；删掉吃 `httpx.Response` 的死方法 + `import httpx`。
  - `delete_resource` 的 not_found 判定改为**按异常类型** `except NotFoundError`（现状字符串匹配 `"not found"/"404"` 能跑但脆）。
- **B2**：`app.py:177` 注入点改为构造 `AsyncHTTPClient`；server 拉起 / opencode MCP 接线**不动**。
- **B3**：`sync.py` 从单篇 `wiki_doc` / `report` 同步改为 feature 级 `wiki_feature` 同步：
  - `sweep_all` 只扫描有发布 Wiki 文档的 feature，按 feature 聚合内容 hash，入队 `source_type="wiki_feature"`。
  - 运行 job 时直接读取 `data_dir/wiki_workspace/current/{slug}/knowledge-base`，调用 `add_wiki_feature`。
  - report snapshots / report work item 不再生成。
  - **已知遗留（不在 M11 修，归 [m12](./m12-wiki-workspace-incremental.md)）**：该磁盘目录目前只在 opencode 会话启动时全量重建，不随 wiki 增删改更新 → "发布 wiki 但未开 opencode" 不会同步、"改后未开 opencode" 会推旧内容。负责人定调：M11 不加桥接，作为遗留由 M12 写时增量投影器根治；M11 的 SDK 迁移本身不因此打回。
- **B4**：`api/wiki/search.py` 去掉 OpenViking-first，直接调用 `NativeWikiSearchService` SQL ILIKE。
- **B5**：opencode/OpenViking 提示词补充召回策略：未知 feature 先搜 `viking://resources/codeask/wiki`，明确 feature 后搜 `viking://resources/codeask/wiki/{slug}`。
- 涉及文件：`rag/openviking/client.py`（核心）、`app.py`（注入）、`pyproject.toml`（`openviking` 依赖 m9 已装）、`tests/unit/test_openviking_client.py`（重写为 fake SDK 客户端）。

> 注：嵌入式方案下的 V1（两核可见性）已随之作废——HTTP 客户端只有 server **一个核**，opencode 与 CodeAsk 都经它，不存在跨进程可见性问题。V2 退化为「server 现有 write→find 行为」，即当前 httpx 实现每天在跑、已验证 OK 的路径，无需专门 spike。

---

## 4. 验收闸门
- [ ] `OpenVikingClient` 内部走官方 `AsyncHTTPClient`；后端不再有自拼 httpx 请求 / multipart 上传的定制代码
- [ ] Wiki 写入按 feature 目录导入：`~/.codeask/wiki_workspace/current/{slug}/knowledge-base` → `viking://resources/codeask/wiki/{slug}`
- [ ] report 不再进入 OpenViking；旧 report sync job 不再由 sweep 产生
- [ ] UI `/api/wiki/search` 只走 SQL ILIKE，不调用 OpenViking
- [ ] breaker 事件 `openviking_breaker_tripped` 已重接到 SDK 异常（`UNAVAILABLE`/`RESOURCE_EXHAUSTED`）并有测试覆盖；无吃 `httpx.Response` 的死代码残留
- [ ] CodeAsk 同步三 feature wiki → OpenViking find 在 `viking://resources/codeask/wiki` 和单 feature 目录均可召回；opencode 会话内 OpenViking 检索仍命中（证明 server/MCP 未受影响）。*注：本验证在磁盘目录已是最新的前提下进行（当前靠 opencode 会话或手动重建保证）；目录自动新鲜度是 M12 的遗留，不阻塞本闸门*
- [ ] 后端 pytest / 集成测试 / live e2e 全绿；ruff / pyright clean
- [ ] 待实现项已记录：当前任务完成后，优先实现 CodeAsk 定时 `sweep + add_resource` 作为 Wiki 内容自动同步；OpenViking `watch_interval` 和 `reindex` 分别作为后续候选/索引维护能力，不阻塞本轮
