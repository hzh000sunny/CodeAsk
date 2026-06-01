# M11 / B0 —— 代码仓进 OpenViking：Live PoC 调研清单（可交接执行）

> 版本：v1.0.5
> 状态：**方向已定**（2026-05-31 架构复核重测推翻"删除残留"冻结 → M11-B 可行）。本文 §5 是开发回填（保留），架构复核更正见下方 §6 与 [feasibility §6](./m11-openviking-repo-feasibility-research.md#6-架构复核重测--最终方向2026-05-31reviewer)。
> 关联：[m11 实现计划](./m11-repo-openviking-sync.md) · [openviking-integration 设计 §2.1/§4](../design/openviking-integration.md) · [m9 运行时预备](./m9-openviking-runtime-provisioning.md)
> 用途：记录 B′ 方案 live PoC 的真实行为与证据；后续 B0.1 在此基础上补新增/修改/读取契约验证。
>
> ⚠️ §5 总判定"不通过/B1/B2 冻结"已被 §6 复核更正：删除本身干净；所谓"残留"经受控复现复不出，疑似异步竞态而非确定性 bug。**M11-B 已解冻**。

---

## 0. 这次到底要验证什么（一句话）

M11 选定的同步方案 **B′** = "首次/重建用 `git archive` 出 zip 全量上传让 OpenViking 解包建库；日常更新用 `git diff` 逐文件 upsert/delete"。
这套方案建立在一串**对 OpenViking 实际行为的假设**之上。免环境的源码查阅（`openviking==0.3.17`，只读不 import）已确认 API *契约存在*，但**契约存在 ≠ 实际跑通**。本清单就是把这些假设逐条放到**真实运行的 OpenViking 实例**上验证。

**2026-05-31 live PoC 结论：B′ 未通过；第二轮与 root/admin 追加验证确认当前仍无完整可签收写入路径。**

- 单文件 `temp_upload + add_resource` 能索引、能 `grep/find`，同路径重复 add 是 upsert。
- 但单文件 add 会把 `repos/<slug>/src/foo.py` 建成目录，真实内容在 `repos/<slug>/src/foo.py/foo.md`；`content/read` 读 `src/foo.py` 会报 `Cannot read directory as file`。
- zip 全量能解包成真实文件节点（如 `src/zip_probe.py`），但后续单文件 add 到同一路径返回 `CONFLICT path_busy`。
- 先删 zip 文件再单文件 add 虽可成功，但会把真实文件节点改成目录化节点，破坏 repo path 读取契约。
- `/api/v1/content/write(mode=create)` 第二轮证明可以创建真实文件节点，`content/read` 可读；但 `wait=true` 返回 `DEADLINE_EXCEEDED`，`find` 未召回 marker。它只能证明文件树写入，不能证明语义索引。
- `/api/v1/content/reindex` 需要 ROOT/ADMIN role；当前 CodeAsk trusted/user header 调用返回 403。
- remote git URL add 能识别 repo 和 `file_count`，但最终 tree 为空、文件不可读，日志有大量 `Directory not found`。
- zip add 的 `to`/`parent` 双变体均 120s 超时，只留下空目录，文件不可读、不可 find。
- 临时 root/admin 实例验证 `content.write(create|replace) + content/reindex` 可让新增文件按 repo path 被 `read/grep/find`，但删除后即使 reindex，`find` 仍返回已删 URI（abstract 为空），删除残留未解。

**当前最关键的闸门已经改变：**
- **R 组（可读 + 可检索）**：任何候选方案必须同时满足 `fs/tree` 有真实文件、`content/read` 可按 repo path 读取、`find/search` 能召回新 token。
- **X 组（删除不残留）**：删除或重命名后，旧 path / 旧 token 不再召回。
- **P 组（权限）**：若方案依赖 `content/reindex`，必须先解决 CodeAsk 到 OpenViking 的 ROOT/ADMIN 调用能力。

旧 D/F 组仍可作为历史证据，但不再足够；HTTP 200、空目录、task_id、可 read 任一单项都不能单独作为 indexed 成功判据。

### 0.1 本轮实测环境

- CodeAsk：`http://127.0.0.1:8000`
- OpenViking：`http://127.0.0.1:1933`，`/health` 返回 `{"healthy": true, "version": "0.3.17", "auth_mode": "trusted"}`
- OpenViking 配置：`/home/hzh/.codeask/openviking/ov.conf`
- PoC URI 前缀：`viking://resources/codeask/repos/m11-poc-*`
- 清理：PoC 结束后已对 `m11-poc-*` 前缀执行 `DELETE /api/v1/fs?recursive=true`
- 代理：本地 curl 均使用 unset proxy 环境执行

---

## 1. 前置：拿到一个能跑的 OpenViking + 怎么调它

> ⚠️ 据 [m9 运行时预备] 复盘，OpenViking "拉得起来"本身有坑（uvx 依赖漂移 + 启动宽限）。**先确认实例健康再开始**，否则下面所有 PoC 的"失败"都可能只是实例没起来。

1. 起一个 OpenViking 实例（用 CodeAsk 现有托管 venv / 既定启动方式），拿到 `BASE_URL`（如 `http://127.0.0.1:<port>`）。
2. 所有请求都带这三个头（与 CodeAsk client 一致，`client.py:_client`）：
   ```
   X-OpenViking-Account: codeask
   X-OpenViking-User: codeask
   X-OpenViking-Agent: codeask
   ```
3. 健康验证：随便发一个 `find` 或列一下 fs，能 200 回应即实例就绪。

### 1.1 三个核心调用的真实形态（抄自 `client.py`，照这个发）

**① 上传单个文件 → 拿 `temp_file_id`**（multipart）
```bash
curl -sS -X POST "$BASE_URL/api/v1/resources/temp_upload" \
  -H "X-OpenViking-Account: codeask" -H "X-OpenViking-User: codeask" -H "X-OpenViking-Agent: codeask" \
  -F "file=@/path/to/foo.py;type=text/x-python" \
  -F "upload_mode=local"
# 返回里取 result.temp_file_id
```

**② 把上传的文件加成资源（建索引）**（JSON；`to` = 目标 URI）
```bash
curl -sS -X POST "$BASE_URL/api/v1/resources" \
  -H "Content-Type: application/json" \
  -H "X-OpenViking-Account: codeask" -H "X-OpenViking-User: codeask" -H "X-OpenViking-Agent: codeask" \
  -d '{
    "temp_file_id": "<上一步拿到的>",
    "to": "viking://resources/codeask/repos/<slug>/src/foo.py",
    "reason": "B0 poc",
    "instruction": "Index this code file for retrieval.",
    "wait": true,
    "source_name": "foo.py",
    "strict": false
  }'
```
> 注：CodeAsk 生产里用 `wait:false` 然后轮询 task；**PoC 阶段建议 `wait:true`** 拿到同步结果更省事（H5 会专门验证两种模式）。

**③ 检索**（POST /search/find，语义）
```bash
curl -sS -X POST "$BASE_URL/api/v1/search/find" \
  -H "Content-Type: application/json" -H "X-OpenViking-Account: codeask" -H "X-OpenViking-User: codeask" -H "X-OpenViking-Agent: codeask" \
  -d '{"query":"<查询词>","target_uri":"viking://resources/codeask/repos/<slug>/","limit":20,"score_threshold":0.0}'
```

**④ 删除**（DELETE /fs）
```bash
curl -sS -X DELETE "$BASE_URL/api/v1/fs?uri=viking://resources/codeask/repos/<slug>/src/foo.py&recursive=false" \
  -H "X-OpenViking-Account: codeask" -H "X-OpenViking-User: codeask" -H "X-OpenViking-Agent: codeask"
```

**⑤ 列文件树 / 看一个 uri 是否存在**：用 `POST /api/v1/search/find|grep|glob`，或 fs 列举端点（`server/routers/search.py` / fs 路由）。执行者需要一个"列出 `repos/<slug>/` 下所有条目及其确切 URI"的手段——这是 B/C/D/E 组反复要用的核对工具，**第一步就把它跑通**。

---

## 1.2 第二轮真实基线（2026-05-31）

仓库管理已清理并由负责人重新加入三仓库；当前真实 DB：

| feature | repo | source | status |
|---|---|---|---|
| `opencode` | OpenCode | git | ready |
| `anything-llm` | AnythingLLM | git | ready |
| `openviking` | OpenViking | git | ready |

已补齐三条 `feature_repos` 绑定。`viking://resources/codeask/repos` 当前为空，说明 repo ready 不代表 repo 内容已进入 OpenViking。

第二轮 PoC 结果摘录：

| 候选 | 结果 |
|---|---|
| remote git URL add | HTTP 200，`file_count=2461`，但目标 tree 0 items，read 404，find 0；日志大量 `Directory not found` |
| zip add `to` | 120s `DEADLINE_EXCEEDED`，目标 tree 空，read 404，find 0 |
| zip add `parent` | 120s `DEADLINE_EXCEEDED`，只留下空目录 `repo.zip/`，read 404，find 0 |
| single file add | 创建 `src/probe.py/` 目录，`content/read(src/probe.py)` 400，find 0 |
| `fs.mkdir + content.write(create)` | 创建真实文件，read 200，find 0 |
| `content.write(wait=true)` | 90s `DEADLINE_EXCEEDED`，文件可读，find 0 |
| `content/reindex` | 当前 header 403 `Requires role: root, admin` |
| root/admin `content.write + reindex` | 新增文件 read/grep/find 通过；删除后 grep 0 但 find 仍返回已删 URI |

完整分析见 [m11-openviking-repo-feasibility-research.md](./m11-openviking-repo-feasibility-research.md)。

---

## 2. 调研项（逐条执行 + 记录）

> 每项格式：**目的 / 决策影响 / 步骤 / 通过判据 / 需记录**。
> 优先级：🔴 闸门（不通方案要改） · 🟡 重要（影响实现细节） · ⚪ 次要（知道边界即可）。
> 准备一个测试仓：5–10 个文件，含多语言（`.py/.ts/.go/.md`）、一个二进制（如小 png）、一个无扩展名文件、一个稍大文件（几 MB）。

### A 组 —— `temp_upload` 契约

- **A1 🟡 返回结构与有效期**
  - 目的：确认 `temp_file_id` 的字段名、`temp_upload` 后多久内必须 `add_resource`（是否有 TTL）。
  - 决策影响：worker 里"先 upload 再 add"两步之间若有 TTL，需控制时序/重试。
  - 步骤：upload 一个文件，记录完整 JSON 返回；隔 1 分钟 / 5 分钟再用该 id add，看是否仍有效。
  - 通过判据：能稳定拿到 `temp_file_id`；明确是否有过期窗口。
  - 需记录：返回 JSON 原文；TTL 表现。

- **A2 🔴 `temp_upload` 体积上限（卡首次 zip）**
  - 目的：找出单文件上传的最大字节数——这决定"首次 zip 全量"是否可行、是否需要分片。
  - 决策影响：若上限远小于大仓 zip → **首次也只能逐文件**（D3 的退化路径直接成为默认），B′ 的"首次 zip"分支作废。
  - 步骤：依次上传 1MB / 10MB / 50MB / 100MB / 500MB 的假文件（`head -c <N> /dev/urandom > big.bin` 或 zip），找到开始报错的阈值；记录报错状态码与 body。
  - 通过判据：明确给出"上限 ≈ X MB"。
  - 需记录：各档结果；报错形态。

- **A3 ⚪ 任意二进制 bytes 是否被接受**
  - 目的：确认 upload 不挑 content-type（增量阶段要传任意代码/二进制文件，不只是 markdown）。
  - 步骤：上传一个 png、一个无扩展名文件、一个 `.py`，看是否都成功拿到 id。
  - 通过判据：均成功。
  - 需记录：是否有 content-type 校验导致拒绝。

### B 组 —— 单文件 add 落 `repos/<slug>/<path>`（= m11 PoC 项 1）

- **B1 🔴 单文件能否被代码解析器索引**
  - 目的：把一个 `.py`/`.ts` 文件 upload→add 到 `repos/<slug>/src/foo.py`，确认 add 任务**成功**且走了代码解析（不是当成纯文本）。
  - 决策影响：B′ 增量阶段全靠"单文件 add"。若代码解析器只在 `.git/.zip` 整树输入时触发、对单文件不解析 → 增量阶段拿不到 code-aware chunk，方案要重想。
  - 步骤：按 §1.1② 发 `wait:true`；记录返回（task 状态 / 是否报"无法解析"）。
  - 通过判据：add 成功完成，无解析错误。
  - 需记录：返回原文；若有 task_id，task 终态。

- **B2 🔴 语义检索能召回该文件**
  - 步骤：用文件里某个函数名/注释语义发 `find`（target_uri = `repos/<slug>/`）。
  - 通过判据：命中里出现该文件的 uri，且 `content/abstract` 是该文件内容。
  - 需记录：命中条目（uri + score + 片段）。

- **B3 🟡 字面检索（grep/glob）能召回**
  - 步骤：用文件里一个独特 token 发 `POST /search/grep`；用路径模式发 `glob`。
  - 通过判据：grep 命中该行；glob 列出该文件。
  - 需记录：grep/glob 返回。

- **B4 🔴 路径保真**
  - 目的：确认资源**确实**落在 `repos/<slug>/src/foo.py`，没有被拍平成 `repos/<slug>/foo.py` 或改名。
  - 决策影响：增量 delete/upsert 靠精确 uri 匹配；路径若被 OV 改写，CodeAsk 这边算出的 uri 对不上。
  - 步骤：用 §1.1⑤ 列 `repos/<slug>/` 下的确切 uri。
  - 通过判据：uri == `viking://resources/codeask/repos/<slug>/src/foo.py`（含目录层级）。
  - 需记录：列出的确切 uri 字符串。

### C 组 —— zip 全量解包（= PoC 项 2 前半）

- **C1 🔴 zip 上传后 OV 是否解包建树**
  - 步骤：`git --git-dir=<bare> archive --format=zip HEAD -o repo.zip` → upload(repo.zip) → `add_resource(temp_file_id, to="viking://resources/codeask/repos/<slug>/", wait:true)`。
  - 通过判据：任务成功；`repos/<slug>/` 下出现多个文件条目（不是一个 zip blob）。
  - 需记录：add 返回；解包后条目数。

- **C2 🔴 解包后的路径前缀规则**
  - 目的：确认内部路径与 `to` 目录如何拼接——`to=repos/<slug>/` + zip 内 `src/foo.py` → 落点是 `repos/<slug>/src/foo.py`？有没有多套一层目录、有没有把 zip 名当前缀。
  - 决策影响：**这是 D 组一致性的前提**。落点规则定了，CodeAsk 才能算出与逐文件 add 一致的 uri。
  - 步骤：列 `repos/<slug>/` 全部 uri，和源仓文件路径逐一对照。
  - 通过判据：落点 == `repos/<slug>/<zip 内相对路径>`，一一对应无多余层级。
  - 需记录：源路径 → OV uri 的对照表（抽样 5 条即可）。

- **C3 🟡 `exclude`/`ignore_dirs` 在 zip 上是否生效**
  - 步骤：add zip 时带 `exclude`（如 `*.png`、`node_modules`），看被排除项是否真没进树。
  - 通过判据：排除项不出现在 `repos/<slug>/` 下。
  - 需记录：传的参数名与实际效果（确认参数名是 `exclude`/`ignore_dirs` 还是别的）。

- **C4 🟡 zip 内二进制/超大文件的处理**
  - 目的：确认坏/大/二进制文件是被**跳过**还是**让整个 add 任务失败**。
  - 决策影响：决定 CodeAsk 是否必须在打 zip 前自己过滤二进制，还是可托付 OV。
  - 步骤：zip 里放一个 png、一个超大文件，不加 exclude，直接 add。
  - 通过判据：明确是"跳过坏文件、其余成功"还是"整任务失败"。
  - 需记录：任务终态；哪些文件进了树。

### D 组 —— zip 全量 与 逐文件增量 的一致性（🔴🔴 最关键闸门，= PoC 项 2 后半）

- **D1 🔴 同路径单文件 add = upsert 还是重复**
  - 步骤：在 C 跑通的树里，挑一个已存在文件（如 `src/foo.py`），改其内容，按 §1.1② 单文件 add 到**同一** `repos/<slug>/src/foo.py`。
  - 通过判据：`repos/<slug>/src/foo.py` 仍只有**一个**条目；`find` 返回的是**新**内容，旧内容召不回。
  - 需记录：add 前后该 uri 的条目数；find 返回的内容版本。

- **D2 🔴 "zip 解包的文件" vs "单独 add 的文件" uri 是否字节一致**
  - 目的：这是 delete 能否命中 zip 建条目的根本。
  - 步骤：对比 C2 里 zip 解包出的 `src/foo.py` 的确切 uri，与 D1 单独 add 后该文件的确切 uri。
  - 通过判据：两者**完全相同**（同一字符串）。
  - 需记录：两个 uri 字符串并排。
  - ⚠️ 若不同 → **D 组判定不通**，进 D3。

- **D3 🔴（仅当 D1/D2 不通）退化路径可行性**
  - 目的：验证"首次也逐文件"（`git ls-tree -r HEAD` 列全部文件，循环 upload+add）能否产出与增量阶段**完全一致**的树。
  - 步骤：不传 zip，改为遍历 `git ls-tree --name-only -r HEAD`，逐个单文件 add；再做一次 D1 式修改 add。
  - 通过判据：全程同一种"单文件 add"码路，uri 一致、upsert 生效。
  - 需记录：是否可行；逐文件首次同步的耗时量级（喂给 H 组）。

### E 组 —— 删除 / tombstone

- **E1 🔴 删单文件**
  - 步骤：`DELETE /fs?uri=repos/<slug>/src/foo.py&recursive=false`。
  - 通过判据：该 uri 消失；`find/grep` 不再召回。
  - 需记录：删除返回；删后检索结果。

- **E2 🔴 递归删整棵子树**
  - 步骤：`DELETE /fs?uri=repos/<slug>/&recursive=true`。
  - 通过判据：`repos/<slug>/` 下清空。
  - 需记录：删除返回；删后列举为空。

- **E3 ⚪ 删不存在的 uri**
  - 步骤：删一个不存在的 path。
  - 通过判据：404 或可识别的"未找到"（CodeAsk client 已把 404 当成功处理）。
  - 需记录：状态码。

### F 组 —— upsert / 重索引语义（🔴 模型根基，与 D1 互补）

- **F1 🔴 同路径连改两次**
  - 步骤：同一 uri add v1 → add v2 → add v3，每次内容不同。
  - 通过判据：始终单条目，`find` 只召回 v3，旧版本的独特 token 召不回。
  - 需记录：每次后的条目数与召回内容。

- **F2 🟡 重命名（删旧+加新）**
  - 步骤：delete `old.py`，add `new.py`（内容相同）。
  - 通过判据：`old.py` 召不回，`new.py` 可召回，无残留旧 embedding。
  - 需记录：前后检索。

### G 组 —— 解析保真 / 召回质量

- **G1 🟡 文件类型支持矩阵**
  - 目的：哪些类型被代码解析、哪些被当纯文本、哪些被静默丢弃。
  - 步骤：分别 add `.py/.ts/.go/.java/.md/.json/.yaml/.lock/无扩展名/.png`，各跑一次 find/grep。
  - 通过判据：产出一张"类型 → 是否索引 / 解析方式 / 可召回"的表。
  - 需记录：该矩阵。

- **G2 🟡 语义召回粒度**
  - 目的：`find` 是返回函数级/片段级 chunk，还是整文件一坨——决定 RAG 的实际价值。
  - 步骤：对一个多函数文件，用某一个函数的语义查询，看命中是否定位到该函数附近。
  - 需记录：命中片段粒度。

- **G3 ⚪ submodule / symlink**
  - 说明：`git archive` 默认**不含 submodule 内容**（只留 gitlink）——记录这是已知边界即可。symlink 在 zip 内是否被解析器按 Zip-Slip 防护处理（源码 `_extract_zip` 有防护）。
  - 需记录：是否遇到异常。

### H 组 —— 运维 / 性能（影响 worker 设计）

- **H1 🟡 单文件 add 端到端耗时**
  - 目的：给"增量 = N 个文件 × 单文件耗时"估时。
  - 步骤：测 upload+add(wait:true)+可被 find 召回 的总耗时，取几次中位数。
  - 需记录：单文件中位耗时（秒）。

- **H2 🟡 是否有批量 add（少 round-trip）**
  - 目的：大 diff 时逐文件 N 次往返是否可接受，或有无批量入口。
  - 步骤：查 `server/routers` 有无多文件/批量端点；没有就记"只能逐文件"。
  - 需记录：结论。

- **H3 🔴 add 返回后索引可见延迟**
  - 目的：`add_resource` 200 之后，多久 `find/grep` 能看到——决定 job"何时算完成"与 e2e 等待时长。
  - 步骤：`wait:false` add 后立即 find，轮询直到召回，记录时延；再 `wait:true` 对比。
  - 需记录：两种模式下"可召回"的时延。

- **H4 🟡 失败响应形态**
  - 目的：超体积/不支持/坏 zip 各返回什么——映射到 CodeAsk 的 `mark_failed`。
  - 步骤：制造几种失败，记录 status code + body。
  - 需记录：错误形态表。

- **H5 🟡 `wait:true` vs `wait:false` + task 轮询**
  - 目的：确认 `wait:false` 时 `/api/v1/resources` 是否返回 `task_id`，能否经 `GET /api/v1/tasks/{id}`（client 已有 `task_status`）轮询到终态。
  - 步骤：`wait:false` add，取返回里的 task_id，轮询 task 直到终态。
  - 需记录：返回字段名；task 状态流转（pending→…→done/failed）。

### I 组 —— git 机制（CodeAsk 侧，**无需 OpenViking**，可纯本地验证）

> 这组验证的是"CodeAsk 能不能稳定产出 B′ 需要的 zip 和 diff"，和 OV 无关，可并行做。

- **I1 🟡 bare 仓直接出 zip**
  - 步骤：`git --git-dir=<bare> archive --format=zip HEAD -o /tmp/r.zip`，解开看路径。
  - 通过判据：无需 checkout 工作树即可产 zip；内部路径是仓根相对、UTF-8。
  - 需记录：是否成功；路径样例。

- **I2 🔴 diff 状态字母覆盖 + rename 检测**
  - 目的：确认 `git diff --name-status <old>..<new>` 要不要 `-M`（rename）/`-C`（copy）；枚举会出现的状态字母（A/M/D/R###/C###/T），确保 worker 全处理。
  - 步骤：造 增/改/删/重命名/改权限 各一例，跑带与不带 `-M` 的 diff。
  - 通过判据：给出"要用的确切命令"和"需处理的状态字母清单"。
  - 需记录：两种命令输出对比。

- **I3 🔴 force-push / 历史改写检测（决定何时回退全量 zip）**
  - 目的：B′ 规定"last sha 不可达 / 历史被改写 → 回退首次 zip 全量"。需要一个可靠判据。
  - 步骤：验证 `git --git-dir=<bare> cat-file -e <old_sha>^{commit}`（old sha 是否仍存在）/ `git merge-base --is-ancestor <old> <new>`（old 是否仍是 new 祖先）能否区分"正常推进" vs "被改写"。
  - 通过判据：给出"判定该回退全量"的确切命令与退出码语义。
  - 需记录：两种场景下命令的退出码。

- **I4 🔴 local_dir 快照能否做 diff**
  - 目的：`_sync_plain_local_dir_snapshot`（本地目录源）产出的快照是否有可 diff 的提交历史；若每次是全新树（无父提交链）→ 这类源只能每次全量，需在计划里特判。
  - 步骤：看 local_dir 源的 bare/快照结构，连续同步两次，验证两个快照间能否 `git diff`。
  - 通过判据：明确 local_dir 源"支持增量 diff"还是"只能全量"。
  - 需记录：结论（直接影响 m11 B2 是否要给 local_dir 单独码路）。

- **I5 ⚪ 二进制识别（建 exclude 用）**
  - 步骤：验证用 `git --git-dir=<bare> diff --numstat`（二进制行显示 `-\t-`）或 `.gitattributes` 识别二进制，供打 zip / 逐文件时过滤。
  - 需记录：选用的识别手段。

- **I6 ⚪ 非 ASCII / 空格路径**
  - 步骤：仓里放含中文/空格的文件名，走 archive + diff + `uri.py` 的 `quote()` 编码，确认 OV 端 uri 能 round-trip。
  - 需记录：是否有编码问题。

---

## 3. 回填给架构复核的格式

每项请按这个结构回（贴原始返回最有用，不要只写"成功/失败"）：

```
[编号] 通过 / 不通过 / 部分
- 实测行为：<一句话>
- 证据：<curl 返回原文 / uri 字符串 / 耗时数字 / 命令退出码>
- 偏离假设处：<如果和本文档预期不一样，写明哪里不一样>
```

特别地，请务必给出这几个**硬结论**（我据此决定 B′ 是否成立、要不要改）：
1. **D2 的两个 uri 是否字节一致**（决定首次 zip 能否保留，或全退化逐文件）。
2. **A2 的 temp_upload 体积上限**（决定首次 zip 是否可行）。
3. **F1 同路径重复 add 是否 upsert**（决定整个增量模型成立与否）。
4. **H3 索引可见延迟**（决定 job 完成语义与 e2e 等待）。
5. **I4 local_dir 源能否增量 diff**（决定要不要给它单开全量码路）。

---

## 4. 原决策矩阵（架构复核时按此判）

> 2026-05-31 实际结果落入 **D2 不一致**，且 D3 退化路径虽能保持单一路径形态，却会暴露 `src/foo.py/foo.md` 内部转换路径；因此不是“直接放弃 zip、首次也逐文件”这么简单，需要 B0.1 继续决策读取契约与新增文件策略。

| 结果 | 对 B′ 的影响 |
|------|------------|
| D2 一致 + A2 上限够大 | B′ 原样成立：首次 zip + 逐文件增量 |
| D2 一致 + A2 上限偏小 | 首次 zip 分片，或首次也逐文件；增量逻辑不变 |
| D2 **不一致** | 放弃"首次 zip"，**首次也逐文件**（D3 已验可行）→ 全程单一码路，更统一 |
| F1 **非 upsert** | 增量模型不成立 → 改为"每次 delete 子树 + 重建"，回到接近方案 B，需重新评估大仓代价 |
| H3 延迟很大 | job 完成判定改为轮询 find 可见，而非 add 返回即完成；e2e 加等待 |
| I4 local_dir 不能 diff | m11 B2 给 local_dir 源单开"每次全量"码路，git 源走增量 |

> B0 闸门通过条件：D/E/F 三组 🔴 全通过（或 D 不通但 D3 退化路径验证可行）→ 回写设计 §2.1/§4 的 repo 落地细节 → 才开 B1。

---

## 5. 2026-05-31 Live PoC 回填

### 总判定

**不通过。** B′ 的关键假设“zip 全量解包后，可用逐文件 `add_resource(to=repos/<slug>/<rel>)` 做增量 upsert/delete”被真实 OpenViking 行为证伪。B1/B2 继续冻结，需新增 B0.1 重新确定写入策略。

### A 组 —— `temp_upload` 契约

[A1] 部分通过
- 实测行为：`temp_upload` 返回结构稳定，字段为 `result.temp_file_id`。
- 证据：`.py` 返回 `{"status":"ok","result":{"temp_file_id":"upload_4bb7eb2d21004f1183acad250d12b543.py"}}`；`.zip` 返回 `upload_5c00c330286b4907bc6c73e37dd0e995.zip`。
- 偏离假设处：本轮未等待 1 分钟 / 5 分钟复用同一个 id；未完整验证 TTL。源码显示 local upload 清理默认按上传临时目录文件年龄清理，需 B0.1 或实现时控制 upload→consume 的时序。

[A2] 部分通过
- 实测行为：源码默认上传上限为 `512 * 1024 * 1024` bytes；本机 `ov.conf` 仅设置 `default_mode=local`，未覆盖该值。
- 证据：`.venv/lib/python3.11/site-packages/openviking/server/config.py` 的 `TempUploadConfig.shared_max_size_bytes = 512 * 1024 * 1024`；`temp_upload_store.py` local/shared 上传均以该值判断超限。
- 偏离假设处：未实测 1MB/10MB/50MB/100MB/500MB 多档；因此只能记录默认配置，不把“大仓 zip 不卡”视为通过。

[A3] 部分通过
- 实测行为：`.py` 和 `.zip` 可上传；zip 内二进制样例可被上传，但解析阶段标为 unsupported 并跳过。
- 证据：zip add 返回 `unsupported_files:[{"path":"assets/small.bin","status":"unsupported","reason":"unsupported"}]`，任务整体 success。
- 偏离假设处：未单独上传 png/无扩展名做 add 解析矩阵。

### B 组 —— 单文件 add 落 `repos/<slug>/<path>`

[B1] 通过但带重大路径副作用
- 实测行为：单 `.py` 文件 add 成功，无解析错误。
- 证据：`add_resource(wait=true)` 返回 `status=success`、`root_uri=viking://resources/codeask/repos/m11-poc-single/src/m11_probe.py`，队列 `Semantic.processed=1`、`Embedding.processed=3`。
- 偏离假设处：root_uri 是请求 URI，但该 URI 在 fs 中是目录，不是可 read 的真实文件。

[B2] 通过
- 实测行为：语义 `find` 能召回单文件内容。
- 证据：查询 “distinctive marmalade scheduler sentinel” 命中 `viking://resources/codeask/repos/m11-poc-single/src/m11_probe.py/m11_probe.md`，score 约 `0.576`。
- 偏离假设处：命中 URI 不是 `src/m11_probe.py`，而是 `src/m11_probe.py/m11_probe.md`。

[B3] 通过
- 实测行为：`grep`/`glob` 均可召回。
- 证据：`grep m11-alpha-token-34719` 命中 `src/m11_probe.py/m11_probe.md`；`glob **/*.py` 返回 `viking://resources/codeask/repos/m11-poc-single/src/m11_probe.py`。
- 偏离假设处：glob 显示的是目录化的 `.py` 节点，grep 命中内部 `.md` 文件。

[B4] 不通过（路径形态不保真）
- 实测行为：请求 `to=repos/<slug>/src/m11_probe.py` 后，fs 树为：
  - `src/`
  - `src/m11_probe.py/`（目录）
  - `src/m11_probe.py/m11_probe.md`（真实内容）
- 证据：`fs/stat?uri=.../src/read_probe.py` 返回 `isDir=true`；`content/read?uri=.../src/read_probe.py` 返回 `INVALID_ARGUMENT Cannot read directory as file`；读 `.../src/read_probe.py/read_probe.md` 才返回源码内容。
- 偏离假设处：这会破坏 repo 文件读取契约，不能直接把单文件 add 的 URI 当作仓库文件 URI。

### C 组 —— zip 全量解包

[C1] 通过
- 实测行为：zip 上传后 OpenViking 解包建树，不是一个 zip blob。
- 证据：add zip 返回 `status=success`，`meta.file_count=3`，`processed_files` 包含 `docs/readme.md`、`src/helper.ts`、`src/zip_probe.py`。
- 偏离假设处：二进制 `assets/small.bin` 被归入 unsupported，但不导致整任务失败。

[C2] 部分通过
- 实测行为：代码文件 `.py/.ts` 按 zip 内相对路径落成真实文件；markdown 会被目录化。
- 证据：
  - `src/helper.ts` → `viking://resources/codeask/repos/m11-poc-zip/src/helper.ts`
  - `src/zip_probe.py` → `viking://resources/codeask/repos/m11-poc-zip/src/zip_probe.py`
  - `docs/readme.md` → `viking://resources/codeask/repos/m11-poc-zip/docs/readme/readme.md`
- 偏离假设处：不同文件类型的节点形态不完全一致，尤其 markdown 被目录化。

[C3] 未验证
- 实测行为：本轮未带 `exclude/ignore_dirs` 单独验证。
- 证据：无。
- 偏离假设处：实现前仍需验证参数名和效果，不能假设过滤完全由 OpenViking 兜底。

[C4] 部分通过
- 实测行为：zip 内二进制被跳过，任务整体成功。
- 证据：`unsupported_files:[{"path":"assets/small.bin","status":"unsupported","reason":"unsupported"}]`。
- 偏离假设处：未验证超大文件、坏 zip 是否整任务失败。

### D 组 —— zip 全量与逐文件增量一致性

[D1] 不通过
- 实测行为：zip 解包出 `src/zip_probe.py` 后，单文件 add 到同 URI 返回冲突，不会 upsert。
- 证据：`add_resource(to=.../src/zip_probe.py)` 返回 `{"code":"CONFLICT","message":"Resource is busy: ...","details":{"conflict_type":"path_busy","retryable":true}}`；等待 5 秒后重试仍为 `path_busy`。
- 偏离假设处：B′ 的 A/M 文件 upsert 路径不成立。

[D2] 不通过
- 实测行为：zip 解包文件与单文件 add 后的节点形态不一致。
- 证据：
  - zip 解包：`src/zip_probe.py` 是真实文件，grep 命中该 URI。
  - 删除后单文件 add：`src/zip_probe.py/` 变成目录，内容在 `src/zip_probe.py/zip_probe.md`。
- 偏离假设处：两者不是同一字符串层面的“内容 URI”；delete/upsert/read 都会出现不一致。

[D3] 部分通过但不能直接定案
- 实测行为：全程单文件 add 路径内部一致，同路径重复 add 能替换旧内容。
- 证据：单文件 v1→v2 后旧 token `m11-alpha-token-34719` 消失，新 token `m11-beta-token-94820` 命中。
- 偏离假设处：退化为“首次也逐文件”会让 repo 文件对外变成目录化路径，`content/read src/foo.py` 不可用；除非 CodeAsk 读取层统一适配，否则不能作为最终方案。

### E 组 —— 删除 / tombstone

[E1] 部分通过
- 实测行为：zip 解包出的真实文件可 `recursive=false` 删除；单文件 add 产生的目录化“文件”必须 `recursive=true`。
- 证据：
  - 对单文件 add 的 `src/m11_probe.py` 执行 `recursive=false` 返回 `FAILED_PRECONDITION Cannot remove directory without --recursive`。
  - 对同 URI 执行 `recursive=true` 后，grep 新 token 为空。
  - 对 zip 真实文件 `src/zip_probe.py` 执行 `recursive=false` 删除成功。
- 偏离假设处：删除策略取决于节点来源，不能只按 repo path 固定 `recursive=false`。

[E2] 通过
- 实测行为：递归删除 `repos/<slug>/` 前缀成功。
- 证据：多个 `m11-poc-*` 前缀清理返回 `status=ok`。

[E3] 部分通过
- 实测行为：删除不存在前缀返回 `status=ok`、`estimated_deleted_count=0`。
- 证据：清理旧 PoC 前缀时返回 `estimated_deleted_count=0`。
- 偏离假设处：未覆盖所有不存在文件/目录细分状态码；OpenViking 当前表现可被 CodeAsk 当作幂等成功处理。

### F 组 —— upsert / 重索引语义

[F1] 通过（仅限同一种单文件 add 码路）
- 实测行为：同一路径单文件 add v1→v2 后旧内容不再召回，新内容可召回。
- 证据：`grep m11-alpha-token-34719` 返回空；`grep m11-beta-token-94820` 命中 `src/m11_probe.py/m11_probe.md`。
- 偏离假设处：这不等于 zip 文件可被单文件 add upsert；D1/D2 已证伪混用路径。

[F2] 未验证
- 实测行为：本轮未完整执行 rename 的删旧+加新语义。
- 证据：无。

### H 组 —— 运维 / 性能

[H2] 通过（源码查阅）
- 实测行为：HTTP 路由未发现多文件批量 add；主要入口为 `temp_upload` + 单个 `add_resource`。
- 证据：`server/routers/resources.py` 只有单文件 `UploadFile` 和单个 `AddResourceRequest`。

[H3/H5] 通过（小文件）
- 实测行为：`wait:false` 返回 `task_id`，可通过 `/api/v1/tasks/{id}` 轮询；小文件约 1-2 秒后 task `completed` 且 grep 可见。
- 证据：`task_id=965656cd-512b-4977-9e6a-22ce95eaa840`；poll 1 为 `running` 且 grep 空；poll 3 为 `completed` 且 grep 命中 `m11-task-token-44091`。
- 偏离假设处：`wait:true` 在 `content.write` 已有文件更新上曾返回 `DEADLINE_EXCEEDED`，但内容实际更新并可 grep；生产完成语义不能只信 `wait=true` 返回。

### I 组 —— git 机制

[I1] 通过
- 实测行为：bare repo 可直接 `git archive --format=zip HEAD`，内部路径为仓根相对路径。
- 证据：`unzip -l archive.zip` 显示 `docs/a.md`、`src/a.py`。

[I2] 部分通过
- 实测行为：增/删/重命名样例中，`git diff --name-status old..new` 与 `git diff -M --name-status old..new` 都输出 `R100 docs/a.md docs/renamed.md`、`D src/a.py`、`A src/b.py`。
- 偏离假设处：未覆盖 copy、type change、权限变更；实现仍建议显式使用 `-M` 并处理未知状态为失败或全量重建。

[I3] 部分通过
- 实测行为：正常推进下 `git merge-base --is-ancestor old new` 退出 `0`，`git cat-file -e old^{commit}` 退出 `0`。
- 偏离假设处：未实测 force-push 改写场景；仍需验证 old commit 不存在 / old 非 new 祖先时的退出码分支。

[I4] 未验证
- 实测行为：本轮未跑 `_sync_plain_local_dir_snapshot` 连续快照 diff。
- 影响：local_dir 是否能统一走 git diff 仍待确认。

### B0.1 新增验证项

原 B′ 已证伪，下一轮不再重复验证“zip + 逐文件 add_resource”是否成立，而应验证以下可落地替代策略：

1. **root/admin reindex 路线（已部分验证）**
   - 独立临时实例 `127.0.0.1:1944`，`auth_mode=api_key` + `root_api_key`。
   - `content.write(mode=create, wait=false)` 可创建真实文件节点；约数秒后 `content/read` 可读、`grep` 可见。
   - `content/reindex(vectors_only, wait=true)` 后，`find("M11_ROOT_REINDEX_MARKER_V3")` 命中文件本身 `src/probe.py`，score 约 `0.80`。
   - 小目录重建也可能很慢：样例 `scanned_records=3/rebuilt_records=5` 曾耗时 `68114ms`。

2. **删除残留（未通过，当前最关键阻塞）**
   - `DELETE /api/v1/fs?uri=...probe.py&recursive=false` 后，文件实际删除：`content/read` 404，`grep` 0。
   - 但删除后再 `content/reindex`，`find("M11_ROOT_REINDEX_MARKER_V3")` 仍返回已删 URI `src/probe.py`，abstract 为空。
   - 因此完成判据不能只看 reindex completed 或 find total；必须要求命中 URI 仍可 read，且 abstract/snippet 非空并对应当前内容。
   - 修复方向：查 OpenViking 是否有向量删除/全量 rebuild 清理模式；若没有，repo semantic mirror 继续冻结。

3. **读取契约适配**
   - 若任何路径会产生 `src/foo.py/foo.md`，CodeAsk 对外必须把它映射回 `src/foo.py`。
   - `openviking_read/glob/find`、agent 工具结果、dashboard 任务详情都不能暴露 OpenViking 内部目录化路径。

4. **最终决策矩阵更新**
   - 若 `content.write + root/admin reindex + delete-clean` 全通过：用 `git diff` 驱动 A/M/D/R，首次/重建逐文件 mirror，避免 zip。
   - 若删除残留无法清理：放弃 OpenViking repo semantic mirror，保留 CodeAsk 原生 repo 工具作为代码主链路。
   - 若 reindex 50-70 秒级耗时在大仓抽样中不可接受：只能做小范围/按需镜像，不能全量镜像大仓。

---

## 6. 架构复核更正（2026-05-31，reviewer）

§5 的"不通过 / 删除残留未解 / B1/B2 冻结"已被真实重测推翻。完整证据与最终方向见 **[feasibility §6](./m11-openviking-repo-feasibility-research.md#6-架构复核重测--最终方向2026-05-31reviewer)**，要点：

- **删除本身干净**：`fs.rm(rec=false)` 后未 reindex 前 find 立刻不返回、`read`→404（trusted 与 root 实例、每次都验证）。
- **§5 的"删除残留"不是确定性 bug**：早期两次（未 drain 异步队列、reindex 很快）抓到 reindex 后已删文件以空 abstract、相同 score、`read`→404 复活；但随后**两次受控复现（drain 队列后）均复不出**，无论有无存活兄弟、无论哪种 mode。修正：**幽灵疑似 in-flight 嵌入任务与删除的异步竞态**，非"reindex 必然复活"。开发复现不出来是对的。触发条件按负责人指示先不深究。
- **写用 `content.write`（真实文件节点，无目录化），且不 reindex 即可 find 召回**（队列嵌入完即可，实测 0.83/0.74）；reindex 仅补 abstract，是可选增强。A/M→write、D→`fs.rm`、R→`fs.mv`（mv 重命名干净）。逐文件 reindex 不可行（409 树锁）。
- **"空 abstract" 不是墓碑信号**：活的新文件在子树 reindex 前 abstract 也空。判据只能用 `read`/`fs.stat` 存在性。
- **瓶颈是 embedding 吞吐**（ollama bge-m3 单次 5–20s，`max_concurrent=1`），非语义缺陷。

**负责人三决策**（据此实现，详见 feasibility §6.3）：① 走 reindex 路线 → CodeAsk 配 root/admin key；② 吞吐慢可接受，只要异步可观测（status/sync_jobs/events/metrics）、任务慢慢推进；③ embedder 将可换（默认改 OV 自带，ollama/三方走自定义配置），设计不写死 bge-m3。

→ 故本文 §0 的 R/X/P 三组闸门已不再是阻塞：R（可读可检索）由 content.write + 队列嵌入满足（reindex 仅补 abstract，可选）；X（删除不残留）由删除本身干净满足，读侧存在性过滤兜罕见竞态孤儿；P（权限）仅在启用 reindex 时才需 root/admin key。**B1/B2 解冻，按 feasibility §6.2 配方进入实现。**
