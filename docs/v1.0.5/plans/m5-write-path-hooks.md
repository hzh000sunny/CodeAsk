# M5 — Wiki / Report 写路径 hook（增量同步 OpenViking）

> 版本：v1.0.5
> 状态：开发中（M5-0 + 主写路径 hook + 20c 服务层发布覆盖已实现）
> 关联：[Phase 1 计划 步骤 20-22](./phase-1-sync-adapter.md) · [验收 checklist §3.7](./acceptance-checklist.md) · [设计](../design/openviking-integration.md)

M5 把 Wiki 文档发布/回滚、legacy 上传、Report verify 生命周期、Wiki 节点软删这些**写路径**接进 OpenViking 增量同步。M1–M4 已交付：M1 提供了同步队列 + 手动 enqueue + 后台 worker，但**不接任何写路径 hook**；M4 的 UI 搜索靠 `openviking_sync_jobs.viking_uri` 反查命中——只有 M5 把写路径喂进队列，搜索才有真实数据可召回。

读真实代码后确认：M5 远不止"在三处调 `enqueue`"。当前同步引擎只能处理**内联了正文的 job**，且**没有任何删除/tombstone 通路**。本文记录已拍板的四个架构决策，再给分批开发清单。

---

## 1. 已锁定的架构决策

### D1 — content 投递：引擎侧"按 source_id 现查正文"（不内联快照）

现状：`run_pending_jobs`（`rag/openviking/sync.py:93`）只能处理 `progress["manual"]` 里**内联了 `content` 的 job**；`_resource_from_job`（`sync.py:187`）拿不到 content 就把 job 标 `failed`。引擎没有"按 source 回查正文"的能力。又因 `enqueue`（`sync.py:55-65`）对同 `(source_type, source_id)` 的**非终态** job 去重返回旧 job、不更新——若把正文内联进 payload，快速二次发布时第二次 enqueue 是 no-op，会索引到**旧正文**。

**决策：给引擎加正文解析器。** job 只存 `source_type` / `source_id` / `viking_uri`（+ operation，见 D2），worker 跑到时按 source 现查 DB 取**当前**正文再 add。去重语义天然正确（job 只表示"这个 source 脏了"，worker 跑时拿最新），无正文冗余。

实现要点：
- `_resource_from_job` 改造 / 新增 `_resolve_content(job, session)`：按 `source_type` 分派——
  - `wiki_doc` → `source_id = WikiDocument.id`，取 `current_version.body_markdown`、filename/uri 见 §2
  - `report` → `source_id = Report.id`，取 `report.body_markdown`
- 兼容保留 `progress["manual"]` 内联路径（M1 admin 手动 enqueue 仍用它）：解析器先看 operation/manual，再走 source 现查。
- 现查时 source 已不存在或不该索引（如 doc 被软删、report 跌出 verified）→ 视为 tombstone（见 D2），不是 failed。

### D2 — tombstone 通路属于净新增（需 spike + client + 引擎）

`OpenVikingClient`（`rag/openviking/client.py`）只有 `add_text_resource` / `task_status` / `find`，**没有删除方法**；引擎也只有 add。步骤 21（unverify / reject / delete report）和步骤 22（节点软删）要的 tombstone 完全没有底座。

**决策：spike 先行，再补 client + 引擎 delete 操作。**
1. **spike**（同 M4 D3 的做法）：对运行中的 OpenViking server 实打，产出"删除/移除资源的接口（REST 端点 + 入参 + 响应 + 一次成功样本）"。M2 spike 记录过 MCP 有 `forget` 工具；REST 侧删除端点未知，**不出结论后续全是返工**。
2. `OpenVikingClient.delete_resource(viking_uri)`（或 spike 确认的签名），复用 `_client()`（trusted headers + `trust_env=False`）。
3. 引擎支持 **operation = `"upsert"` | `"delete"`**：建议存进 `progress` JSON（如 `{"op": "delete"}`），**免迁移**；`enqueue` 增加可选 `operation` 形参，默认 `"upsert"`。worker 按 op 调 add 或 delete。
4. tombstone 的 `viking_uri` 必须能算出来——unverify/软删时 source 可能还在 DB，按 §2 规则生成 URI 即可。

