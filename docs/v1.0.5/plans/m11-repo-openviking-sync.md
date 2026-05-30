# M11 — 代码仓 → OpenViking 内容同步

> 版本：v1.0.5
> 状态：Planned（B0 spike 未完成前不开 B1）
> 关联：[openviking-integration 设计 §2.1/§4](../design/openviking-integration.md) · [m5 写路径 hook](./m5-write-path-hooks.md) · [m6 同步完整性](./m6-sync-completeness-and-events.md) · [m10 同步任务 UX](./m10-sync-jobs-ux.md) · [acceptance §3.2/§3.7](./acceptance-checklist.md)
> 来源：2026-05-30 终验复盘——设计自始至终包含"代码仓进 OpenViking"，但实现只接了 `wiki_doc` / `report` 两类 `source_type`，repo 同步链从未接线。**这是架构拆任务时的遗漏**（M5 引擎只实现 wiki_doc/report 正文解析、M6 backfill 只枚举 wiki+report、cloner 仅发 `repo_synced` 事件不入队），本里程碑补齐。

---

## 0. 缺口事实（已核对代码）

设计要求（`openviking-integration.md`）：
- §2.1 写入流明示 `Wiki / 报告 / 仓库变更 → openviking_sync_jobs`，`└─ 仓库: 从 $CODEASK_DATA_DIR/repos/<repo_id>/... 派生`。
- §3.1 `source_type` 注释含 `repo`；§4 URI 表有 `仓库 <repo_slug> → viking://resources/codeask/repos/<repo_slug>/`。
- §2.2 读取侧要求 OpenViking 对仓库提供 `find/search/read/grep/glob`——必须有真实文件树进 OpenViking。

实现现状：
- `sync.py:54` / `hooks.py:31` 的 `source_type` `Literal` 只有 `{"wiki_doc", "report"}`。
- 引擎 `_resolve_content`（M5）只分派 wiki_doc / report；M6 backfill 只枚举 `WikiDocument` + verified `Report`。
- `cloner.py` 仓库 ready 后**只 `emit_event("repo_synced")`**（`cloner.py:264` 的 `source_type="repo"` 是事件标签），**不 enqueue、不上传内容**。
- `uri.py:repo_uri` 是**零调用方的死 helper**，坐实从未接线。

后果：`viking://.../repos/...` 下无任何内容，OpenViking 的 find/search 召不回代码。代码当前仅通过 opencode `codeask_prepare_worktree` + 原生 read/grep/glob 可见（§2.2 末段那条路是通的），**但 RAG / 语义检索代码的能力缺失**。

---

## 1. 决策（2026-05-30 负责人认可）

> repo 灌进 OpenViking **不由 CodeAsk 自己切片**：把仓库**工作树交给 OpenViking 自索引**（OpenViking 本就是代码 RAG 引擎，§2.2 读取侧要 read/grep/glob，必须有真实文件树）。CodeAsk 职责收敛为：**入队 + 提供仓库工作树 + 跟踪状态**，切片/嵌入由 OpenViking 负责。

### 已知未决（B0 spike 必须先解决）
1. **OpenViking 吃仓库的接口**：现 `OpenVikingClient` 只有 `add_text_resource`（单条 markdown 文本）。OpenViking 是否有"注册目录 / ingest 路径"的 API？若没有，是否要逐文件 `add_text_resource`（量级/性能/tombstone 复杂度需评估）？
2. **工作树来源**：`cloner.py` 产出的是 **bare 克隆（无工作树）**。OpenViking 要文件 → 需要一个工作树快照（`git worktree add` 临时检出？还是改克隆策略？复用 opencode 已有的 `worktree_manager`？）。
3. **viking_uri 粒度**：`repos/<repo_slug>/` 是目录前缀；逐文件时每文件一个 uri，还是整库一个资源？决定 tombstone 与去重口径。
4. **增量**：repo refresh 后是全量重灌还是按变更文件增量？M5 的"按 source 现查正文"模式对 repo 是否适用（repo 没有单一"正文"）。

**B0 闸门**：以上 4 点出结论 → 回写设计 §2.1/§4（补 repo 落地细节）→ 才开 B1。spike 由架构（我）做，不外包。

---

## 2. 任务拆分

> spike 归架构；B1–B3 实现归开发 + 架构 review/验收。

### B0 —— spike：OpenViking 吃仓库的方式（架构，闸门）
- 验证 §1 的 4 个未决点；产出最小可行方案（接口 + 工作树来源 + uri 粒度 + 增量策略）。
- 落地物：更新 `design/openviking-integration.md` §2.1（仓库分支补实现细节）、§4（repo uri 规则补充）；在本 plan §1 标注结论与放弃的备选。
- 退出条件：能对一个真实 repo 跑通"工作树 → OpenViking → find 召回代码片段"的手动 PoC。

