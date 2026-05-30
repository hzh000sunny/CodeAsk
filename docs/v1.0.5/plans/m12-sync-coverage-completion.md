# M12 — 同步覆盖补全（feature_readme / wiki_dir / global_index）

> 版本：v1.0.5（排期在 m11 之后；价值边际，可滑到后续版本）
> 状态：Planned（占位 + 决策记录，待 m11 的多-source 分派模式稳定后启动）
> 关联：[openviking-integration 设计 §3.1/§4](../design/openviking-integration.md) · [m11 代码仓同步](./m11-repo-openviking-sync.md) · [m10 同步任务 UX](./m10-sync-jobs-ux.md)
> 来源：2026-05-30 终验复盘——设计 §3.1 列了 6 种 `source_type`，实现只接了 `wiki_doc` / `report`；repo 已拆 m11，剩余 `feature_readme` / `wiki_dir` / `global_index` 设计了却从未实现。**这是架构拆任务时的遗漏**，本里程碑显式认领并排期，而非默默丢弃。

---

## 0. 缺口事实（已核对代码）

设计 §3.1 `source_type` 全集：`wiki_doc / wiki_dir / report / repo / feature_readme / global_index`。实现状态：

| source_type | 设计来源 | 实现 | 归属 |
|---|---|---|---|
| `wiki_doc` | §4 knowledge-base 节点 | ✅ 全接 | M5 |
| `report` | §4 verified 报告 | ✅ 全接（仅 verified，draft 有意排除）| M5 |
| `repo` | §4 `repos/<slug>/` | ❌ 缺失 | → m11 |
| **`feature_readme`** | §4 `features/<slug>/README.md` | ❌ `feature_readme_uri` 仅搜索侧反查路径用，从不同步 | **本里程碑** |
| **`wiki_dir`** | §3.1 注释 | ❌ 无 helper、无实现 | **本里程碑** |
| **`global_index`** | §4 三个全局目录（`feature-index.md` / `repo-index.md` / `report-index.md`）| ❌ 完全没有生成 / 同步 | **本里程碑** |

---

## 1. 决策：有意排在 repo 主线之后（2026-05-30 负责人认可）

这三类相对 `repo` 是**导航 / 概览增强**，价值边际，不构成 RAG-over-代码 的主链路：

- `feature_readme`：让 RAG 召回"特性概览"。价值中等，实现轻（与 `wiki_doc` 同路子，`_resolve_content` 加一个分派 + 复用 `feature_readme_uri`）。
- `wiki_dir`：目录级节点（如目录 README / 索引）。价值低，需先定"目录级资源到底灌什么"。
- `global_index`：三个全局目录文件，给 OpenViking 一张顶层地图（有哪些特性 / 仓库 / 报告）。价值取决于 OpenViking 是否真的消费这类"目录索引"——需先验证收益再投入（可能本就该砍）。

**排期理由**：① 依赖 m11 把 `_resolve_content` 的多-source 分派模式打稳，否则三类各写一遍重复脚手架；② v1.0.5 主价值（wiki/report/repo 进 RAG）由 m5/m6/m11 覆盖，这三类滑到后续版本不阻断主线。

**可砍信号**：若 m11 spike 或后续 live 验证表明 OpenViking 不消费 `global_index` 这类目录文件，则 `global_index` 直接从设计 §4 删除而非实现——避免造无人读的索引文件。

---

## 2. 任务拆分（待 m11 后细化，此处定骨架）

> 全部归属：开发实现 + 架构 review/验收；启动前由架构确认 `global_index` 是否保留。

### C-A `feature_readme` 同步
- 写路径 hook：Feature README 变更 → `enqueue(source_type="feature_readme", source_id=<feature_id>, viking_uri=feature_readme_uri(slug))`。
- 引擎 `_resolve_content` 加 `feature_readme` 分派：现查 Feature README 正文 upsert；Feature 删除 → tombstone。
- backfill 纳入所有 Feature README。

### C-B `wiki_dir` 同步（先定语义）
- 先决：目录级资源灌什么内容（目录 README？子节点清单？）——无明确产物则本项一并评估是否砍。
- 若保留：hook + 引擎分派 + uri helper（设计 §4 未给 wiki_dir 独立 uri，需补）。

### C-C `global_index` 三个目录文件（先验证收益）
- 先决：OpenViking 是否消费目录索引文件（B0/live 验证）。不消费 → 从设计 §4 删除并关闭本项。
- 若保留：生成 `feature-index.md` / `repo-index.md` / `report-index.md`（聚合现有主数据）→ 定时 sweep 重生并 upsert。

---

## 3. 即时已做的文档诚实化（不等本里程碑排期）
- [x] `acceptance-checklist.md` §3.2"仓库变更 hook 全部接入"误判已拆正（repo 内容同步 → m11 跟踪）。
- [x] `design/openviking-integration.md` §4 URI 表对 `feature_readme` / `wiki_dir` / `global_index` 标注"设计保留、实现推迟到 m12"，避免文档与实现继续矛盾。

---

## 4. 验收清单
- [ ] 启动前：架构确认 `global_index` / `wiki_dir` 保留还是砍；砍则更新设计 §4 并关闭对应子项
- [ ] `feature_readme`：变更 hook + 引擎分派 + backfill 全接；Feature README 进 OpenViking，`find` 可召回
- [ ] `feature_readme` 删除路径 tombstone 正确
- [ ] （若保留）`wiki_dir` 语义已定且实现，或已显式从设计删除
- [ ] （若保留）`global_index` 三文件生成 + sweep upsert，或已显式从设计删除
- [ ] 这三类任务在 m10 卡片自动走人话化展示，`display_name` 可读
- [ ] 后端 / 前端 / e2e 全绿，lint / 类型 clean
