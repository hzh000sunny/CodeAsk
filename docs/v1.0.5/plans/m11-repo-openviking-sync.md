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

> repo 内容由 **CodeAsk 驱动同步进 OpenViking**：以 CodeAsk 的 bare 克隆快照为准（保证 RAG 索引 == agent 在 worktree 所见，无漂移），**不**让 OpenViking 自己 watch URL 拉取（会与 CodeAsk 既有 refresh 重复且漂移）。日常更新走**文件级增量**（git diff），首次/重建走 zip 全量。OpenViking 只做解析/嵌入/检索，被动接收 CodeAsk 推送的内容。

### B0 spike 调研结论（2026-05-30，免环境调研已完成）

只读查阅已安装 `openviking==0.3.17` 的 HTTP API 与解析器（不 import、不改源码，符合 AGPL 边界），关键事实：

- **`POST /api/v1/resources`（`add_resource`）只接两种来源**：① `path` = 远程源（`http(s)://` / `git@` / `ssh://` / `git://` 仓库 URL）；② `temp_file_id` = 经 `POST /resources/temp_upload` 上传的**单个本地文件**。
- **HTTP server 明确拒绝 host 本地路径**：`server/local_input_guard.py:require_remote_resource_source` 对非远程源直接抛 `PermissionDeniedError`。→ **不能把 cloner 的本地裸仓/工作树路径直接指给 OpenViking。**
- **代码解析器原生吃 `.git` 与 `.zip`**：`parse/parsers/code/code.py`（`extensions=[".git", ".zip"]`）+ `parse/parsers/zip_parser.py`；`_extract_zip(zip_path, target_dir)`（code.py:513）**解压本地 zip**（带 Zip-Slip/symlink 防护）成代码树再索引。配 `parse/directory_scan.py` + `gitignore.py` 按 gitignore 扫描。→ **上传一个 zip 即可让 OpenViking 解包整库索引。**
- **`add_resource` 支持目录级参数**：`ignore_dirs / include / exclude / preserve_structure / directly_upload_media`。
- **`watch_interval`（分钟）= OpenViking 自带定时重索引**（仅对它能自己拉取的远程源有意义）；本方案**不使用**（见下）。
- **删除 = `DELETE /api/v1/fs?uri=&recursive=true`**（即现有 `delete_resource`），可一次清掉 `repos/<slug>/` 整棵子树。
- 读取侧 `find / search / grep / glob` 路由齐全（`server/routers/search.py`）。

### 选定方案 B′：CodeAsk git-diff 文件级增量（+ 首次 zip 全量）

CodeAsk 的 bare 克隆带完整历史，repo 同步任务已记 `source_hash`（上次同步的 commit sha）。

- **首次 / 重建**（无 last sha，或历史被 force-push 改写致 diff 失效）：`git --git-dir=<bare> archive --format=zip <ref>`（bare 仓直接产 zip，**无需检出工作树**）→ `temp_upload(<slug>.zip)` → `add_resource(temp_file_id, to=repo_uri(slug), exclude=二进制/大文件)`，OpenViking 解包建库。
- **日常更新**：`git --git-dir=<bare> diff --name-status <old_sha>..<new_sha>` →
  - `A/M` 文件 → `temp_upload(file)` + `add_resource(to=repos/<slug>/<path>)`（upsert）
  - `D` 文件 → `delete_resource(repos/<slug>/<path>)`
  - `R` 文件 → 删旧 + 加新
  - 成功后记 `new_sha` 为 last sha。
- **代价 ∝ 改动文件数，与仓库大小无关**——解决"大仓库每次全量"的不可接受问题。
- git 源 + local_dir 源**统一**（两类 cloner 都落 `repo.bare_path`，含 local_dir 的 `_sync_plain_local_dir_snapshot`）；**零 OpenViking 凭据**（内容由 CodeAsk 推，OV 不去拉私有仓）；快照与 agent 所见一致。
- 全程复用 wiki 三件套 `temp_upload / add_resource / delete_resource`，client 只需在现有 `add_text_resource` 外加"上传文件 bytes / zip"的变体。

