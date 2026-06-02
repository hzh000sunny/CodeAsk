# M12 — Wiki workspace 写时增量持久化 / 去 opencode 耦合

> 版本：v1.0.5（排期在 m11 之后）
> 状态：Implemented（2026-06-01 架构 review 后补齐 bootstrap / 失败降级 / report 投影 / legacy 兼容投影）
> 关联：[openviking-integration 设计 §3.1/§4](../design/openviking-integration.md) · [m11 OpenViking SDK 迁移](./m11-openviking-sdk-migration.md) · [m10 同步任务 UX](./m10-sync-jobs-ux.md)
> 来源：2026-06-01 review——m11 把 wiki→OV 同步改为「按 feature 目录 import」后，发现被 import 的磁盘目录 `wiki_workspace/current/` 只在 **opencode 会话启动时**全量重建（`backend.py:149`），不随 wiki 增删改更新。负责人定调：磁盘目录应由 **wiki 写路径**写时增量、针对性维护，与 opencode 解耦。
>
> **本里程碑取代了旧 M12「同步覆盖补全（feature_readme / wiki_dir / global_index）」**：旧 M12 建立在"逐 `source_type` 经 `_resolve_content` 分派同步"的模型上，已被 m11 的「整目录 import」推翻而退役。旧 M12 追的那些内容问题没消失，但从"加同步 source_type"变成"决定被 import 的 wiki 目录里放什么"，并入本里程碑 §5。

---

## 0. 现状与问题（已核对代码）

`WikiWorkspaceExporter`（`agent/opencode_compat/wiki_workspace.py`）把当前 wiki 投影成一棵磁盘目录树，供消费方 grep/read/import：

```
data_dir/wiki_workspace/current/
  <feature_slug>/
    knowledge-base/...        ← OpenViking 只 import 这棵
    problem-reports/verified|drafts/...  ← 仅供 opencode / 本地文件视图，不进 OpenViking
    README.md
  (顶层 manifest)
```

**两个结构性问题**：

1. **耦合错位**：唯一重建该目录的 `export_current()` 只在 opencode 会话启动时被调（`backend.py:149`）。但该目录的消费方现在有两个——opencode **和** OpenViking sync（m11）。让一个消费者（opencode）顺带负责刷新共享数据，导致：
   - 发布 wiki 但从未开 opencode → 目录不存在 → m11 `sweep_all` 存在性 guard 跳过 → **wiki 永不进 OV**；
   - 开过 opencode、之后改 wiki → DB 变了、目录没变 → m11 读到旧目录、推旧内容却盖新 hash → **OV 永久滞后**。
2. **全量删除重建太糙**：`export_current()` 每次 `rmtree` 整棵 `current/` 再 rebuild（`wiki_workspace.py:120-122`）。改一篇文档却重建所有 feature，浪费；且重建瞬间目录残缺/不存在，正在读它的 OV `add_resource` / opencode 可能撞空窗。

> 排期口径（负责人定）：**M11 不加桥接**，上述失效模式作为 M11 的**已知遗留**留存（M11 的 SDK 迁移本身已 review 通过、不因此打回）；由本里程碑用写时增量投影器根治。

---

## 1. 目标与范围

**目标**：磁盘 `wiki_workspace/current/` 成为一份**由 wiki 写路径写时维护**的持久镜像，任何消费方（opencode / OpenViking sync）读到的永远是当前 DB 状态。

**范围内**：
- 新增写时增量投影器（写哪篇动哪个文件，删哪篇删哪个文件，移动即 move）。
- 在 wiki 写路径接钩子（文档发布/回滚/删/恢复、节点移动/删除、promotion、import apply、feature 生命周期、报告引用变化）。
- opencode 去耦合：移除会话启动时的 `export_current()`，opencode 退化为纯读者。
- OpenViking sync 去桥接：不再触发任何 export，纯读。
- 吸收旧 M12 的内容决策（§5）。

**范围外**：
- OpenViking 客户端 / SDK（m11 已做）。
- 代码仓 → OpenViking（延后）。
- UI Wiki 搜索（m11 已定为纯 SQL）。
- Report → OpenViking：report 已退出 OpenViking 同步。本里程碑即使继续维护 `problem-reports/` 文件视图，也不得让 report 触发 OpenViking job。

---

