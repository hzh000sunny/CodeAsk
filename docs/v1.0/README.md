# CodeAsk 文档 — v1.0

| 字段 | 值 |
|---|---|
| 版本 | v1.0 |
| 起始日期 | 2026-04-29 |
| 状态 | Active |
| 主题 | 初始 MVP — 知识库 + 代码混合问答 |
| 当前实现进度 | `foundation`、`wiki-knowledge`、`code-index`、`agent-runtime` 已完成；下一阶段 `frontend-workbench` |

## 目录结构

```text
v1.0/
├── README.md                 ← 本文件（版本元信息和导航）
├── prd/
│   └── codeask.md            ← 产品需求文档（PRD），唯一产品契约
├── design/                   ← 系统设计文档（SDD），15 份
│   ├── overview.md
│   ├── agent-runtime.md
│   ├── debugging-workflow.md
│   ├── wiki-search.md
│   ├── code-index.md
│   ├── evidence-report.md
│   ├── tools.md
│   ├── llm-gateway.md
│   ├── frontend-workbench.md
│   ├── api-data-model.md
│   ├── session-input.md
│   ├── deployment-security.md
│   ├── testing-eval.md
│   ├── metrics-collection.md
│   └── dependencies.md
├── plans/                    ← 实现计划（拆 SDD → bite-sized TDD task）
│   ├── roadmap.md
│   ├── foundation.md
│   ├── wiki-knowledge.md
│   ├── code-index.md
│   ├── agent-runtime.md
│   ├── agent-runtime-handoff.md
│   ├── frontend-workbench.md
│   ├── metrics-eval.md
│   └── deployment.md
└── specs/                    ← 早期草稿 / 过程性产物
    └── codeask-initial-draft.md
```

## 实现进度

| Plan | 状态 | 备注 |
|---|---|---|
| `foundation` | 已完成 | tag：`foundation-v0.1.0` |
| `wiki-knowledge` | 已完成 | tag：`wiki-knowledge-v0.1.0`；Alembic head 到 `0005` |
| `code-index` | 已完成 | tag：`code-index-v0.1.0`；Alembic head 到 `0006` |
| `agent-runtime` | 已完成 | tag：`agent-runtime-v0.1.0`；Alembic head 到 `0012`；REST + SSE API 已暴露 |
| `frontend-workbench` | 下一阶段 | 从 `plans/frontend-workbench.md` 开始，消费 agent-runtime 的 REST + SSE |
| `metrics-eval` | 未开始 | 替换 `AuditWriter` stub 为真实 `audit_log` 落表 |
| `deployment` | 未开始 | 前置 plan 完成后收口部署 |

## 推荐阅读顺序

| 你是 | 先读 | 再读 |
|---|---|---|
| 新人入门 | `prd/codeask.md` | `design/overview.md` |
| 想做架构决策 | `prd/codeask.md` §3-§4 | 对应 SDD 文档 |
| 想看历史推导 | `prd/codeask.md` §9 对齐说明 | `specs/codeask-initial-draft.md` |
| 想找特定主题（日志、检索、Agent…） | `design/overview.md` 的文档地图 | 对应 SDD 文档 |

## PRD vs SDD 关系

| | PRD | SDD |
|---|---|---|
| 文件 | `prd/codeask.md` | `design/*.md` |
| 回答的问题 | 为谁 / 为什么 / 做什么 / 不做什么 | 怎么实现 |
| 变更频率 | 低（产品契约） | 中（实施学到新东西可改） |
| 冲突时谁赢 | **PRD 赢** | SDD 应同步更新 |

## 当前对齐状态

PRD v1.0 推翻了 `design/` 中的若干早期判断（详见 PRD §9 对齐表）。当前 `design/` 下的 SDD 已按对齐表完成更新；后续若 PRD 再变更，SDD 应同步更新。

## 版本演进

本版本的演进规则见 `prd/codeask.md` 末尾"文档维护"小节，以及顶层 `../README.md`。
