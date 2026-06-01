# M11 — OpenViking 代码仓同步可实施性再调研

> 版本：v1.0.5
> 状态：**方向已定（2026-05-31 架构复核重测推翻"删除残留"冻结结论 → M11-B 可行）**；开发第二轮调研结论见 §0–§5（保留原始证据），架构复核更正与最终方向见 **§6**。
> 关联：[m11-repo-openviking-sync](./m11-repo-openviking-sync.md) · [m11-b0-research-checklist](./m11-b0-research-checklist.md) · [openviking-integration 设计](../design/openviking-integration.md)
> 背景：负责人要求抛开原 zip 方案，重新全面调研 git repo / local code repo 进入 OpenViking 的可实施方向。
>
> ⚠️ **读这份文档先看 §6**：§0–§5 是开发第二轮的结论（曾据此冻结 M11-B），其核心阻塞"删除后 find 仍返回已删 URI"在 §6 的架构复核重测中被推翻——删除本身干净，该现象经受控复现复不出、疑似异步竞态而非确定性 bug。M11-B 因此**解冻、方向已定**。

---

## 0. 结论摘要

原 B′（首次 zip + 后续逐文件 `add_resource`）已经证伪；第二轮进一步确认：**不能把任何一个 OpenViking 写接口的 HTTP 200 当作“仓库已进入可检索语义索引”。**

当前可用能力分层如下：

| 能力 | 实测结论 | 是否可作为 M11 主方案 |
|---|---|---|
| CodeAsk 仓库管理 git URL clone | 三个 fixture repo 均 `ready` | 是，作为数据源 |
| feature-repo 绑定 | 三个 fixture 已绑定 | 是，作为 scope 元数据 |
| OpenViking `temp_upload + add_resource` 单文件 | 可返回 success，但把 `src/foo.py` 建成目录 `src/foo.py/`，不是文件 | 否，除非接受路径适配 |
| OpenViking zip add | 当前环境返回 success/timeout 后只留下空目录；文件不可读、不可 find | 否 |
| OpenViking remote git URL add | 接受 URL 并识别 `file_count`，但最终目标树为空；日志出现大量 `Directory not found` | 否 |
| OpenViking `fs.mkdir + content.write(mode=create)` | 能创建真实文件节点，`content/read` 可读 | 只能作为文件树写入候选 |
| `content.write(wait=true)` / write 后 find | `wait=true` 90s 超时，`find` 未召回 marker | 不能证明可检索 |
| `content/reindex` | 当前 trusted/user 身份 403，需要 root/admin role | 当前 CodeAsk client 不可用 |
| 临时 root/admin `content.write + content/reindex` | 新增文件可 read/grep/find；但删除后 `find` 仍返回已删 URI（空 abstract） | 仍不能签收为完整 repo semantic mirror |

推荐方向：**M11 先不要做“把完整代码仓交给 OpenViking 语义索引”的实现承诺。**可进入开发的最小可靠方案应拆成两层：

1. **确定性代码能力继续走 CodeAsk 原生 repo 工具**：`prepare_worktree/read/grep/glob` 已能精确读真实仓库快照，这是当前可靠主链路。
2. **OpenViking repo 语义索引另起 M11-B2 spike/适配层**：`content.write + root/admin reindex` 已证明“新增文件可 read/find”，但尚未证明“删除后旧 URI 不召回”。只有删除残留解决后，才接入 `openviking_sync_jobs(source_type=repo)`。

---

## 1. 测试基线

### 1.1 清理与重建

按负责人要求，已清理仓库管理残留：

- `repos`：从 51 清到 0
- `feature_repos`：从 39 清到 0
- `session_repo_bindings`：保持 0
- repo 相关 dashboard events：从 1770 清到 0
- `~/.codeask/repos/*`：清空

随后负责人已重新加入三条 repo；本轮补齐 feature-repo 绑定。

### 1.2 当前三特性 / 三仓库状态

真实 DB 状态：

