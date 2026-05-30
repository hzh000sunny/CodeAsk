# M8 — OpenViking Dashboard UX 与指标实装

> 版本：v1.0.5
> 状态：Completed
> 关联：[acceptance §4](./acceptance-checklist.md) · [m1-dashboard-ui-redesign](./m1-dashboard-ui-redesign.md) · [m7](./m7-turn-control-and-multi-repo.md)
> 来源：2026-05-28 负责人在真实库使用反馈，四条 dashboard 体验缺陷 + 一项后端 stub。

---

## 0. 背景与范围

2026-05-28 在真实库使用 OpenViking dashboard（`/settings` 页）时观察到四类问题，逐项确认全部是真实缺陷：

1. **字段含义"乱码"**：同步任务卡片显示 `wiki_doc / 47 / openviking-degraded-fallback-1779937966813`，事件流显示 `repo · f7606c2988444040`；用户读不出来是什么资源。运行指标卡三项全显示"未采集"。
2. **`显示 indexed (46)` 后顺序错乱**：indexed 与 cancelled 行按 `updated_at DESC` 完全交错；后端 `list_jobs(limit=50)` 上限固定 200，任务量再大也只能看到 200 条窗口。
3. **加载更多"闪一下回去 + 计数无端增加"**：分页交互与 `collapseConsecutiveEvents` 折叠规则、`refetchInterval` 互打架；分页期间新事件被 `before_id` 过滤掉、再也不显示。
4. **调优参数全展开**：11 个键一次性铺满，没有折叠/分组切换。

### 真实数据库证据（`~/.codeask/data.db`，2026-05-28 实测）

```
sync_jobs:        wiki_doc/indexed × 60, e2e_unknown/cancelled × 4   （cap 50 → 显示 46 indexed + 4 cancelled）
dashboard_events: repo_synced/repo/success × 258, manual_retry_failed × 192, tuning_change × 175+14, ...
repo_synced payload: {"repo_id": "...", "name": "Feature scoped claude-code ...", "source": "...", "reason": "..."}
                     payload.name 已落库但 UI 完全没读
```

### 锁定决策（2026-05-28 负责人拍板）

- **① 全部四项都修**。
- **1d 指标采集**：要"**真实采集**"，不只是隐藏卡片。
- **1c e2e 残留**：测试自己 teardown + 一次性 SQL 清历史（不在产品 API 里加测试数据清理按钮）。
- **④ 调优样式**:采用 **B 方案(摘要 + 操作面板)**,不做 A 行折叠表单。设计参考截图 `~/img/m8-tuning-b-collapsed.png` / `m8-tuning-b-expanded.png`,demo HTML 在 `.tmp/m8-tuning-demo/`。
- **新 plan**：本文件 `docs/v1.0.5/plans/m8-dashboard-ux.md`，与 m1/m7 并列。

### 改动面（仅范围说明，细节见各小节）

- 后端：
  - `src/codeask/api/openviking_status.py`（sync_jobs 排序与分页、events 接口保持不变但增加 `since_id` 概念可选、`_job_to_dict` 补 `display_name`、`_metrics_snapshot` 改为真实采集）
  - `src/codeask/rag/openviking/sync.py`（`list_jobs` 增加按状态 + cursor 分页）
  - `src/codeask/rag/openviking/client.py`（latency ring buffer instrumentation）
  - `src/codeask/rag/openviking/metrics.py`（**新建**，5min 滚动窗口聚合 throughput / latency p95 / breaker trips）
- 前端：
  - `frontend/src/components/settings/OpenVikingDashboard.tsx`（事件 summary 读 payload.name；同步任务卡片按状态分组 + 服务端分页；事件流改为完整分页栏；调优默认折叠 + scope `<details>` 切换）
  - `frontend/src/lib/api-openviking.ts`（新增 status/cursor 参数）
  - `frontend/src/types/api.ts`（`OpenVikingSyncJob.display_name`、`SyncJobsResponse.next_cursor` 等）
- 测试与 e2e：
  - 单测 + vitest + e2e teardown
- 一次性 SQL 清理脚本：`scripts/cleanup_openviking_e2e_fixture.sql`（**新建**）

---

## ① 同步任务/事件流字段含义

### 1a — `eventSummary` 优先读 `payload.name`

#### 现状

`frontend/src/components/settings/OpenVikingDashboard.tsx:962-997`

```ts
function eventSummary(event) {
  if (event.event_type === "tuning_change") { ... }
  if (payload?.count !== undefined) { ... }
  if (payload?.job_id !== undefined) { ... }
  if (event.source_id) {
    return `${event.source_type ?? "system"} · ${event.source_id}`;  // → "repo · f7606c2988444040"
  }
  ...
}
```

`payload.name` / `payload.title` 完全没被读。`repo_synced` 事件 payload 里有 `name`（"Feature scoped claude-code ..." 等可读字符串）。`wiki_doc_changed` 也类似。

#### 改动

- 在 `if (event.source_id)` **之前** 增加优先级链：
  - 若 `payload?.name` 是字符串 → 返回 `${source_type} · ${payload.name}`
  - 若 `payload?.title` 是字符串 → 返回 `${source_type} · ${payload.title}`
  - 若 `payload?.feature_slug` 是字符串且 `payload?.relative_path` 是字符串 → 返回 `${source_type} · ${feature_slug}/${relative_path}`
- 既有的 `count` / `job_id` 分支保留；只是把"可读名"提前到 `source_id` fallback 之前。

#### 测试

- vitest `frontend/tests/openviking-dashboard.test.tsx`：mount 一条 `repo_synced` 事件 fixture，payload 含 `name: "Feature scoped claude-code 1778952333054"`，断言渲染文本含该名字、**不含** hex `f7606c2988444040`。
- vitest 同文件另一个用例：payload 不含 name 但有 source_id 时，回退到旧行为。

### 1b — sync_jobs API 增加 `display_name` 字段

#### 现状

`src/codeask/api/openviking_status.py:402-419`

```py
def _job_to_dict(job: OpenVikingSyncJob) -> dict[str, Any]:
    return {
        "id": job.id, "source_type": job.source_type, "source_id": job.source_id,
        "feature_slug": job.feature_slug, "viking_uri": job.viking_uri,
        ...
    }
```

`source_id` 对 wiki_doc 是 `WikiDocument.id`（数字主键），对 e2e_unknown 是 fixture 串。前端没有任何字段可以展示"这条任务在同步谁"。

`WikiNode.name`（节点名/文档名，`db/models/wiki/node.py:36`）和 `WikiNode.path` 都已存在，缺的是查询/序列化。

#### 改动

- **新增子查询**：在 `_job_to_dict` 之前，统一为返回的一批 jobs 预解析 `display_name`：
  - `source_type == "wiki_doc"`：`SELECT wn.name FROM wiki_documents wd JOIN wiki_nodes wn ON wn.id = wd.node_id WHERE wd.id = ?`（按一次性 IN 批量解析，避免 N+1）；若文档已删/路径缺失，回落到 `feature_slug + "/" + source_id`。
  - `source_type == "report"`：从 `reports` 表读 `title`（或 `summary` 截断）。
  - `source_type == "e2e_unknown"` 或未知：回落 `source_id`。
- 返回字段：`"display_name": str | null`。
- 前端 `SyncJobItem`（`OpenVikingDashboard.tsx:539-578`）的 `<strong>` 改用 `job.display_name ?? job.source_type`，`<span>` 改用 `job.source_id`；若都有，三行为 "name / source_type · source_id / feature_slug"。

#### 测试

- pytest：`tests/integration/test_openviking_admin_api.py` 添加用例 — 准备 wiki_doc/Reports/feature，GET `/admin/openviking/sync_jobs`，断言每条返回的 `display_name` 与底层 `WikiNode.name` / `Report.title` 一致；e2e_unknown 行 `display_name` 是 source_id 或 null。
- vitest：fixture 含 `display_name` 字段，断言渲染。

