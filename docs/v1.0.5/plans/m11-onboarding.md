# M11 上手学习路径 —— 给接手 SDK 迁移的新开发

> 目标任务：把 CodeAsk 后端写 wiki / 写 report / find 这几个走 HTTP 的 OpenViking 调用，改成官方**进程内嵌入式 SDK** `AsyncOpenViking`。`openviking-server` 原样不动。
> 任务定义见 [m11-openviking-sdk-migration.md](./m11-openviking-sdk-migration.md)（先别急着读，按下面顺序到 §5 再读）。
> 分工：你负责实现 + 自测；architect 做 review / 最终验收。

---

## 阶段 0 —— 把环境跑起来（半天）

目的：能本地启动 CodeAsk + OpenViking，能跑测试。跑不起来后面全是空中楼阁。

1. 装依赖：项目用 `uv`。`uv sync` 一次装齐（`openviking==0.3.17` 是声明依赖，会进 `.venv`）。
2. 前置组件：
   - Ollama + `bge-m3` embedding 模型 —— 见 [`specs/ollama-installation.md`](../specs/ollama-installation.md)。
   - OpenViking server 启动机制 —— 见 [`specs/openviking-server-bootstrap.md`](../specs/openviking-server-bootstrap.md) 与 [`m9-openviking-runtime-provisioning.md`](./m9-openviking-runtime-provisioning.md)（server 生命周期 CodeAsk 已托管，**你不用改它**，但要懂它怎么起的）。
3. 启动：`README.md` / `INSTALL.md` + `./start.sh`（需要先 `export CODEASK_DATA_KEY=...`，脚本里有生成命令）。
4. 测试 / 静态检查命令（背下来，全程要用）：
   - `uv run pytest tests/unit/test_openviking_*.py`（先只跑 openviking 相关）
   - `uv run pytest`（全量）
   - `uv run ruff check . && uv run pyright`

**产出**：本地能登录 admin、OpenViking server 健康、`uv run pytest tests/unit/test_openviking_client.py` 绿。

---

## 阶段 1 —— 全局认知：CodeAsk 怎么用 OpenViking（半天，只读）

目的：在脑子里建立"两个消费方 + 一个 server"的架构图。

按顺序读：
1. [`docs/v1.0.5/README.md`](../README.md) —— v1.0.5 在做什么（Wiki/Report 的 RAG）。
2. [`docs/v1.0.5/prd/rag-knowledge.md`](../prd/rag-knowledge.md) —— 产品契约：为什么要 RAG、wiki_doc / report 两类知识、检索怎么用。
3. [`docs/v1.0.5/design/openviking-integration.md`](../design/openviking-integration.md) —— **最重要**。OpenViking 集成设计：URI 体系、同步、检索、opencode 经 MCP 检索。

**必须建立的认知（读完能自己画出来）**：
```
openviking-server 子进程 (:1933, CodeAsk 托管生命周期, ov.conf)
   ├── CodeAsk 后端  (rag/openviking/client.py, httpx)  → 写 wiki/report、删、find   ← 【本任务只改这条】
   └── opencode (独立进程)  → /mcp 检索                                              ← 【绝对不动】
```
- opencode 是独立进程，只能走 HTTP MCP，**物理上无法用进程内 Python SDK** → 这就是 server 必须保留的原因。

**产出**：一句话说清"本任务改哪条、为什么 server 不能动"。

---

## 阶段 2 —— 读懂集成模块 `src/codeask/rag/openviking/`（1 天，只读）

逐文件过一遍（带着"哪些是本任务要碰的"去读）：

| 文件 | 看什么 | 本任务相关度 |
|---|---|---|
| `client.py` | **`OpenVikingClient` 的 4 个方法**：`add_text_resource` / `delete_resource` / `find` / `task_status`，现在都是手搓 httpx 打 `/api/v1/...` | ★★★ 要改的就是这里 |
| `sync.py` | 同步引擎：`SyncResource`、`enqueue`、`run_pending_jobs`、`_wiki_doc_snapshots` / `_report_snapshots`。看 wiki_doc/report 怎么变成 `SyncResource` 再调 `add_text_resource` | ★★★ 调用方，签名不能破 |
| `config.py` | `ov.conf` 生成（server 段 / embedding 段 / storage workspace 路径） | ★★ 要知道 workspace 路径从哪来 |
| `process.py` | `OpenVikingProcessManager`：server 拉起 / 健康探针 / 生命周期 | ★ 只读，不改 |
| `uri.py` | `wiki_doc_uri` / `report_uri`：viking:// URI 规则 | ★★ 写入落位用 |
| `models.py` `metrics.py` `dashboard.py` `health.py` `hooks.py` `tuning.py` | 数据模型、指标、事件、健康 | ★ 了解即可 |

然后看接线：`src/codeask/app.py` 搜 `OpenVikingClient(` / `OpenVikingProcessManager(` / `_resolve_openviking_mcp_config`（约 169–225、764 行附近）—— **`OpenVikingClient` 在哪构造、注入给谁**（这是 B2 的改点）；`opencode` 的 MCP 接线长什么样（确认你不会碰到它）。

**产出**：能指出"`add_text_resource` 从被调用到发 HTTP 的完整链路"，以及"`OpenVikingClient` 在 app.py 的构造点"。

---

## 阶段 3 —— 跟一遍数据流（半天，跑 + 读）

把阶段 2 的静态认知变成动态的：

1. 看测试当文档：`tests/unit/test_openviking_sync.py`、`tests/unit/test_openviking_client.py`、`tests/integration/test_openviking_write_hooks.py` —— 它们怎么造一篇 wiki / report、怎么断言写入与召回。
2. 本地实操：在 admin 里建一个 feature + 一篇 wiki，观察同步任务（m8/m10 的 dashboard），确认它最终经 `add_text_resource` 写进 OpenViking，然后 wiki 搜索能召回。