### 放弃的备选（决策留痕）
- **方案 A（给 OV 仓库 URL + `watch_interval` 自动拉）**：放弃。OV 拉自己的 ref，可能 ≠ CodeAsk 工作树/agent 所见 → 检索与阅读漂移；且只覆盖有可达 URL 的 git 源、要给 OV 配私有仓凭据。
- **方案 A′（给 URL 但 CodeAsk 钉 commit 驱动重索引）**：放弃。能拿到 OV 的 git 增量，但 git/local 两条码路 + 仍要给 OV 配凭据；B′ 的文件级增量已覆盖增量诉求且更统一、免凭据。
- **方案 B（每次整包 zip 重传）**：放弃。大仓库每次更新全量重传不可接受（负责人 2026-05-30 否决）。仅其"首次全量"部分被 B′ 采纳。

### 仍需 live PoC 验证（B0 闸门未完成项）
1. **单代码文件**经 `temp_upload + add_resource` 落到 `repos/<slug>/<path>`，OpenViking 能否正确解析 + 被 `find/grep` 召回（单文件 vs 整树解析路径可能不同）。
2. **混用**首次 zip 全量解包 + 后续逐文件 add，在同一 `repos/<slug>/` 前缀下结构/检索是否一致；若不一致 → 退化为"首次也逐文件"彻底统一一种模式。
3. `temp_upload` 是否有体积上限卡首次 zip（localhost 传输本身不是瓶颈）。

**B0 闸门**：上述 3 个 PoC 项验证通过 → 回写设计 §2.1/§4（补 repo B′ 落地细节）→ 才开 B1。spike 由架构（我）做，不外包。

---

## 2. 任务拆分

> spike 归架构；B1–B3 实现归开发 + 架构 review/验收。

### B0 —— spike：确认 B′ 可落地（架构，闸门）
- 免环境调研**已完成**（见 §1：API 契约 + 选定 B′ + 放弃 A/A′/B）。
- 待办 = §1 末"仍需 live PoC 验证"的 3 项：单文件 add 可检索 / zip 全量与逐文件增量可混用 / temp_upload 体积上限。
- 落地物：PoC 通过后更新 `design/openviking-integration.md` §2.1（仓库分支按 B′ 补实现细节：首次 zip + git-diff 增量）、§4（repo uri 规则：`repos/<slug>/<rel>` 逐文件粒度）。
- 退出条件：真实 repo 跑通"首次 zip 全量 → 改两文件 → git diff 增量 upsert/delete → `find/grep` 召回新内容且旧内容已删"。

### B1 —— cloner 接入入队
- `cloner.py` 仓库 ready / refresh 成功后，除现有 `repo_synced` 事件外，`enqueue(source_type="repo", source_id=<repo_id>, feature_slug=…, viking_uri=repo_uri(repo_slug), source_hash=<当前 HEAD commit sha>)`。
- 放宽 `sync.py` / `hooks.py` 的 `source_type` `Literal` 纳入 `"repo"`。
- 去重语义沿用 M5：job 只表示"该 repo 脏了"，worker 跑时取最新 HEAD；`(source_type, source_id)` 非终态唯一约束对 repo 同样成立。
- 注意 commit 边界：沿用 M5 §"commit 后再 enqueue"，避免孤儿 job。
- **记录 last-synced sha**：worker 需要"上次同步到的 commit"来算 diff。沿用 `source_hash` 语义——成功后把本次 HEAD sha 落库，下次 worker 以它为 diff 基线。

### B2 —— 引擎 + client 的 repo 分派（B′：首次 zip + git-diff 增量）
- `run_pending_jobs` 增加 `repo` 分支：
  - **无 last sha / 历史改写致 diff 失效** → 首次/重建：`git --git-dir=<bare> archive --format=zip <HEAD>` → 上传 zip → `add_resource(to=repo_uri, exclude=二进制/大文件, preserve_structure)`。
  - **有 last sha** → 增量：`git diff --name-status <last>..<HEAD>` → A/M 文件 upsert（`add_resource(to=repos/<slug>/<rel>)`）、D 文件 `delete_resource`、R 文件删旧加新。