## 2. 目标设计：WikiWorkspaceProjector（写时增量）

新增组件（建议落在 `agent/opencode_compat/` 或 `wiki/` 下，需消费 wiki 主数据），契约：

- **投影布局与现有 exporter 对齐，但修正已知 manifest path 问题**——复用 `_export_documents` / `_export_reports` / `_write_feature_index` / `_write_manifest` / `_relative_wiki_path` 的渲染与路径规则，保证 opencode 看到的结构不变；`_manifest.json.features[].path` 应指向 `./<feature_slug>`，不能继续写不存在的 `./wiki/<feature_slug>`。把这些渲染逻辑从"全量遍历"中抽出为"针对单个文档/报告/feature"的可复用单元。
- **针对性操作**：
  - document node create → 只刷新 feature README / manifest；没有 `current_version_id` 时不写空正文 md。
  - 文档 publish / rollback / restore → 渲染并写 `knowledge-base/<相对路径>.md`（**临时文件 + `os.replace` 原子替换**）。
  - 文档/节点 delete → 删对应文件 + 向上清理空目录。
  - 节点 move/rename → 必须用变更前采集的 `old_path` 和提交后的 `new_path` 移动文件；subtree move 必须覆盖 descendants。
  - 报告引用 add/remove/verified 翻转 → 在 `problem-reports/verified|drafts/` 下写/移/删对应文件。
  - feature 新建 → 建子目录；feature name/description 更新 → 刷新 README + manifest；feature 归档/删除 → 只 `rmtree` 该 feature 子树；feature restore → 重建该 feature 子树。
  - 每次变更后刷新**该 feature 的 `README.md`** 与顶层 manifest 计数（manifest 可增量改或按需廉价重算）。
- **结构性重建实现**：node move/delete/restore、feature restore、report projection 等需要 per-feature rebuild 的路径，不再先 `rmtree(<feature>)` 造成空目录窗口；实现先在 sibling temp feature 目录生成完整镜像，再逐文件原子替换到目标 feature，最后清理 stale 文件。feature archive/prune 仍会删除该 feature 子树，这是业务上该 feature 不再可读的终态。
- **触发时机**：wiki DB 写 **提交成功之后**。失败的事务不得污染磁盘。
- **失败恢复**：DB 提交成功但投影失败时，不回滚业务事务；写 `wiki_workspace_projection_failed` event / 日志，并返回 2xx 给业务写请求。OpenViking 同步在投影失败时不得继续基于旧目录 add_resource。现阶段 repair 入口是启动 bootstrap / 管理员重建对账。
- **并发控制**：增量 projector 与全量 bootstrap / 管理员重建共用同一把 app 内锁；若未来多进程部署，再补文件锁。full rebuild 采用 `current.tmp.<pid>` + atomic rename，不能与增量写互相覆盖。
- **幂等**：每个投影操作可重复执行结果一致——这样 bootstrap / 对账重建能安全复用同一套单元。
- **去掉全量 rmtree 活路径**：`export_current()` 降级为：① 首次/空目录 bootstrap；② 管理员"重建/对账"兜底动作（怀疑漂移时手动跑一次，原子 rename 全量替换）。不再挂在 opencode 会话上。
- **启动 bootstrap**：app lifespan 在 OpenViking startup sweep 之前检查 `wiki_workspace/current/_manifest.json`，缺失时幂等执行 `WikiWorkspaceProjector.bootstrap()`，保证存量 DB 内容先落盘，再由 sweep/add_resource 读取。

---

## 3. 接线点（关键：今天没有集中事件）

`wiki/signals.py` 是文本分析工具、**不是事件总线**；wiki 写路径散在多个 service。两种接法，建议选 A：

- **A（推荐）「提交后 hook」**：在 wiki 写 service 内把事件暂存在 `session.info`，API `commit()` 成功后统一 drain。顺序必须是：业务 DB commit → projector 更新磁盘 → OpenViking enqueue。这样 OpenViking 只会读取已经更新过的 `knowledge-base/`。需要发事件的写点：
  - `wiki/documents/service.py`（文档 CRUD）
  - `wiki/tree/service.py`（节点移动 / 删除）
  - `wiki/tree/ordering.py`（拖拽移动 / 跨父节点移动）
  - `wiki/promotions/service.py`（current ↔ draft 提升）
  - `wiki/imports/service.py`（import apply）
  - `wiki/imports/session_service.py`（分片/会话式 import apply）
  - `api/features.py` / `wiki/tree/service.py::restore_archived_space`（feature update / archive / restore）
  - `wiki/reports.py` / report 引用变更（`report_projection.py`）
