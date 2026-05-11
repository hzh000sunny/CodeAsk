# 升级兼容与数据目录规则

> 范围：跨版本规则
> 状态：Active

本文定义 CodeAsk 在版本升级、数据迁移、配置保留和回滚时必须长期遵守的稳定规则。

本规则约束：

- 安装和升级文档
- 后端启动与数据库迁移
- `CODEASK_DATA_DIR` 数据目录布局
- `CODEASK_DATA_KEY` 生命周期
- 前后端版本一致性
- 版本发布和验收清单

## 1. 基本原则

CodeAsk 的源码可以更新，依赖可以重装，前端可以重新构建，但用户数据目录不能被升级过程破坏。

升级过程必须满足：

1. 不删除、不重建、不覆盖用户的 `CODEASK_DATA_DIR`。
2. 不静默更换 `CODEASK_DATA_KEY`。
3. 不要求用户清空数据库才能升级。
4. 不允许前端和后端长期运行在不同源码版本。
5. 数据库 schema 变化必须通过 Alembic migration 表达。
6. 升级前必须有可恢复的备份。

## 2. 数据目录兼容规则

`CODEASK_DATA_DIR` 是 CodeAsk 的用户数据根目录，默认值为：

```text
~/.codeask
```

该目录至少包含：

```text
~/.codeask/
├── data.db
├── secrets/
│   └── data.key
├── wiki/
├── skills/
├── sessions/
├── repos/
├── index/
└── logs/
```

规则：

1. 升级不得删除整个数据目录。
2. 升级不得删除未知子目录。未来版本可能增加新的数据子目录，旧版本工具不能假设只存在当前目录。
3. 临时缓存、索引缓存可以重建，但源数据不能被清理。
4. 会话附件、Wiki 资源、仓库缓存和数据库之间的引用关系必须保持一致。
5. 如果未来需要改变物理目录结构，必须提供 migration 或兼容读取层。

## 3. `CODEASK_DATA_KEY` 规则

`CODEASK_DATA_KEY` 是本地敏感字段加密主密钥，当前用于加密 LLM API Key 和管理员会话签名相关能力。

从当前规则生效后，CodeAsk 支持将首次启动提供的 key 缓存在数据目录：

```text
<CODEASK_DATA_DIR>/secrets/data.key
```

读取优先级：

1. 如果环境变量 `CODEASK_DATA_KEY` 存在，优先使用环境变量。
2. 如果环境变量不存在，读取 `<CODEASK_DATA_DIR>/secrets/data.key`。
3. 如果两者都不存在，启动失败，提示首次启动必须显式提供 `CODEASK_DATA_KEY`。

缓存写入规则：

1. 首次启动时，如果用户提供了 `CODEASK_DATA_KEY` 且缓存文件不存在，CodeAsk 应把该 key 写入 `<CODEASK_DATA_DIR>/secrets/data.key`。
2. 缓存目录权限应为 `0700`。
3. 缓存文件权限应为 `0600`。
4. 如果缓存文件已存在且和环境变量一致，正常启动。
5. 如果缓存文件已存在但和环境变量不一致，必须拒绝启动。

禁止行为：

1. 不允许环境变量静默覆盖已经存在的缓存 key。
2. 不允许启动时自动生成 key 并悄悄进入生产使用。
3. 不允许删除缓存 key 后继续使用旧数据库。
4. 不允许把 key 写入仓库、日志、前端页面或 API 响应。

后续如果需要更换 key，必须提供独立 key rotation 流程。key rotation 必须读取旧 key、解密敏感字段、使用新 key 重新加密，再原子替换缓存 key。不能把“覆盖文件”当成 key rotation。

## 4. 备份规则

升级前必须备份整个 `CODEASK_DATA_DIR`，而不是只备份 `data.db`。

原因：

- `secrets/data.key` 决定数据库中敏感字段能否解密。
- `wiki/` 中可能包含 Markdown 资源和图片。
- `sessions/` 中包含会话附件和日志。
- `repos/` 中包含代码仓库缓存和 worktree 相关状态。
- `index/` 中可能包含可重建但耗时的索引数据。