| feature | repo | source | repo status |
|---|---|---|---|
| `opencode` | OpenCode | git | ready |
| `anything-llm` | AnythingLLM | git | ready |
| `openviking` | OpenViking | git | ready |

仓库 HEAD 由 CodeAsk bare repo 给出：

| repo | bare size | HEAD |
|---|---:|---|
| OpenCode | 280 MiB | `331bed246` |
| AnythingLLM | 60 MiB | `c0e94148` |
| OpenViking | 135 MiB | `05540114` |

### 1.3 运行环境

- CodeAsk：`127.0.0.1:8000`
- OpenViking：`127.0.0.1:1933`
- OpenViking 进程稳定：`openviking-server --config /home/hzh/.codeask/openviking/ov.conf`
- OpenViking auth：`trusted`
- CodeAsk 当前 OpenViking HTTP client header：
  - `X-OpenViking-Account: codeask`
  - `X-OpenViking-User: codeask`
  - `X-OpenViking-Agent: codeask`

补充发现：直接执行 `.venv/bin/codeask` 时，如果 `PATH` 没有 `.venv/bin`，`openviking_bin="openviking-server"` 会解析失败；用 `uv run codeask` 或显式 `CODEASK_OPENVIKING_BIN=/home/hzh/workspace/CodeAsk/.venv/bin/openviking-server` 可避免。

---

## 2. 候选方案矩阵

### 2.1 方案 A：让 OpenViking 直接拉 remote git URL

实测请求：

```json
{
  "path": "https://github.com/volcengine/OpenViking.git",
  "to": "viking://resources/codeask/m11-feasibility/remote-git-openviking",
  "wait": false,
  "strict": false,
  "include": "README*",
  "exclude": ".git/**",
  "preserve_structure": true
}
```

返回：

- HTTP 200
- `status: success`
- `meta.file_count: 2461`
- `meta.repo_name: volcengine/OpenViking`
- `task_id: 1af0119f-49ba-4e19-8cac-21ef86d84abf`

复查：

- `fs/tree(remote-git-openviking, level_limit=20, node_limit=10000)`：0 items
- `content/read(.../README.md)`：404
- `content/read(.../openviking/server/app.py)`：404
- `find("OpenViking")`：0 results
- server log 出现大量：
  - `Failed to list directory viking://resources/codeask/m11-feasibility/remote-git-openviking/...: Directory not found`

判断：

- OpenViking 的 GitAccessor 能识别 remote git URL，也会进入后续语义 DAG。
- 但当前版本在本环境没有形成可读文件树；HTTP 200 不能作为成功判据。
- 即使修通，也仍有产品边界：私有仓凭据、commit pinning、CodeAsk bare repo 与 OpenViking 自拉 repo 漂移。

结论：**不作为主方案。**可作为未来“公开仓一键探索”能力，不适合作为 CodeAsk 的同步真相源。

### 2.2 方案 B：CodeAsk `git archive` zip 全量上传

第二轮实测两个变体：

- `to + wait=true`
- `parent + create_parent + wait=true`

结果：

| 变体 | OpenViking 返回 | tree | read | find |
|---|---|---|---|---|
| `to=viking://.../to-wait` | 504 `DEADLINE_EXCEEDED` after 120s | 空 | `src/a.py` 404 | 0 |
| `parent=viking://.../m11-feasibility-zip2` | 504 `DEADLINE_EXCEEDED` after 120s | 只有空目录 `repo.zip/` | `repo.zip/src/b.py` 404 | 0 |

与第一轮旧 PoC 的差异：

- 第一轮曾观察到 zip 可解包真实文件。
- 第二轮在真实运行栈、`wait=true`、`to/parent` 双变体下均未形成文件树。
- 因此不能把 zip 视为稳定 API。至少需要 OpenViking 侧修复/解释 task 与 persist 行为后再评估。

结论：**不作为当前主方案。**

### 2.3 方案 C：单文件 `temp_upload + add_resource`

实测：