### 1c — e2e fixture 自清 + 一次性历史清理

#### 现状

`frontend/e2e/openviking-dashboard-management-live.spec.ts:57-61`

```ts
const sourceId = `mgmt-retry-${Date.now()}`;
await api.post("/api/admin/openviking/sync_jobs/enqueue", {
  data: { source_type: "e2e_unknown", source_id: sourceId, ... }
});
```

测试结束没有任何清理；每次跑都往真库塞一条。库里现存 4 条历史污染。

#### 改动

- **测试自清**（在 spec 内部）：
  - 使用 Playwright 的 `test.afterEach(async ({ ... }) => { ... })` 钩子。
  - 钩子里通过新增 admin DELETE 接口删除该 spec 创建的具体 job id。
  - 接口：`DELETE /api/admin/openviking/sync_jobs/{job_id}`，**只允许删 `status in ("cancelled","failed")` 的行**（保护性：跑中/已索引的不能删）。这个 DELETE 本身是产品合理操作（清失败/取消），不是测试专用 API。
  - spec 在 `test.afterEach` 里记录 `createdJobIds: string[]`，逐个调 DELETE。
- **一次性清理脚本**：`scripts/cleanup_openviking_e2e_fixture.sql`
  ```sql
  -- 删 e2e_unknown 历史残留 sync job 行 + 关联 events
  DELETE FROM openviking_dashboard_events WHERE source_type = 'e2e_unknown';
  DELETE FROM openviking_sync_jobs WHERE source_type = 'e2e_unknown';
  ```
  - README 或本 plan 末尾给出 sqlite3 调用命令，由负责人手动跑一次。**不**加到 alembic（这是数据清理不是 schema 变更）。
- **不动**：测试不专门跑在隔离 DB（live e2e 本来就期望命中真栈）。

#### 测试

- pytest：`tests/integration/test_openviking_admin_api.py` 新增 `test_delete_sync_job_allowed_for_cancelled` / `test_delete_sync_job_rejected_for_running`。
- Playwright spec 自身的 `afterEach` 跑一遍后，再 GET `/admin/openviking/sync_jobs?status=cancelled&source_type=e2e_unknown` 应返回空。

### 1d — 真实指标采集

#### 现状

`src/codeask/api/openviking_status.py:347-355`

```py
def _metrics_snapshot() -> dict[str, Any]:
    return {"collected": False, "window_seconds": 300,
            "throughput_per_min": None, "latency_p95_ms": None, "breaker_trips": None,
            "message": "未采集"}
```

**永远返回 stub**。没有任何采集源。

#### 采集源决策（**在本 plan 内锁定**）

| 指标 | 采集源 | 实施 |
|---|---|---|
| **throughput_per_min** | `openviking_sync_jobs.last_indexed_at >= now-5min` 行数 / 5 | SQL 聚合，无新状态 |
| **breaker_trips** | `openviking_dashboard_events.event_type IN ('openviking_breaker_tripped','openviking_restart_detected')` 5min 内行数 | 已部分入库（restart_detected 已有；breaker_tripped 需要新写一个 emit_event 钩子） |
| **latency_p95_ms** | `OpenVikingClient` 每次请求的 perf_counter delta → 进程内 deque（cap 1000） | 新增内存状态；进程重启清零（合理） |

#### 实施步骤

##### 1d-1 新建 `src/codeask/rag/openviking/metrics.py`

- 一个进程级单例 `OpenVikingMetricsRecorder`：
  ```py
  class OpenVikingMetricsRecorder:
      def __init__(self, *, window_seconds: int = 300, cap: int = 1000) -> None:
          self._window = window_seconds
          self._latencies: deque[tuple[float, float]] = deque(maxlen=cap)  # (epoch_seconds, ms)
          self._lock = asyncio.Lock()
      async def record_latency(self, ms: float) -> None: ...
      def snapshot(self, *, now: float | None = None) -> dict[str, Any]: ...
  ```
- `snapshot()` 返回 `{collected: True, window_seconds: 300, latency_p95_ms: <int|None>, samples: <int>}`；空 deque 时 `collected=False` 且 `message="warming up"`。
- 注：throughput / breaker_trips 不在 recorder 内 —— 它们走 DB SQL（无内存状态），由 `_metrics_snapshot()` 调用。

##### 1d-2 `OpenVikingClient` instrumentation

- 文件：`src/codeask/rag/openviking/client.py`
- 在每个对外 HTTP 请求方法（`search`, `temp_upload`, `delete_resource`, ...）开头打 `start = time.perf_counter()`，结尾 `await recorder.record_latency((time.perf_counter() - start) * 1000)`。
- recorder 通过依赖注入（app.state）或模块级 singleton 拿到；倾向 `app.state.openviking_metrics_recorder`，client 实例化时传入。
- 失败请求也记录（用 try/finally）。

##### 1d-3 Breaker trip 事件入库

- 现状：OpenViking 进程内部如果熔断，会拒服务 503。CodeAsk 这一侧 `OpenVikingClient` 拿到 503 / "circuit open" 错误时，要 emit 一条 `event_type='openviking_breaker_tripped'` 的 dashboard event。
- 文件：`src/codeask/rag/openviking/client.py`，在异常分支判定 `_is_circuit_open_response(response)` 后调用 `emit_event(...)`（async fire-and-forget，不影响主流程）。
- 失败兜底：emit_event 自身失败时只 log 不抛。

##### 1d-4 `_metrics_snapshot` 改为真实聚合

- 文件：`src/codeask/api/openviking_status.py:347-355`
- 改签：`async def _metrics_snapshot(request: Request) -> dict[str, Any]:`（拿 session_factory + recorder）。
- 内部：
  ```py
  recorder = request.app.state.openviking_metrics_recorder
  latency = recorder.snapshot()
  async with factory() as session:
      throughput_count = await session.scalar(
          select(func.count()).select_from(OpenVikingSyncJob)
          .where(OpenVikingSyncJob.last_indexed_at >= now - timedelta(seconds=300))
      )
      breaker_count = await session.scalar(
          select(func.count()).select_from(OpenVikingDashboardEvent)
          .where(OpenVikingDashboardEvent.event_type.in_(("openviking_breaker_tripped","openviking_restart_detected")))
          .where(OpenVikingDashboardEvent.created_at >= now - timedelta(seconds=300))
      )
  return {
      "collected": True,
      "window_seconds": 300,
      "throughput_per_min": round((throughput_count or 0) / 5, 2),
      "latency_p95_ms": latency.get("latency_p95_ms"),
      "latency_samples": latency.get("samples"),
      "breaker_trips": int(breaker_count or 0),
      "message": None,
  }
  ```
- 上游 `get_openviking_status`（同文件 line 56 附近）改为 `status_payload["metrics_5min"] = await _metrics_snapshot(request)`。

##### 1d-5 前端 `OpenVikingMetricsCard` 适配

- 文件：`OpenVikingDashboard.tsx:838-860`
- `collected === false` 时显示原"未采集"卡片但顺便显示 `metrics.message`（如 "warming up"）。
- `collected === true` 时把数字呈现。
- 新增：第四个小单元格显示 `samples`（latency sample count），让用户能看出"有多少请求支撑了 p95"。

##### 1d-6 App startup 注册 recorder

- 文件：`src/codeask/app.py`（或 lifespan 入口）
- `app.state.openviking_metrics_recorder = OpenVikingMetricsRecorder()`，在 OpenVikingClient 构造时把它注入。

#### 测试

- 单测：`tests/unit/test_openviking_metrics.py`（新）
  - `recorder.record_latency(50)` × 100 → `snapshot()["latency_p95_ms"]` 约 50（容差）。
  - 时间漂移 600s 后 snapshot 仍返回（deque 不按时间裁剪而按 cap；但 `_metrics_snapshot` 的 throughput/breaker 走 SQL 时间窗）。