**2026-05-26 delete spike 结论：**

- REST 端点：`DELETE /api/v1/fs?uri={viking_uri}&recursive={bool}`
- 认证头：沿用 trusted headers：`X-OpenViking-Account/User/Agent`
- 响应 envelope：`{"status":"ok","result":{"uri":"...","estimated_deleted_count":0},"error":null,"telemetry":null}`
- 实测样本：先通过 `POST /api/v1/resources/temp_upload` + `POST /api/v1/resources` 写入
  `viking://resources/codeask/spikes/codeask-delete-spike-1779790626.md`，随后
  `DELETE /api/v1/fs?...&recursive=true` 返回 200。
- 注意：同一个样本用 `recursive=false` 返回 412 `FAILED_PRECONDITION`，提示
  `Cannot remove directory without --recursive`。CodeAsk 的 tombstone 删除统一使用
  `recursive=true`，保证 OpenViking 将目标作为目录资源时也能删除。

### D3 — hook 一律放 API 端点 commit 之后

所有 service 方法（`publish_document` `documents/service.py:150`、`rollback_to_version:269`、`verify/unverify/reject` `wiki/reports.py:233/268/294`、`sync_legacy_markdown_document` `wiki/sync/service.py:67`）**只 `flush`**，`commit` 都在 **API 层**。`enqueue` 自己开 session 独立 commit——若放在 service 内（flush 后、外层 commit 前），外层一旦回滚就留下孤儿 job。Phase 1 §5 也明确要求"commit 后再 enqueue"。

**决策：hook 放 API 端点 `session.commit()` 之后**，通过 `Request` 取 `app.state.openviking_sync_service`（已在 `app.py:312` 暴露）注入。

> 这修正了 Phase 1 步骤 20 的旧措辞（它说放进 `sync_legacy_markdown_document` 内）。legacy 上传应放它的两个调用方 commit 后，不在函数内部，见 §3 步骤 20b。

enqueue 失败**不得阻塞主写路径**：commit 已成功，enqueue 包 try/except，失败只 log（与 `dashboard.emit_event` 同等容错）。

### D4 — 软删分散，M5 覆盖主路径，其余后置

`WikiNode.deleted_at` 写入点分散：
- `wiki/tree/service.py:465`（用户删节点 / 子树，**主路径**）→ M5 发 tombstone
- `wiki/tree/service.py:517`（**恢复** `deleted_at=None`）→ M5 重新 upsert（不是 tombstone）
- `wiki/sync/service.py:149`（`soft_delete_legacy_document`，legacy 文档软删）→ M5 发 tombstone（端点 `documents_compat.py:134`，commit `:148`）
- `wiki/imports/session_service.py:1126`（导入会话内软删）→ **不在 M5 范围**，标注后置

子树批量删除：一次操作可能软删多个 node，需收集受影响的 `WikiDocument` 逐个入队 tombstone。

---

## 2. URI / source_id 约定（必须与 M4 反查一致）

M4 搜索反查（`api/wiki/search.py`）按以下映射把 OpenViking 命中还原成节点，**M5 入队必须对齐**，否则发布的内容搜不回来：

| source_type | source_id（字符串） | URI helper | M4 反查锚点 |
|---|---|---|---|
| `wiki_doc` | `str(WikiDocument.id)` | `wiki_doc_uri(feature.slug, 相对路径)` | `search.py:276` |
| `report` | `str(Report.id)` | `report_uri(feature.slug, filename)` | `search.py:331` |

