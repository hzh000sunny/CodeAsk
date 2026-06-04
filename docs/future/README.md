# CodeAsk 未来功能规划

> 状态：Active
> 作用：承载**尚未明确排入某个版本号**、但已经形成稳定方向的未来功能规划，避免产品设计和技术思路在后续迭代中丢失。

## 目录定位

`docs/future/` 不属于某个具体发布版本。

它用于记录以下内容：

- 已经达成方向共识，但还未决定排入 `vN.M` 或 `vN.M.PATCH` 的能力。
- 明确需要长期跟踪的架构演进主题。
- 对外部参考项目的吸收结论，以及对 CodeAsk 的适配方向。

它**不替代**版本目录：

- 一旦某项能力被正式纳入某个版本，应在对应 `docs/vN.M/` 下补齐 `prd/`、`design/`、`plans/` 或 `specs/`。
- `docs/future/` 中的文档保留为设计前史和方向记录，不作为某个版本的最终契约。

## 当前规划主题

- [RAG 与知识处理增强路线](./rag-knowledge-pipeline.md)
- [OpenViking RAG 调研记录 2026-05-20](./openviking-rag-research-2026-05-20.md)
- [特性边界探测与上下文隔离](./scoped-context-boundary-probe.md)
- [外部 Agent Backend：Claude Code 与 opencode](./external-agent-backends.md)
- [CodeAsk × OpenCode 对接方案](./opencode-integration.md)（设计前史；当前 v1.0.4 落地契约见 `../v1.0.4/`）
- [OpenCode Bash 命令白名单规划](./opencode-bash-command-whitelist.md)
- [结构化思考链处理与上下文隔离](./structured-reasoning-handling.md)（设计前史；当前 v1.0.2 落地计划见 `../v1.0.2/plans/structured-reasoning.md`）
- ~~前端 UI 重构路线~~（2026-06-03 已提升为 v1.0.6 UI 主线，见 `../v1.0.6/plans/frontend-ui-restyle.md`）

## 使用规则

- 文件名按主题命名，使用小写短横线风格。
- 文档内容以“方向、边界、约束、候选方案、版本待定项”为主，不写成已承诺交付的版本计划。
- 若某项内容正式进入版本开发，应在对应版本文档中引用本目录，而不是直接把本目录当作版本计划执行。