最低备份内容：

```text
data.db
secrets/data.key
wiki/
sessions/
```

推荐备份内容：

```text
整个 CODEASK_DATA_DIR
```

## 5. 数据库迁移规则

CodeAsk 使用 Alembic 管理数据库 schema。

规则：

1. schema 变化必须新增 Alembic migration 文件，不允许只改 SQLAlchemy model。
2. migration 文件必须可以从上一发布版本顺序升级到当前版本。
3. migration 不能依赖开发者本机路径。
4. migration 不能删除用户数据，除非对应版本文档明确说明并提供备份 / 恢复方案。
5. 启动时允许自动执行 `upgrade head`，但正式部署文档必须要求升级前备份。
6. 后续应提供显式 `doctor / backup / migrate / version` 命令，减少正式环境对启动时自动迁移的依赖。

回滚规则：

1. 如果新版本尚未启动、migration 尚未执行，可以直接回滚代码。
2. 如果 migration 已执行，不能只回滚代码。
3. migration 已执行后的回滚必须恢复升级前备份的数据目录。
4. 不承诺任意版本的 Alembic downgrade 可安全恢复业务数据。

## 6. 前后端版本一致性

CodeAsk 当前不支持长期混用不同版本的前端和后端。

规则：

1. 单进程部署时，`frontend/dist` 必须由当前后端源码同一 commit 构建。
2. 开发联调时，前端分支和后端分支必须保持一致。
3. 版本发布时，前端构建产物、后端源码、Alembic migration 必须来自同一版本。
4. 后续可以引入 `/api/version` 和前端 build revision 校验，但在校验机制落地前，文档必须明确要求同版本部署。

## 7. 标准升级流程

已有部署升级到新版本时，必须按以下顺序：

1. 停止 CodeAsk 服务。
2. 确认当前 `CODEASK_DATA_DIR`。
3. 备份整个 `CODEASK_DATA_DIR`。
4. 拉取新源码或切换 release 分支 / tag。
5. 安装后端依赖。
6. 安装前端依赖。
7. 重新构建前端。
8. 使用原有 `CODEASK_DATA_DIR` 和原有 `CODEASK_DATA_KEY` 或缓存 key 启动服务。
9. 等待 Alembic migration 完成。
10. 执行健康检查。
11. 打开浏览器验证管理员登录、会话列表、设置页、Wiki 和报告页。
12. 执行当前版本要求的 smoke / E2E 验收。

## 8. 发布验收要求

每次发布前，版本验收清单必须覆盖：

1. 新增 migration 是否存在并通过测试。
2. 从旧数据目录升级到当前版本是否验证。
3. 是否至少在一份真实用户数据目录或其完整备份上执行过升级验证，而不只是空库或临时 seed 库。
4. 升级验证后，原有 `features`、`llm_configs`、`repos`、`system_settings`、Wiki 和 sessions 是否仍然可读。
5. 浏览器是否实际连接到目标 `CODEASK_DATA_DIR`，而不是临时测试目录。
6. 如果使用真实数据运行浏览器 E2E，是否限制为只读检查或已验证可清理的临时写操作。
7. `CODEASK_DATA_KEY` 是否不会被重置。
8. `secrets/data.key` 是否能支撑无 env 的二次启动。
9. env key 与缓存 key 冲突时是否拒绝启动。
10. 前端构建产物是否来自当前源码。
11. 升级失败时是否能通过恢复备份回到旧版本。
12. 安装文档和升级文档是否同步更新。

## 9. 后续工具化方向

以下能力属于后续版本，不阻塞当前规则生效：

- `uv run codeask doctor`：检查工具链、数据目录、数据库版本和前端构建产物。
- `uv run codeask backup`：生成带时间戳的数据目录备份。
- `uv run codeask migrate`：显式执行数据库 migration。
- `uv run codeask version`：输出后端版本、前端 build revision 和数据库 revision。
- `/api/version`：供前端检测前后端版本一致性。

这些工具落地前，文档中的手动流程是升级兼容的权威路径。