### B1 —— cloner 接入入队
- `cloner.py` 仓库 ready / refresh 成功后，除现有 `repo_synced` 事件外，按 B0 结论 `enqueue(source_type="repo", source_id=<repo_id>, feature_slug=…, viking_uri=repo_uri(repo_slug), source_hash=<工作树/commit hash>)`。
- 放宽 `sync.py` / `hooks.py` 的 `source_type` `Literal` 纳入 `"repo"`。
- 去重语义沿用 M5：job 只表示"该 repo 脏了"，worker 跑时取最新工作树；`(source_type, source_id)` 非终态唯一约束对 repo 同样成立。
- 注意 commit 边界：沿用 M5 §"commit 后再 enqueue"，避免孤儿 job。

### B2 —— 引擎 + client 的 repo 分派
- `_resolve_content` / `run_pending_jobs` 增加 `repo` 分支：按 B0 方案把工作树交给 OpenViking（目录 ingest 或逐文件 add）。
- `OpenVikingClient` 按需新增方法（如 `add_directory_resource` / 复用 `add_text_resource` 批量）。
- tombstone：删仓 / slug 重命名 → 旧 uri `delete_resource`（对应设计 §4 "slug 重命名 → tombstone → 删除 → 新 pending" 那条，此前对 repo 不存在，本里程碑补上）。
- 失败 / 重试 / cancelled 走既有 `mark_failed` 收敛（M8 已定），repo 类失败自动出现在事件流与 m10 卡片。

### B3 —— backfill 纳入 repo
- M6 的启动 backfill / 定时 sweep 枚举范围从"WikiDocument + verified Report"扩展到"+ 已 ready 的 repo"。
- 幂等：`source_hash`（工作树/commit）未变 → `enqueued=0`；变更 → 重新入队。

### B4 —— UX 自动覆盖（无新前端）
- m10 落地后，repo 类同步任务在卡片中**自动**走人话化/状态/降噪/`data-status` 展示。本里程碑只需确认 `display_name` 反查对 repo 给出可读名（避免 `repo · <hex-id>`），其余零前端改动。

---

## 3. 影响面 / 涉及文件
- `src/codeask/code_index/cloner.py`：ready/refresh 后 enqueue repo（B1）。
- `src/codeask/rag/openviking/sync.py`：`source_type` Literal 纳入 repo；`_resolve_content` repo 分派；backfill 枚举 repo（B1/B2/B3）。
- `src/codeask/rag/openviking/hooks.py`：`source_type` Literal 纳入 repo（B1）。
- `src/codeask/rag/openviking/client.py`：按 B0 结论新增/调整上传方法（B2）。
- `src/codeask/rag/openviking/uri.py`：`repo_uri` 复活为真实调用方；按 B0 补 repo uri 规则（B2）。
- `src/codeask/api/openviking_status.py`：`display_name` 反查覆盖 repo（B4）。
- 设计文档 `design/openviking-integration.md` §2.1/§4（B0）。
- 测试：cloner enqueue 单测、引擎 repo 分派单测、backfill 含 repo 单测、live e2e（repo → OpenViking → find 召回）。

---

## 4. 依赖与边界
- **依赖**：B0 spike 是 B1–B3 的硬闸门。与 m10（前端 UX）**可并行**，互不阻塞。
- **不含**：`feature_readme` / `wiki_dir` / `global_index` 三类 source_type → [m12](./m12-sync-coverage-completion.md)。
- **前置修正**：[acceptance-checklist.md](./acceptance-checklist.md) §3.2 中"仓库变更 hook 全部接入 `[x]`"系误判（实际仅 `repo_synced` 事件），已拆为"事件 ✅ / 内容同步 ❌（本里程碑跟踪）"。

---

## 5. 验收清单
- [ ] **B0** spike 出结论：OpenViking 吃仓库的接口 + 工作树来源 + uri 粒度 + 增量策略；设计 §2.1/§4 已更新；真实 repo 跑通"工作树 → OpenViking → find 召回代码"手动 PoC
- [ ] **B1** cloner ready/refresh 成功后入队 `source_type="repo"` 任务，`source_type` Literal 已纳入 repo，commit 后入队无孤儿
- [ ] **B1** `(source_type, source_id)` 非终态唯一约束对 repo 成立；快速二次 refresh 索引到最新工作树（去重不致 staleness）
- [ ] **B2** 引擎 repo 分派把工作树交给 OpenViking；删仓 / slug 重命名触发 tombstone（旧 uri delete + 新 pending）
- [ ] **B2** repo 失败走 `mark_failed` 收敛，出现在事件流与 m10 卡片
- [ ] **B3** 启动 backfill / 定时 sweep 纳入已 ready 的 repo；`source_hash` 未变 → enqueued=0，变更 → 重新入队
- [ ] **B4** repo 类同步任务在卡片显示可读 `display_name`，不出现 `repo · <hex-id>`；其余 UX 复用 m10，零新前端
- [ ] live e2e：发布/刷新一个 repo → OpenViking `find` 能召回该 repo 的代码片段
- [ ] 后端 pytest / 前端 vitest / e2e 全绿，ruff / pyright / tsc / eslint clean
