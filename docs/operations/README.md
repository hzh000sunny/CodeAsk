# CodeAsk 运维文档

> 范围：安装后的部署、升级、数据目录、排障和验收。
> 状态：Active

根目录 [INSTALL.md](../../INSTALL.md) 只保留第一次上手和基础启动路径。本目录承载更细的运维说明，避免安装入口过长。

## 文档入口

| 文档 | 用途 |
|---|---|
| [data-directory.md](./data-directory.md) | 说明 `CODEASK_DATA_DIR` 的目录结构、备份重点和 key 规则 |
| [openviking-rag.md](./openviking-rag.md) | 说明 OpenViking Wiki RAG 的范围、同步、模型配置和排障 |
| [upgrade.md](./upgrade.md) | 说明已有部署升级、备份、验证和回滚流程 |
| [troubleshooting.md](./troubleshooting.md) | 常见启动、端口、前端、opencode 和工具链问题排查 |
| [deployment-checklist.md](./deployment-checklist.md) | 给人工或自动化部署使用的最小验收清单 |

跨版本的强约束仍以 [docs/rules/upgrade-compatibility.md](../rules/upgrade-compatibility.md) 为准。
