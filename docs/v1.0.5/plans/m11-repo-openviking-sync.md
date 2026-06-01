# M11 — 代码仓 → OpenViking 内容同步

> 版本：v1.0.5
> 状态：**Ready for B1（2026-05-31 架构复核重测：B0.1 闸门通过，写入策略已定）**。开发曾因"删除后 find 残留"冻结；复核证明删除本身干净，所谓残留经受控复现复不出、疑似异步竞态而非确定性 bug → 解冻。最终写入配方见 [feasibility §6.2](./m11-openviking-repo-feasibility-research.md#62-最终方向m11-b-可落地配方)。
> 关联：[openviking-integration 设计 §2.1/§4](../design/openviking-integration.md) · [m5 写路径 hook](./m5-write-path-hooks.md) · [m6 同步完整性](./m6-sync-completeness-and-events.md) · [m10 同步任务 UX](./m10-sync-jobs-ux.md) · [acceptance §3.2/§3.7](./acceptance-checklist.md) · [可行性再调研](./m11-openviking-repo-feasibility-research.md)
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

> repo 内容如果进入 OpenViking，必须由 **CodeAsk 驱动同步**：以 CodeAsk 的 bare 克隆快照为准（保证 RAG 索引 == agent 在 worktree 所见，无漂移），**不**让 OpenViking 自己 watch URL 拉取。这个方向保留。具体写入策略：原候选 B′（首次 zip + 逐文件 `add_resource`）已证伪；**2026-05-31 架构复核重测确定改用 `content.write` 文件镜像配方**（A/M→`content.write`、D→`fs.rm`、R→`fs.mv`；**写后队列嵌入即可 find，reindex 仅为可选 abstract 增强**；读侧 `read/stat` 存在性过滤作防御）。开发曾报"删除后 find 仍返回已删 URI"，复核证明删除本身干净，该现象经受控复现复不出、疑似异步竞态而非确定性 bug，**不是删除失败**。B0.1 闸门通过，B1/B2 解冻。详见 [feasibility §6](./m11-openviking-repo-feasibility-research.md#6-架构复核重测--最终方向2026-05-31reviewer)。

### B0 spike 调研结论（2026-05-30，免环境调研已完成）

只读查阅已安装 `openviking==0.3.17` 的 HTTP API 与解析器，关键事实：

- **`POST /api/v1/resources`（`add_resource`）只接两种来源**：① `path` = 远程源（`http(s)://` / `git@` / `ssh://` / `git://` 仓库 URL）；② `temp_file_id` = 经 `POST /resources/temp_upload` 上传的**单个本地文件**。
- **HTTP server 明确拒绝 host 本地路径**：`server/local_input_guard.py:require_remote_resource_source` 对非远程源直接抛 `PermissionDeniedError`。→ **不能把 cloner 的本地裸仓/工作树路径直接指给 OpenViking。**
- **代码解析器原生吃 `.git` 与 `.zip`**：`parse/parsers/code/code.py`（`extensions=[".git", ".zip"]`）+ `parse/parsers/zip_parser.py`；`_extract_zip(zip_path, target_dir)`（code.py:513）**解压本地 zip**（带 Zip-Slip/symlink 防护）成代码树再索引。配 `parse/directory_scan.py` + `gitignore.py` 按 gitignore 扫描。→ **上传一个 zip 即可让 OpenViking 解包整库索引。**
- **`add_resource` 支持目录级参数**：`ignore_dirs / include / exclude / preserve_structure / directly_upload_media`。
- **`watch_interval`（分钟）= OpenViking 自带定时重索引**（仅对它能自己拉取的远程源有意义）；本方案**不使用**（见下）。
- **删除 = `DELETE /api/v1/fs?uri=&recursive=true`**（即现有 `delete_resource`），可一次清掉 `repos/<slug>/` 整棵子树。
- 读取侧 `find / search / grep / glob` 路由齐全（`server/routers/search.py`）。

### live PoC 结论（2026-05-31）：B′ 未通过

实测环境：
- CodeAsk `127.0.0.1:8000`，OpenViking `127.0.0.1:1933`，`/health` 返回 `healthy=true`，OpenViking `0.3.17`。
- `ov.conf` 仅配置 `server.temp_upload.default_mode = local`；源码默认上传上限 `shared_max_size_bytes = 512 MiB`，但本轮未做多档大文件实测。
- PoC 路径使用 `viking://resources/codeask/repos/m11-poc-*`，测试后已删除前缀。

关键事实：
- **单文件 `temp_upload + add_resource` 可索引、可 `grep/find` 召回**，同一路径重复 add 会替换旧内容，不堆重复。
- **但单文件 add 的节点形态不是“真实代码文件”**：`to=repos/<slug>/src/foo.py` 会创建目录 `src/foo.py/`，真实内容落到 `src/foo.py/foo.md`。读取 `src/foo.py` 会报 `Cannot read directory as file`；删除该“文件”必须 `recursive=true`。
- **zip 全量可解包建树**：`git archive` zip 上传到 `repos/<slug>/` 后，`.py/.ts` 落成真实文件节点（如 `src/zip_probe.py`），二进制样例被标为 `unsupported` 并跳过，其余成功。
- **zip 建树与后续逐文件 add 不能混用**：对 zip 解包出的 `src/zip_probe.py` 再执行单文件 `add_resource(to=.../src/zip_probe.py)` 返回 `CONFLICT path_busy`；先删再 add 虽可成功，但会把真实文件节点改成目录化形态 `src/zip_probe.py/zip_probe.md`，破坏读取契约。
- **`/api/v1/content/write` 不能创建新文件**（不存在路径返回 `NOT_FOUND`）。它能更新 zip 解包出的已有真实文件，并且 `grep` 能看到新内容，但 `wait=true` 曾返回 `DEADLINE_EXCEEDED`；只能作为 B0.1 候选，不能直接当完整增量方案。
- `wait:false + task_id` 可用，小文件约 1-2 秒后 task `completed` 且 grep 可见；生产 worker 更适合轮询 task/可见性，而不是长时间阻塞 `wait:true`。
- CodeAsk 侧 bare git 能直接 `archive`，`git diff --name-status` 能产出 `A/D/R100`，`merge-base --is-ancestor` / `cat-file -e` 可用于正常推进与历史改写判定。

硬结论：
- **D2 不通过**：zip 解包文件和单文件 add 后的 URI/节点形态不一致。
- **B′ 不可按原样开发**：不能再把“首次 zip + 后续逐文件 `add_resource`”写作默认方案。
- **B1/B2 继续冻结**：必须先完成 B0.1，确定新增/修改/删除文件的统一写入策略和读取映射。

### 原候选方案 B′：CodeAsk git-diff 文件级增量（+ 首次 zip 全量）——已证伪，不作为默认方案

CodeAsk 的 bare 克隆带完整历史，repo 同步任务已记 `source_hash`（上次同步的 commit sha）。

- **首次 / 重建**（无 last sha，或历史被 force-push 改写致 diff 失效）：`git --git-dir=<bare> archive --format=zip <ref>`（bare 仓直接产 zip，**无需检出工作树**）→ `temp_upload(<slug>.zip)` → `add_resource(temp_file_id, to=repo_uri(slug), exclude=二进制/大文件)`，OpenViking 解包建库。
- **日常更新**：`git --git-dir=<bare> diff --name-status <old_sha>..<new_sha>` →
  - `A/M` 文件 → `temp_upload(file)` + `add_resource(to=repos/<slug>/<path>)`（upsert）
  - `D` 文件 → `delete_resource(repos/<slug>/<path>)`
  - `R` 文件 → 删旧 + 加新
  - 成功后记 `new_sha` 为 last sha。
- **理论代价 ∝ 改动文件数，与仓库大小无关**——这是 B′ 的目标，但 live PoC 已证明 OpenViking 的 zip 节点与单文件 add 节点形态不一致，不能直接实现。
- git 源 + local_dir 源**统一**（两类 cloner 都落 `repo.bare_path`，含 local_dir 的 `_sync_plain_local_dir_snapshot`）；**零 OpenViking 凭据**（内容由 CodeAsk 推，OV 不去拉私有仓）；快照与 agent 所见一致。
- 全程复用 wiki 三件套 `temp_upload / add_resource / delete_resource`，client 只需在现有 `add_text_resource` 外加"上传文件 bytes / zip"的变体。

### 放弃的备选（决策留痕）
- **方案 A（给 OV 仓库 URL + `watch_interval` 自动拉）**：放弃。OV 拉自己的 ref，可能 ≠ CodeAsk 工作树/agent 所见 → 检索与阅读漂移；且只覆盖有可达 URL 的 git 源、要给 OV 配私有仓凭据。
- **方案 A′（给 URL 但 CodeAsk 钉 commit 驱动重索引）**：放弃。能拿到 OV 的 git 增量，但 git/local 两条码路 + 仍要给 OV 配凭据；B′ 的文件级增量已覆盖增量诉求且更统一、免凭据。
- **方案 B（每次整包 zip 重传）**：放弃。大仓库每次更新全量重传不可接受（负责人 2026-05-30 否决）。仅其"首次全量"部分被 B′ 采纳。

### 第二轮可行性调研结论（2026-05-31）

详见 [m11-openviking-repo-feasibility-research.md](./m11-openviking-repo-feasibility-research.md)。关键新增事实：

- 三个 fixture repo 已在真实 DB 中 ready，并已绑定到对应 feature：`opencode`、`anything-llm`、`openviking`。
- OpenViking `repos` 根目录仍为空；仓库管理 ready 不等于 repo 内容已进入 OpenViking。
- OpenViking remote git URL add 会返回 200 并识别 `file_count`，但最终目标树为空；日志大量 `Directory not found`，文件不可读、不可 find。
- zip add 的 `to` / `parent` 两种方式在第二轮均 120s 超时，目标下只有空目录，文件不可读、不可 find。
- 单文件 `add_resource` 仍会目录化 `src/foo.py/`，不符合 repo path 契约。
- `fs.mkdir + content.write(mode=create)` 能创建真实文件节点，`content/read` 可读；但 `wait=true` 90s 超时，`find` 不召回 marker。
- `content/reindex` 需要 ROOT/ADMIN，当前 CodeAsk trusted/user client 403。
- 在独立临时实例 `127.0.0.1:1944`（`auth_mode=api_key` + root key）追加验证：`content.write(create|replace) + content/reindex` 可让新增文件 `src/probe.py` 被 `find` 命中文件本身，score 约 `0.80`；但 `DELETE /fs` 删除并 reindex 后，`grep` 清零、`content/read` 404，`find` 仍返回已删 URI（abstract 为空）。

硬结论：

- **当前没有可签收的 OpenViking repo semantic mirror 写入方案**：root/admin reindex 是候选，但删除残留未解决。
- **不能把 HTTP 200 或空目录创建视为同步成功**；repo sync job 的完成判据必须至少包含：真实文件树可读 + `find/search` 可召回 + 删除后旧 token 不召回。
- **近期可靠主链路应是 CodeAsk 原生 repo 工具**（worktree/read/grep/glob）+ OpenViking 继续服务 wiki/report 语义召回。

### B0.1 待决策项（第二轮后重定义）

> 完整可交接执行的逐项清单见 **[m11-b0-research-checklist.md](./m11-b0-research-checklist.md)**（含真实 endpoint/参数、通过判据、回填格式、决策矩阵）。下列为其中三条最关键概要：
1. **删除残留**：先定位删除后 `find` 仍返回已删 URI 的原因；没有删除清理保证，repo semantic mirror 不能签收。
2. **权限策略**：若删除残留可解，再给 CodeAsk 配置 OpenViking root/admin key，使 `content/reindex` 可用；没有 reindex 权限，`content.write` 只能证明可读，不能证明可检索。
3. **file mirror 策略**：若 `content.write + reindex + delete-clean` 成立，A/M/D/R 可走 `git diff` + `content.write`/`fs.rm`，首次/重建可逐文件 mirror，避免 zip。
4. **完成判据**：repo sync job 必须等待 read + find 双通过；`find` 命中的 URI 必须仍可读、abstract/snippet 非空并对应当前内容。若 find 超时/失败或返回已删 URI，不能标 indexed。
5. **OpenViking bug/上游适配**：zip/remote git 返回 success 但树为空，以及 reindex 后删除残留的问题需要复现给 OpenViking 或本地适配，不能在 CodeAsk 侧掩盖。

**B0.1 闸门**：确认一种完整策略能覆盖 A/M/D/R、新增文件、读取路径、语义检索和删除不残留；回写设计 §2.1/§4 后，才开 B1/B2。

---

## 2. 任务拆分

> spike 归架构；B1–B3 实现归开发 + 架构 review/验收。

### B0 —— spike：确认原 B′ 可落地（架构，闸门）
- 免环境调研**已完成**（见 §1：API 契约 + 候选 B′ + 放弃 A/A′/B）。
- live PoC **已完成且未通过**：单文件 add 可检索、zip 全量可解包，但 zip 与逐文件 add 不能混用。
- 结论：B′ 不能直接进入开发；不得按“首次 zip + 后续逐文件 add_resource”实现。

### B0.1 —— spike：重新确定写入策略（架构，闸门）✅ 已通过（2026-05-31 复核）
- 第二轮 live PoC：remote git / zip / 单文件 `add_resource` 均不可用（已否决）。
- **架构复核重测定案**（[feasibility §6](./m11-openviking-repo-feasibility-research.md#6-架构复核重测--最终方向2026-05-31reviewer)）：选 **`content.write` 文件镜像**为主路径——写后队列嵌入即可 find，**reindex（补 abstract）与读侧存在性过滤均为可选增强/防御，非主路径必需**。"删除残留"经受控复现复不出、疑似异步竞态而非确定性 bug，删除本身干净，闸门通过。
- repo URI 对外契约：agent/UI 看到的必须是仓库相对路径；用 `content.write` 直接写真实文件节点，**不会**产生 `src/foo.py/foo.md`（那是 `add_resource` 的形态，本方案不用）。
- 负责人决策：① 配 root/admin key 启用 reindex；② 吞吐慢可接受、靠现有可观测面（status/sync_jobs/events/metrics）暴露异步进度，job 长期 `running` 是正常态；③ embedder 将可换（默认 OV 自带，三方走自定义配置），不写死 bge-m3。
- 落地物：更新 `design/openviking-integration.md` §2.1/§4 为 content.write 配方（随 B2 实现一并改）。

### B1 —— cloner 接入入队
- `cloner.py` 仓库 ready / refresh 成功后，除现有 `repo_synced` 事件外，`enqueue(source_type="repo", source_id=<repo_id>, feature_slug=…, viking_uri=repo_uri(repo_slug), source_hash=<当前 HEAD commit sha>)`。
- 放宽 `sync.py` / `hooks.py` 的 `source_type` `Literal` 纳入 `"repo"`。
- 去重语义沿用 M5：job 只表示"该 repo 脏了"，worker 跑时取最新 HEAD；`(source_type, source_id)` 非终态唯一约束对 repo 同样成立。
- 注意 commit 边界：沿用 M5 §"commit 后再 enqueue"，避免孤儿 job。
- **记录 last-synced sha**：worker 需要"上次同步到的 commit"来算 diff。沿用 `source_hash` 语义——成功后把本次 HEAD sha 落库，下次 worker 以它为 diff 基线。

### B2 —— 引擎 + client 的 repo 分派（B0.1 已定稿，配方见 feasibility §6.2）
- `run_pending_jobs` 增加 `repo` 分支，按 `git diff --name-status <last>..<HEAD>` 映射：
  - `A`/`M` → `fs.mkdir(parent, 幂等)` + `content.write(uri=repos/<slug>/<rel>, mode=create|replace)`
  - `D` → `fs.rm(uri, recursive=false)`（删除自清理，无需事后 reindex 该文件）
  - `R` → `fs.mv(from_uri, to_uri)`（重命名干净，旧 URI 不残留）
  - **禁止** `add_resource`（目录化）/ zip（不稳定）/ 逐文件 reindex（409 树锁）。
- 写后内容靠队列嵌入即可被 find 召回（**不依赖 reindex**）。**可选增强**：一批写完后做**子树** `content/reindex(uri=repos/<slug>/, mode=semantic_and_vectors)` 生成 abstract / 提升摘要级召回；这一步才需 root/admin key + `X-OpenViking-Account/User` 头。先按"无 reindex"跑通，确认 abstract 对 repo 召回确有价值再启用。
- `OpenVikingClient` 新增：`write_content` / `mkdir` / `mv` / `read`(/`stat`)；`reindex`（带 root 凭据与租户头，启用 reindex 时才需）；`delete_resource` 复用。
- **读侧护栏（防御性）**：`openviking_find/search` wrapper 丢弃 `fs.stat`/`content/read`→404 的命中。它本就要把 find 命中映射到真实仓库读取（代码经 worktree 读），零额外成本；顺带兜 feasibility §6.1.3 那种罕见竞态孤儿及任何 fs↔向量漂移，**非堵确定性 bug**。两阶段完成判据：`read`/`stat` 存在（mirrored/running）→ 目标文件 find 可召回且命中 URI 仍可 read（indexed）；删除文件 `read`→404。**绝不**用"find 不再返回旧 URI"判定删除。
- 失败 / 重试 / cancelled 走既有 `mark_failed`（M8）。embedding 慢导致 find 暂不可见时，job 保持 `running` 慢慢推进（负责人决策②），不算失败。
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
- `src/codeask/rag/openviking/sync.py`：`source_type` Literal 纳入 repo；`run_pending_jobs` repo 分支（写入策略待 B0.1 定稿）；last sha 落库；backfill 枚举 repo（B1/B2/B3）。
- `src/codeask/rag/openviking/hooks.py`：`source_type` Literal 纳入 repo（B1）。
- `src/codeask/rag/openviking/config.py`：**启用 reindex 时**才在生成的 `ov.conf` 配 root/admin key（决策①）；**不写死 embedder**——保留 ollama/bge-m3 为可换默认，后续切 OV 自带 embedding（决策③）。
- `src/codeask/rag/openviking/client.py`：新增 `write_content` / `mkdir` / `mv` / `read`(/`stat`)；`reindex`（带 root 凭据 + 租户头，启用 reindex 时才用）；`find/search` wrapper 加 `read/stat` 存在性过滤；复用 `delete_resource`（B2）。
- `src/codeask/rag/openviking/uri.py`：`repo_uri` 复活为真实调用方；repo uri = `repos/<slug>/<仓库相对路径>`（B2）。
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
- [x] **B0** live PoC 已跑：单文件 add 可召回、zip 可解包，但 zip 与逐文件 add 不能混用；原 B′ 判定未通过
- [x] **B0.1 第二轮调研** 已跑：三 fixture repo ready + 绑定；remote git / zip / 单文件 add 否决
- [x] **B0.2 正向验证** 已跑：`content.write(create) + content/reindex` 可让新增文件按 repo path 被 read/grep/find
- [x] **B0.2 删除残留** ✅ 复核澄清（2026-05-31）：删除本身干净（`fs.rm` 后未 reindex 即不召回、`read`→404）；所谓残留经受控复现复不出、疑似异步竞态而非确定性 bug（读侧存在性过滤作防御保险）。**闸门通过，B1/B2 解冻**
- [ ] **B1** cloner ready/refresh 成功后入队 `source_type="repo"` 任务（带 HEAD sha），`source_type` Literal 已纳入 repo，commit 后入队无孤儿
- [ ] **B1** 成功后落库 last-synced sha 作下次 diff 基线；`(source_type, source_id)` 非终态唯一约束对 repo 成立
- [ ] **B2** 按 feasibility §6.2 配方实现 repo 分派：A/M→`content.write`、D→`fs.rm`、R→`fs.mv`；写后队列嵌入即可 find（不依赖 reindex）；读侧 `read/stat` 存在性过滤；两阶段完成判据（mirrored=存在性 / indexed=find 可召回且命中可 read），不用"find 不返回旧 URI"判删除
- [ ] **B2（可选增强）** 若确认 abstract 对 repo 召回有价值：子树 `semantic_and_vectors` reindex；此时才在 ov.conf 配 root/admin key、client reindex 调用带 root 凭据 + 租户头
- [ ] **B2** repo 全局删除 / slug 重命名触发 tombstone：`delete_resource(repos/<slug>/, recursive=True)` 清整棵子树
- [ ] **B2** repo 失败走 `mark_failed` 收敛，出现在事件流与 m10 卡片
- [ ] **B3** 启动 backfill / 定时 sweep 纳入已 ready 的 repo；`source_hash` 未变 → enqueued=0，变更 → 重新入队
- [ ] **B4** repo 类同步任务在卡片显示可读 `display_name`，不出现 `repo · <hex-id>`；其余 UX 复用 m10，零新前端
- [ ] live e2e：发布/刷新一个 repo → OpenViking `find` 能召回该 repo 的代码片段
- [ ] 后端 pytest / 前端 vitest / e2e 全绿，ruff / pyright / tsc / eslint clean
