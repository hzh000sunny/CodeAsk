# M11 — CodeAsk 后端 OpenViking 调用：HTTP → 官方 SDK

> 版本：v1.0.5
> 状态：方向已定（2026-06-01），待开发实现。
> 一句话：**把 CodeAsk 后端写 wiki / 写 report / find 这三类当前走 HTTP 的调用，改成官方 SDK（进程内嵌入式 `AsyncOpenViking`）调用。`openviking-server` 原样不动。**
> 关联：[openviking-integration 设计](../design/openviking-integration.md) · [m9 运行时拉起](./m9-openviking-runtime-provisioning.md)
> 来源：负责人定调——CodeAsk 自己用 SDK；server 不动（生命周期 CodeAsk 已实现、full capability、继续服务 opencode 的 MCP，不限制、不只读）；代码仓→OpenViking（旧 M11）延后。

---

## 0. 范围（就这么大）

本版本 CodeAsk 后端对 OpenViking 的自有调用只有三类，全在 `rag/openviking/client.py:OpenVikingClient`：

| 现状（HTTP） | 用途 | 改成 |
|---|---|---|
| `add_text_resource`（temp_upload + `POST /resources`） | 写 `wiki_doc` / `report`（两类都是 markdown 文本，同构） | 官方 SDK 写 |
| `delete_resource`（`DELETE /fs`） | 删除已下线的 wiki/report | 官方 SDK 删 |
| `find`（`POST /search/find`） | wiki 搜索召回 | 官方 SDK find |
| `task_status`（`GET /tasks`） | 同步任务状态查询 | 官方 SDK 查询 |

**不在范围**：
- `openviking-server` 的拉起 / 生命周期 / 健康探针 / 配置——CodeAsk 已实现，本里程碑不碰。
- opencode 的 `/mcp` 接线——不动。server 保持 full capability，不做任何"只读 / 限工具 / 禁 worker"改造。
- 代码仓 → OpenViking（旧 M11，已延后）。

---

## 1. 用哪个 SDK 入口

`openviking.__all__ = [SyncOpenViking, AsyncOpenViking, SyncHTTPClient, AsyncHTTPClient]`。
- 用 **`AsyncOpenViking(path=workspace)`**（进程内嵌入式，async，单例，直接挂本地 workspace）。CodeAsk 是 async FastAPI，用异步版。
- 不用 `AsyncHTTPClient`（那是 SDK 自带的连服务器 HTTP 客户端，本质还是 HTTP，不是"CodeAsk 用 SDK"的诉求）。

方法对应：写→`write(uri, content)` 或 `add_resource(...)`；删→`rm(uri, recursive)`；搜→`find(...)`；任务→对应任务查询。

---

## 2. 落地前的一项运行时验证（先做，10 分钟级）

> 这是唯一一个可能"静默出错"的点，不是流程负担：

CodeAsk 写改走嵌入式核后，**opencode 仍从 server 那个核读**（server 不动）。两个核共享同一本地 workspace。需确认：

- [ ] **V1**：CodeAsk 嵌入式核 `write` 一篇 wiki → server 核（即 opencode 走的 `/mcp` find）**能否召回到这篇新内容**。
  - 能 → 两核经共享 workspace 可见，方案成立，直接进 §3。
  - 不能（server 核的本地向量索引常驻内存、不感知另一进程写入）→ opencode 会看不到 CodeAsk 新同步的 wiki，这是要在实现前就知道的硬事实，带结论回负责人再定（不在文档里擅自加方案）。
- [ ] **V2**：嵌入式核**自己** `write` 后 `find` 能召回（CodeAsk wiki 搜索直接依赖它）。上个会话独立嵌入式进程实测出现过 `find` 召回空、`reindex` 报 `OpenVikingService not initialized`，需确认在 CodeAsk 正常初始化路径下是否复现 / 如何避免。

---

## 3. 实现（开发）

- **B1**：`OpenVikingClient` 内部从 httpx 改为持有 `AsyncOpenViking(path=workspace)`，app 启动时 `initialize()` 一次（单例）。
  - 公开方法签名**保持不变**（`add_text_resource` / `delete_resource` / `find` / `task_status`），让 `sync.py`、wiki 搜索映射、admin/status API 调用方零改动。
  - `add_text_resource` → `write`/`add_resource`（按 V2 选定能进语义/向量队列、之后 find 可召回的那条）。
  - `find` → 嵌入式 `find`，结果映射回现有 `OpenVikingSearchHit`。
  - `delete_resource` → `rm`（保留现状 not_found 不抛的语义）。
  - 指标 / 错误事件：包裹嵌入式调用计时 + 捕获 SDK 异常（嵌入式无 HTTP 503 breaker，改异常分类映射 `openviking_breaker_tripped` 等事件）。
- **B2**：`app.py:177` 注入点改为构造嵌入式核；server 拉起 / opencode MCP 接线**不动**。
- 涉及文件：`rag/openviking/client.py`（核心）、`app.py`（注入）、`pyproject.toml`（`from openviking import AsyncOpenViking`，依赖 m9 已装）、`tests/unit/test_openviking_client.py`（重写为嵌入式核）。

---

## 4. 验收闸门
- [ ] V1 / V2 验证结论成文（§2 勾选 + 数据）
- [ ] `OpenVikingClient` 内部走嵌入式 `AsyncOpenViking`，公开接口未变；后端不再有自身→server 的 HTTP 调用
- [ ] `sync.py` / wiki 搜索映射 / admin/status API 调用方零改动仍全绿
- [ ] CodeAsk 同步 wiki/report → CodeAsk wiki 搜索召回正常；opencode 会话内 OpenViking 检索仍命中（证明 server/MCP 未受影响）
- [ ] 后端 pytest / 集成测试 / live e2e 全绿；ruff / pyright clean
- [ ] 保留旧 httpx 实现一版周期，feature-flag 可切回（回滚演练通过）
