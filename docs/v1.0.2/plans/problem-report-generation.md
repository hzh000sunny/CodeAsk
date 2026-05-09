# Session 问题报告生成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将会话里的“生成报告”重做为 AI 成文的正式报告流程，满足一会话一报告、覆盖式再生成、默认特性推断和删除会话不删报告。

**Architecture:** 后端拆成“草稿准备”和“报告保存”两个动作：`prepare` 负责启动异步草稿任务并返回 `request_id/status`，状态查询接口负责返回 AI 生成的默认标题与正文，`save` 负责按会话唯一绑定规则 upsert 报告。数据层新增 `reports.session_id` 作为活动绑定字段，删除会话时仅解除绑定、不删除报告；前端弹窗改为消费 AI 生成的草稿，并默认选中最相关特性。

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy async, Alembic, Pydantic, pytest, React, TypeScript, TanStack Query, Vitest, Testing Library, uv。

**Execution Status:** 已于 2026-05-08 完成实现并通过定向回归；报告草稿准备已从长同步 POST 改为异步任务轮询，规避公网代理 / Vite dev proxy 在长响应返回阶段出现 503 后丢失草稿的问题。

**收尾修复记录（2026-05-09）：**

- prepare 阶段的默认绑定特性不再继承上一次保存的旧报告绑定。优先级调整为：用户显式传入 `feature_id` > 当前会话证据推断 > 既有报告旧绑定。这样用户曾经误选 `Browser Smoke` 后，再次生成同一会话报告时，默认仍会回到当前 Wiki / 工具证据命中的 `AnythingLLM Reference`。
- 前端点击“生成报告”时不再把本地 `detectedFeatureIds[0]` 作为显式 `feature_id` 提交给 prepare。prepare 请求默认传 `feature_id: null`，由后端基于完整 trace、Wiki 命中、工具证据和范围判断做默认推断；保存时才提交用户在确认弹窗中最终选择的特性。
- 保存会话报告时同时识别 `reports.session_id` 和早期 `metadata_json.session_id` 形态的历史报告。若同一会话存在重复报告，会保留当前会话活跃报告，删除历史重复报告，并同步删除旧特性 Wiki 目录下的 `report_ref`。
- 当前约束明确为：一个会话只能保留一篇问题报告；一篇问题报告只能绑定一个特性；重复生成是覆盖更新，不是创建新报告。
- 修复报告草稿解析容错：真实会话 `sess_6464227882e745ec` 暴露出模型会返回包在 ```json 代码块中的 JSON-like 内容，其中 `body_markdown` 包含未转义半角双引号，导致严格 `json.loads` 失败并把标题兜底成 `YYYY-MM-DD 未命名问题`。当前解析器已改为严格 JSON 优先，失败后仅针对固定报告 schema 做有限容错，能恢复 `title_description` 和 `body_markdown`，避免把原始 JSON 保存成报告正文。

**Verified Commands:**

```bash
uv run pytest tests/unit/test_session_report_generation.py tests/integration/test_session_report_generation.py tests/integration/test_sessions_api.py -q
corepack pnpm --dir frontend test:run tests/api.test.ts tests/session-workspace.test.tsx
uv run pytest tests/unit/test_session_report_generation.py tests/integration/test_session_report_generation.py -q
uv run ruff check src/codeask/sessions/report_generation.py tests/unit/test_session_report_generation.py
```

---

## 0. 文件结构

后端新增或修改：

```text
alembic/versions/20260508_0022_report_session_binding.py
src/codeask/db/models/report.py
src/codeask/api/schemas/session.py
src/codeask/api/sessions.py
src/codeask/sessions/reports.py
src/codeask/sessions/report_generation.py
src/codeask/wiki/reports.py
tests/integration/test_session_report_generation.py
tests/unit/test_session_report_generation.py
```

前端新增或修改：

```text
frontend/src/lib/api-sessions.ts
frontend/src/components/session/useSessionReport.ts
frontend/src/components/session/SessionWorkspaceDialogs.tsx
frontend/src/components/session/SessionDialogs.tsx
frontend/tests/api.test.ts
frontend/tests/session-workspace.test.tsx
```

## 当前接口契约

报告草稿准备不再由 `POST /api/sessions/{session_id}/reports/prepare` 长时间等待 LLM 返回完整正文。

当前契约：

1. `POST /api/sessions/{session_id}/reports/prepare`
   - 请求体：`{ "feature_id": number | null }`
   - 请求头：可选 `X-CodeAsk-Request-Id`
   - 响应：`{ "request_id": "...", "status": "running", "draft": null, "error": null }`
   - 行为：完成基础校验后创建后台任务并立即返回。

2. `GET /api/sessions/{session_id}/reports/prepare/{request_id}`
   - 响应 running：`{ "request_id": "...", "status": "running", "draft": null, "error": null }`
   - 响应 succeeded：`{ "request_id": "...", "status": "succeeded", "draft": SessionReportPrepared, "error": null }`
   - 响应 failed：`{ "request_id": "...", "status": "failed", "draft": null, "error": "..." }`
   - 行为：任务状态按 `session_id + request_id` 隔离，不能跨会话读取。

前端要求：

- 点击“生成报告”后立即显示“正在准备报告”弹窗。
- POST 返回后以后端返回的 `request_id` 为准轮询状态。
- 轮询策略使用分段退避：启动任务后立即查询一次状态；前 30 秒每 2 秒查询一次；30 秒后每 5 秒查询一次；总等待时间保持 10 分钟。
- 如果 POST 仍因代理异常返回 503，但前端已持有本地 request id，应继续尝试查询状态，兼容已经启动成功但响应失败的场景。
- 成功进入报告确认弹窗；失败必须走页面中央阻断式错误弹窗。
- prepare 请求默认不传前端本地猜测的特性，除非用户已经在 UI 中明确选择。默认特性由后端当前会话证据推断返回。
- 确认弹窗允许用户修改 AI 生成的标题和默认绑定特性；保存时才把最终 `feature_id` 写入报告。

文档修改：

```text
docs/rules/problem-report.md
docs/v1.0.2/design/agent-chat-runtime.md
docs/v1.0.2/plans/acceptance-checklist.md
docs/v1.0.2/README.md
```

## 任务 1：固定会话与报告的唯一绑定关系

**Files:**
- Create: `alembic/versions/20260508_0022_report_session_binding.py`
- Modify: `src/codeask/db/models/report.py`
- Modify: `src/codeask/wiki/reports.py`
- Test: `tests/integration/test_session_report_generation.py`

- [ ] **Step 1: 先写失败的集成测试，锁定“一会话一报告”和“删会话不删报告”**

```python
@pytest.mark.asyncio
async def test_session_report_is_upserted_and_survives_session_delete(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    feature = await client.post(
        "/api/features",
        json={"name": "Payment", "description": "payment feature"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    feature_id = feature.json()["id"]

    created = await client.post(
        "/api/sessions",
        json={"title": "支付启动失败"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    session_id = created.json()["id"]

    async with app.state.session_factory() as db:
        db.add_all(
            [
                SessionTurn(
                    id="turn_report_user",
                    session_id=session_id,
                    turn_index=0,
                    role="user",
                    content="支付服务启动失败",
                    evidence=None,
                ),
                SessionTurn(
                    id="turn_report_agent",
                    session_id=session_id,
                    turn_index=1,
                    role="agent",
                    content="初步判断是配置缺失。",
                    evidence=None,
                ),
            ]
        )
        await db.commit()

    first = await client.post(
        f"/api/sessions/{session_id}/reports",
        json={
            "feature_id": feature_id,
            "title": "2026-05-08 支付服务启动失败",
            "body_markdown": "# 初稿",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    second = await client.post(
        f"/api/sessions/{session_id}/reports",
        json={
            "feature_id": feature_id,
            "title": "2026-05-08 支付服务启动失败（更新）",
            "body_markdown": "# 更新稿",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first.json()["id"]

    deleted = await client.delete(
        f"/api/sessions/{session_id}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert deleted.status_code == 204

    report = await client.get(
        f"/api/reports/{first.json()['id']}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert report.status_code == 200, report.text
```

- [ ] **Step 2: 运行测试，确认当前行为失败**

Run:

```bash
uv run pytest tests/integration/test_session_report_generation.py::test_session_report_is_upserted_and_survives_session_delete -q
```

Expected:

```text
FAIL：当前 /sessions/{session_id}/reports 会重复创建新报告，且请求体不接受 body_markdown。
```

- [ ] **Step 3: 增加 reports.session_id 活跃绑定字段和唯一索引**

```python
class Report(Base, TimestampMixin):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    feature_id: Mapped[int | None] = mapped_column(
        ForeignKey("features.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, unique=True, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
```

```python
def upgrade() -> None:
    op.add_column("reports", sa.Column("session_id", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_reports_session_id_sessions",
        "reports",
        "sessions",
        ["session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_reports_session_id", "reports", ["session_id"], unique=True)
```

- [ ] **Step 4: 在 ReportService 中增加按 session upsert 的持久化入口**

```python
async def get_session_bound_report(
    self,
    session: AsyncSession,
    *,
    session_id: str,
) -> Report | None:
    return (
        await session.execute(select(Report).where(Report.session_id == session_id))
    ).scalar_one_or_none()


async def upsert_session_draft(
    self,
    session: AsyncSession,
    *,
    session_id: str,
    feature_id: int | None,
    title: str,
    body_markdown: str,
    metadata: dict[str, Any],
    subject_id: str,
) -> Report:
    existing = await self.get_session_bound_report(session, session_id=session_id)
    if existing is None:
        existing = Report(
            session_id=session_id,
            feature_id=feature_id,
            title=title,
            body_markdown=body_markdown,
            metadata_json=metadata,
            status="draft",
            verified=False,
            created_by_subject_id=subject_id,
        )
        session.add(existing)
        await session.flush()
        return existing
    existing.feature_id = feature_id
    existing.title = title
    existing.body_markdown = body_markdown
    existing.metadata_json = metadata
    if existing.status == "rejected":
        existing.status = "draft"
    return existing
```

- [ ] **Step 5: 重新运行测试，确认通过**

Run:

```bash
uv run pytest tests/integration/test_session_report_generation.py::test_session_report_is_upserted_and_survives_session_delete -q
```

Expected:

```text
1 passed
```

- [ ] **Step 6: 提交这一小步**

```bash
git add alembic/versions/20260508_0022_report_session_binding.py src/codeask/db/models/report.py src/codeask/wiki/reports.py tests/integration/test_session_report_generation.py
git commit -m "feat: persist unique session report binding"
```

## 任务 2：把报告生成改成 AI 成文的草稿准备流程

**Files:**
- Create: `src/codeask/sessions/report_generation.py`
- Modify: `src/codeask/api/schemas/session.py`
- Modify: `src/codeask/api/sessions.py`
- Modify: `src/codeask/sessions/reports.py`
- Test: `tests/unit/test_session_report_generation.py`
- Test: `tests/integration/test_session_report_generation.py`

- [ ] **Step 1: 写失败的后端测试，锁定 prepare 接口和 AI prompt 上下文**

```python
@pytest.mark.asyncio
async def test_prepare_session_report_calls_llm_with_report_rules(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    feature = await client.post(
        "/api/features",
        json={"name": "Payment", "description": "payment feature"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    feature_id = feature.json()["id"]
    created = await client.post(
        "/api/sessions",
        json={"title": "支付启动失败"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    session_id = created.json()["id"]

    async with app.state.session_factory() as db:
        db.add_all(
            [
                SessionTurn(
                    id="turn_prepare_user",
                    session_id=session_id,
                    turn_index=0,
                    role="user",
                    content="支付服务启动失败",
                    evidence=None,
                ),
                SessionTurn(
                    id="turn_prepare_agent",
                    session_id=session_id,
                    turn_index=1,
                    role="agent",
                    content="初步判断和配置缺失有关。",
                    evidence=None,
                ),
            ]
        )
        await db.commit()

    mock = MockLLMClient(
        [
            text_message(
                '{"title_description":"支付服务启动失败","body_markdown":"# 问题背景\\n\\n支付服务启动失败。"}'
            )
        ]
    )
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    prepared = await client.post(
        f"/api/sessions/{session_id}/reports/prepare",
        json={"feature_id": feature_id},
        headers={"X-Subject-Id": "alice@dev-1"},
    )

    assert prepared.status_code == 200, prepared.text
    payload = prepared.json()
    assert payload["feature_id"] == feature_id
    assert payload["title"].startswith("2026-05-08 ")
    prompt_text = "\n".join(
        block["text"]
        for message in mock.calls[0]["messages"]
        for block in message["content"]
        if block["type"] == "text"
    )
    assert "报告不是聊天记录副本" in prompt_text
    assert "已确认事实" in prompt_text
    assert "未确认项" in prompt_text
```

- [ ] **Step 2: 运行测试，确认缺少 prepare 接口和生成模块**

Run:

```bash
uv run pytest tests/unit/test_session_report_generation.py tests/integration/test_session_report_generation.py::test_prepare_session_report_calls_llm_with_report_rules -q
```

Expected:

```text
FAIL：/reports/prepare 不存在，且当前没有 AI 报告生成模块。
```

- [ ] **Step 3: 定义 prepare 请求与响应 schema**

```python
class SessionReportPrepareRequest(BaseModel):
    feature_id: int | None = None


class SessionReportPrepared(BaseModel):
    existing_report_id: int | None = None
    feature_id: int | None = None
    title: str
    body_markdown: str
    inferred_feature_ids: list[int] = Field(default_factory=list)
```

- [ ] **Step 4: 新增 report_generation.py，统一处理 prompt、标题规范和 LLM 输出解析**

```python
async def prepare_session_report_draft(
    *,
    gateway: LLMGateway,
    subject_id: str,
    turns: list[SessionTurn],
    tool_action_summary: str | None,
    feature_options: list[Feature],
    selected_feature_id: int | None,
    existing_report: Report | None,
    today: date,
) -> PreparedSessionReport:
    prompt = build_session_report_prompt(
        turns=turns,
        tool_action_summary=tool_action_summary,
        feature_options=feature_options,
        selected_feature_id=selected_feature_id,
        existing_report=existing_report,
        today=today,
    )
    raw = await generate_single_text(
        gateway,
        subject_id=subject_id,
        prompt=prompt,
    )
    parsed = parse_prepared_report_json(raw)
    return normalize_prepared_report(parsed, today=today, existing_report=existing_report)
```

- [ ] **Step 5: 在 API 层新增 prepare 端点，但保持 save 端点只负责保存**

```python
@router.post("/sessions/{session_id}/reports/prepare", response_model=SessionReportPrepared)
async def prepare_session_report(
    session_id: str,
    payload: SessionReportPrepareRequest,
    request: Request,
) -> SessionReportPrepared:
    ...
```

- [ ] **Step 6: 重新运行测试，确认 prepare 行为通过**

Run:

```bash
uv run pytest tests/unit/test_session_report_generation.py tests/integration/test_session_report_generation.py::test_prepare_session_report_calls_llm_with_report_rules -q
```

Expected:

```text
2 passed
```

- [ ] **Step 7: 提交这一小步**

```bash
git add src/codeask/api/schemas/session.py src/codeask/api/sessions.py src/codeask/sessions/reports.py src/codeask/sessions/report_generation.py tests/unit/test_session_report_generation.py tests/integration/test_session_report_generation.py
git commit -m "feat: prepare ai-authored session report drafts"
```

## 任务 3：保存报告时按会话唯一关系覆盖更新

**Files:**
- Modify: `src/codeask/api/sessions.py`
- Modify: `src/codeask/wiki/reports.py`
- Modify: `src/codeask/sessions/reports.py`
- Test: `tests/integration/test_session_report_generation.py`

- [ ] **Step 1: 写失败的 API 测试，锁定“再次生成覆盖原报告”**

```python
@pytest.mark.asyncio
async def test_save_session_report_updates_existing_report_instead_of_creating_new_one(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    ...
    first = await client.post(
        f"/api/sessions/{session_id}/reports",
        json={
            "feature_id": feature_id,
            "title": "2026-05-08 支付服务启动失败",
            "body_markdown": "# 第一版",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    second = await client.post(
        f"/api/sessions/{session_id}/reports",
        json={
            "feature_id": feature_id,
            "title": "2026-05-08 支付服务启动失败",
            "body_markdown": "# 第二版",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )

    assert second.json()["id"] == first.json()["id"]
    assert second.json()["body_markdown"] == "# 第二版"
```

- [ ] **Step 2: 运行测试，确认当前 save 接口语义不匹配**

Run:

```bash
uv run pytest tests/integration/test_session_report_generation.py::test_save_session_report_updates_existing_report_instead_of_creating_new_one -q
```

Expected:

```text
FAIL：当前 save 接口依旧按 create_draft 创建新报告。
```

- [ ] **Step 3: 调整 save 请求模型，改为显式保存 prepare 草稿**

```python
class SessionReportCreate(BaseModel):
    feature_id: int | None = None
    title: str = Field(..., min_length=1, max_length=500)
    body_markdown: str = Field(..., min_length=1)
```

- [ ] **Step 4: save 接口调用 upsert_session_draft，并合并 session 元数据**

```python
report = await ReportService().upsert_session_draft(
    session,
    session_id=session_id,
    feature_id=payload.feature_id,
    title=payload.title,
    body_markdown=payload.body_markdown,
    metadata=merge_session_report_metadata(existing_metadata, session_id, list(turns)),
    subject_id=request.state.subject_id,
)
```

- [ ] **Step 5: 运行针对性后端测试**

Run:

```bash
uv run pytest tests/integration/test_session_report_generation.py -q
```

Expected:

```text
全部通过，覆盖 prepare、save upsert、delete session keeps report。
```

- [ ] **Step 6: 提交这一小步**

```bash
git add src/codeask/api/sessions.py src/codeask/api/schemas/session.py src/codeask/wiki/reports.py src/codeask/sessions/reports.py tests/integration/test_session_report_generation.py
git commit -m "feat: upsert session generated reports"
```

## 任务 4：前端弹窗默认选中特性并消费 AI 草稿

**Files:**
- Modify: `frontend/src/lib/api-sessions.ts`
- Modify: `frontend/src/components/session/useSessionReport.ts`
- Modify: `frontend/src/components/session/SessionWorkspaceDialogs.tsx`
- Modify: `frontend/src/components/session/SessionDialogs.tsx`
- Test: `frontend/tests/api.test.ts`
- Test: `frontend/tests/session-workspace.test.tsx`

- [ ] **Step 1: 写失败的前端 API 与交互测试**

```tsx
it("prepares a session report draft before saving", async () => {
  const fetchMock = vi.fn(async () =>
    new Response(
      JSON.stringify({
        existing_report_id: 12,
        feature_id: 7,
        inferred_feature_ids: [7, 9],
        title: "2026-05-08 支付服务启动失败",
        body_markdown: "# 问题背景",
      }),
      { headers: { "Content-Type": "application/json" } },
    ),
  );
  vi.stubGlobal("fetch", fetchMock);

  await prepareSessionReport("sess_1", { feature_id: 7 });

  const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  expect(path).toBe("/api/sessions/sess_1/reports/prepare");
  expect(init.method).toBe("POST");
});
```

```tsx
it("defaults the report dialog to the strongest inferred feature", async () => {
  ...
  fireEvent.click(screen.getByRole("button", { name: "生成报告" }));
  expect(await screen.findByDisplayValue("支付结算")).toBeInTheDocument();
  expect(screen.getByDisplayValue("2026-05-08 支付服务启动失败")).toBeInTheDocument();
});
```

- [ ] **Step 2: 运行测试，确认前端尚未请求 prepare 接口**

Run:

```bash
uv run --directory frontend vitest run tests/api.test.ts tests/session-workspace.test.tsx
```

Expected:

```text
FAIL：缺少 prepareSessionReport API 和新的弹窗默认值逻辑。
```

- [ ] **Step 3: 前端 API 拆成 prepare + save 两步**

```ts
export function prepareSessionReport(
  sessionId: string,
  payload: { feature_id?: number | null },
) {
  return apiRequest<SessionReportPrepared>(`/api/sessions/${sessionId}/reports/prepare`, {
    method: "POST",
    body: payload,
  });
}

export function generateSessionReport(
  sessionId: string,
  payload: { feature_id?: number | null; title: string; body_markdown: string },
) {
  return apiRequest<ReportRead>(`/api/sessions/${sessionId}/reports`, {
    method: "POST",
    body: payload,
  });
}
```

- [ ] **Step 4: useSessionReport 改成“先 prepare，后 save”，并处理已存在报告**

```ts
const [preparedReport, setPreparedReport] = useState<SessionReportPrepared | null>(null);

async function openReportDialog() {
  ...
  const prepared = await prepareMutation.mutateAsync({
    session: selected,
    featureId: inferredFeatureId ?? null,
  });
  setPreparedReport(prepared);
  setReportFeatureId(prepared.feature_id ? String(prepared.feature_id) : "");
  setReportTitle(prepared.title);
  setReportDialog("confirm");
}
```

- [ ] **Step 5: 弹窗文案与按钮语义更新**

```tsx
<Button
  disabled={!title.trim() || isGenerating}
  onClick={onConfirm}
  type="button"
  variant="primary"
>
  {existingReportId ? "更新报告" : "保存报告"}
</Button>
```

- [ ] **Step 6: 运行前端测试**

Run:

```bash
uv run --directory frontend vitest run tests/api.test.ts tests/session-workspace.test.tsx
```

Expected:

```text
全部通过，覆盖 prepare 调用、默认特性、默认标题和更新语义。
```

- [ ] **Step 7: 提交这一小步**

```bash
git add frontend/src/lib/api-sessions.ts frontend/src/components/session/useSessionReport.ts frontend/src/components/session/SessionWorkspaceDialogs.tsx frontend/src/components/session/SessionDialogs.tsx frontend/tests/api.test.ts frontend/tests/session-workspace.test.tsx
git commit -m "feat: wire ai session report draft dialog"
```

## 任务 5：整体验证与文档收口

**Files:**
- Modify: `docs/v1.0.2/plans/acceptance-checklist.md`
- Modify: `docs/v1.0.2/README.md`
- Test: `tests/integration/test_sessions_api.py`
- Test: `frontend/tests/session-workspace.test.tsx`

- [ ] **Step 1: 跑后端回归，确认旧会话能力未被破坏**

Run:

```bash
uv run pytest tests/integration/test_sessions_api.py tests/integration/test_session_report_generation.py tests/unit/test_session_report_generation.py -q
```

Expected:

```text
全部通过。
```

- [ ] **Step 2: 跑前端回归，确认会话页未被报告弹窗改坏**

Run:

```bash
uv run --directory frontend vitest run tests/session-workspace.test.tsx tests/api.test.ts
```

Expected:

```text
全部通过。
```

- [ ] **Step 3: 如果本地 dev server 可用，补一次管理员浏览器手动验收**

Run:

```bash
uv run python -m codeask
uv run --directory frontend vite --host 0.0.0.0 --port 5173
```

Manual checklist:

```text
1. 进入一个已有问答的会话，点击“生成报告”。
2. 弹窗默认选中最相关特性。
3. 标题默认是“当天日期 + AI 生成的问题描述”。
4. 用户可以修改问题描述后保存。
5. 第二次生成同一会话报告时，更新原报告而不是新增。
6. 删除会话后，该报告仍能从报告列表打开。
```

- [ ] **Step 4: 文档状态回填**

```text
将以下文档中的对应条目标记为已完成：
- docs/v1.0.2/plans/acceptance-checklist.md
- docs/v1.0.2/README.md
```

- [ ] **Step 5: 最终提交**

```bash
git add docs/v1.0.2/plans/acceptance-checklist.md docs/v1.0.2/README.md
git commit -m "docs: close session report generation plan"
```