- `OpenVikingClient` 在现有 `add_text_resource` 外新增上传变体：`add_file_resource`（任意文件 bytes，按扩展名/二进制处理）与 `add_zip_resource`（首次全量）。
- tombstone：**repo 全局删除** / slug 重命名 → 旧 uri `delete_resource(repos/<slug>/, recursive=True)`（一次清整棵子树）。对应设计 §4 "slug 重命名 → tombstone → 删除 → 新 pending"，此前对 repo 不存在，本里程碑补上。删除入队点在 `code_index` 删仓 API commit 后（沿用 M5 commit 边界）。
- 失败 / 重试 / cancelled 走既有 `mark_failed` 收敛（M8 已定），repo 类失败自动出现在事件流与 m10 卡片。

### B3 —— backfill 纳入 repo
- M6 的启动 backfill / 定时 sweep 枚举范围从"WikiDocument + verified Report"扩展到"+ 已 ready 的 repo"。
- 幂等：`source_hash`（HEAD commit sha）未变 → `enqueued=0`；变更 → 重新入队（worker 据 last sha 走增量）。

### B4 —— UX 自动覆盖（无新前端）
- m10 落地后，repo 类同步任务在卡片中**自动**走人话化/状态/降噪/`data-status` 展示。本里程碑只需确认 `display_name` 反查对 repo 给出可读名（避免 `repo · <hex-id>`），其余零前端改动。

---

## 3. 影响面 / 涉及文件
- `src/codeask/code_index/cloner.py`：ready/refresh 后 enqueue repo + 落 HEAD sha（B1）。
- `src/codeask/api/code_index.py`：删仓端点 commit 后 enqueue tombstone（B2 删除路径）。
- `src/codeask/rag/openviking/sync.py`：`source_type` Literal 纳入 repo；`run_pending_jobs` repo 分支（首次 zip / git-diff 增量）；last sha 落库；backfill 枚举 repo（B1/B2/B3）。
- `src/codeask/rag/openviking/hooks.py`：`source_type` Literal 纳入 repo（B1）。
- `src/codeask/rag/openviking/client.py`：新增 `add_file_resource`（文件 bytes）与 `add_zip_resource`（首次全量）；复用 `delete_resource`（B2）。
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
- [ ] **B0**（免环境段已完成）live PoC 三项通过：单文件 add 可被 find/grep 召回 / 首次 zip 与逐文件增量在同前缀可混用 / temp_upload 不卡首次 zip 体积；设计 §2.1/§4 按 B′ 更新
- [ ] **B1** cloner ready/refresh 成功后入队 `source_type="repo"` 任务（带 HEAD sha），`source_type` Literal 已纳入 repo，commit 后入队无孤儿
- [ ] **B1** 成功后落库 last-synced sha 作下次 diff 基线；`(source_type, source_id)` 非终态唯一约束对 repo 成立
- [ ] **B2** 首次/重建走 zip 全量；有 last sha 走 `git diff` 文件级增量（A/M upsert、D delete、R 删旧加新），更新成本 ∝ 改动文件数
- [ ] **B2** repo 全局删除 / slug 重命名触发 tombstone：`delete_resource(repos/<slug>/, recursive=True)` 清整棵子树
- [ ] **B2** repo 失败走 `mark_failed` 收敛，出现在事件流与 m10 卡片
- [ ] **B3** 启动 backfill / 定时 sweep 纳入已 ready 的 repo；`source_hash` 未变 → enqueued=0，变更 → 重新入队
- [ ] **B4** repo 类同步任务在卡片显示可读 `display_name`，不出现 `repo · <hex-id>`；其余 UX 复用 m10，零新前端
- [ ] live e2e：发布/刷新一个 repo → OpenViking `find` 能召回该 repo 的代码片段
- [ ] 后端 pytest / 前端 vitest / e2e 全绿，ruff / pyright / tsc / eslint clean