```json
{
  "temp_file_id": "...",
  "to": "viking://resources/codeask/m11-feasibility/single/src/probe.py",
  "wait": false,
  "strict": false,
  "source_name": "probe.py"
}
```

结果：

- HTTP 200 `status=success`
- tree：
  - `single/src/`
  - `single/src/probe.py/`，注意是目录
- `content/read(single/src/probe.py)`：400 `Cannot read directory as file`
- `find("M11_SINGLE_MARKER")`：0

判断：

- 单文件 add 不产生真实 `probe.py` 文件节点。
- 路径语义和 repo 工具需要的“相对文件路径”冲突。

结论：**不能直接用于 repo path 同步。**除非后续决定在 CodeAsk 读取层显式适配 `src/foo.py/foo.md` 这种 OpenViking 内部结构，但这会让用户和 agent 看到两套路径，不建议。

### 2.4 方案 D：`fs.mkdir + content.write(mode=create)`

实测：

```json
{
  "uri": "viking://resources/codeask/m11-feasibility/write/src/write_probe.py",
  "content": "def m11_write_marker(): ...",
  "mode": "create",
  "wait": false
}
```

结果：

- HTTP 200
- tree：
  - `write/src/`
  - `write/src/write_probe.py`，真实文件，`isDir=false`
- `content/read(write/src/write_probe.py)`：200，内容正确
- `find("M11_WRITE_MARKER")`：0

再测 `wait=true`：

- `content.write(wait=true, timeout=90)`：504 `DEADLINE_EXCEEDED`
- 文件仍真实写入且可 `content/read`
- `find("M11_WAIT_MARKER")`：0

判断：

- 这是目前唯一稳定创建真实文件节点的路径。
- 但它只证明了 L2 文件树，不证明语义索引/向量可用。
- `content/reindex` 理论可补索引，但当前 CodeAsk trusted/user 身份调用会 403。

结论：**可作为“OpenViking 文件树镜像”的候选底座，但不能单独作为 RAG 语义同步方案。**

### 2.5 方案 E：`content/reindex`

实测：

- `X-OpenViking-Agent: codeask/admin/root` 均返回 403
- 错误：`Requires role: root, admin`

源码确认：

- `content/reindex` 使用 `require_role(Role.ROOT, Role.ADMIN)`
- trusted 模式下，仅有 account/user header 时默认 role 是 `USER`
- 当前 CodeAsk client 没有 root API key / APIKeyManager user role 授权路径

结论：

- 如果 M11 选择 `content.write` 作为写树方式，需要新增 OpenViking admin/root 调用能力，或证明 write 自带队列能完成检索。
- 当前不能假设 CodeAsk 可以调用 reindex。

#### 2.5.1 追加验证：临时 root/admin reindex（2026-05-31）

为确认问题是否只是权限阻塞，另起独立 OpenViking 临时实例：

- 配置：`.tmp/m11-root-reindex/ov.conf`
- 端口：`127.0.0.1:1944`
- auth：`server.auth_mode="api_key"` + `server.root_api_key="m11-root-key"`
- workspace：`.tmp/m11-root-reindex/workspace`
- 不触碰 `127.0.0.1:1933` 的真实 CodeAsk OpenViking 数据。

实测步骤与结果：

| 步骤 | 结果 |
|---|---|
| `fs.mkdir(viking://resources/codeask/repos/root-reindex/src)` | 200 |
| `content.write(mode=create, wait=false)` 写 `src/probe.py` | 返回 `semantic_status=queued`；约 3 秒后 `fs/tree` 有真实文件节点，`content/read` 可读 |
| `search/grep` marker | 命中 `src/probe.py` |
| `content/reindex(root-reindex, vectors_only, wait=true)` | 200，样例中一次 `duration_ms=6795`，一次 `duration_ms=68114`，小目录也可能 50-70 秒 |
| reindex 后 `search/find("M11_ROOT_REINDEX_MARKER_V3")` | 命中文件本身 `src/probe.py`，score 约 `0.80`，abstract 为文件内容 |
| `find("M11_ROOT_REINDEX_MARKER_V2")` | 仍返回同一文件，但 abstract 已是 V3 内容；说明语义 find 不是严格 token 判等，不能用“旧 query 有结果”直接判定旧内容残留 |
| `DELETE /api/v1/fs?...probe.py&recursive=false` | 文件实际删除；`content/read` 404，`grep` 0；但返回 `estimated_deleted_count=0`，返回值不可作为删除成功判据 |
| 删除后 reindex | 200，`scanned_records=2/rebuilt_records=4` |
| 删除后 `grep("M11_ROOT_REINDEX_MARKER_V3")` | 0，字面索引干净 |
| 删除后 `find("M11_ROOT_REINDEX_MARKER_V3")` | 仍返回已删 URI `src/probe.py`，abstract 为空，同时返回目录 overview |