- 集成：`tests/integration/test_openviking_status_api.py`（新或合入既有）
  - 准备 5 条 `last_indexed_at = now - 60s` 的 sync job + 1 条 `openviking_breaker_tripped` event。
  - GET status，断言 `metrics_5min.throughput_per_min ≈ 1.0`、`breaker_trips == 1`、`collected: true`。
- vitest：`MetricsCard` 渲染 fixture，断言 collected/未采集 两态展示。

---

## ② indexed 展开后顺序错乱 + 上限

### 现状

- 后端 `src/codeask/api/openviking_status.py:68-80`：`list_openviking_sync_jobs(status_filter, limit=50, max 200)`，**单一**按 `updated_at DESC` 排序（`sync.py:286`），不分页。
- 前端 `OpenVikingDashboard.tsx:444-537`：不传 limit/status，拿 50 条全打回来，本地用 `showIndexed` 切换、`visibleCount` 切片。
- 后果：indexed/cancelled/failed 混合按时间倒序，体感乱；且 `counts.indexed = 46` 是 50 条窗口里的统计，不是全表总数（实测全表 60）。

### 目标

- 服务端真正分页 + 按状态过滤。
- 前端按状态分块展示，每块单独"加载更多"。
- 卡片头上的 4 个 StatusPill（pending/running/failed/indexed）显示**全表**真实统计，不再依赖窗口。

### 实施步骤

#### ②-1 后端：分状态聚合接口

- 新增 `GET /admin/openviking/sync_jobs/summary`（轻量计数接口）：
  ```py
  @router.get("/admin/openviking/sync_jobs/summary")
  async def openviking_sync_jobs_summary(request: Request) -> dict[str, Any]:
      require_admin(request)
      async with request.app.state.session_factory() as session:
          rows = await session.execute(
              select(OpenVikingSyncJob.status, func.count())
              .group_by(OpenVikingSyncJob.status)
          )
      return {"counts": {str(s): int(n) for s, n in rows}}
  ```
- 修改 `list_openviking_sync_jobs`：
  - 接受 `status` (单个) + `limit` (默认 25，cap 100) + `cursor`（基于 `(updated_at, id)` 的 opaque base64 字符串）。
  - 排序保持 `updated_at DESC, id DESC` 做稳定分页。
  - 返回 `{ items: [...], next_cursor: str | null }`。
- `sync.py:283-290 list_jobs` 重写支持 `(status, cursor)` 参数；cursor 解析为 `(updated_at, id)` tuple，SQL where `(updated_at, id) < (cursor.updated_at, cursor.id)`。

#### ②-2 前端：分状态分块卡片

- 文件：`OpenVikingDashboard.tsx:444-537`
- 改造 `OpenVikingSyncJobsCard`：
  - 新增 `summaryQuery = useQuery({ queryFn: getOpenVikingSyncJobsSummary, ... })`，4 个 StatusPill 直接读 `summaryQuery.data.counts`（**全表** count）。
  - 卡片主体改为 4 个折叠分组：`failed`（默认展开）、`pending`、`running`、`indexed`（默认折叠）。`cancelled` 与 `failed` 合一组或单独一组，由实施者按视觉效果选；本 plan 不强约束。
  - 每组独立 `useInfiniteQuery`：`queryFn: ({ pageParam }) => listOpenVikingSyncJobs({ status, cursor: pageParam, limit: 10 })`。
  - 每组下方"加载更多"按钮调 `fetchNextPage`。
  - 删掉旧 `showIndexed` / `visibleCount` 切片本地状态。
- 文件：`frontend/src/lib/api-openviking.ts`
  - `listOpenVikingSyncJobs({ status?, cursor?, limit? })` —— 加参数。
  - 新增 `getOpenVikingSyncJobsSummary()`。
- 文件：`frontend/src/types/api.ts`
  - `OpenVikingSyncJobsResponse` 加 `next_cursor: string | null`。
  - 新增 `OpenVikingSyncJobsSummaryResponse`。

#### ②-3 兼容旧调用

- 旧 `listOpenVikingSyncJobs()` 不传参数仍走 `limit=25 + status=null`；其它前端引用点（如有）保持工作。grep 验证 `listOpenVikingSyncJobs` 引用全部走新签名。

### 测试

- pytest `tests/integration/test_openviking_admin_api.py`：
  - 准备 30 条 indexed + 10 failed → GET summary 返回精确 counts；GET `?status=indexed&limit=10` 返回 10 条 + next_cursor；带 cursor 续拉返回剩下 20 条 + next_cursor=null；带错 status 返回 422 或 400。
- vitest：`OpenVikingSyncJobsCard` 渲染 fixture，summary 显示总数；每分组初始 10 条 + "加载更多"按钮在 `next_cursor` 非空时出现；点击不会触发跨分组刷新。

---

## ③ 事件流直接分页，取消加载更多聚合

### 现状

`OpenVikingDashboard.tsx:128-176`

```ts
const eventsQuery = useQuery({
  queryKey: ["admin-openviking-events", eventOutcome, eventType, eventBeforeId],
  queryFn: () => listOpenVikingEvents({ ..., beforeId: eventBeforeId, limit: 10 }),
  refetchInterval: 5000,  // ← 分页时仍在跑
});
useEffect(() => {
  const payload = eventsQuery.data;
  if (!payload) return;
  if (!eventBeforeId) {
    setEventItems(payload.items);   // 一旦 next_before_id=null 回到 undefined，整列表被替换
    return;
  }
  setEventItems((current) => [...current, ...新增（去重）]);
}, [eventsQuery.data, eventBeforeId]);
```

合 `collapseConsecutiveEvents`（行 944-960），连续同 event_type 折叠成一行 + count。
真实数据库里 `repo_synced × 258` 连续，结果首屏 10 条 → "repo_synced ×10"；分页 10 条 → "×20"，视觉上无新行，只是 chip 数字涨。

后果两条：
- **a. 分页期间新事件丢失**：`before_id` 过滤掉所有新生成事件，refetchInterval 又一直跑同一个 before_id（5s 拉同一批旧数据）。
- **b. 折叠让分页"看不见"**：同类型连续事件被折叠成单 chip，加载更多只是让 chip 数字递增。

### 目标

- 取消"加载更多事件"模式，改为明确的上一页 / 下一页分页。
- 每页只展示当前页事件行，不跨页追加，不显示 `×N` 聚合 chip。
- 默认每页 5 条；底部显示总条数、当前页 / 总页数，支持选择每页 5 / 10 / 20 / 50 条，并可输入页码直接跳转。
- 历史页**暂停** refetchInterval；回到第 1 页时恢复实时刷新。
- 不再用 `setEventItems(payload.items)` 手工拼接，也不再使用 `useInfiniteQuery` 为事件流累积页；改为按 `(eventType, outcome, page, limit)` 查询单页数据。

### 实施步骤

#### ③-1 用页状态替换手工拼装 / infinite append

- 文件：`OpenVikingDashboard.tsx:128-176, 580-647`
- 改为：
  ```ts
  const [eventPage, setEventPage] = useState(1);
  const [eventPageSize, setEventPageSize] = useState(5);

  const eventsQuery = useQuery({
    queryKey: ["admin-openviking-events", eventOutcome, eventType, eventPage, eventPageSize],
    queryFn: () => listOpenVikingEvents({
      eventType: eventType || undefined, outcome: eventOutcome || undefined,
      page: eventPage, limit: eventPageSize,
    }),
    refetchInterval: eventPage === 1 ? 5000 : false,
  });
  const events = eventsQuery.data?.items ?? [];
  ```
- 删 `eventBeforeId` / `eventItems` / 手工 useEffect。
- `onOutcomeChange` / `onEventTypeChange` 同步重置 `eventPage=1`。
- 下一页 / 上一页：基于接口返回的 `total_pages` 做边界限制。
- 每页条数变更：重置到第 1 页，避免旧页码越界。
- 跳页：输入页码后按 `1..total_pages` 夹取；只在接口数据返回后做越界修正，避免加载中误把目标页夹回第 1 页。