**产出**：亲眼看到"一篇 wiki 从录入 → 同步 → 可搜索"的全过程。

---

## 阶段 4 —— 学 OpenViking SDK（半天）

只学本任务要用的那一个入口。

1. SDK 装在 `.venv/lib/python3.*/site-packages/openviking/`。顶层 `__all__ = [SyncOpenViking, AsyncOpenViking, SyncHTTPClient, AsyncHTTPClient]`。
2. **本任务用 `AsyncOpenViking`**（`async_client.py`，docstring "embedded mode only"）：
   ```python
   from openviking import AsyncOpenViking
   client = AsyncOpenViking(path="/path/to/workspace")   # 进程内核，直接挂本地 workspace，单例
   await client.initialize()
   await client.write(uri, content)        # 或 add_resource(...)
   await client.find(query=..., target_uri=..., limit=...)
   await client.rm(uri, recursive=...)
   ```
3. **不要用 `AsyncHTTPClient`** —— 它是 SDK 自带的"连服务器 HTTP 客户端"，本质还是 HTTP，不是本任务要的"CodeAsk 自己用 SDK"。（这点踩过坑，明确否决。）
4. 方法清单可直接 `grep "async def" .venv/.../openviking/async_client.py` 或读源码；够本任务用的有 `write / add_resource / find / search / read / rm / mv / mkdir / stat / ls`。

**产出**：能在一个独立小脚本里 `AsyncOpenViking(path=...)` 写一篇 md、再 `find` 出来。

---

## 阶段 5 —— 读任务定义 + 硬约束（半天）

现在读 [`m11-openviking-sdk-migration.md`](./m11-openviking-sdk-migration.md) 全文。重点吃透：

- **范围**：只改 `OpenVikingClient` 的 4 个方法的内部实现；公开方法签名**不变**（这样 `sync.py` / wiki 搜索映射 / admin API 零改动）。
- **硬约束（违反即返工）**：
  1. `openviking-server` 原样不动 —— 生命周期 / 配置 / 健康探针 / MCP 都不碰。
  2. **不许**把 server 改成只读、不许限制它的 MCP 工具、不许禁它的嵌入 worker —— 那是破坏 server 自身能力。
  3. 不用 `AsyncHTTPClient`。
  4. 不做代码仓 → OpenViking（那是延后的旧 M11，见同目录 `m11-repo-openviking-sync.md` 顶部 banner）。

**产出**：能复述范围和 4 条硬约束。

---

## 阶段 6 —— 先跑两个验证（动手第一步，关键）

**别先写实现**。先用阶段 4 的小脚本能力，回答两个可能"静默出错"的问题（任务文档 §2 的 V1/V2）：

- **V1**：CodeAsk 嵌入式核 `write` 一篇 wiki 到共享 workspace 后，**server 那个核（opencode 走的 `/mcp` find）能否召回到**？
  - 背景：server 不动，opencode 仍从 server 核读；两核共享同一本地 workspace。server 的本地向量索引若常驻内存、不感知另一进程的写，opencode 就看不到新 wiki。
  - 做法：起着 server，另起一个嵌入式核 `write` 一篇，然后用 server 的 HTTP `/search/find`（或 MCP）查能否召回。
- **V2**：嵌入式核**自己** `write` 后 `find` 能否召回？（CodeAsk wiki 搜索直接依赖它。历史上独立嵌入式进程测过 `find` 召回空、`reindex` 报 `OpenVikingService not initialized`，要确认在正常初始化路径下是否复现 / 如何避免。）

**产出**：V1 / V2 的结论 + 证据，写进任务文档 §2 的勾选项。**若 V1 不通或 V2 召回空，先停下来同步给 architect/负责人，不要擅自加方案。**

---

## 阶段 7 —— 实现 + 自测

V1/V2 通过后，按任务文档 §3：

- B1：`OpenVikingClient` 内部换成持有 `AsyncOpenViking(path=workspace)`，4 个方法逐个映射（写→`write`/`add_resource`、删→`rm`、find→`find`、task→任务查询）；保留指标计时 + 把 SDK 异常映射成现有事件。
- B2：`app.py` 的 `OpenVikingClient` 构造点改造；server / opencode MCP 接线不动。
- 测试：重写 `tests/unit/test_openviking_client.py`；确认 `tests/unit/test_openviking_sync.py`、wiki 搜索映射、admin/status 集成测试**因接口未变而基本不改仍绿**；补 V1/V2 的集成/e2e。
- 收尾：`uv run pytest` 全绿 + `uv run ruff check . && uv run pyright` clean；保留旧 httpx 实现 + feature-flag 可回滚。

**产出**：对照任务文档 §4 验收闸门逐条自查通过，交 architect review。

---

## 常见坑 / 提醒

- **embedding 慢是环境问题，不是 bug**：本机 ollama `bge-m3` `max_concurrent=1`、单次 5–20s，队列会堆积。慢不等于错——确认任务在异步推进即可，别误判失败、别去加吞吐上限。
- **删除判据**：判断一篇是否真被删，看 `read`/`stat` 是否 404，**别**用"find 不再返回该 URI"。
- workspace 路径来自 `config.py` 的 `OpenVikingRuntimeConfig`（`data_dir/openviking/workspace`），嵌入式核要挂的就是这个，和 server 同一个。
- 改动只在 `rag/openviking/` + `app.py` 注入点；任何想去动 server / opencode / MCP 的冲动，停下来，那不在范围内。