结论：

- `content.write(create|replace) + root/admin content/reindex` 是目前唯一证明“真实 repo path 文件节点 + read + grep + find 正向召回”的候选路线。
- 但它**仍未满足删除不残留**：删除并 reindex 后，`find` 仍可能返回已删文件 URI，只是 abstract 为空。
- 生产完成判据不能只看 `find.total > 0` 或 reindex `status=completed`。至少要验证命中的 URI 仍可 `content/read`，且命中 abstract/snippet 非空并包含当前内容。
- 如果 OpenViking 不能提供向量删除/重建清理保证，repo semantic mirror 仍应冻结，继续走 CodeAsk 原生 repo 工具。

### 2.6 方案 F：继续使用 CodeAsk 原生 repo 工具，不强行进 OpenViking

现有能力：

- CodeAsk repo cloner 已把三仓库拉成 ready bare repo。
- opencode / native tools 可用 worktree + grep/read/glob 精确读取代码。
- feature-repo 绑定已存在，可作为 scope source。

优点：

- 和 agent 所见快照一致。
- 对 git URL / local_dir 都统一。
- 不依赖 OpenViking 对代码仓的 ingest 细节。
- 可立即支撑“读源码回答问题”的可靠路径。

缺点：

- 没有 OpenViking 语义召回代码能力。
- 需要在 agent 编排上把“语义 wiki/report + 精确代码工具”组合好。

结论：

- 这是当前可靠主链路。
- OpenViking repo RAG 作为增强能力继续 spike，不应阻塞已可靠的代码读取能力。

---

## 3. 推荐路线

### 3.1 近期可交付：M11 拆成两层

**M11-A：仓库绑定与原生代码检索闭环**

- 保持 CodeAsk repo cloner / feature-repo 绑定为事实源。
- agent 检索阶段：
  - wiki/report 继续优先走 OpenViking 语义召回。
  - code repo 使用 `prepare_worktree + grep/read/glob`，必要时由 LLM 根据 query 选择路径。
- dashboard / sync jobs 不声明 repo 已进入 OpenViking 语义索引。

**M11-B：OpenViking repo semantic mirror（继续 spike）**

进入实现前必须满足四条硬门槛：

1. 写入后 `fs/tree` 能看到真实文件节点。
2. `content/read` 能按仓库相对路径读取。
3. `find/search` 能召回新内容，且命中的 URI 可读、abstract/snippet 非空并对应当前文件内容。
4. 删除/重命名后旧 URI 不再出现在 `find/search` 结果；只做到 `grep` 清零不够。

### 3.2 若必须继续探索 OpenViking repo semantic mirror

优先探索顺序：

1. **删除残留定位**：在 root/admin reindex 可用前提下，定位删除后 `find` 仍返回已删 URI 的原因，确认是否有向量删除 API、全量 rebuild 模式或账号级 purge 能清理残留。
2. **root/admin 接入策略**：若删除残留可解，再为 CodeAsk 的 OpenViking client 配置 root_api_key 或创建 admin user key；trusted/user header 不能调用 `content/reindex`。
3. **OpenViking issue/补丁方向**：复现 zip/remote git “返回 success 但文件树为空”的问题，定位是否是 lifecycle lock / temp copy / semantic queue 的 bug。
4. **统一 file mirror**：若 reindex + 删除清理可行，则 CodeAsk 用 `git diff` 驱动：
   - A/M：`fs.mkdir` parent + `content.write(create|replace)`
   - D：`fs.rm`
   - R：删旧 + 写新
   - 成功判据：read + find 双通过；删除后 `find` 不返回旧 URI
