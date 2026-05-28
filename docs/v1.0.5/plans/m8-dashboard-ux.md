# M8 — OpenViking Dashboard UX 与指标实装

> 版本：v1.0.5
> 状态：Planned
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
  - `frontend/src/components/settings/OpenVikingDashboard.tsx`（事件 summary 读 payload.name；同步任务卡片按状态分组 + 服务端分页；事件流分页时关 polling、折叠 chip 可展开；调优默认折叠 + scope `<details>` 切换）
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

## ③ 加载更多 + 折叠 + 计数错觉

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

- 分页时**暂停** refetchInterval；返回首页时再恢复。
- 折叠 chip 可展开看到底层每一条。
- 不再用 `setEventItems(payload.items)` 替换式赋值；改为 React Query 原生 `useInfiniteQuery`，由库管理多页拼接。

### 实施步骤

#### ③-1 用 `useInfiniteQuery` 替换手工拼装

- 文件：`OpenVikingDashboard.tsx:128-176, 580-647`
- 改为：
  ```ts
  const eventsQuery = useInfiniteQuery({
    queryKey: ["admin-openviking-events", eventOutcome, eventType],
    queryFn: ({ pageParam }) => listOpenVikingEvents({
      eventType: eventType || undefined, outcome: eventOutcome || undefined,
      beforeId: pageParam, limit: EVENT_PAGE_SIZE,
    }),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) => last.next_before_id ?? undefined,
    refetchInterval: (query) => query.state.data?.pages.length === 1 ? 5000 : false,
    //                          ← 第 1 页时才轮询；翻过页就停
  });
  const events = useMemo(() =>
    eventsQuery.data?.pages.flatMap((page) => page.items) ?? [], [eventsQuery.data]);
  ```
- 删 `eventBeforeId` / `eventItems` / 手工 useEffect。
- `onOutcomeChange` / `onEventTypeChange` 不需要重置 state，只是改 queryKey，React Query 自动重新拿第 1 页。
- `加载更多` 改调 `eventsQuery.fetchNextPage()`，按钮 `disabled={!eventsQuery.hasNextPage}`。

#### ③-2 折叠 chip 可展开

- 文件：`OpenVikingDashboard.tsx:944-960` 的 `collapseConsecutiveEvents` 保留；改返回 `EventGroup` 结构追加 `events: OpenVikingDashboardEvent[]`（完整列表，不止 leader）。
- `EventItem`（行 650-665）改为：
  - `group.count > 1` 时 chip "×N" 变成 button：`onClick` 切换 `expanded`；
  - `expanded` 时下方渲染 group.events 全部 children（每条单独一行，复用现有 row 样式但缩进）。

#### ③-3 暂停时的可见提示

- 当 `eventsQuery.isFetchingNextPage === false && eventsQuery.hasNextPage === false && (events.length > EVENT_PAGE_SIZE)` 时（即已经翻过页且到底），卡片底部显示一行小字 "已加载全部事件，刷新自动暂停。返回顶部以恢复实时刷新"。
- 提供 "返回顶部" 按钮：`onClick={() => eventsQuery.refetch({ refetchPage: (_, index) => index === 0 })}` 或更直接 `queryClient.resetQueries({ queryKey: ["admin-openviking-events", ...] })`。

### 测试

- vitest：`OpenVikingEventStream` 渲染 fixture
  1. 给 10 条同 type 事件 → chip "×10"，点击展开后 10 行可见。
  2. 模拟 `hasNextPage=true`，点击 "加载更多" 调 `fetchNextPage`（mock）；新增 10 条再折叠成"×20"，展开仍能看到 20 行。
  3. 翻过页后 `refetchInterval` 函数返回 `false`（用 react-query 内部状态断言或 mock fetch 次数）。
- pytest：`tests/integration/test_openviking_admin_api.py` 已经覆盖 events 接口 cursor 行为；不新增。

---

## ④ 调优参数：摘要 + 操作面板（**锁定 demo B**）

### 决策

2026-05-28 负责人对照 demo 截图 `~/img/m8-tuning-b-collapsed.png` / `m8-tuning-b-expanded.png` 拍板：**采用 B 方案（摘要 + 操作面板）**，不做 A 行折叠表单。