- **legacy 兼容入口**：旧 `/api/documents` 上传和 legacy backfill 仍会创建 native `WikiDocument`。这些路径通过 `enqueue_legacy_wiki_document_sync → enqueue_wiki_document_sync` 先调用 projector 投影对应文档 / feature，再入 `wiki_feature` job，避免只 enqueue 但磁盘目录只有 README 的空内容。
- **B（不推荐）**：每个 service 直接调 Projector。耦合更重、易漏点。

事件载荷不能只带 node id；凡是旧磁盘路径会消失的变更，必须在 DB mutation 前采集旧状态。最小事件模型：

```text
WikiWorkspaceEvent:
  feature_id
  feature_slug
  space_id
kind:
    document_published
    feature_created
    node_created
    node_moved
    node_deleted
    node_restored
    feature_metadata_changed
    feature_archived
    feature_restored
    report_projection_changed
  node_id?
  old_path?
  new_path?
  affected_node_ids?
  report_id?
```

> 设计抉择：本里程碑先做最小事件暂存 + drain，不抽象成全局事件总线。未来 RAG / 审计若复用，再独立升级。

---

## 4. 消费方改造

- **opencode**：删除 `backend.py:149` 的活跃 `export_current()`；会话启动不再重建 wiki_workspace，退化为纯读者。冷启动 repair 由 app startup bootstrap 负责。opencode 行为对用户无感（目录一直是最新）。
- **OpenViking sync（m11）**：移除任何"import 前触发 export"的桥接；`run_pending_jobs` 直接读已恒为最新的 `wiki_workspace/current/<feature>/knowledge-base`。`sweep_all` 的 DB-hash 仍决定 **何时** 重新 import，目录的 **新鲜度** 由 Projector 保证——两者职责清晰分离。report 文件不进入 OpenViking，不触发 OpenViking job。

---

## 5. 内容决策（吸收退役的旧 M12）

旧 M12 的三类不再是"同步 source_type"，而是"被 import 的 feature 目录里放不放"的内容问题，在本里程碑一并定：

| 旧 source_type | 新归属 |
|---|---|
| `feature_readme` | 作为 `<feature>/README.md` 投影，供 opencode / 本地文件视图使用；默认不放进 `knowledge-base/`，因此不参与 OpenViking 召回，除非后续明确验收需要 |
| `wiki_dir` | **作废**——OpenViking import `knowledge-base/` 目录本身，目录结构由 `add_resource(preserve_structure=True)` 自带，无需独立 source_type |
| `global_index` | report-index 随 report 退出 OV 作废；repo-index 属延后代码仓；feature 级概览已有 per-feature `README.md` + manifest。**默认不再单独造全局索引文件**，除非后续验证 opencode 确实需要 |

---

## 6. 任务拆分（开发实现 + 架构 review/验收）