5. **fallback rebuild**：如果增量失败，整棵 `repos/<slug>/` 删除后用 `content.write` 逐文件重建，而不是 zip；但必须先证明全树删除后向量也清干净。

### 3.3 不建议继续投入的方向

- **zip 首次全量**：当前不稳定，且与单文件 add 形态不一致。
- **单文件 add_resource**：目录化文件路径不符合 repo path 契约。
- **OpenViking 自拉 remote git URL**：当前不落真实文件树，且与 CodeAsk 快照一致性矛盾。

---

## 4. 本轮对产品文档的影响

需要同步修正：

- `m11-repo-openviking-sync.md`：B0.1 不再只是“修补 B′”，而是重新选型；`content.write + root/admin reindex` 是候选路线，但删除后 find 残留未解。
- `m11-b0-research-checklist.md`：补第二轮 live PoC 与 root/admin reindex 追加验证，标明 zip/remote/content.write 的真实状态。
- `openviking-integration.md`：设计层的 `repo → OpenViking` 只能保留为目标，不应写成已证实实现路径。
- acceptance checklist：不能勾选“repo 内容同步进 OpenViking / repo RAG 召回”。

---

## 5. 后续验证清单

- [x] 在带 root/admin reindex 权限的 OpenViking 配置下，复测 `content.write + reindex + find`：新增文件正向召回成立。
- [ ] 定位删除后 `find` 仍返回已删 URI 的残留问题；修复前 repo semantic mirror 不进入实现。
- [ ] 最小 repo 逐文件 mirror：10 文件以内，A/M/D/R 全覆盖，验证 read/find/delete，尤其删除后 find 不返回旧 URI。
- [ ] 大 repo 抽样 mirror：从三 fixture repo 各取 100 个文本文件，测耗时、失败率、队列延迟。
- [ ] 删除 feature/repo 时同步清理 OpenViking `features/*` 和 `repos/*` 旧资源，避免 UI 删除后索引残留。
- [ ] 将 repo sync job 的完成判据定义为“文件树写入成功 + 可检索成功”，不能只看 HTTP 200。

---

## 6. 架构复核重测 + 最终方向（2026-05-31，reviewer）

带着质疑在真实 OpenViking 上重跑了 §2.5/§2.5.1 的关键结论。**§0–§5 用来冻结 M11-B 的核心阻塞——"删除文件并 reindex 后 find 仍返回已删 URI"——经受控复现证明：删除本身干净，该现象不是 OpenViking 的确定性行为（见 §6.1.3）。M11-B 解冻、方向已定。**

测试用两台实例：root/admin `:1944`（带 reindex 权限）+ 真实 trusted `:1933`（throwaway 前缀，已清理）。每步抓原始返回。

### 6.1 复核重测：硬结论（带证据）

1. **`content.write` 建真实文件节点，路径保真。** `fs.mkdir(parent)` + `content.write(mode=create|replace, uri=<repo 相对路径>)` 落 `src/probe.py`（`isDir=false`，`content/read` 200）。§2.3 的目录化 `src/foo.py/foo.md` 只是 `add_resource` 的坑，本方案根本不用 `add_resource`。

2. **删除本身干净（自清理）。** `fs.rm(recursive=false)` 后**未 reindex 前**，find 立刻不返回该文件、`content/read`→404。trusted `:1933` 与 root `:1944` 均如此。