设计参考(已渲染截图):
- `~/img/m8-tuning-b-collapsed.png` — 默认态:scope 顶栏 + 偏离项卡片 + 已对齐折叠行。
- `~/img/m8-tuning-b-expanded.png` — 已对齐展开态:紧凑表格(每行 name + input + 推荐 + 应用)。
- Demo HTML 源:`.tmp/m8-tuning-demo/b.html`、`_base.css`。

### 现状

`OpenVikingDashboard.tsx:667-836` 的 `OpenVikingTuningCard`：

- `groups.map((scope, scopeRows) => scopeRows.map(row => …))` — 三个 scope 的 11 行全部展开。
- 每行：`key + description + impact + input + 推荐值 + 应用 + 回滚` 五列布局，纵向占空间大。
- 没有 disclosure，没有摘要，没有偏离/对齐区分。

### 目标视图

#### 卡片头
- `调优参数` + 副标题 `当前推荐预设:{preset} · 共 N 项,M 项偏离推荐`(M=0 时副标题省略后半段)。
- 头部右上 actions:`[一键对齐推荐]`(仅当 M>0 可点;M==0 时禁用并显示 tooltip) + `[套用预设]`(保留)。

#### 每个 scope 一个 `ScopeSummaryCard`
- `data-state` 属性区分 `warn`(有偏离,黄色边框)/`ok`(全对齐,默认边框);视觉:`m8-tuning-b-collapsed.png` 中第一张卡片黄边、后两张白边。
- 顶部一行:`<h3>SCOPE_LABEL</h3>` + 右上 pill(`● N 项偏离` 黄色 / `✓ 全部对齐` 绿色)+ `<span>/ N 项共</span>` 浅灰副信息。

#### 偏离项 `DivergentItemCard`(仅 scope 有偏离时存在)
- 每个偏离 key 一张卡片(白底 + 黄边),内容:
  - `<strong>{key}</strong>`(完整 key 不截断)。
  - 一行说明:`当前 {current} · 推荐 {recommended} · {impact}`(impact 来自 TUNING_DESCRIPTIONS map)。
  - 右侧两个按钮:`[对齐推荐]`(主操作,一键把 current 改成 recommended 调用 applyMutation)、`[详细配置]`(切换状态,展开为内嵌 input + `[应用]` + `[回滚]`,允许手工输入非推荐值)。
- 不再展示 description 长文 / max 长宽 input。

#### 已对齐折叠区
- scope 内若有 K 项已对齐(K>=1),底部一行 `<details>`:
  - summary:`✓ {K} 项 已与推荐值对齐 [展开查看 ▾]`。
  - 展开后渲染 `AdvancedTable`:每行 `{key} | <input> | 推荐 {recommended} | [应用]`,单行高度 ~36px,无描述,无回滚按钮(已对齐项目无需回滚)。
- 若 K==0(scope 全部偏离),不渲染折叠区。

#### Scope 全部对齐情形
- 没有 `DivergentItemCard`;直接渲染折叠区,summary 文案改为 `所有参数与推荐值一致 [展开查看 ▾]`。

#### 底部 snippet 区
- `Ollama systemd snippet`(`OpenVikingDashboard.tsx:803-833`)布局不动。

### 实施步骤

#### ④-1 拆分组件

- 文件:`OpenVikingDashboard.tsx`(在 `OpenVikingTuningCard` 内部拆,不新建文件)。
- 新内部组件(从上到下):
  - `TuningCardHeader`(头部摘要副标题 + actions)
  - `ScopeSummaryCard`({ scope, rows })
    - 内部分两段:
      - `divergentRows.map(row => <DivergentItemCard ... />)`
      - `alignedRows.length > 0 && <AlignedFoldout rows={alignedRows} />`
- 删除 `flattenTuningRows` 中 scope 排序保留;`groupTuningRows` 现有逻辑仍可用。

#### ④-2 偏离/对齐判定

- 已有 helper `valueDiffersFromRecommended(value, recommended)`(line 886-894)直接复用。
- 在 `ScopeSummaryCard` 顶部计算 `const { divergent, aligned } = useMemo(() => partition(rows, valueDiffersFromRecommended(draft, recommended)), [rows, drafts])`。

#### ④-3 一键对齐推荐