- **A1**：抽取可复用投影单元（单文档 / 单报告 / 单 feature index / manifest），与现有 exporter 渲染对齐；全量 `export_current` 改为复用这些单元（bootstrap/对账路径）。
- **A2**：实现 Projector 的增量操作（write/delete/move/feature-prune），每文件原子替换。
- **A3**：接线——采用 §3 A 的 `session.info` 暂存 + commit 后统一 drain，在各写 service 记录事件，API route 提交后 drain。
- **A4**：opencode 去耦合（删 `export_current` 活调用，保留 bootstrap 守卫）。
- **A5**：m11 去桥接（若有）。
- **A6**：内容决策落地（§5：feature_readme 投影与否、关掉 global_index）。
- **A7（review 补齐）**：启动 bootstrap 接线；投影失败吞掉并发事件、不继续 enqueue；report projection 事件接入 report API；feature create 使用 `feature_created`；per-feature rebuild 去掉先删目录空窗；legacy 兼容入口先投影再 enqueue。
- **A8（feature 删除竞态）**：真实 OpenViking 验证显示：`add_resource` task 仍在 `running` 时对同 root URI 调 `delete_resource` 会抛 `ConflictError: Resource is being processed`。因此 feature archive/delete 不直接硬删 processing 中资源；CodeAsk 将同一个 `wiki_feature` running job 覆盖为 `op=delete + delete_deferred_until_task_done`，等待旧 task 完成/队列 drain 后转为 pending delete，再调用 `delete_resource`。这样避免 embedding 处理中异常，同时保证已删除 feature 最终从 OpenViking 清理。
- **A9（定时远端对账兜底）**：2026-06-02 已用官方 HTTP SDK 验证 `AsyncHTTPClient.ls("viking://resources/codeask/wiki", simple=True)` 能列出 OpenViking 中现存 feature root URI；官方 filesystem/API 文档也把 `ls viking://resources/` 作为资源枚举入口。每小时 `scheduled_add_resource_sweep` 应先执行一次远端对账：读取 DB 中 active/current feature slug 集合，与 OpenViking 远端 wiki root 下的 slug 集合比较；对 `remote_slugs - active_slugs` enqueue `wiki_feature op=delete`。若对应 job 正在 running upsert，则复用 A8 deferred delete；若已有 delete pending/running/failed，不重复创建。`ls` 失败只写 warning summary，不阻断正常 add_resource sweep。官方资源文档确认 `add_resource(to=...)` 在目标已存在时走 incremental update，`watch_interval > 0` 可创建 watch task；但本阶段先落 CodeAsk 每小时 sweep + add_resource / remote delete 对账，OpenViking watch 作为后续计划，不在本次实现。
- **A10（最小化持久化 wiki 文件改动）**：2026-06-02 实测 `sweep_all(force_enqueue=True)` 对同一 `knowledge-base/` 目录重复 `add_resource` 后，OpenViking 仍新建约 390 条 Embedding 队列消息；因此必须减少 CodeAsk 对持久化 wiki 文件的无意义重写。常规 wiki 结构事件不得用 `rebuild_feature()` 作为默认路径；只允许修改受影响的 `knowledge-base/*.md`、必要的 `<feature>/README.md` 和 `_manifest.json`。`rebuild_feature()` 仅保留给 cold bootstrap / explicit repair / feature restore 这类兜底路径。新建、删除、移动、重命名、恢复 wiki 节点必须做 targeted projection，并用 mtime/content 断言未受影响文件不变。

---