3. **§2.5.1 的"删除残留"不是删除失败，也不是 reindex 的确定性行为——疑似异步竞态，受控复现复不出。**
   - 早期两次（probe1/probe2，reindex 仅 8–31s、且**未** drain 异步队列）确实抓到：删文件 → find 干净 → 一次成功的子树 reindex 后，已删文件以 `abstract:""`、score 与删前**逐字节相同**（0.635 / 0.531）、`content/read`→404 重新出现在 find 里——即向量索引留了孤儿。证据真实。
   - **但随后两次受控复现（每步用 `system/wait` drain 队列、reindex 175–216s）均无法重现**：删除后无论是否有存活兄弟文件、无论 `vectors_only` 还是 `semantic_and_vectors`，reindex 后 `find` 都不再返回已删文件（命中=False、`read`→404）。
   - 结论修正：**幽灵不是"reindex 必然复活已删文件"**（此前我据 probe1/2 下的强断言过度了，开发复现不出来是对的）。两次出现与复不出的唯一差别是**删除前后异步嵌入/语义队列是否已 drain**——最可能是 **in-flight 嵌入任务与删除的竞态**：任务在删除后才完成、把向量写回，被随后的 reindex/find 暴露；队列 settle 后即不出现。具体触发条件未进一步钉死（负责人指示先不深究）。
   - 影响：孤儿从"确定性阻塞"降级为"罕见瞬态竞态"，读侧存在性过滤因此是**廉价防御保险**，不是堵确定性 bug 的必备护栏（见 §6.2）。

4. **"空 abstract" 不是墓碑信号。** 刚写入、embedding 已入队的**活文件**，在子树 reindex 生成 abstract 之前，find 里 `abstract` 同样为空（实测 `gamma.py` score 0.542、abstract 空、`content/read`→200）。唯一可靠判据是 **`content/read`/`fs.stat` 存在性**。开发提议的完成/删除判据"find 不再返回 URI"两头都错（活文件可能 abstract 空；幽灵可能仍被 find 返回）。

5. **`fs.mv` 处理 git `R`（重命名）干净。** `beta.py`→`beta_renamed.py`：reindex 后新路径可召回、旧路径 `content/read`→404 且不在 find。无需"删旧+加新"。

6. **逐文件 reindex 不可行**（`reindex(file_uri)` 返回 `409 CONFLICT Failed to acquire tree lock`）。reindex 只能子树级，且需 **root/admin role + `X-OpenViking-Account/User` 头**（trusted client 调不了；ROOT key 也必须带租户头，否则 `INVALID_ARGUMENT`）。

7. **真正瓶颈是 embedding 吞吐，不是写/删语义。** clean 实例上文件无需 reindex 即可被 content 相似度 find 到（0.542）；loaded `:1933` 上同样写入 120s+ 仍 find 不到，因为 `:1933` 日志持续 `embedding slow call … duration_ms=5000–20000`（ollama bge-m3，`max_concurrent=1`），`system/wait` 反复 `DEADLINE_EXCEEDED`。文件**终会**被索引，纯延迟问题。

### 6.2 最终方向（M11-B 可落地配方）

弃用 zip / `add_resource` / 逐文件 reindex，改为 **git diff 驱动的 content.write 镜像**：

| git diff | 动作 |
|---|---|
| `A` / `M` | `fs.mkdir(parent)` + `content.write(mode=create\|replace)` 到 repo 相对 URI |
| `D` | `fs.rm(recursive=false)`（自清理） |
| `R` | `fs.mv(from, to)`（干净迁移，含向量/abstract） |

- **索引**：内容靠 embedding 队列自动入向量（基础 content 召回即可用，**不依赖 reindex**——write 后队列嵌入完即可 find，实测 score 0.83/0.74）；子树 `content/reindex(semantic_and_vectors)` **仅用于补 abstract / 摘要级召回，是可选增强**，不是建索引必经步骤。
- **读侧护栏（防御性，非必备）**：CodeAsk 的 `openviking_find/search` wrapper **丢弃任何 `fs.stat`/`content/read`→404 的命中**。它本就要把 find 命中映射到真实仓库读取（代码经 worktree 读），存在性检查零额外成本；顺带兜住 §6.1.3 那种罕见异步竞态孤儿及任何 fs↔向量漂移。**不是为了堵一个确定性 bug**。
- **完成判据**：触达文件 `read`/`stat` 存在性（mirrored）→ 目标文件 `find` 可召回且命中 URI 仍可 `read`（indexed）；删除文件 `read`→404。**绝不**用"find 不再返回旧 URI"做删除判据（既因竞态孤儿可能短暂存在，也因活文件 abstract 可能为空）。