#### ③-2 事件行直接展示

- 删除 `collapseConsecutiveEvents` / `EventGroup` / `settings-openviking-event-count` / child rows。
- `OpenVikingEventStream` 直接 `events.map(event => <EventItem event={event} />)`。
- 每条事件仍显示 `event_type`、`eventSummary(event)`、`created_at` 和 outcome badge。

#### ③-3 分页控件和暂停提示

- 卡片底部固定显示分页控件：`共 N 条 · 第 X / Y 页`、每页条数选择、`上一页` / `下一页`、页码输入 + `跳转`。
- 第 1 页时 `上一页` disabled；当前页等于 `total_pages` 时 `下一页` disabled。
- `pageNumber > 1` 时显示："正在查看历史事件页，实时刷新暂停；回到第 1 页后恢复刷新。"

### 测试

- vitest：`OpenVikingEventStream` 渲染 fixture
  1. 同一页给多条同 type 事件 → 每条事件都直接可见，不出现 `×N`。
  2. 默认每页 5 条，分页栏显示总条数与总页数。
  3. 输入页码跳转后只显示目标页事件，上一页事件不再留在列表里。
  4. 修改每页条数后回到第 1 页，并使用新的 `limit` 请求接口。
- pytest：`tests/integration/test_openviking_admin_api.py` 覆盖 events 接口 `page` / `limit` / `total` / `total_pages` 行为。

> **2026-05-28 验收补充**：分页骨架（页码 / 上一页下一页 / 跳页 / 每页条数 / 翻页暂停刷新）验收通过，"×N 数字累加"已消除。但事件**行内容**仍是机器字段、错误信息缺失、无处置入口——见 §⑥。§③-2 中"每条事件仍显示 `event_type`、`eventSummary`、`created_at` 和 badge"被 §⑥ 取代。

---

## ⑥ 事件行人话化与可操作性（2026-05-28 验收反馈追加）

### 现状缺陷（已逐条核对代码）

- **看不懂**：`EventItem`（`OpenVikingDashboard.tsx:1000`）标题直接渲染原始枚举 `event_type`（`repo_synced` / `sync_job_enqueued` / `openviking_breaker_tripped`…），无中文标题映射；`eventSummary`（:1398）多数情况退化成 `key=value · key=value` 的 payload dump；badge 是原始英文 `info/success/warning/error`。
- **错误信息丢失（真 bug）**：`eventSummary` 末尾 `Object.entries(payload).slice(0, 3)`。`scheduled_refresh_summary` 失败时 payload=`{scanned, enqueued, skipped, error}`，`error` 是第 4 键被切掉，红徽章下只剩 `scanned=0 · enqueued=0 · skipped=0`。全程未对 `error/detail/message/reason` 做优先展示。
- **失败事件根本没入流（后端缺口）**：同步任务失败走 `sync.py` `mark_failed`→`_apply_failure_state`，只写 `job.error`，**不 emit 任何事件**。管理员最该看到的"某资源索引失败"在事件流里完全缺席。
- **不可操作**：warning/error 行无处置建议、无指向相关同步任务的链接/按钮（`sync_job_id` 数据里有但 UI 未用）。

### 锁定决策（2026-05-28 负责人拍板）

1. **完整人话行**：每种事件 = 中文标题 + 一句话人话描述；warning/error 时错误原因排在描述最前；badge 中文化。
2. **建议文案 + 按钮**：warning/error 行显示"建议：…"，并对可处置的事件给一个动作按钮/链接。
3. **补 emit `sync_job_failed`**：让同步失败出现在事件流里。

### ⑥-1 前端：事件行信息模型

在 `OpenVikingDashboard.tsx` 内新增三张映射 + 重写 `EventItem` / `eventSummary`：

- **标题映射** `EVENT_LABELS: Record<string, string>`（未命中回退原始 `event_type`）。至少覆盖：

  | event_type | 中文标题 |
  |---|---|
  | `repo_synced` | 仓库已同步 |
  | `sync_job_enqueued` | 同步任务已入队 |
  | `sync_job_failed` | 同步任务失败 |
  | `tuning_change` | 调优参数变更 |
  | `manual_retry` / `manual_retry_failed` | 手动重试 / 重试全部失败任务 |
  | `manual_resync` | 手动重新同步 |
  | `manual_rebuild_index` | 手动重建索引 |
  | `openviking_breaker_tripped` | OpenViking 熔断触发 |
  | `openviking_restart_detected` | OpenViking 进程重启 |
  | `scheduled_refresh_summary` | 定时同步汇总 |
  | `embedding_model_switched` / `embedding_rebuild_requested` | 向量模型切换 / 向量重建已请求 |
  | `ollama_settings_verified` / `ollama_recovery` | Ollama 设置已验证 / Ollama 已恢复 |

- **描述函数** `describeEvent(event): string`——按类型套人话模板，保留已有 `tuning_change`（`scope.key: before → after`）和 `repo_synced`（带 `name`）逻辑，并新增：
  - `sync_job_failed`：`{资源名} 索引失败：{error}（第 {attempts} 次，{将重试/已放弃}）`
  - `openviking_breaker_tripped`：`OpenViking 返回 {status_code}：{detail}`
  - `openviking_restart_detected`：`进程重启（pid {old}→{new}），原因 {reason}`
  - `scheduled_refresh_summary`：成功→`扫描 {scanned} · 入队 {enqueued} · 跳过 {skipped}`；失败→把 `error` 放最前。
- **错误优先规则（替代 slice bug）**：当 `outcome` ∈ `{warning, error}`，描述**必须**优先取 `payload.error ?? payload.detail ?? payload.message ?? payload.reason`（熔断额外带 `status_code`）放在最前；**禁止**再用 `Object.entries().slice()` 把错误字段截断。未知类型的兜底仍可列 payload 摘要，但 error 类字段永远不被截掉。
- **badge 中文化**：`info/success/warning/error → 信息/成功/警告/错误`（颜色/`data-outcome` 不变）。

### ⑥-2 前端：建议文案 + 动作按钮

- 新增 `REMEDIATION: Record<string, { hint: string; action?: {...} }>`，**仅 warning/error 行**渲染 `<small class="settings-openviking-suggest">建议：{hint}</small>` + 可选按钮：
  - `sync_job_failed` → 按钮"重试该任务"，调 `retrySyncJob(event.sync_job_id)`，成功后 `feedback.showSuccess` 并触发事件流/任务卡刷新。`sync_job_id` 为空时只显示文案。
  - `scheduled_refresh_summary`(error) → 按钮"立即重新同步"，调 `resyncOpenViking()`。
  - `manual_rebuild_index`(error) → 文案"清理失败：{clear_result.error}"，按钮"重试重建"（`rebuildOpenVikingIndex()`）。
  - `openviking_breaker_tripped` → 文案"OpenViking 返回 503，熔断已打开；确认进程健康后稍后重试"，无按钮（或滚动到进程卡）。
  - `openviking_restart_detected` → 文案"进程已重启，如频繁重启请检查日志"，无按钮。
- 动作按钮复用既有 `feedback` / `requestConfirm` 模式（破坏性动作走居中确认弹窗，禁用 `window.confirm`）。

### ⑥-3 后端：补发 `sync_job_failed` 事件

- 在 `sync.py` `mark_failed`（commit 之后）`emit_event`：
  - `event_type="sync_job_failed"`，`source_type=job.source_type`，`source_id=job.source_id`，`sync_job_id=job.id`；
  - `payload={"error": error, "attempts": job.attempts, "operation": job.operation, "name": <可读名>}`；
  - `outcome`：`job.status == "cancelled"` → `"error"`（已放弃重试）；否则 `"warning"`（仍会重试）。
- 复用 §1a 的 `display_name`/`name` 推导逻辑，让描述能显示资源可读名而非 `source_id` 哈希。

### 测试