- `feature.slug` 存在（`db/models/feature.py:22`）。Report 只有 `feature_id`，需查 `Feature` 取 slug。
- `rag/openviking/uri.py` 的 `wiki_doc_uri` / `report_uri` **目前零调用方**（M1 manual enqueue 让 admin 直接传 `viking_uri`），M5 是首个使用者，没有现成相对路径约定，需在本里程碑确立：
  - **wiki_doc 相对路径**：文档节点挂在 knowledge_base 系统根下，`wiki_doc_uri` 第二参要传**相对 KB 根**的路径——需把 `node.path` 的 KB 根前缀剥掉再传（dev 核对 `node.path` 实际结构）。
  - **report filename**：Report 无天然文件名。**用 `f"{report_id}.md"`**（稳定、唯一，避免 OpenViking 侧资源碰撞）。反查靠 `source_id` 不靠 filename，filename 选择属低风险。
- 反查靠 job 上存的 `source_type` + `source_id`，不靠 URI 结构，但 URI 仍须唯一稳定（OpenViking 侧寻址 + delete 需要）。

---

## 3. 分批开发清单

> 纪律：每步独立可跑、可回滚；每步退出条件 = 相关 pytest 绿 + ruff 绿 + pyright 0（gate 已是硬约束，新增代码须带类型）。

### 步骤 M5-0 —— 引擎底座（D1 + D2，最重，先做）

- **0a delete spike**：实打 OpenViking 删除/移除资源端点，记录端点 / 入参 / 响应 / 成功样本（产出后再写 client）。✅ 2026-05-26 已完成，见 D2 记录。
- **0b** `OpenVikingClient.delete_resource(...)`，复用 `_client()`；单测覆盖正常 + 异常。✅ 已实现，REST `DELETE /api/v1/fs`，默认 `recursive=true`。
- **0c** `enqueue` 增加 `operation: Literal["upsert","delete"] = "upsert"` 形参，存入 `progress`（免迁移）。✅ 已实现。
- **0d** `run_pending_jobs` / `_resource_from_job` 改造为按 `source_type` + `source_id` 现查正文（upsert）或调 `delete_resource`（delete）；保留 manual 内联兼容路径。✅ 已实现。
- **0e** 引擎单测：upsert 现查最新正文、delete 调用、去重在"现查"模型下不丢更新、source 已删时转 tombstone。✅ 已覆盖 `tests/unit/test_openviking_sync.py`。

### 步骤 20 —— Wiki 文档发布 / 回滚 → upsert

- `api/wiki/documents.py:34` publish 端点 `session.commit()`（`:40`）后：`enqueue(source_type="wiki_doc", source_id=str(document.id), feature_slug=…, viking_uri=wiki_doc_uri(...), source_hash=新版本 markdown sha)`。
- `api/wiki/versions.py:79` rollback 端点 commit（`:85`）后：同上 enqueue。
- `save_draft`（`service.py:108`）/ `delete_draft`（`:134`）对应端点 **不入队**。
- 端点拿不到 `feature.slug` / `node.path`（`get_document_detail` 返回 dict 不含）——publish/rollback 端点 enqueue 前需补查（node→space→feature，已有 `_load_feature_for_document` 可复用思路），或让 service 返回所需标识。

2026-05-26：已通过 `src/codeask/rag/openviking/hooks.py` 在 commit 后按 `document_id`
补查 `Feature/WikiNode/current_version`，生成 `wiki_doc_uri` 与正文 hash 后入队；draft 路径不入队。

### 步骤 20b —— legacy `/documents` 上传 + backfill → upsert

- `api/documents_compat.py:43` upload 端点 commit（`:110`）后入队；source_id 用同步出的 `WikiDocument.id`（与 M4 一致，非 legacy `Document.id`）。
- `backfill_feature_content`（`wiki/sync/service.py:28`，由 `wiki/tree/service.py:139` 在建空间时调用）循环回填多文档——其调用方 commit 后逐个入队（收集回填出的 `WikiDocument.id` 列表）。只挂 upload 端点会漏 backfill 路径。
- 两条路径都经过 `sync_legacy_markdown_document`，但 hook **不**放函数内（D3）。