### 6.3 负责人 2026-05-31 决策（据此实现）

1. **需要 reindex 就配 root/admin。** M11-B 走 reindex 路线：CodeAsk 生成的 `ov.conf` 带 root/admin key（改 `rag/openviking/config.py`：auth_mode + root_api_key），client 调 reindex 时带 root key + account/user 头（改 `client.py`）。
2. **吞吐慢可接受（测试环境）。** 只要异步在跑、管理员界面可查、指标监控能看到、任务慢慢推进即可。repo sync job 允许长时间停在 `running`，靠现有 m8/m10 可观测面暴露进度：`/admin/openviking/status`（queue + `metrics_5min`）、`/admin/openviking/sync_jobs`（pending/running/indexed/failed/cancelled）、`/admin/openviking/events`、OpenViking `/api/v1/metrics`、`/api/v1/tasks{,/{id}}`。**完成判据=存在性 + find 可见，期间 `running` 是正常态**，不是卡死。repo 接入只需 B1/B2 入队 + B4 `display_name`，复用 m10 卡片。
3. **embedder 将可换。** 后续默认改用 OpenViking 自带 embedding 模型，ollama/三方走自定义配置。设计**不得写死 ollama bge-m3 假设**；`max_concurrent`/embedder 是 config 不是设计约束；§6.1.7 的 slow call 是当前环境现象，不是方案缺陷，**不阻塞 M11-B**。

### 6.4 与 §3.3"不建议"的对账

§3.3 仍成立：zip 首次全量、单文件 `add_resource`、OV 自拉 remote git 三条继续否决。**新增可行项**：`content.write + fs.rm/fs.mv`（reindex 与读侧存在性过滤为可选增强/防御）——这是 §3.1 "M11-B" 进入实现前四条硬门槛的达成路径。门槛 4"删除后旧 URI 不召回"**底层删除本就满足**（删后 find 立刻干净）；读侧存在性过滤只是兜罕见竞态孤儿的额外保险。

### 6.5 开发落地记录（2026-06-01，⚠️ 已校正：未落地）

> **2026-06-01 架构校正**：repo→OpenViking 已被负责人延后，M11 重定为 OpenViking HTTP→SDK 迁移（见 [m11-openviking-sdk-migration](./m11-openviking-sdk-migration.md)）。下列为当时草稿，**未合入当前代码库 / 已回退**——核对当前代码：`sync.py` 仅 `wiki_feature`、`client.py` 无 `write_content`/`read_content`、search 已回 SQL、`RepoCloner` 不入 repo sync 队列。保留作后续 repo 里程碑参考。

曾起草的 **B2.1 全量镜像版** 方案（未落地）：

- clone ready/refresh 后自动 enqueue `source_type="repo"`。
- 启动 backfill / scheduled sweep 纳入 ready 且绑定 feature 的 repo，按 HEAD sha 幂等。
- repo worker 处理时清空 `repos/<repo_id>/` 子树，再按当前 HEAD `git ls-tree -r` 全量写入文本文件到 `content.write(mode=create, wait=false)`；跳过 gitlink/submodule、二进制、超大文件、常见依赖目录和 OpenViking 当前拒绝的无扩展名文件。
- 默认不调用 `content/reindex`，也不走 zip / `add_resource` / OpenViking 自拉 git。
- search 读侧已支持 repo hit 映射，并用 `content/read` 404/None 过滤不可读命中。

后续若全量镜像在大仓上不可接受，再补 B2.2 增量 diff（A/M/D/R + `fs.mv`）和可选 reindex/root key；这不是 B2.1 的签收前提。