- vitest（`tests/openviking-dashboard.test.tsx`）：
  1. `repo_synced` 行显示"仓库已同步"标题与可读资源名，badge 显示"成功"。
  2. `scheduled_refresh_summary` error fixture（payload 含 `error` 第 4 键）→ 行内可见 `error` 文案（回归 slice bug），且渲染"建议 + 立即重新同步"按钮。
  3. `sync_job_failed` fixture（带 `sync_job_id`）→ 显示"重试该任务"按钮，点击调用 `retrySyncJob` 并弹成功 toast；`sync_job_id` 缺失时只剩文案、无按钮。
  4. `openviking_breaker_tripped` → 描述含 `status_code` 与 `detail`，显示熔断建议文案。
  5. 未知 `event_type` → 回退原始枚举标题，且 error 类字段不被截断。
- pytest（`tests/integration/test_openviking_admin_api.py` 或 `tests/unit`）：`mark_failed` 后事件表新增一条 `sync_job_failed`，`status="cancelled"` 时 `outcome="error"`、否则 `"warning"`，payload 含 `error`/`attempts`。

---

## ④ 调优参数：普通折叠配置面板

### 决策

2026-05-28 负责人对照 demo 截图 `~/img/m8-tuning-b-collapsed.png` / `m8-tuning-b-expanded.png` 拍板：先采用 B 方案（摘要 + 操作面板），不做 A 行折叠表单。随后根据真实页面验收反馈进一步收敛：**取消"偏离推荐 / 已对齐"分流展示**，不再自动高亮或展开与推荐值不一致的参数；三个 scope 均默认折叠，用户展开后查看和修改全部参数。

设计参考(已渲染截图):
- `~/img/m8-tuning-b-collapsed.png` / `m8-tuning-b-expanded.png` — 仅作为中间设计参考；最终实现保留紧凑四列配置表，去掉偏离 / 已对齐分区。
- Demo HTML 源:`.tmp/m8-tuning-demo/b.html`、`_base.css`。

### 现状

`OpenVikingDashboard.tsx:667-836` 的 `OpenVikingTuningCard`：

- `groups.map((scope, scopeRows) => scopeRows.map(row => …))` — 三个 scope 的 11 行全部展开。
- 每行：`key + description + impact + input + 推荐值 + 应用 + 回滚` 五列布局，纵向占空间大。
- 没有 disclosure，没有摘要，没有偏离/对齐区分。

### 目标视图

#### 卡片头
- `调优参数` + 副标题 `当前推荐预设:{preset} · 共 N 项`。
- 头部右上 actions 仅保留 `[套用预设]`；不提供 `[一键对齐推荐]`，避免把推荐值变成唯一明显路径。

#### 每个 scope 一个 `ScopeSummaryCard`
- 每个 scope 是一个原生 `<details>`，默认 closed。
- summary 顶部一行：`<h3>SCOPE_LABEL</h3>` + 一句短提示 + 右上 `{N} 项参数` pill + `展开参数 / 收起参数` 操作 pill + chevron。
- hover / focus / open 状态必须有明确视觉反馈，让第一次进入页面的管理员能判断这里可点击。
- 展开后渲染统一配置表：`参数 | 自定义值 | 推荐值 | 操作`。
- 每行左侧展示 `{key}`、参数描述和影响说明；右侧依次展示输入框、`推荐 {recommended}`、`[应用]`。
- 不提供 `[对齐推荐]` 或 `[回滚]`。推荐值只作为参考信息，修改由用户输入自定义值后点击应用完成。

#### 底部 snippet 区
- `Ollama systemd snippet`(`OpenVikingDashboard.tsx:803-833`)布局不动。

### 实施步骤

#### ④-1 拆分组件

- 文件:`OpenVikingDashboard.tsx`(在 `OpenVikingTuningCard` 内部拆,不新建文件)。
- 新内部组件(从上到下):
  - `TuningCardHeader`(头部摘要副标题 + actions)
  - `ScopeSummaryCard`({ scope, rows })
    - 内部用 `<details>` 包住整个 scope 参数表
  - `TuningParameterRow`(单行参数、描述、推荐值和应用按钮)
- 删除 `flattenTuningRows` 中 scope 排序保留;`groupTuningRows` 现有逻辑仍可用。

#### ④-2 推荐值处理

- 不再计算偏离 / 已对齐状态，不再用 `valueDiffersFromRecommended` 影响展示。
- 推荐值只在参数表中以 `推荐 {recommended}` 展示，供管理员参考。

#### ④-3 套用预设

- 头部只保留 `[套用预设]` 按钮。
- 批量把当前预设值应用到 OpenViking / CodeAsk scope；触发前保留二次确认。
- 单项修改统一走每行右侧的 `自定义值` + `[应用]`。

#### ④-4 参数行的自定义配置

- scope 展开后直接渲染四列行：`参数 | 自定义值 input | 推荐值 | [应用]`。
- 每行保留参数描述和影响说明。
- 不提供 `[详细配置]` / `[对齐推荐]` / `[回滚]`。

#### ④-5 AdvancedTable

- `<details>` 元素直接用,无需自实现 disclosure。
- 内层 grid 使用固定共享列模板：`minmax(180px, 1fr) 120px 96px 72px`，表头和行共用同一套列宽，避免 `auto` 导致"操作"列上下错位。
- 每行右侧仅 `[应用]` 一个按钮。
- 输入框值未变化时点击 `[应用]` 不弹确认，只提示无需应用；值变化时先弹页面内居中确认框。

#### ④-6 样式落地

- 新增 CSS class(添加到 `frontend/src/styles/globals.css`):
  - `.tuning-scope-summary`
  - `.tuning-scope-summary-head` / `.tuning-scope-title` / `.tuning-scope-actions` / `.tuning-scope-pills` / `.tuning-scope-action`
  - `.tuning-row-label`
  - `.tuning-advanced-table` / `.tuning-advanced-row`
- scope 不再按偏离状态染色，统一使用默认边框和背景。
- `.tuning-scope-action` 使用 pill + chevron 表示 disclosure，open 时 chevron 旋转；移动端 summary 改为上下布局，避免动作区挤压标题。
- 旧 `.settings-openviking-tuning-row` / `-meta` / `-recommended` / `-recommendation-delta` / `-actions` 经 grep 确认仅服务旧 Tuning 行表单，已随旧渲染删除；`settings-openviking-tuning-list` 与 `settings-openviking-tuning-field` 仍被新面板复用，保留。

#### ④-7 删除旧 inline-form 渲染

- 删除现有 `{groups.map(([scope, scopeRows]) => <section>... scopeRows.map(row => <div className="settings-openviking-tuning-row">...)</section>)}` 整段。
- `useEffect(() => { setDrafts(...) }, [rows])` 保留(初始化 drafts 字典,新组件仍需要)。

### 测试

- vitest `frontend/tests/openviking-dashboard.test.tsx` 新增四组用例:
  1. 渲染 fixture → 三个 scope 均为 `<details>` 默认 closed，显示"展开参数"，卡片头不出现偏离 / 对齐文案。
  2. 展开 scope 后显示全部参数、描述、影响说明、推荐值和 `[应用]`。
  3. 点击 scope summary 后 `aria-expanded` 从 `false` 变为 `true`，动作文案变为"收起参数"。
  4. 断言调优面板不渲染 `[对齐推荐]` / `[回滚]`。
  5. `[套用预设]` 仍走二次确认。
- 既有 `[套用预设]` / `[验证 Ollama 设置]` 测试保持。
- 删除原 inline tuning row 相关用例(grep 后逐条调整)。

---

## 验收口径回填（实现完成后回写 acceptance-checklist.md）

- §4.1（M1 dashboard）受影响行：把 "运行指标 5 分钟窗口" 描述从"占位"改为"真实采集，throughput 来自 sync_jobs，latency p95 来自 client wrapper，breaker_trips 来自 events 表"。
- §4.x 新增："同步任务卡片按状态分组分页 + summary 接口提供全表 count" / "事件流完整分页栏，历史页不轮询" / "调优默认折叠"。
- §4.x 新增："`DELETE /admin/openviking/sync_jobs/{id}` 仅允许 cancelled/failed 行" 与 "e2e fixture 自清"。
- 具体行号由开发实现后回写。