## 7. 验收闸门
- [ ] wiki 文档 publish / rollback / restore → `knowledge-base/<path>.md` 内容为当前版本；draft save/delete 不生成文件、不触发 OpenViking
- [ ] document node create 未 publish 时不生成正文 md；只刷新 feature README / manifest
- [ ] wiki 文档删、节点 rename/move/subtree move/delete/restore、promotion、import apply、报告引用变更 → 磁盘 `wiki_workspace/current/` 对应文件**实时**正确（针对性，非全量重建）
- [ ] node rename/move/subtree move 后旧磁盘路径不存在，新路径存在，内容不丢
- [ ] 单文件写为原子替换；无活路径 `rmtree` 整树
- [ ] full rebuild / bootstrap 与增量写互斥，不互相覆盖
- [ ] opencode 会话启动不再触发 export；冷启动空目录能 bootstrap
- [ ] OpenViking sync 不触发 export，纯读 `wiki_workspace/current/<feature>/knowledge-base`；**"发布 wiki 但从未开 opencode" 也能正确同步到 OV**（针对 §0 失效模式的集成测试）
- [ ] "改 wiki 后未开 opencode，sync 推上去的是新内容、非旧快照"集成测试通过
- [ ] OpenViking import 路径只允许 `knowledge-base/`；`problem-reports/` 不进入 OpenViking，report 变化不触发 OpenViking job
- [ ] feature archive/delete 时，若 OpenViking upsert task 正在 embedding，sync job 记录 deferred delete，不立即调用 `delete_resource`；旧 task 完成后执行 delete，避免 OpenViking `ConflictError: Resource is being processed`
- [ ] 每小时 scheduled refresh 对账 OpenViking `viking://resources/codeask/wiki` 下的远端 feature roots；远端存在但 DB active/current 不存在的 feature 自动 enqueue delete，并复用 deferred delete / retry 语义
- [ ] 常规 wiki 结构变更遵守最小化持久化文件改动原则：未受影响的 `knowledge-base/*.md` 文件 content 与 mtime 均不变；不得因为新建/删除/移动/重命名单个 wiki 而重写整个 feature 的 `knowledge-base`
- [ ] `rebuild_feature()` 只允许在 cold bootstrap / explicit repair / feature restore 等兜底路径使用；`node_created` / `node_moved` / `node_deleted` / `node_restored` / `feature_metadata_changed` / `report_projection_changed` 不再默认调用 feature 级 rebuild
- [ ] `document_published` 只写当前文档 md + 必要索引文件；draft save/delete 不写持久化 wiki 文件、不触发 OpenViking
- [ ] `node_created` 未 publish 时不创建正文 md；只刷新必要索引文件，不触发 OpenViking add_resource
- [ ] `node_deleted` 只删除被删文档/子树对应 md，并清理空目录；其他 md 不重写
- [ ] `node_moved` / rename 只移动/重写受影响子树对应 md；同 feature 其他 md 不重写
- [ ] `node_restored` 只恢复受影响节点对应 md；同 feature 其他 md 不重写
- [ ] `feature_metadata_changed` 只刷新 `<feature>/README.md` / `_manifest.json`，不触碰 `knowledge-base/*.md`，不触发 OpenViking add_resource
- [ ] feature update 刷新 README / manifest；feature 归档/删除只清该 feature 子树，不误删他者；restore 后重建该 feature 子树
- [ ] 投影失败有 `wiki_workspace_projection_failed` 事件 / 日志和可 repair 路径；失败时不继续基于旧目录 enqueue OpenViking
- [ ] 内容决策（§5）有结论：feature_readme 投影到 `<feature>/README.md`；global_index 关闭或显式保留并更新设计 §4
- [ ] 管理员"重建/对账"动作可全量重建并与增量结果一致（幂等）
- [ ] 后端 / 前端 / e2e 全绿，lint / 类型 clean
- [ ] 文档诚实化：`design/openviking-integration.md §4`、`plans/acceptance-checklist.md` 对 feature_readme/wiki_dir/global_index 的状态更新为"knowledge-base 目录 import 取代 / 见 m12"

---

## 8. A10 实施 Checklist

- [ ] C1：补投影最小化测试工具，记录 `knowledge-base/*.md` 的 path/content/mtime_ns 快照，断言未受影响文件不变。
- [ ] C2：`document_published`：验证只写当前文档 md，其他 md 不变；仍 enqueue 当前 feature 的 OpenViking upsert。
- [ ] C3：`node_created`：未 publish 的 document/folder 只刷新 README/manifest；不创建正文 md，不 enqueue OpenViking upsert。
- [ ] C4：`node_deleted`：删除单文档只删除该 md；删除 folder 子树只删除子树 md；同 feature 其他 md content/mtime 不变；仍 enqueue 当前 feature upsert。
- [ ] C5：`node_moved` / rename：移动或重命名单文档只移动该 md 并更新 front matter；移动 folder 子树只移动/更新子树 md；同 feature 其他 md content/mtime 不变；仍 enqueue 当前 feature upsert。
- [ ] C6：`node_restored`：只恢复受影响节点对应 md；同 feature 其他 md content/mtime 不变；仍 enqueue 当前 feature upsert。
- [ ] C7：`feature_metadata_changed`：只刷新 `<feature>/README.md` 与 `_manifest.json`；`knowledge-base/*.md` content/mtime 不变；不 enqueue OpenViking upsert。
- [ ] C8：`report_projection_changed`：只更新 `problem-reports/` 文件；不触碰 `knowledge-base/*.md`，不 enqueue OpenViking upsert。
- [ ] C9：保留 `rebuild_feature()` 用于 bootstrap / repair / feature restore；常规事件分发中移除默认 rebuild。
- [ ] C10：真实 e2e：创建测试 feature，依次执行 publish、create node、rename、move、delete、restore、feature metadata update、report status update；每步采集持久化 wiki 快照并核对 OpenViking sync job 是否符合预期。
- [ ] C11：真实 OpenViking 观测：对只改 README/manifest 的操作确认不会新增 OpenViking job；对单文档变更确认只由 CodeAsk 入队一次 feature upsert，且持久化目录未产生无关文件 mtime 变化。