2026-05-26：legacy 上传 commit 后按 `legacy_document_id` 反查 native `WikiDocument.id`
入队；`backfill_feature_content` 改为返回本次新创建的 native document ids，由
`GET /api/wiki/tree?feature_id=...` 调用方 commit 后逐个入队。

### 步骤 21 —— Report verify 生命周期

- `api/reports.py` verify 端点（`:96`，commit `:112`）：`verified=false→true` → upsert（`source_type="report"`, `source_id=str(report.id)`）。
- unverify（`:118` commit `:128`）/ reject（`:134` commit `:142`）→ **tombstone**（`operation="delete"`）。
- delete report 端点（commit `:165`）→ tombstone。
- `update_draft`（`reports.py:214`，未 verified 态编辑，端点 commit `:91`）**不入队**。
- verified 态下编辑且 hash 变化 → upsert（若产品允许直接编辑 verified report；否则该路径不存在，dev 核对）。

2026-05-26：已核对当前 `ReportService.update_draft` 仅允许 `draft/rejected` 编辑，verified
态不可编辑，因此没有 verified edit hook。verify commit 后 upsert；unverify/reject/delete
commit 后 tombstone，其中 delete 在删除前预计算 `report_uri`，commit 后入队。

### 步骤 22 —— Wiki 节点软删 → tombstone

- tree 删除端点（`wiki/tree/service.py:465` 所属端点）commit 后：对受影响 doc / 子树逐个发 tombstone。
- legacy 软删（`documents_compat.py:134` 端点，commit `:148`）→ tombstone。
- 恢复（`tree/service.py:517` 所属端点）→ 重新 upsert。
- 导入会话软删（`imports/session_service.py:1126`）**后置，不在 M5**。

2026-05-26：tree 删除 / 恢复端点已在 commit 后按受影响子树文档逐个入队；
legacy `/api/documents/{id}` 软删 commit 后按 native `WikiDocument.id` 入 tombstone。

### 步骤 20c —— 覆盖服务层发布路径（F1 补齐，验收阻塞项）

> 状态：已实现。验收发现：D3"hook 放端点"漏掉了**从内部调用 `WikiDocumentService.publish_document` 的服务层**——这些路径产出真实已发布 wiki 文档，但不经过已挂 hook 的 publish/rollback 端点，因此**永不入队**，直到有人在 UI 重新发布。

确认的绕过入口（全部 `await ... publish_document(...)`，外层端点都有 commit）：

| 发布来源 | 服务层调用点 | 触发端点（commit 后可挂 drain） |
|---|---|---|
| 晋级会话附件 | `wiki/promotions/service.py:161` | `POST /wiki/promotions/session-attachment`（`promotions.py:39`） |
| 导入 resolve 单项 | `wiki/imports/session_service.py:790`（`resolve_item`） | `POST /wiki/imports/sessions/{id}/items/{item}/resolve`（`imports.py:216`） |
| 导入 bulk resolve | 同上（`bulk_resolve_items`） | `.../items/bulk-resolve`（`imports.py:234`） |
| 导入 retry | 同上（`_materialize_or_mark_failed`） | retry item/session 端点（`imports.py:270`/`:286`） |
| 导入 job apply | `wiki/imports/service.py:287`（`WikiImportJobService.apply_job`） | `POST /wiki/imports/{job_id}/apply`（`imports.py:349`） |

逐端点把 `document_id` 从深层服务方法串上来不现实（≥6 个端点、3 个 `_materialize` 调用点）。**采用集中式 stash + drain**：

