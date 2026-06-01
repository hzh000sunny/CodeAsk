# M12 — Wiki workspace 写时增量持久化 / 去 opencode 耦合

> 版本：v1.0.5（排期在 m11 之后）
> 状态：Planned（方向已定 2026-06-01，待开发实现）
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
    knowledge-base/...        ← m11 的 add_wiki_feature 就 import 这棵
    problem-reports/verified|drafts/...
    index.md
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
- 在 wiki 写路径接钩子（文档增/改/删、节点移动/删除、promotion、import apply、报告引用变化）。
- opencode 去耦合：移除会话启动时的 `export_current()`，opencode 退化为纯读者。
- OpenViking sync 去桥接：不再触发任何 export，纯读。
- 吸收旧 M12 的内容决策（§5）。

**范围外**：
- OpenViking 客户端 / SDK（m11 已做）。
- 代码仓 → OpenViking（延后）。
- UI Wiki 搜索（m11 已定为纯 SQL）。

---

## 2. 目标设计：WikiWorkspaceProjector（写时增量）

新增组件（建议落在 `agent/opencode_compat/` 或 `wiki/` 下，需消费 wiki 主数据），契约：

- **投影布局与现有 exporter 完全一致**——复用 `_export_documents` / `_export_reports` / `_write_feature_index` / `_write_manifest` / `_relative_wiki_path` 的渲染与路径规则，保证 opencode/OV 看到的结构不变。把这些渲染逻辑从"全量遍历"中抽出为"针对单个文档/报告/feature"的可复用单元。
- **针对性操作**：
  - 文档 create/update → 渲染并写 `knowledge-base/<相对路径>.md`（**临时文件 + `os.replace` 原子替换**）。
  - 文档/节点 delete → 删对应文件 + 向上清理空目录。
  - 节点 move/rename → `os.replace` 旧→新路径。
  - 报告引用 add/remove/verified 翻转 → 在 `problem-reports/verified|drafts/` 下写/移/删对应文件。
  - feature 新建 → 建子目录；feature 归档/删除 → 只 `rmtree` 该 feature 子树。
  - 每次变更后刷新**该 feature 的 `index.md`** 与顶层 manifest 计数（manifest 可增量改或按需廉价重算）。
- **触发时机**：wiki DB 写 **提交成功之后**。失败的事务不得污染磁盘。
- **幂等**：每个投影操作可重复执行结果一致——这样 bootstrap / 对账重建能安全复用同一套单元。
- **去掉全量 rmtree 活路径**：`export_current()` 降级为：① 首次/空目录 bootstrap；② 管理员"重建/对账"兜底动作（怀疑漂移时手动跑一次，原子 rename 全量替换）。不再挂在 opencode 会话上。

---

## 3. 接线点（关键：今天没有集中事件）

`wiki/signals.py` 是文本分析工具、**不是事件总线**；wiki 写路径散在多个 service。两种接法，建议选 A：

- **A（推荐）「提交后 hook」**：在 wiki 写 service 提交后发一个轻量事件（feature_slug + 变更类型 + 受影响节点），Projector 订阅。一处订阅、多处发事件，避免把文件 IO 逻辑散进每个 service。需要发事件的写点：
  - `wiki/documents/service.py`（文档 CRUD）
  - `wiki/tree/service.py`（节点移动 / 删除）
  - `wiki/promotions/service.py`（current ↔ draft 提升）
  - `wiki/imports/service.py`（import apply）
  - `wiki/reports.py` / report 引用变更（`report_projection.py`）
- **B（不推荐）**：每个 service 直接调 Projector。耦合更重、易漏点。

> 设计抉择留给开发与架构确认：事件总线要不要做成通用 wiki 事件（未来 RAG / 审计也能复用），还是只为 workspace 投影做一个最小回调。

---

## 4. 消费方改造

- **opencode**：删除 `backend.py:149` 的 `export_current()`；会话启动只需确认目录存在（不存在则触发一次 bootstrap）。opencode 行为对用户无感（目录一直是最新）。
- **OpenViking sync（m11）**：移除任何"import 前触发 export"的桥接；`run_pending_jobs` 直接读已恒为最新的目录。`sweep_all` 的 DB-hash 仍决定 **何时** 重新 import，目录的 **新鲜度** 由 Projector 保证——两者职责清晰分离。

---

## 5. 内容决策（吸收退役的旧 M12）

旧 M12 的三类不再是"同步 source_type"，而是"被 import 的 feature 目录里放不放"的内容问题，在本里程碑一并定：

| 旧 source_type | 新归属 |
|---|---|
| `feature_readme` | 决定 Feature README 要不要作为一个文件投影进 `<slug>/`（如 `README.md` 或并入 `index.md`）。轻量，Projector 顺带产出即可 |
| `wiki_dir` | **作废**——目录结构随 `add_resource(preserve_structure=True)` 整目录 import 自带，无需独立处理 |
| `global_index` | report-index 随 report 退出 OV 作废；repo-index 属延后代码仓；feature 级概览已有 per-feature `index.md` + manifest。**默认不再单独造全局索引文件**，除非后续验证 OpenViking 确实消费目录索引 |

---

## 6. 任务拆分（开发实现 + 架构 review/验收）

- **A1**：抽取可复用投影单元（单文档 / 单报告 / 单 feature index / manifest），与现有 exporter 渲染对齐；全量 `export_current` 改为复用这些单元（bootstrap/对账路径）。
- **A2**：实现 Projector 的增量操作（write/delete/move/feature-prune），每文件原子替换。
- **A3**：接线——选定 hook 机制（§3 A/B），在各写 service 提交后发事件 / 调用。
- **A4**：opencode 去耦合（删 `export_current` 活调用，保留 bootstrap 守卫）。
- **A5**：m11 去桥接（若有）。
- **A6**：内容决策落地（§5：feature_readme 投影与否、关掉 global_index）。

---

## 7. 验收闸门
- [ ] wiki 文档增/改/删、节点移动、promotion、import apply、报告引用变更 → 磁盘 `wiki_workspace/current/` 对应文件**实时**正确（针对性，非全量重建）
- [ ] 单文件写为原子替换；无活路径 `rmtree` 整树
- [ ] opencode 会话启动不再触发 export；冷启动空目录能 bootstrap
- [ ] OpenViking sync 不触发 export，纯读；**"发布 wiki 但从未开 opencode" 也能正确同步到 OV**（针对 §0 失效模式的集成测试）
- [ ] "改 wiki 后未开 opencode，sync 推上去的是新内容、非旧快照"集成测试通过
- [ ] feature 归档/删除只清该 feature 子树，不误删他者
- [ ] 内容决策（§5）有结论：feature_readme 投影方式定；global_index 关闭或显式保留并更新设计 §4
- [ ] 管理员"重建/对账"动作可全量重建并与增量结果一致（幂等）
- [ ] 后端 / 前端 / e2e 全绿，lint / 类型 clean
- [ ] 文档诚实化：`design/openviking-integration.md §4`、`acceptance-checklist.md` 对 feature_readme/wiki_dir/global_index 的状态更新为"目录 import 取代 / 见 m12"