---

## 质量门禁（每项退出条件）

- `uv run pyright src/codeask evals` = 0；`uv run pytest -q` 绿；`uv run ruff check src tests evals` + `ruff format --check` 绿。
- `corepack pnpm --dir frontend exec tsc --noEmit`、`eslint --max-warnings=0`、`vitest run` 绿。
- alembic：本 plan **不引入新迁移**；现有 head 不变。
- 一次性 SQL 脚本 `scripts/cleanup_openviking_e2e_fixture.sql` 在本地真库跑通一次（4 条 e2e_unknown 行清零；events 表对应 source_type 清零）。
- live 检查（可选）：启动 dev server，截图 dashboard，肉眼对照 m8 修复前后差异；记录在本 plan 末尾。

---

## 不在本 plan 范围

- **OpenViking 进程自身的 prometheus_client 指标暴露**：本 plan 在 CodeAsk 侧 wrapper 做 latency 采集；如未来 OpenViking upstream 暴露 /metrics，可单独迁移采集源。
- **指标历史持久化**：本 plan 的 throughput / breaker_trips 走 SQL（已是持久化），latency p95 在进程内存，重启清零。如需长历史，单独立项。
- **管理员误删保护**：DELETE sync_job 仅限 cancelled/failed；如需"撤销删除"或"软删 + 回收站"，单独立项。
- **事件流的全文搜索 / 按 source_id 过滤**：仅在本 plan 之外，按需求再加。
- **调优参数的预设管理 UI**（保存自定义预设、切换多个预设）：仍走"套用预设"按钮，单选。
- **多用户场景下 metrics recorder 的进程间共享**：本 plan 假定单进程；多 worker 部署需单独评估。

---

## 完整开发 Checklist（开发执行视角，可直接逐项勾）

### ① 字段含义

#### 1a — payload.name 优先
- [x] `OpenVikingDashboard.tsx` `eventSummary` 增加 `payload.name` / `title` / `feature_slug+relative_path` 优先级链
- [x] vitest `frontend/tests/openviking-dashboard.test.tsx` 新增两条用例（含 name vs 无 name）

#### 1b — sync_jobs display_name
- [x] `openviking_status.py` 新增 `_resolve_display_names(jobs)` 批量解析 wiki_doc / report
- [x] `_job_to_dict` 增加 `display_name` 字段；list_jobs 端点调用 resolver
- [x] `frontend/src/types/api.ts` `OpenVikingSyncJob` 加 `display_name: string | null`
- [x] `OpenVikingDashboard.tsx` SyncJobItem 主行改用 display_name
- [x] pytest `tests/integration/test_openviking_admin_api.py` 新增 display_name 解析用例
- [x] vitest 渲染断言

#### 1c — e2e teardown + 一次性清理
- [x] `openviking_status.py` 新增 `DELETE /admin/openviking/sync_jobs/{id}`（仅 cancelled/failed 可删）
- [x] `frontend/src/lib/api-openviking.ts` 新增 `deleteOpenVikingSyncJob(id)`
- [x] `frontend/e2e/openviking-dashboard-management-live.spec.ts` 用 `test.afterEach` 删本 spec 创建的 e2e_unknown 行
- [x] 新建 `scripts/cleanup_openviking_e2e_fixture.sql`
- [x] 在本地真库手动跑一次 SQL，确认 `openviking_sync_jobs` 中 `e2e_unknown` 清零
- [x] pytest 新增 DELETE 接口的允许/拒绝两态测试

#### 1d — 真实指标采集
- [x] 新建 `src/codeask/rag/openviking/metrics.py`：`OpenVikingMetricsRecorder`（latency deque + snapshot）
- [x] `src/codeask/app.py` lifespan 注册 `app.state.openviking_metrics_recorder`
- [x] `OpenVikingClient` 构造接收 recorder；每次请求 perf_counter 包裹
- [x] `OpenVikingClient` 503/circuit-open 分支调 `emit_event(event_type='openviking_breaker_tripped', ...)`
- [x] `openviking_status.py` `_metrics_snapshot` 改 async + SQL 聚合 throughput/breaker
- [x] `get_openviking_status` 改 `status_payload["metrics_5min"] = await _metrics_snapshot(request)`
- [x] `OpenVikingDashboard.tsx` MetricsCard 适配 `collected` true/false 双态 + samples 显示
- [x] 单测 `tests/unit/test_openviking_metrics.py`：recorder 行为 + snapshot p95 正确
- [x] 集成 `tests/integration/test_openviking_admin_api.py`：throughput/breaker 真实 SQL 聚合
- [x] vitest MetricsCard 双态渲染

### ② 同步任务分状态分页

- [x] `openviking_status.py` 新增 `/admin/openviking/sync_jobs/summary`
- [x] `openviking_status.py` `list_openviking_sync_jobs` 增加 status + cursor + limit(25/cap 100) 三参数；返回 next_cursor
- [x] `sync.py` `list_jobs` 重写支持 `(status, cursor)` keyset 分页
- [x] `frontend/src/lib/api-openviking.ts` `listOpenVikingSyncJobs({status?, cursor?, limit?})` + 新 `getOpenVikingSyncJobsSummary()`
- [x] `frontend/src/types/api.ts` `OpenVikingSyncJobsResponse.next_cursor`、新 `OpenVikingSyncJobsSummaryResponse`
- [x] `OpenVikingDashboard.tsx` SyncJobsCard 重构：summary 驱动 StatusPill，分状态分组 + 每组 `useInfiniteQuery`
- [x] 删旧 `showIndexed` / `visibleCount` 切片逻辑；`JOB_PAGE_SIZE` 改为每组分页大小常量
- [x] pytest 新增 summary + cursor + 多状态分页用例
- [x] vitest SyncJobsCard 分组渲染 + 加载更多 + summary 显示全表 count

### ③ 事件流直接分页

- [x] `OpenVikingDashboard.tsx` 用单页 `useQuery` + `eventPage` / `eventPageSize` 替换 `useState eventItems` + `useEffect` 拼装
- [x] `refetchInterval` 仅第 1 页 5s 轮询；历史页返回 false
- [x] 删除 `collapseConsecutiveEvents` / `EventGroup` / `×N` 聚合 chip
- [x] `EventItem` 改为一条事件渲染一行
- [x] 增加 "上一页事件" / "下一页事件" 分页按钮、总条数 / 总页数、每页条数选择、页码输入跳转；默认每页 5 条
- [x] vitest 新增直接分页用例：同页多条同类事件不聚合，页码跳转只显示目标页，修改每页条数会回到第 1 页
- [x] pytest 覆盖 `/admin/openviking/events?page=...&limit=...` 的总数和总页数返回

### ④ 调优折叠配置面板

- [x] 设计参考截图保存在仓外 `~/img/m8-tuning-b-*.png` 与 `.tmp/m8-tuning-demo/`，未纳入提交范围
- [x] `OpenVikingDashboard.tsx` `OpenVikingTuningCard` 内拆出 `TuningCardHeader` / `ScopeSummaryCard` / `TuningParameterRow` / `AdvancedTable` 内部组件
- [x] 头部副标题显示 `当前推荐预设:{preset} · 共 N 项`，不展示偏离推荐计数
- [x] 头部 actions 仅保留 `[套用预设]`
- [x] 三个 scope 均默认折叠，不再根据推荐值偏离状态自动展开或高亮；summary 右侧显式展示"展开参数 / 收起参数"动作和 chevron，hover / focus / open 状态有视觉反馈
- [x] 展开 scope 后使用统一四列行布局：`参数 | 自定义值 | 推荐值 | 操作`，并保留参数描述、影响说明和推荐值；操作列仅展示短按钮"应用"
- [x] 调优面板不再渲染 `[对齐推荐]` / `[回滚]`
- [x] `globals.css` 加新 class:`.tuning-scope-summary` / `-head` / `-title` / `-actions` / `-pills` / `-action` / `.tuning-row-label` / `.tuning-advanced-table` / `-row`
- [x] 删除旧 inline `settings-openviking-tuning-row` 渲染逻辑，并清理旧 row/meta/recommended/delta/actions CSS
- [x] vitest 新增默认折叠、展开 / 收起动作提示、`aria-expanded` 状态、展开后显示说明 / 推荐值 / 应用、无偏离 / 对齐 / 回滚按钮、套用预设 confirm 覆盖
- [x] 截图回归：已在 dev server 下抓取 `frontend/.tmp/m8-dashboard-current.png` 与 `frontend/.tmp/m8-dashboard-tuning-current.png`，人工对照 `~/img/m8-tuning-b-*.png`

