# Test Feature — opencode

## 元信息

| 字段 | 值 |
|---|---|
| 特性 slug | `opencode` |
| 显示名 | OpenCode |
| 上游仓库 | `https://github.com/anomalyco/opencode` |
| Git URL | `git@github.com:anomalyco/opencode.git` |
| 已锁定版本 | `1.14.48`（与 v1.0.4 验证版本一致；详见 `docs/v1.0.4/specs/opencode-1.14.48-phase0-spike.md`） |
| 上游主语言 | TypeScript / JavaScript |
| wiki 抓取日期 | 2026-05-20 |
| wiki 抓取来源 | `/home/hzh/wiki/opencode-docs` |

## Wiki 内容

`wiki/` 目录包含上游 opencode 项目的结构化文档 dump，覆盖 agent / cli / config / core / function / llm / lsp / mcp / permission / plugin / provider / server / session 等模块。可作为 CodeAsk Wiki 文档批量导入到该测试特性下，用于：

- Phase 0 / Phase 1 / Phase 2 真实 Wiki 同步链路
- RAG 召回基线（含真实业务 query "如何配置 opencode 的 mcp"、"opencode session 是怎么保存的" 等）
- 连续会话回归（围绕 opencode 主题多轮追问）
- v1.0.4 已有 opencode 主链路与本特性的天然契合验证

## 源码

源码不在 git 仓库中。开发者按需：

```bash
git clone git@github.com:anomalyco/opencode.git $CODEASK_REFERENCES_DIR/opencode
```

CodeAsk 内 `references/opencode/` 已在 `.gitignore` 中。代码仓注册到 CodeAsk 时使用上述上游 URL，或本地 `--source local_dir --local-path` 指向 clone 目录。

## 使用入口

- `docs/rules/test-features.md` — 全局使用约定
- `docs/v1.0.5/plans/phase-0-spike.md` §4 — 第一类样本（Feature Wiki + verified report 同步）
- `frontend/e2e/*-live.spec.ts` — 后续 live E2E 沿用本特性作为代码调查目标