- 头部 `[一键对齐推荐]` 按钮:
  - 计算所有 scope 内所有 `valueDiffersFromRecommended` 的行,批量提交 `applyOpenVikingTuning({ changes: rows.map(r => ({ scope: r.scope, key: r.key, value: r.recommended })) })`(后端接口 `POST /admin/openviking/tuning` 已支持数组 `changes`,见 `api/openviking_tuning.py:331` 周边)。
  - 单 mutation;失败时 `rejectedFromMutation(...)` 已能渲染。
  - 触发前 `window.confirm("一键对齐 N 项参数到推荐值,影响包括重启 OpenViking。是否继续?")`。

#### ④-4 DivergentItemCard 的"详细配置"toggle

- 默认仅渲染说明 + 两按钮;`[详细配置]` 切换 `expanded` state,展开为:
  - 一行 input(`draftValue` 受控)+ `[应用](使用 draftValue)` + `[回滚](使用 previous_value,逻辑同现有)`。
  - 关闭时丢弃 draft(回到 row.value)。
- 这是单卡片内的局部 state,不需要全局 state。

#### ④-5 AlignedFoldout / AdvancedTable

- `<details>` 元素直接用,无需自实现 disclosure。
- 内层 grid:`grid-template-columns: 1fr 110px 96px auto`,与 demo B `_base.css` 的 `.advanced-row` 一致。
- 每行右侧仅 `[应用]` 一个按钮(已对齐项不需要回滚)。
- 输入框只读时(用户没改过 draftValue 与 row.value 相同),`[应用]` 按钮禁用。

#### ④-6 样式落地

- 新增 CSS class(添加到 `frontend/src/styles/globals.css`):
  - `.tuning-scope-summary` / `[data-state="warn"]` / `[data-state="ok"]`
  - `.tuning-scope-summary-head` / `.tuning-scope-pills`
  - `.tuning-divergent-item` / `.tuning-divergent-meta` / `.tuning-divergent-actions`
  - `.tuning-aligned-row` (`<summary>`)
  - `.tuning-advanced-table` / `.tuning-advanced-row`
- 颜色与圆角与 `~/img/m8-tuning-b-*.png` 截图一致(黄色 `#fedf89`/`#fffaeb`/`#b54708`,绿色 `#d1fadf`/`#ecfdf3`/`#027a48`,这些 token 已在现有 globals.css 出现过)。
- 旧 `.settings-openviking-tuning-row` / `-meta` / `-field` / `-recommended` / `-recommendation-delta` / `-actions` **保留**(其它卡片用得到的不动;若 grep 仅 TuningCard 用到则一并删除清理,由开发判断)。

#### ④-7 删除旧 inline-form 渲染

- 删除现有 `{groups.map(([scope, scopeRows]) => <section>... scopeRows.map(row => <div className="settings-openviking-tuning-row">...)</section>)}` 整段。
- `useEffect(() => { setDrafts(...) }, [rows])` 保留(初始化 drafts 字典,新组件仍需要)。

### 测试

- vitest `frontend/tests/openviking-dashboard.test.tsx` 新增四组用例:
  1. 渲染 fixture(一个 scope 1 偏离 + 1 已对齐,一个 scope 全对齐) → 偏离卡片可见 + 已对齐折叠为 `<details>`(默认 closed),summary 文案正确;全对齐 scope 仅渲染 summary 折叠行。
  2. 点击 `[对齐推荐]` → applyMutation 用 recommended 值调用一次;不弹出 confirm(单项快捷动作可不二次确认,本节取消 confirm 来减少摩擦,与"一键对齐推荐"区分)。
  3. 点击 `[详细配置]` → input 可见,改值后 `[应用]` 调用 applyMutation 用 draftValue,`[回滚]` 调用 rollbackMutation。
  4. `[一键对齐推荐]`:
     - M==0 时禁用;
     - M>0 时点击 → window.confirm 弹出,确认后 batch applyMutation 用 changes 数组提交所有偏离项。
- 既有 `[套用预设]` / `[验证 Ollama 设置]` 测试保持。
- 删除原 inline tuning row 相关用例(grep 后逐条调整)。

---

## 验收口径回填（实现完成后回写 acceptance-checklist.md）