### ⑤ 全局按钮反馈

- [x] OpenViking Dashboard 接入 `AppFeedbackProvider` 的 `useAppFeedback`
- [x] 复制路径、复制 Ollama snippet 成功后显示居中 toast；浏览器不支持或复制失败时弹出错误对话框
- [x] Embedding 切换 / 向量索引重建、同步任务重试 / 重新同步 / 重排队列、调优应用 / 套用预设 / Ollama 验证均在成功时显示居中 toast，接口失败时显示全局错误弹窗
- [x] 所有会修改后端状态的按钮先弹页面内居中确认框，确认后才提交；取消不发请求。禁止使用浏览器原生 `window.confirm`
- [x] 调优单项应用在值变更时先弹页面内确认框；取消不发请求，确认后才提交。值未变更时不弹确认，只提示无需应用
- [x] 同步任务分组加载更多有即时 toast 反馈；事件流分页不弹 toast，以分页栏页码状态作为反馈，避免普通翻页像业务操作
- [x] vitest 覆盖代表性按钮：路径复制、事件分页、Ollama 验证、同步任务重试、调优应用，以及调优失败的全局错误弹窗

### ⑥ 事件行人话化与可操作性

- [x] `OpenVikingDashboard.tsx` 增加 `EVENT_LABELS` / `OUTCOME_LABELS`，事件标题和 badge 改为中文展示；未知事件类型保留原始枚举作为回退
- [x] `describeEvent()` 替代旧 `eventSummary()`：按事件类型生成可读描述，`warning` / `error` 优先展示 `payload.error ?? detail ?? message ?? reason`，并覆盖 `scheduled_refresh_summary` 错误字段被截断的回归场景
- [x] 每条事件行提供"详情 / 收起详情"按钮，展开后显示事件 id、原始 event_type、来源、source_id、sync_job_id、触发人、创建时间与 payload JSON；兜底建议中的"查看事件详情"有明确入口
- [x] warning/error 行渲染"建议：…"与可选动作按钮：`sync_job_failed` 可重试任务，`scheduled_refresh_summary` error 可立即重新同步，`manual_rebuild_index` error 可重试重建；所有动作使用页面内居中确认与既有 feedback
- [x] `sync.py` `mark_failed()` 在失败状态落库后补发 `sync_job_failed` 事件，payload 包含 `error` / `attempts` / `operation` / 可读资源名；仍可重试为 warning，达到上限 cancelled 为 error
- [x] vitest 覆盖 repo 可读名、scheduled error、sync job failed 有/无 `sync_job_id`、breaker status/detail、未知类型错误不被截断；pytest 覆盖 `mark_failed` 的 warning/error 事件输出

### ⑦ 事件生产降噪与保留策略

- [x] 默认事件视图改为"重点事件"，只展示 warning / error 和关键运维汇总；`repo_synced` success、`manual_retry_failed count=0`、`tuning_change` success 等历史噪声默认隐藏，管理员可切换到"全部事件"查看原始事件表，保留审计排查能力
- [x] `retry_failed` 在没有 failed job 时直接返回 `{queued: 0}`，不再写 `manual_retry_failed count=0` 事件，也不写 no-op audit
- [x] `POST /admin/openviking/tuning` 在 `previous_value == value` 时跳过，不写 `OpenVikingTuningSetting`、不写 audit、不写 `tuning_change`，避免 no-op 调参污染历史
- [x] 批量仓库刷新（含 hourly refresh）不再为每个仓库写一条 `repo_synced` 成功事件；改写一条 `repo_refresh_summary`，payload 含 `reason` / `scanned` / `succeeded` / `failed`
- [x] 单仓库手动同步仍保留 `repo_synced`，用于确认具体仓库同步成功；批量刷新用汇总事件，避免 51 个仓库每小时刷出 51 条 success
- [x] `openviking_event_retention` APScheduler 任务接入，每 24 小时裁剪 `openviking_dashboard_events`，每个 `event_type` 默认保留最近 2000 条；保留参数来自 `CODEASK_OPENVIKING_EVENT_RETENTION_COUNT`
- [x] `prune_dashboard_events()` 单测覆盖每 event_type 保留最近 N 条；集成测试覆盖空失败重试不发事件、no-op 调参不落库、重点事件视图过滤 `repo_synced` success 噪声

### ⑦ 补遗（2026-05-29 review 复检，负责人确认要修）

review 通过门禁后又发现 3 处问题，#1 与 §⑦ 降噪目标冲突，必须修；#2/#3 顺手修。

#### 补遗-1（中）：`sync_job_failed` 每次重试都发事件，是降噪反例

- **现状**：`sync.py` `mark_failed` 每次失败都 `emit_event`（仍会重试→warning，cancelled→error）。一个任务重试到 cancelled 最多发 **4 条 warning + 1 条 error**，且全部命中默认"重点事件"视图——几个 flaky 资源就能把刚清干净的看板重新刷满。
- **决策（负责人 2026-05-29 拍板：按推荐收敛）**：每个失败资源最多发 2 条。判定优先级：
  1. `job.status == "cancelled"`（已放弃）→ emit **error**（不论 attempts）；
  2. 否则 `job.attempts == 1`（首次失败）→ emit **warning**；
  3. 否则（中间重试，status=failed 且 attempts>1）→ **不 emit**。
  > 边界：若 `max_repeat_failures==1` 导致首次失败即 cancelled，按规则 1 发 error（cancelled 优先于 attempts==1），不发 warning。
- **测试**：更新 `tests/unit/test_openviking_sync.py`——首次失败(attempts=1, failed)发 1 条 warning；中间重试(attempts=2, failed)发 0 条；cancelled 发 1 条 error。删除/改写原来"每次失败都发"的断言。

#### 补遗-2（低）：EventItem 成功 toast 弹两次

- **现状**：`OpenVikingDashboard.tsx` `handleRemediationAction` 的 onConfirm 弹 "重试任务已提交"（:1133），mutation `onSuccess` 又弹**一模一样**的 "重试任务已提交"（:1098）；resync（:1145/1106）、rebuild（:1157/1114）同样。
- **改动**：去掉 onConfirm 里的乐观 `feedback.showSuccess(...)`（三处），只保留 mutation `onSuccess` 的成功 toast（请求真正成功才提示，不在请求发出前就声称"已提交"）。
- **测试**：vitest 断言点击建议按钮→确认后，成功 toast 只出现一次。

#### 补遗-3（低）：后端 no-op 调参守卫与前端口径不一致

- **现状**：`openviking_tuning.py:298` 用裸 `previous_value == change.value`；前端 `valuesEqual` 是 `displayValue(x).trim()` 的**去空格字符串相等**（注意：并非数值归一化，"10" 与 "10.0" 前后端都视为不等）。唯一分歧是**首尾空格**：带空格的语义相同值后端仍会落库+发事件。
- **改动**：后端比较前对两侧做 `.strip()` 以对齐前端（仅 trim，不引入数值归一化）；`previous_value is None` 时维持"首次设置→写入"语义。
- **测试**：pytest 覆盖 `previous_value="10"` vs `change.value=" 10 "` 视为相等→跳过写入与事件。

