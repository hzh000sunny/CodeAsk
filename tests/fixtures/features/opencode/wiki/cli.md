# OpenCode CLI -- 入口点与命令系统

## 概述

OpenCode 的命令行入口位于 `packages/opencode/src/index.ts`（247 行），是整个 CLI 系统的中枢。它负责进程初始化、中间件调度、命令注册、错误处理和进程生命周期管理。底层使用 [yargs](https://yargs.js.org/) 构建命令行解析框架。

---

## 启动流程图

```
┌─────────────────────────────────────────────────────────────────┐
│                      进程启动 (process)                          │
│                   ensureProcessMetadata("main")                  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  注册全局错误处理                                                 │
│  · unhandledRejection → 日志记录                                 │
│  · uncaughtException  → 日志记录                                 │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  解析命令行参数                                                   │
│  hideBin(process.argv) → 过滤前两个参数 (node binary, script)     │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  构建 yargs CLI 实例                                              │
│  · parserConfiguration: {"populate--": true}                    │
│  · scriptName: "opencode", wrap: 100                            │
│  · 注册所有全局选项和中间件                                        │
│  · 注册全部 24 个命令                                            │
│  · .strict() 启用严格模式                                        │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  执行启动中间件 (middleware)                                      │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ 1. --pure 标志 → OPENCODE_PURE=1                            ││
│  │ 2. 初始化日志系统                                             ││
│  │ 3. 启动堆内存监控 (HeapProfiler)                              ││
│  │ 4. 设置进程环境变量                                           ││
│  │ 5. 记录启动信息                                               ││
│  │ 6. 一次性 JSON→SQLite 数据库迁移                              ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  路由到具体命令处理程序                                            │
│  · 如果是 -h/--help → 特殊输出路径 (显示 Logo)                    │
│  · 否则 → cli.parse() 标准解析                                   │
└─────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
              ┌──────────┐           ┌──────────────┐
              │  成功执行  │           │  错误处理     │
              │  命令逻辑  │           │  try/catch   │
              └──────────┘           └──────────────┘
                                            │
                                            ▼
                                    ┌─────────────────┐
                                    │ finally:         │
                                    │ process.exit()   │
                                    │ (清理子进程)      │
                                    └─────────────────┘
```

---

## 启动中间件管线

所有命令在执行具体 handler 之前，都会经过同一个中间件函数。该中间件按顺序执行以下步骤：

### 1. Pure 模式（外挂隔离）

```bash
opencode --pure  # env: OPENCODE_PURE=1
```

`--pure` 标志设置环境变量 `OPENCODE_PURE=1`，使 opencode 在无外部插件的环境中运行，仅加载内置功能。

### 2. 日志初始化

日志级别的判断逻辑：

| 条件 | 级别 |
|------|------|
| `--log-level DEBUG` 明确指定 | `DEBUG` |
| `--log-level INFO` 明确指定 | `INFO` |
| `--log-level WARN` 明确指定 | `WARN` |
| `--log-level ERROR` 明确指定 | `ERROR` |
| 本地开发安装 (`Installation.isLocal()`) | `DEBUG` |
| 生产环境安装（默认） | `INFO` |

日志输出目标由 `--print-logs` 控制：指定时直接输出到 `stderr`，否则仅写入日志文件。

### 3. 堆内存监控

`Heap.start()` 每 60 秒检查一次进程内存使用量（RSS）。当 RSS 超过 2GB 上限且 `OPENCODE_AUTO_HEAP_SNAPSHOT` 环境变量已设置时，自动生成 V8 堆快照文件，用于后续内存泄漏分析。

快照文件路径：`{Global.Path.log}/heap-{pid}-{timestamp}.heapsnapshot`

### 4. 环境变量注入

中间件注入以下环境变量，供子进程和内部模块识别运行上下文：

| 变量 | 值 | 说明 |
|------|-----|------|
| `AGENT` | `1` | 标识运行在 agent 模式 |
| `OPENCODE` | `1` | 标识处于 opencode 运行时 |
| `OPENCODE_PID` | `<pid>` | 当前进程 PID |

### 5. 启动信息日志

记录启动诊断信息：版本号、完整命令行参数、进程角色（固定为 `"main"`）、运行 ID。

### 6. 一次性 JSON 到 SQLite 数据库迁移

这是中间件中执行的最重操作。流程如下：

1. 检查标记文件 `{Global.Path.data}/opencode.db` 是否存在
2. 若不存在（即首次启动），执行一次性迁移
3. 在 TTY 终端上显示彩色进度条（橙色 `■` 填充），非 TTY 输出 `sqlite-migration:{percent}` 纯文本进度
4. 迁移过程依次处理 7 类数据：
   - **Projects** (`project/*.json`)
   - **Sessions** (`session/*/*.json`)
   - **Messages** (`message/*/*.json`)
   - **Parts** (`part/*/*.json`)
   - **Todos** (`todo/*.json`)
   - **Permissions** (`permission/*.json`)
   - **Session Shares** (`session_share/*.json`)
5. 每类数据以 1000 条为一批次进行批量插入，使用 `BEGIN TRANSACTION` / `COMMIT` 包裹全部写入
6. 迁移前启用 SQLite 性能优化：`WAL` 日志模式、`synchronous=OFF`、`cache_size=10000`、`temp_store=MEMORY`
7. 迁移完成后输出统计信息

进度条格式（TTY 终端）：

```
■■■■■■■■■■■■■■■■■■■■■■■･･･････････  67%  sessions    1234/5678
```

迁移遵循严格的外键顺序：Projects → Sessions → Messages → Parts，确保引用完整性。孤立的 session、todo、permission、share 数据会被跳过并记录警告。

迁移完成后写入标记文件，后续启动跳过此步骤。

---

## 完整命令列表

### 核心命令

| 命令 | 描述 |
|------|------|
| `run [message..]` | 运行 opencode 会话，支持非交互模式（默认）、交互模式（`--interactive`）和远程附加模式（`--interactive --attach`）。支持 `--command` 执行斜杠命令、`--format json` 输出原始事件流、`--continue`/`--session` 恢复会话、`--fork` 在继续前分叉会话 |
| `generate` | 从服务端 OpenAPI 规范生成带 `x-codeSamples` 示例的 SDK 代码，经 prettier 格式化后输出到 stdout |
| `tui [project]` | 启动全功能 TUI 交互界面（`opencode tui`），支持 `--model`、`--agent`、`--continue`、`--session` 等参数 |
| `attach <url>` | 连接到正在运行的 opencode 服务器（如 `http://localhost:4096`）并在 TUI 模式下交互 |

### 服务端命令

| 命令 | 描述 |
|------|------|
| `acp` | 启动 ACP（Agent Communication Protocol）服务器，通过 stdin/stdout 的 NDJSON 流与 Agent 代理通信 |
| `mcp` | MCP（Model Context Protocol）服务器管理。子命令：`list`（列出服务器及状态）、`auth`（OAuth 认证）、`logout`（移除 OAuth 凭据）、`add`（添加 MCP 服务器）、`debug`（调试 OAuth 连接） |
| `serve` | 启动无头 HTTP API 服务器，监听指定端口，支持 `--hostname`、`--port`、`--mdns` 等网络选项。实例按请求的 `x-opencode-directory` 头按需加载 |
| `web` | 启动 opencode 服务器并自动打开 Web 界面。显示本地访问 URL、网络 IP 访问 URL、mDNS 地址 |

### 账户与提供者

| 命令 | 描述 |
|------|------|
| `console` | 账户/控制台管理。子命令：`login`（登录控制台）、`logout`（退出登录）、`switch`（切换活跃组织）、`orgs`（列出组织）、`open`（在浏览器中打开活跃账户） |
| `providers` | AI 提供商管理。子命令：`list`（列出提供商和凭据）、`login`（登录提供商）、`logout`（退出提供商登录） |
| `models [provider]` | 列出所有可用模型，可按提供商 ID 筛选。支持 `--verbose`（显示成本等元数据）、`--refresh`（刷新 models.dev 缓存） |

### Agent 与会话管理

| 命令 | 描述 |
|------|------|
| `agent` | Agent 管理。子命令：`create`（创建新 agent，支持指定目录、模式、权限、模型）、`list`（列出所有可用 agent） |
| `session` | 会话管理。子命令：`delete <sessionID>`（删除指定会话）、`list`（列出会话，支持 `--limit` 和 `--format` 参数） |
| `export [sessionID]` | 将会话数据导出为 JSON 格式。支持 `--redact`（脱敏处理敏感信息） |
| `import <file>` | 从 JSON 文件或分享 URL 导入会话数据 |
| `stats` | 显示 token 使用量和成本统计。支持 `--days`（最近 N 天）、`--tools`（工具使用排名）、`--models`（模型统计）、`--project`（按项目筛选） |

### GitHub 集成

| 命令 | 描述 |
|------|------|
| `github` | GitHub Agent 管理。子命令：`install`（安装 GitHub Agent）、`run`（运行 GitHub Agent，支持 `--token` 和 `--event` 参数） |
| `pr <number>` | 拉取并检出 GitHub Pull Request 分支，然后运行 opencode |

### 插件与系统维护

| 命令 | 描述 |
|------|------|
| `plugin <module>`（别名 `plug`） | 安装 npm 插件并更新配置文件。支持 `--global`（全局安装）、`--force`（替换已有版本） |
| `upgrade [target]` | 升级 opencode 到最新版本或指定版本。支持多种安装方式：`curl`、`npm`、`pnpm`、`bun`、`brew`、`choco`、`scoop` |
| `uninstall` | 卸载 opencode 并移除所有相关文件。支持 `--keep-config`（保留配置文件）、`--keep-data`（保留会话数据和快照） |
| `db` | 数据库工具。子命令：`$0 [query]`（交互式 sqlite3 shell 或执行 SQL 查询，支持 `--format json|tsv`）、`path`（打印数据库文件路径）、`migrate`（手动触发 JSON 到 SQLite 的数据迁移） |

### 调试命令

| 命令 | 描述 |
|------|------|
| `debug info` | 显示调试信息 |
| `debug paths` | 显示全局路径（data、config、cache、state） |
| `debug agent <name>` | 显示指定 agent 的配置详情 |
| `debug config` | 显示解析后的完整配置 |
| `debug file search <query>` | 按查询搜索文件 |
| `debug file read <path>` | 以 JSON 格式读取文件内容 |
| `debug file status` | 显示文件状态信息 |
| `debug file list <path>` | 列出目录中的文件 |
| `debug file tree [dir]` | 显示目录树（限制 200 项） |
| `debug lsp diagnostics <file>` | 获取文件的 LSP 诊断信息 |
| `debug lsp symbols <query>` | 搜索工作区符号 |
| `debug lsp document-symbols <uri>` | 获取文档内的符号 |
| `debug rg` | Ripgrep 调试工具 |
| `debug scrap` | 列出所有已知项目 |
| `debug skill` | 列出所有可用技能 |
| `debug snapshot track` | 跟踪当前快照状态 |
| `debug snapshot patch <hash>` | 显示指定快照哈希的补丁 |
| `debug snapshot diff <hash>` | 显示指定快照哈希的差异 |
| `debug startup` | 打印启动时序信息 |
| `debug wait` | 无限等待（用于调试目的） |

---

## 全局选项

通过 yargs 注册的全局选项，适用于所有命令：

| 选项 | 别名 | 类型 | 描述 |
|------|------|------|------|
| `--help` | `-h` | flag | 显示帮助信息 |
| `--version` | `-v` | flag | 显示版本号 |
| `--print-logs` | — | boolean | 将日志输出到 stderr |
| `--log-level` | — | string | 日志级别：`DEBUG`、`INFO`、`WARN`、`ERROR` |
| `--pure` | — | boolean | 在无外部插件的纯净模式下运行 |

此外：
- `--completion` 生成 Shell 自动补全脚本
- `--` 标记后续参数为命令的额外参数（`populate--: true`）

---

## 错误处理策略

### 全局异常捕获

```typescript
process.on("unhandledRejection", (e) => {
  Log.Default.error("rejection", { e: errorMessage(e) })
})

process.on("uncaughtException", (e) => {
  Log.Default.error("exception", { e: errorMessage(e) })
})
```

全局捕获未处理的 Promise 拒绝和未捕获的异常，将其记录到日志系统，避免进程静默崩溃。

### yargs 层面的失败处理

`.fail()` 回调处理三类场景：

| 场景 | 检测方式 | 行为 |
|------|----------|------|
| 未知参数 | `msg.startsWith("Unknown argument")` | 显示帮助信息 |
| 参数不足 | `msg.startsWith("Not enough non-option arguments")` | 显示帮助信息 |
| 无效值 | `msg.startsWith("Invalid values:")` | 显示帮助信息 |
| 其他错误 | `err` 存在 | 抛出异常，由外层 catch 处理 |

### 逐级降级的错误格式化

捕获异常后，按以下策略依次尝试格式化错误信息：

1. **对象信息收集**：根据异常类型提取不同数据
   - `NamedError` 实例 → 提取 `toObject()` 中的数据
   - `Error` 实例 → 提取 `name`、`message`、`cause`、`stack`
   - `ResolveMessage`（Bun 模块解析错误）→ 提取 `code`、`specifier`、`referrer`、`position`、`importKind`

2. **分级错误格式化**（`FormatError` 函数）：
   - `CliError`（命令行域错误）→ 提取消息，设置退出码
   - `MCPFailed` → 提示 MCP 服务器故障
   - `AccountServiceError` / `AccountTransportError` → 提取消息
   - `ProviderModelNotFoundError` → 列出建议的替代模型
   - `ProviderInitError` → 提示检查凭据和配置
   - `ConfigJsonError` → 指出 JSON(C) 格式问题
   - `ConfigDirectoryTypoError` → 提示目录命名拼写错误
   - `ConfigFrontmatterError` → 配置的前置元数据错误
   - `ConfigInvalidError` → 列出所有配置校验问题及路径
   - `UICancelledError` → 返回空字符串（用户取消操作）

3. **兜底处理**：如果 `FormatError` 返回 `undefined`，则输出通用错误信息，提示用户查看日志文件

4. **退出码**：错误时设置 `process.exitCode = 1`

### 自定义帮助显示

帮助信息通过 `show()` 函数输出，判断逻辑：
- 若输出以 `"opencode "` 开头 → 直接输出到 stderr
- 否则 → 先输出 Logo，再输出帮助文本到 stderr

---

## 数据库迁移过程（详细）

### 触发条件

中间件检查标记文件 `{Global.Path.data}/opencode.db` 是否存在。不存在时执行迁移，迁移后文件自然存在，避免重复执行。此外可通过 `opencode db migrate` 手动触发。

### 数据源

从 `{Global.Path.data}/storage/` 目录读取旧版 JSON 文件，按 glob 模式扫描：

```
storage/
├── project/*.json        → projects
├── session/*/*.json      → sessions (目录名即 projectID)
├── message/*/*.json      → messages (目录名即 sessionID)
├── part/*/*.json         → parts (目录名即 messageID)
├── todo/*.json           → todos (文件名即 sessionID)
├── permission/*.json     → permissions (文件名即 projectID)
└── session_share/*.json  → shares (文件名即 sessionID)
```

### 迁移策略

1. **预扫描**：并行扫描全部 7 类文件，获取完整文件清单
2. **批量读取**：每批 1000 个文件，使用 `Promise.allSettled` 并发读取
3. **批量写入**：在单个事务内，每批 1000 条插入，使用 `INSERT ... ON CONFLICT DO NOTHING` 实现幂等
4. **外键顺序**：严格遵循 Projects → Sessions → Messages → Parts 的顺序，确保外键引用的主键先于外键产生
5. **孤儿数据**：跳过无法关联父记录的孤儿数据（如 session 关联的 project 不存在），记录警告日志
6. **SQLite 优化**：
   - `PRAGMA journal_mode = WAL`（写入前日志，提升并发写入性能）
   - `PRAGMA synchronous = OFF`（关闭同步写入，大幅提升速度）
   - `PRAGMA cache_size = 10000`（增大页面缓存）
   - `PRAGMA temp_store = MEMORY`（临时表使用内存）

### 进度报告

- **TTY 终端**：彩色进度条 `■･･･ 67% sessions 1234/5678`，橙色进度，灰色统计
  - 动画控制：光标隐藏（`\x1b[?25l`），仅在百分比变化时重绘
  - 迁移完成后恢复光标（`\x1b[?25h`）
- **非 TTY 环境**：纯文本 `sqlite-migration:{percent}`，避免控制码污染日志

### 迁移结果

迁移完成后输出统计信息，包括：
- 各类数据的迁移数量（projects、sessions、messages、parts、todos、permissions、shares）
- 错误数量（最多报告前 20 条）
- 总耗时（毫秒）

---

## 进程生命周期

### 角色标识

```typescript
const processMetadata = ensureProcessMetadata("main")
```

`ensureProcessMetadata("main")` 将当前进程标识为 **主进程**（role = `"main"`），区别于可能 fork 出的子进程。元数据包含：
- `processRole`：始终为 `"main"`
- `runID`：本次运行的唯一标识

### 启动日志

中间件记录的结构化启动日志包含：
- `version`：安装版本号
- `args`：原始命令行参数数组
- `process_role`：`"main"`
- `run_id`：运行 ID

### 退出策略

**关键设计**：`finally` 块中无条件调用 `process.exit()`。

原因：某些子进程（特别是 docker-container-based MCP servers）对 SIGTERM 等信号处理不当，除非使用 `docker run --init`。显式调用 `process.exit()` 确保不会遗留僵尸子进程。

执行流程：
```
try {
  ── 解析命令行并执行命令处理程序 ──
} catch (e) {
  ── 逐级降级的错误格式化 ──
  ── process.exitCode = 1 ──
} finally {
  process.exit()  // 100% 保证执行，清理所有子进程
}
```

---

## Yargs 配置详情

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `parserConfiguration` | `{ "populate--": true }` | `--` 后的参数填充到 `argv["--"]` 数组 |
| `scriptName` | `"opencode"` | 脚本名称，用于帮助信息 |
| `wrap` | `100` | 帮助文本最大列宽 |
| `help` | `"help"` | 帮助选项名 |
| `alias("help", "h")` | — | `-h` 等同 `--help` |
| `version` | 动态（`InstallationVersion`） | 版本选项 |
| `alias("version", "v")` | — | `-v` 等同 `--version` |
| `.strict()` | — | 严格模式：未知选项触发 `.fail()` |

---

## 架构要点总结

1. **单进程多模式**：同一个入口同时支持 TUI、无头服务器、ACP/MCP 协议服务器、headless session 执行等模式
2. **中间件驱动初始化**：所有启动逻辑集中在单个 yargs middleware 中，保证任何命令执行前初始化都已就绪
3. **自愈式错误处理**：5 层降级策略（原始异常 → NamedError → 特定格式 → 通用格式 → 兜底消息），确保所有错误都有可读输出
4. **幂等的数据库迁移**：以 `.db` 标记文件为哨兵，`ON CONFLICT DO NOTHING` 保证可重复执行
5. **强制退出保证**：`finally` 块执行 `process.exit()`，避免 MCP 等子进程僵尸化
6. **`--pure` 隔离模式**：通过环境变量控制插件加载，用于调试和纯净运行场景
7. **结构化启动日志**：每次启动记录版本、参数、角色、运行 ID，便于问题追踪和审计