- §4.1（M1 dashboard）受影响行：把 "运行指标 5 分钟窗口" 描述从"占位"改为"真实采集，throughput 来自 sync_jobs，latency p95 来自 client wrapper，breaker_trips 来自 events 表"。
- §4.x 新增："同步任务卡片按状态分组分页 + summary 接口提供全表 count" / "事件流分页期间不轮询" / "事件 chip 可展开" / "调优默认折叠"。
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
- [ ] `OpenVikingDashboard.tsx:962-997` `eventSummary` 增加 `payload.name` / `title` / `feature_slug+relative_path` 优先级链
- [ ] vitest `frontend/tests/openviking-dashboard.test.tsx` 新增两条用例（含 name vs 无 name）

#### 1b — sync_jobs display_name
- [ ] `openviking_status.py` 新增 `_resolve_display_names(jobs)` 批量解析 wiki_doc / report
- [ ] `_job_to_dict` 增加 `display_name` 字段；list_jobs 端点调用 resolver
- [ ] `frontend/src/types/api.ts` `OpenVikingSyncJob` 加 `display_name: string | null`
- [ ] `OpenVikingDashboard.tsx:539-578` SyncJobItem 主行改用 display_name
- [ ] pytest `tests/integration/test_openviking_admin_api.py` 新增 display_name 解析用例
- [ ] vitest 渲染断言

#### 1c — e2e teardown + 一次性清理
- [ ] `openviking_status.py` 新增 `DELETE /admin/openviking/sync_jobs/{id}`（仅 cancelled/failed 可删）
- [ ] `frontend/src/lib/api-openviking.ts` 新增 `deleteOpenVikingSyncJob(id)`
- [ ] `frontend/e2e/openviking-dashboard-management-live.spec.ts` 用 `test.afterEach` 删本 spec 创建的 e2e_unknown 行
- [ ] 新建 `scripts/cleanup_openviking_e2e_fixture.sql`
- [ ] 在本地真库手动跑一次 SQL，确认清干净（截图前后对比可选）
- [ ] pytest 新增 DELETE 接口的允许/拒绝两态测试

#### 1d — 真实指标采集
- [ ] 新建 `src/codeask/rag/openviking/metrics.py`：`OpenVikingMetricsRecorder`（latency deque + snapshot）
- [ ] `src/codeask/app.py` lifespan 注册 `app.state.openviking_metrics_recorder`
- [ ] `OpenVikingClient` 构造接收 recorder；每次请求 perf_counter 包裹
- [ ] `OpenVikingClient` 503/circuit-open 分支调 `emit_event(event_type='openviking_breaker_tripped', ...)`
- [ ] `openviking_status.py:347-355` `_metrics_snapshot` 改 async + SQL 聚合 throughput/breaker
- [ ] `get_openviking_status` 改 `status_payload["metrics_5min"] = await _metrics_snapshot(request)`
- [ ] `OpenVikingDashboard.tsx:838-860` MetricsCard 适配 `collected` true/false 双态 + samples 显示
- [ ] 单测 `tests/unit/test_openviking_metrics.py`：recorder 行为 + snapshot p95 正确
- [ ] 集成 `tests/integration/test_openviking_status_api.py`：throughput/breaker 真实 SQL 聚合
- [ ] vitest MetricsCard 双态渲染

### ② 同步任务分状态分页

- [ ] `openviking_status.py` 新增 `/admin/openviking/sync_jobs/summary`
- [ ] `openviking_status.py` `list_openviking_sync_jobs` 增加 status + cursor + limit(25/cap 100) 三参数；返回 next_cursor
- [ ] `sync.py:283-290` `list_jobs` 重写支持 `(status, cursor)` keyset 分页
- [ ] `frontend/src/lib/api-openviking.ts` `listOpenVikingSyncJobs({status?, cursor?, limit?})` + 新 `getOpenVikingSyncJobsSummary()`
- [ ] `frontend/src/types/api.ts` `OpenVikingSyncJobsResponse.next_cursor`、新 `OpenVikingSyncJobsSummaryResponse`
- [ ] `OpenVikingDashboard.tsx:444-537` SyncJobsCard 重构：summary 驱动 StatusPill，4 个分状态分组 + 每组 `useInfiniteQuery`
- [ ] 删旧 `showIndexed` / `visibleCount` / `JOB_PAGE_SIZE` 切片逻辑
- [ ] pytest 新增 summary + cursor + 多状态分页用例
- [ ] vitest SyncJobsCard 分组渲染 + 加载更多 + summary 显示全表 count