### 复检与修复记录（2026-05-29 Claude 终验接手）

负责人/开发交付后，Claude 做最终验收，跑了全量单测 + live e2e，发现两类问题并修复：

1. **restart 事件 bug（开发已修，已验）**：`_ensure_openviking_server` 把 `pid` 当"最近健康 pid"和"最近观测 pid"混用，重生进程在 health-pending 窗口就覆盖了 pid，导致 `openviking_restart_detected` 永不发出。开发拆出 `healthy_pid`（仅健康分支更新，`app.py:606`）并补回归单测 `test_openviking_restart_event_is_emitted_after_pending_process_becomes_healthy`（pending→healthy 序列）。Claude 验证：该单测 3 passed；开发另附隔离环境实测 kill→重生确有 `openviking_restart_detected{old,new}` 写入。churn 未复现，`startup_grace_seconds=30` 不动。
2. **3 个 stale live e2e（Claude 修）**：开发的 §⑥ 人话化 + §⑦ 降噪改了行为，但没更新断言原始枚举文案的 live e2e（E3/E5/E10），且 §⑦ 取消 count=0 `manual_retry_failed` 后 E5 的造数前提失效。修复：
   - 事件行加 `data-event-type={event.event_type}`（`OpenVikingDashboard.tsx`），e2e 按机器枚举选行，与展示文案解耦，根治"一改文案就挂 e2e"。
   - E3/E10：`hasText:"manual_retry"/"ollama_settings_verified"` → `[data-event-type="…"]` 选择器。
   - E5 重写：改用"造 13 个失败 e2e_unknown 任务 → 每个发一条 `sync_job_failed`(warning)"凑分页数据，按 `data-event-type` 选行 + outcome 过滤。
   - 发现并修复连带 flake：E5 新负载并行撞 E9 调参重启（隔离单跑 E9 12.7s 通过），给本 spec 加 `test.describe.configure({ mode: "serial" })`——共享后端 + OpenViking 进程的有状态 live 用例本就该串行。
3. **终验结果（全绿）**：后端 `pytest tests/` 0 失败 / 8 已知 skip；前端 `vitest` 246/246；ruff / pyright / tsc / eslint clean；OpenViking live e2e 串行 **7 passed / 3 skipped(E2/E4/E7 占位) / 0 failed**。acceptance §3.2 line 69（restart 事件）、§3.2.2 e2e 覆盖此时为真实绿。
4. **附注**：Playwright 拆栈用的是硬杀，后端 lifespan 优雅 shutdown 未必跑完，会留 openviking-server 孤儿占 1933（优雅 SIGTERM 路径手测能正确回收子进程）；属测试基建小瑕，已手动清理，未改产品代码。

### 收口

- [x] 更新 `acceptance-checklist.md`（受影响行 + 新增行号回填）
- [x] 本 plan 状态 Planned → Completed，回填"完成记录"小节
- [ ] docs / 后端 / 前端 commit 拆分由负责人合并前决定；当前只完成代码与文档收口，不 push
- [x] 一次性 SQL 脚本手动跑一次清掉 e2e_unknown 历史污染（命令在下方"附录"）

---

## 附录 A — 一次性清理命令

负责人在本地真库执行一次（**仅一次**，跑完即可）：

```bash
sqlite3 ~/.codeask/data.db < /home/hzh/workspace/CodeAsk/scripts/cleanup_openviking_e2e_fixture.sql
```

验证：

```bash
sqlite3 ~/.codeask/data.db "SELECT COUNT(*) FROM openviking_sync_jobs WHERE source_type='e2e_unknown';"
# 期望 0

sqlite3 ~/.codeask/data.db "SELECT COUNT(*) FROM openviking_dashboard_events WHERE source_type='e2e_unknown';"
# 期望 0
```

---

## 附录 B — 评估表（修复前 / 修复后）

实施完成后由开发回填，截图或文字对照：

| 项 | 修复前 | 修复后 |
|---|---|---|
| 1a 事件流 repo_synced 显示 | `repo · f7606c2988444040` | `repo · Feature scoped claude-code 1778952333054` |
| 1b sync_job wiki_doc 显示 | `wiki_doc / 47 / openviking-rag-live` | `<WikiNode.name> / wiki_doc · 47 / openviking-rag-live` |
| 1c e2e_unknown 残留计数 | 4 | `openviking_sync_jobs` 已清零；`openviking_dashboard_events` 脚本同表规则清理 |
| 1d 指标 | "未采集" × 3 | throughput / latency p95 / breaker_trips 真实数值 |
| 2 indexed 展开顺序 | 与 cancelled 时间倒序混排 | 按状态分块，每块独立分页 |
| 3 加载更多 | 闪一下回去 + 数字膨胀 | 取消加载更多，改为完整分页栏；默认 5 条/页，显示总页数，可选每页条数，可输入页码跳转 |
| 4 调优 | 11 行 input 表单全展开 | scope 默认折叠，summary 显式提示可展开，展开后统一四列配置表，保留说明和推荐值，只有自定义应用与套用预设 |

---

## 完成记录

2026-05-28 实施完成：

- 后端：新增 `OpenVikingMetricsRecorder`，在 `OpenVikingClient` 包裹请求耗时并写入 breaker 事件；`/admin/openviking/status` 输出真实 5 分钟指标；`/admin/openviking/sync_jobs` 支持 `status` / `cursor` / `limit`，新增 summary 与安全 DELETE；sync job 序列化补 `display_name`。
- 前端：OpenViking Dashboard 同步任务按状态分组并独立分页；事件流改为完整分页栏，默认 5 条/页，支持总页数、每页条数选择和页码跳转，默认只看"重点事件"，可切到"全部事件"，历史页暂停轮询，不再跨页追加或聚合；事件行改为中文标题、中文 badge、人话描述，错误原因优先展示且附建议文案 / 可操作按钮，并提供行内详情展开查看原始事件字段与 payload；调优面板改为普通折叠配置面板，scope 默认折叠，展开后保留说明、推荐值和应用按钮；metrics 卡显示真实采集态与 samples。
- 交互反馈：OpenViking Dashboard 所有按钮统一接入全局反馈；成功显示居中 toast，失败显示居中错误弹窗，复制 / 分页 / 展开收起 / 重试 / 重建 / 调优 / Ollama 验证均已覆盖。所有会修改后端状态的按钮均先弹页面内居中确认框，确认后才提交，不再使用浏览器原生确认框。
- 事件降噪：空失败重试不写事件；no-op 调参不落库、不写 audit、不写 `tuning_change`；批量 repo refresh 改为单条 `repo_refresh_summary`；事件 retention 接入 APScheduler，每 event_type 默认保留最近 2000 条。
- 测试：新增 `tests/unit/test_openviking_metrics.py`；扩展 `tests/integration/test_openviking_admin_api.py`；扩展 `frontend/tests/openviking-dashboard.test.tsx`；live management e2e 增加 fixture teardown。
- 数据清理：已本地执行 `sqlite3 /home/hzh/.codeask/data.db < scripts/cleanup_openviking_e2e_fixture.sql`，并确认 `openviking_sync_jobs` 中 `source_type='e2e_unknown'` 计数为 `0`。
- 真实浏览器：`openviking-dashboard-live.spec.ts` + `openviking-dashboard-management-live.spec.ts` 在重启后的真实栈通过，结果 `7 passed / 3 skipped`（破坏性隔离用例按计划 skip）。
- 截图回归：已抓取 `frontend/.tmp/m8-dashboard-current.png` 与 `frontend/.tmp/m8-dashboard-tuning-current.png`。调优面板已从 B 方案进一步收敛为普通折叠配置面板，不再展示偏离 / 已对齐分区，只有自定义应用与套用预设。
- 质量门禁：`pyright` / `pytest` / `ruff` / `tsc` / `eslint` / `vitest` 已全部通过。