1. **service 侧打标（中性、不引 openviking 依赖）**：`WikiDocumentService.publish_document` 与 `rollback_to_version` 在赋值 `document.current_version_id` 后，向 `session.info.setdefault("_pending_openviking_wiki_doc_ids", []).append(int(document.id))`。不 import rag.openviking，保持 wiki→rag 无耦合。
2. **drain helper（放 `rag/openviking/hooks.py`）**：`async def drain_wiki_document_syncs(request, session)` —— 取出并清空 `session.info["_pending_openviking_wiki_doc_ids"]`，去重后逐个 `enqueue_wiki_document_sync(request, document_id=..., operation="upsert")`；整体 best-effort try/except。
3. **端点接线**：所有"会触发 publish/rollback"的端点 `session.commit()` 后调 `drain_wiki_document_syncs`：publish、rollback、promotion、import resolve / bulk-resolve / retry(item+session) / apply_job。
4. **统一机制**：把步骤 20 publish/rollback 端点原先"从 `data["document_id"]` 显式 enqueue"也改为走 drain（避免两套机制 + 重复入队；`enqueue` 去重虽幂等但冗余）。

新入口（晋级/导入）覆盖后，未来任何新调用 `publish_document` 的服务层只要其端点已挂 drain 即自动覆盖；service 侧打标是唯一单点。`enqueue` 的去重保证同一 doc 多次 drain 不产生重复 job。

2026-05-26：已实现集中式 stash + drain。`WikiDocumentService.publish_document` /
`rollback_to_version` 在设置 `current_version_id` 后写入
`session.info["_pending_openviking_wiki_doc_ids"]`，不 import `rag.openviking`；
`rag/openviking/hooks.py` 新增 `drain_wiki_document_syncs`，端点 commit 后统一取标并
best-effort upsert。已接线 publish、rollback、promotion、import upload / resolve /
bulk-resolve / retry(item+session) / apply_job。`upload_item` 也接入 drain，因为最后一个
导入文件上传完成时同样可能触发 `_materialize_or_mark_failed` 并发布文档。

### 收尾

- 升级路径在真实数据备份上回归一次。
- 勾选 `acceptance-checklist.md` §3.7。

---

## 4. 测试矩阵

| 层次 | 用例 |
|---|---|
| 单元（引擎） | upsert 现查最新正文；delete 操作；`enqueue` 去重在现查模型下不丢更新；source 已软删→转 tombstone；URI/source_id 与 M4 反查往返一致 |
| 集成 | 发布文档 → M4 搜索能命中；unverify / 软删 → tombstone 后搜不到；恢复 → 重新可搜；**快速二次发布 → 索引到新正文**（验证 D1 选择消除了 staleness）；legacy 上传 + backfill 两路径都入队 |
| 过滤 | draft 保存/删除、unverified 编辑 **不入队**；verify true→/→false 各入对应操作的 job |
| 故障 | OpenViking 不可用时 hook 不阻塞主写路径（commit 已成功，enqueue 失败只 log，主响应仍 2xx）；delete 端点不可用时 tombstone job 走退避重试 |
| 升级 | 真实数据备份升级后写路径首次触发入队正确 |

详细 case 落 `acceptance-checklist.md` §3.7。

---

## 5. 验收（见 acceptance §3.7）

- 发布 / 回滚 / 上传 / backfill / verify(true) → `openviking_sync_jobs` 新增 pending，`source_type` / `source_id` 与 M4 反查一致。
- unverify / reject / delete report / 节点软删 → tombstone（`operation=delete`）job；恢复 → upsert。
- draft 保存/删除、unverified 编辑、verified→false 后再编辑 **不增加 upsert job**。
- 引擎按 source 现查正文，无正文内联进 `progress`；快速二次发布索引到最新正文。
- **服务层发布路径全覆盖（步骤 20c）**：晋级会话附件、导入 resolve/bulk-resolve/retry/apply_job 产出的已发布文档都入队 upsert（不再依赖 UI 重新发布）。
- hook 在 commit 之后；OpenViking / delete 端点不可用不阻塞主写路径。
- pyright 0、pytest 绿、ruff 绿、前端不受影响（写路径 hook 纯后端）。

---

## 6. 工作量提示

最重的是 **M5-0**（引擎改造 + delete spike + client + operation），其次 tombstone 的端到端连通。步骤 20-22 在底座就绪后才是"调 enqueue"的表象。底座没定之前不要先写 hook。