### ③ 事件流分页 + 折叠展开

- [ ] `OpenVikingDashboard.tsx:128-176` 用 `useInfiniteQuery` 替换 `useState eventItems` + `useEffect` 拼装
- [ ] `refetchInterval` 改为函数，仅首页 5s 轮询；非首页返回 false
- [ ] `collapseConsecutiveEvents` 返回值附加 `events: OpenVikingDashboardEvent[]`
- [ ] `EventItem` chip 改为可点击 button；展开后渲染 group.events
- [ ] 加 "返回顶部" 按钮（仅在已翻过页时显示）
- [ ] 删旧 `eventBeforeId` / `setEventItems` 状态
- [ ] vitest 新增三条用例：折叠展开、加载更多、翻页关 polling

### ④ 调优摘要 + 操作面板(B 方案)

- [ ] 设计参考截图保存在仓内备查:`.tmp/m8-tuning-demo/` 下 `a.html` / `b.html` / `_base.css` / `shoot.mjs`,以及 `~/img/m8-tuning-b-*.png` 截图(commit 时**不**纳入 `.tmp/` 目录,仅作 plan 阶段参考)
- [ ] `OpenVikingDashboard.tsx` `OpenVikingTuningCard` 内拆出 `TuningCardHeader` / `ScopeSummaryCard` / `DivergentItemCard` / `AlignedFoldout` / `AdvancedTable` 五个内部子组件
- [ ] 头部副标题加 `共 N 项,M 项偏离推荐` 计数(M==0 时省略后半段)
- [ ] 头部 actions 增加 `[一键对齐推荐]`(M==0 禁用;M>0 走 confirm + batch applyMutation)
- [ ] 偏离项卡片:`[对齐推荐]` 快捷一键(无 confirm)+ `[详细配置]` toggle 展开 input + `[应用]` + `[回滚]`
- [ ] 已对齐折叠区:`<details>` 包 `AdvancedTable`,行布局 `1fr 110px 96px auto`,只有 `[应用]` 一个按钮
- [ ] scope `data-state=warn|ok` 切换边框配色;pill 黄/绿/灰三色,沿用现有 token
- [ ] `globals.css` 加新 class:`.tuning-scope-summary` / `-head` / `-pills` / `.tuning-divergent-item` / `-meta` / `-actions` / `.tuning-aligned-row` / `.tuning-advanced-table` / `-row`
- [ ] 删除旧 inline `settings-openviking-tuning-row` 渲染逻辑(grep 确认其它卡片未用,可一并删 CSS;若 grep 命中则只删 JSX 渲染)
- [ ] vitest 新增四条:默认渲染分态、`[对齐推荐]` 快捷、`[详细配置]` toggle + 应用/回滚、`[一键对齐推荐]` confirm + batch
- [ ] 截图回归:跑 `~/img/m8-tuning-b-*.png` 同等场景,人工对照实现是否对齐

### 收口

- [ ] 更新 `acceptance-checklist.md`（受影响行 + 新增行号回填）
- [ ] 本 plan 状态 Planned → Completed，回填"完成记录"小节
- [ ] docs 改动单独 commit；功能/接口/测试一个 commit；前端改一个 commit（开发可视改动量再拆）
- [ ] 一次性 SQL 脚本手动跑一次清掉 e2e_unknown 历史污染（命令在下方"附录"）

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
| 1c e2e_unknown 残留计数 | 4 | 0 |
| 1d 指标 | "未采集" × 3 | throughput / latency p95 / breaker_trips 真实数值 |
| 2 indexed 展开顺序 | 与 cancelled 时间倒序混排 | 按状态分块，每块独立分页 |
| 3 加载更多 | 闪一下回去 + 数字膨胀 | 新条目展开可见 + 分页期间不刷新轮询 |
| 4 调优 | 11 行 input 表单全展开 | 默认仅显示偏离项卡片 + 一键对齐推荐;已对齐项折叠为 `N 项 已对齐` 单行 |

---

## 完成记录

（实施后回填：代码范围、测试覆盖、收口命令、关键文件 git ref）
