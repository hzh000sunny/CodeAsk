# OpenCode 工具系统 (Tool System)

## 概述

OpenCode 的工具系统是一个基于 Effect 框架的、可扩展的 LLM 工具调用基础设施。它将内置工具、自定义工具（来自配置文件和插件）统一管理，并根据模型和提供商的能力在运行时筛选和增强工具定义。

核心文件位于 `/home/hzh/wiki/opencode/packages/opencode/src/tool/` 目录下，主入口为 `registry.ts`（379 行）。

---

## 1. 核心架构

### 1.1 工具定义 (`Tool.Def`)

每个工具都遵循 `Tool.Def` 接口，定义于 `tool/tool.ts`：

```typescript
interface Def<Parameters, M extends Metadata> {
  id: string              // 工具唯一标识符
  description: string     // 传递给 LLM 的工具描述
  parameters: Parameters  // 参数 Schema（Effect Schema）
  execute(args, ctx): Effect<ExecuteResult<M>>  // 执行函数
  formatValidationError?(error): string  // 参数校验错误格式化函数
}
```

执行上下文 (`Context`) 包含：
- `sessionID` / `messageID` / `agent` — 当前会话与消息标识
- `abort` — 取消信号 (AbortSignal)
- `messages` — 会话消息列表（用于 read 工具注入 instruction）
- `metadata(input)` — 推送元数据（如流式输出进度）
- `ask(input)` — 触发权限询问（permission system）

### 1.2 工具信息 (`Tool.Info`)

`Tool.Info` 是将参数和元数据类型绑定在一起的工厂接口：

```typescript
interface Info<Parameters, M> {
  id: string
  init(): Effect<DefWithoutID<Parameters, M>>
}
```

### 1.3 工具注册表 (`ToolRegistry`)

`ToolRegistry` 是一个 Effect 服务（`@opencode/ToolRegistry`），对外暴露四个主要方法：

| 方法 | 返回类型 | 功能 |
|------|----------|------|
| `ids()` | `Effect<string[]>` | 获取所有工具 ID 列表 |
| `all()` | `Effect<Tool.Def[]>` | 获取所有工具定义（内置 + 自定义） |
| `named()` | `Effect<{ task, read }>` | 获取特定命名工具（task、read）的强类型定义 |
| `tools(model)` | `Effect<Tool.Def[]>` | 获取针对特定模型筛选和增强后的工具列表 |

---

## 2. 内置工具完整列表

### 2.1 文件操作工具

#### `read` — 读取文件

| 属性 | 值 |
|------|-----|
| ID | `read` |
| 描述文件 | `read.txt` |
| 参数 | `filePath` (绝对路径), `offset` (可选, 行偏移), `limit` (可选, 最大行数, 默认2000) |
| 功能 | 读取文件或目录内容。支持图片和 PDF 附件渲染。支持二进制文件检测。自动匹配相似文件名并提供纠正建议。配合 LSP 预热机制（后台触发诊断）。 |
| 权限 | `read` |

#### `write` — 写入/覆写文件

| 属性 | 值 |
|------|-----|
| ID | `write` |
| 描述文件 | `write.txt` |
| 参数 | `filePath` (绝对路径), `content` (文件内容) |
| 功能 | 创建或完全覆写文件。自动创建父目录。支持 BOM 检测。写后触发格式化（通过 Format 服务）和 LSP 诊断。发布 `File.Edited` 和 `FileWatcher.Updated` 总线事件。 |
| 权限 | `edit` |

#### `edit` — 字符串替换编辑

| 属性 | 值 |
|------|-----|
| ID | `edit` |
| 描述文件 | `edit.txt` |
| 参数 | `filePath` (绝对路径), `oldString` (要替换的文本), `newString` (替换后的文本), `replaceAll` (可选, 替换所有匹配项) |
| 功能 | 在文件中执行精确的字符串替换。使用多种容错匹配策略（9 种替换器链）：精确匹配、行尾裁剪匹配、块锚点匹配、空白规范化匹配、缩进灵活匹配、转义规范化匹配、裁剪边界匹配、上下文感知匹配、多次出现匹配。编辑操作按文件路径加锁（信号量），避免并发冲突。写后触发格式化与 LSP 诊断。 |
| 权限 | `edit` |

#### `apply_patch` — 应用补丁

| 属性 | 值 |
|------|-----|
| ID | `apply_patch` |
| 描述文件 | `apply_patch.txt` |
| 参数 | `patchText` (完整补丁文本) |
| 功能 | 解析并应用统一的 diff 补丁。支持 add、update、delete、move 四种块类型。通过 `Patch.parsePatch()` 解析 hunks，再逐一应用到文件。支持文件创建、内容修改、文件删除和文件重命名。适用于 GPT 系列模型（替代 edit + write）。 |
| 权限 | `edit` |

#### `glob` — 文件模式匹配

| 属性 | 值 |
|------|-----|
| ID | `glob` |
| 描述文件 | `glob.txt` |
| 参数 | `pattern` (glob 模式), `path` (可选, 搜索目录) |
| 功能 | 使用 ripgrep 的文件搜索能力按 glob 模式匹配文件。默认最多返回 100 个结果，按修改时间降序排列。 |
| 权限 | `glob` |

#### `grep` — 文件内容搜索

| 属性 | 值 |
|------|-----|
| ID | `grep` |
| 描述文件 | `grep.txt` |
| 参数 | `pattern` (正则表达式), `path` (可选, 搜索目录), `include` (可选, 文件类型过滤) |
| 功能 | 在文件内容中搜索正则模式。使用 ripgrep 进行高性能内容搜索。最多返回 100 个匹配结果，按文件修改时间降序排列。支持文件类型过滤。 |
| 权限 | `grep` |

### 2.2 执行工具

#### `shell` — 执行 Shell 命令

| 属性 | 值 |
|------|-----|
| ID | `shell` |
| 描述文件 | `shell/prompt.ts` |
| 参数 | `command` (Shell 命令), `description` (描述), `timeout` (可选, 毫秒), `workdir` (可选, 工作目录) |
| 功能 | 执行任意 shell 命令。支持 bash 和 PowerShell（Windows）。使用 tree-sitter 解析命令语法树，提取文件路径参数进行权限检查。流式输出实时推送到元数据。输出过长时自动截断并写入截断目录。支持超时和取消。 |
| 权限 | `shell` / `external_directory` |

#### `task` — 子代理任务

| 属性 | 值 |
|------|-----|
| ID | `task` |
| 描述文件 | `task.txt` |
| 参数 | `description` (简短描述), `prompt` (任务提示), `subagent_type` (子代理类型), `task_id` (可选, 续接之前的任务), `command` (可选, 触发命令) |
| 功能 | 启动子代理执行独立任务。通过 `Agent.list()` 获取可用代理列表并生成动态描述。创建新的会话作为子会话，继承父会话权限。支持 `task_id` 参数续接之前未完成的任务。任务结果包装在 `<task_result>` 标签中。 |
| 权限 | `task` |

### 2.3 交互工具

#### `question` — 向用户提问

| 属性 | 值 |
|------|-----|
| ID | `question` |
| 描述文件 | `question.txt` |
| 参数 | `questions` (Question.Prompt 数组) |
| 功能 | 向用户展示问题并收集答案。仅在 app/cli/desktop 客户端或通过 `OPENCODE_ENABLE_QUESTION_TOOL` 环境变量启用。支持自定义选项和多选。答案格式化返回：`"问题文本"="用户答案"`。 |
| 权限 | 无（内建交互） |

#### `todowrite` — 任务列表管理

| 属性 | 值 |
|------|-----|
| ID | `todowrite` |
| 描述文件 | `todowrite.txt` |
| 参数 | `todos` (Todo 项目数组: `{ content, status, priority }`) |
| 功能 | 创建和更新会话级待办事项列表。状态支持: `pending`、`in_progress`、`completed`、`cancelled`。优先级支持: `high`、`medium`、`low`。 |
| 权限 | `todowrite` |

### 2.4 网络工具

#### `webfetch` — 获取网页内容

| 属性 | 值 |
|------|-----|
| ID | `webfetch` |
| 描述文件 | `webfetch.txt` |
| 参数 | `url` (网页 URL), `format` (可选: `text`/`markdown`/`html`, 默认 `markdown`), `timeout` (可选, 秒) |
| 功能 | 获取 URL 内容并转换格式。HTML 到 Markdown 使用 TurndownService。HTML 到纯文本使用 HTMLRewriter。支持图片附件渲染。Cloudflare 检测到 bot 时自动使用诚实 User-Agent 重试。响应大小限制 5MB，超时最长 120 秒。 |
| 权限 | `webfetch` |

#### `websearch` — 网络搜索

| 属性 | 值 |
|------|-----|
| ID | `websearch` |
| 描述文件 | `websearch.txt` |
| 参数 | `query` (搜索查询), `numResults` (可选, 默认8), `livecrawl` (可选: `fallback`/`preferred`), `type` (可选: `auto`/`fast`/`deep`), `contextMaxCharacters` (可选, 默认10000) |
| 功能 | 执行网络搜索。支持两种后端提供商：Exa 和 Parallel。provider 选择逻辑：使用 `OPENCODE_WEBSEARCH_PROVIDER` 环境变量、feature flag 或基于 sessionID 的哈希轮换。仅在 opencode 提供商或配置了 EXA/PARALLEL 标志时启用。 |
| 权限 | `websearch` |

#### `codesearch` — 代码搜索

| 属性 | 值 |
|------|-----|
| ID | `codesearch` |
| 描述文件 | `codesearch.txt` |
| 参数 | `query` (查询内容), `tokensNum` (可选, 1000-50000, 默认5000) |
| 功能 | 搜索 API 文档、库和 SDK 的代码上下文。使用 Exa 的 `get_code_context_exa` API。feature flag: `OPENCODE_EXPERIMENTAL_SCOUT`。 |
| 权限 | `codesearch` |

### 2.5 仓库操作工具

#### `repo_clone` — 克隆 Git 仓库

| 属性 | 值 |
|------|-----|
| ID | `repo_clone` |
| 描述文件 | `repo_clone.txt` |
| 参数 | `repository` (git URL/仓库引用), `refresh` (可选, 拉取最新), `branch` (可选, 分支/ref) |
| 功能 | 克隆或缓存远程仓库。支持 git URL、host/path 引用或 GitHub owner/repo 简写。使用 `RepositoryCache.ensure()` 管理缓存状态（cached/cloned/refreshed）。feature flag: `OPENCODE_EXPERIMENTAL_SCOUT`。 |
| 权限 | `repo_clone` |

#### `repo_overview` — 仓库结构概览

| 属性 | 值 |
|------|-----|
| ID | `repo_overview` |
| 描述文件 | `repo_overview.txt` |
| 参数 | `repository` (可选, 仓库引用), `path` (可选, 目录路径), `depth` (可选, 最大深度, 默认3) |
| 功能 | 分析仓库结构，检测生态系统（Node.js/Python/Go/Rust/Ruby/Java/PHP）、包管理器（npm/yarn/pnpm/bun）、入口点、依赖文件。最多展示 200 个文件/目录条目。自动忽略 `.git`、`node_modules` 等目录。feature flag: `OPENCODE_EXPERIMENTAL_SCOUT`。 |
| 权限 | `repo_overview` |

### 2.6 高级功能工具

#### `skill` — 加载专业技能

| 属性 | 值 |
|------|-----|
| ID | `skill` |
| 描述文件 | `skill.txt` |
| 参数 | `name` (技能名称) |
| 功能 | 加载领域特定的技能指令和资源。通过 `Skill.Service.get()` 获取技能内容。输出包含 `<skill_content>` 包裹的技能指令、基础目录路径及采样文件列表（最多 10 个）。技能描述通过 `Skill.fmt()` 动态生成为可用技能列表。 |
| 权限 | `skill` |

#### `lsp` — LSP 集成

| 属性 | 值 |
|------|-----|
| ID | `lsp` |
| 描述文件 | `lsp.txt` |
| 参数 | `operation` (9种操作), `filePath` (文件路径), `line` (行号, 1-based), `character` (字符偏移, 1-based), `query` (可选, workspaceSymbol 搜索) |
| 功能 | 与语言服务器交互，支持 9 种 LSP 操作：`goToDefinition`、`findReferences`、`hover`、`documentSymbol`、`workspaceSymbol`、`goToImplementation`、`prepareCallHierarchy`、`incomingCalls`、`outgoingCalls`。feature flag: `OPENCODE_EXPERIMENTAL_LSP_TOOL`。 |
| 权限 | `lsp` |

#### `plan_exit` — 退出计划模式

| 属性 | 值 |
|------|-----|
| ID | `plan_exit` |
| 描述文件 | `plan-exit.txt` |
| 参数 | 无（空 Struct） |
| 功能 | 退出计划模式，切换到构建代理 (build agent)。询问用户确认后，创建新的用户消息切换到 build agent 并注入计划文件路径。feature flag: `OPENCODE_EXPERIMENTAL_PLAN_MODE` 且客户端为 `cli`。 |
| 权限 | 无 |

#### `invalid` — 哨兵工具

| 属性 | 值 |
|------|-----|
| ID | `invalid` |
| 描述 | `"Do not use"` |
| 参数 | `tool` (工具名), `error` (错误信息) |
| 功能 | 占位工具，用于表示无效的工具调用。始终返回参数错误信息。在所有模型中始终可用（不对 LLM 隐藏）。 |

---

## 3. 自定义工具加载机制

自定义工具从两个来源加载：

### 3.1 配置文件目录

系统扫描配置目录（通过 `config.directories()` 获取）中的 `{tool,tools}/*.{js,ts}` 文件：

```typescript
const matches = dirs.flatMap((dir) =>
  Glob.scanSync("{tool,tools}/*.{js,ts}", { cwd: dir, absolute: true, dot: true, symlink: true }),
)
```

- 使用 `import()` 动态加载匹配的文件
- 文件名为 namespace：例如 `my_tool.ts` 中的 `default` 导出其 ID 为 `my_tool`，命名导出为 `my_tool_exportName`
- 如果匹配到文件，会等待 `config.waitForDependencies()` 确保依赖就绪

### 3.2 插件包

从已加载插件（`plugin.list()`）的 `tool` 导出中提取：

```typescript
const plugins = yield* plugin.list()
for (const p of plugins) {
  for (const [id, def] of Object.entries(p.tool ?? {})) {
    custom.push(fromPlugin(id, def))
  }
}
```

### 3.3 插件工具定义格式

插件工具使用 `@opencode-ai/plugin` 的 `tool()` 函数定义：

```typescript
function tool<Args extends z.ZodRawShape>(input: {
  description: string
  args: Args                    // Zod schema shape
  execute(args, context): Promise<ToolResult>
})
```

- `args` 使用 Zod 原始 schema 定义参数形状
- 返回类型 `ToolResult` 可以是 `string` 或 `{ output: string, metadata?: {...} }`

### 3.4 Schema 适配层 (`fromPlugin`)

将插件工具的 Zod schema 包装为 Effect Schema：

```typescript
function fromPlugin(id: string, def: ToolDefinition): Tool.Def {
  const zodParams = z.object(def.args)
  const parameters = Schema.declare<unknown>(
    (u): u is unknown => zodParams.safeParse(u).success
  ).annotate({
    [ZodOverride]: zodParams,  // 标记原始 Zod 对象，供 JSON Schema 生成器使用
  })
  // ...
}
```

- 使用 `Schema.declare()` 创建运行时校验闭包
- 通过 `ZodOverride` 注解保留原始 Zod 对象，使 LLM JSON Schema 导出器能正确生成参数描述

### 3.5 插件上下文适配

自定义工具的执行函数接收增强后的插件上下文：

```typescript
execute: (args, toolCtx) =>
  Effect.gen(function* () {
    const pluginCtx: PluginToolContext = {
      ...toolCtx,                   // 标准上下文字段
      ask: (req) => toolCtx.ask(req),  // 权限询问
      directory: ctx.directory,      // 项目工作目录
      worktree: ctx.worktree,        // 项目 worktree 根目录
    }
    const result = yield* Effect.promise(() => def.execute(args as any, pluginCtx))
    // 自动截断输出...
  })
```

执行结果自动经过截断处理：
1. 获取当前 agent 信息
2. 调用 `truncate.output()` 检查是否超出限制
3. 如果截断，返回包含 `outputPath` 和 `truncated` 标记的元数据

---

## 4. 工具初始化流程

```
loadPluginsAndConfig
  │
  ├─► 1. 从配置文件目录扫描 {tool,tools}/*.{js,ts} 文件
  │      └─► 动态 import → 提取 default/命名导出 → fromPlugin() 包装
  │
  ├─► 2. 从插件包提取 tool 导出
  │      └─► plugin.list() → 遍历 p.tool → fromPlugin() 包装
  │
  └─► 3. 注册表 Effect 初始化 (InstanceState)
         │
         ├─► 创建所有内置工具 (Effect.all)
         │   ├─► invalid (始终可用)
         │   ├─► question (条件: client=app/cli/desktop 或 OPENCODE_ENABLE_QUESTION_TOOL)
         │   ├─► shell, read, glob, grep, edit, write (始终可用)
         │   ├─► task, fetch, todo, search (始终可用)
         │   ├─► code, repo_clone, repo_overview (条件: OPENCODE_EXPERIMENTAL_SCOUT)
         │   ├─► skill, patch (始终可用，但 patch 可能被模型层隐藏)
         │   ├─► lsp (条件: OPENCODE_EXPERIMENTAL_LSP_TOOL)
         │   └─► plan_exit (条件: OPENCODE_EXPERIMENTAL_PLAN_MODE && client=cli)
         │
         └─► 返回 State { custom[], builtin[], task, read }

ToolRegistry.all() → [...builtin, ...custom]

ToolRegistry.tools(model) → 按模型筛选 + 增强 → 最终工具列表
```

### 4.1 实例状态缓存

系统使用 `InstanceState` 模式（单次求值并缓存），确保工具列表在其生命周期内只初始化一次。

### 4.2 依赖注入

`ToolRegistry` 层依赖以下服务（通过 Effect Layer 注入）：

| 服务 | 用途 |
|------|------|
| `Config.Service` | 读取配置和目录 |
| `Plugin.Service` | 获取插件列表和触发 `tool.definition` hook |
| `Agent.Service` | 获取代理列表（用于 task 工具描述） |
| `Skill.Service` | 获取技能列表（用于 skill 工具描述） |
| `Session.Service` | 会话管理（task 工具创建子会话） |
| `Provider.Service` | 获取默认模型 |
| `Question.Service` | question 和 plan_exit 工具 |
| `Todo.Service` | todo 持久化 |
| `LSP.Service` | LSP 诊断和操作 |
| `Instruction.Service` | read 工具的指令注入 |
| `AppFileSystem.Service` | 文件系统抽象 |
| `HttpClient` | HTTP 请求（webfetch、websearch、codesearch） |
| `ChildProcessSpawner` | Shell 命令执行 |
| `Ripgrep.Service` | glob 和 grep 的底层搜索 |
| `Format.Service` | 写后代码格式化 |
| `Truncate.Service` | 输出截断 |
| `Bus.Service` | 文件变更事件通知 |
| `Git.Service` | repo_clone 和 repo_overview |
| `Reference.Service` | read 工具的引用跟踪 |

---

## 5. 按模型筛选工具

`ToolRegistry.tools(model)` 方法接收模型信息并筛选工具：

```typescript
const tools: Interface["tools"] = Effect.fn("ToolRegistry.tools")(function* (input) {
  const filtered = (yield* all()).filter((tool) => {
    // 规则 1: WebSearch 仅对 opencode provider 或配置了特定 flag 的 provider 启用
    if (tool.id === WebSearchTool.id) {
      return webSearchEnabled(input.providerID)
    }

    // 规则 2: GPT 模型使用 apply_patch 替代 edit + write
    const usePatch =
      input.modelID.includes("gpt-") &&
      !input.modelID.includes("oss") &&
      !input.modelID.includes("gpt-4")
    if (tool.id === ApplyPatchTool.id) return usePatch
    if (tool.id === EditTool.id || tool.id === WriteTool.id) return !usePatch

    return true
  })
  // ...
})
```

### 5.1 WebSearch 启用条件

`webSearchEnabled()` 函数判断：

```typescript
function webSearchEnabled(providerID, flags) {
  return providerID === ProviderID.opencode || flags.exa || flags.parallel
}
```

- `opencode` 提供商始终启用
- 配置了 `OPENCODE_ENABLE_EXA` 或 `OPENCODE_ENABLE_PARALLEL` 标志时也对其他提供商启用

### 5.2 Edit/Write vs ApplyPatch 选择逻辑

| 模型 | 使用工具 |
|------|----------|
| 非 GPT 模型 | `edit` + `write` |
| `gpt-4*` 系列 | `edit` + `write` |
| `gpt-*-oss*` 系列 | `edit` + `write` |
| 其他 GPT 模型 (gpt-5 等) | `apply_patch` |

`apply_patch` 和 `edit`+`write` 互斥显示——当一组可见时另一组隐藏。

---

## 6. 工具执行流程

```
LLM 调用工具
  │
  ├─► 1. 参数校验 (Schema.decodeUnknownEffect)
  │      ├─► 成功 → 继续
  │      └─► 失败 → 调用 formatValidationError 或默认错误消息
  │
  ├─► 2. 外部目录检查 (assertExternalDirectoryEffect)
  │      └─► 对于涉及文件路径的工具，检查是否在项目目录或外部
  │           ├─► 外部路径 → 触发 external_directory 权限询问
  │           └─► 内部路径 → 跳过
  │
  ├─► 3. 执行工具 execute(args, ctx)
  │      ├─► 内置工具: 直接执行 Effect 流程
  │      │     ├─► 文件操作 (read/edit/write) → 文件锁 → 权限询问 → 写入 → 格式化 → LSP → 总线事件
  │      │     ├─► Shell → tree-sitter 解析 → 权限扫描 → 子进程执行 → 流式输出 → 截断
  │      │     ├─► Task → 权限检查 → 创建子会话 → 传递 prompt → 返回 task_id 和结果
  │      │     ├─► WebFetch/WebSearch → HTTP 请求 → 格式转换
  │      │     └─► Skill → 加载内容 → 列表文件 → 输出 <skill_content>
  │      └─► 自定义工具:
  │            ├─► 构建 PluginToolContext（注入 directory、worktree）
  │            └─► 调用插件的 execute 函数 → 截断输出
  │
  ├─► 4. 输出截断 (Truncate.output)
  │      ├─► 行数 ≤ maxLines 且 字节数 ≤ maxBytes → 原样返回
  │      └─► 超出限制 → 写入截断目录 → 返回预览 + 文件路径提示
  │
  └─► 5. 返回 ExecuteResult
         ├─► title: 工具执行标题
         ├─► output: 输出文本（可能被截断）
         ├─► metadata: 扩展元数据（截断信息等）
         └─► attachments: 可选的文件附件（图片、PDF）
```

### 6.1 截断系统 (Truncate)

截断系统 (`tool/truncate.ts`) 管理工具输出大小：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `maxLines` | 2000 | 从 `tool_output.max_lines` 配置覆盖 |
| `maxBytes` | 50KB | 从 `tool_output.max_bytes` 配置覆盖 |
| 方向 | head | 从开头截断 |

- 超出限制的输出写入 `TRUNCATION_DIR` 下的唯一文件
- 文件保留 7 天后由每小时运行一次的清理任务删除
- 提示信息根据是否可用 task 工具动态生成建议

### 6.2 文件锁机制

`edit` 工具对每个文件路径使用信号量锁：

```typescript
const locks = new Map<string, Semaphore.Semaphore>()
// 每个文件路径一个信号量(1)，确保并发编辑序列化
yield* lock(filePath).withPermits(1)(...)
```

---

## 7. Task 工具子代理描述生成

`describeTask()` 动态生成 task 工具的描述文本：

```typescript
const describeTask = Effect.fn("ToolRegistry.describeTask")(function* (agent: Agent.Info) {
  // 1. 获取所有代理，过滤掉 primary 模式
  const items = (yield* agents.list()).filter((item) => item.mode !== "primary")

  // 2. 按权限过滤：排除当前代理无权调用的子代理
  const filtered = items.filter(
    (item) => Permission.evaluate("task", item.name, agent.permission).action !== "deny",
  )

  // 3. 按名称排序并生成带描述的列表
  const list = filtered.toSorted((a, b) => a.name.localeCompare(b.name))
  const description = list.map((item) =>
    `- ${item.name}: ${item.description ?? "This subagent should only be called manually by the user."}`
  ).join("\n")

  return [
    "Available agent types and the tools they have access to:",
    description,
  ].join("\n")
})
```

逻辑：
1. 从 `agents.list()` 获取所有注册的代理
2. 排除 `mode: "primary"` 的主代理
3. 通过权限系统检查当前代理是否有权调用每个子代理（`Permission.evaluate("task", agentName, agentPermission)`）
4. 仅返回 `action !== "deny"` 的子代理
5. 按字母顺序排序后格式化为描述文本

### 7.1 Skill 工具描述生成

类似地，`describeSkill()` 动态生成 skill 工具的可用技能列表：

```typescript
const describeSkill = Effect.fn("ToolRegistry.describeSkill")(function* (agent: Agent.Info) {
  const list = yield* skill.available(agent)
  if (list.length === 0) return "No skills are currently available."
  return [
    "Load a specialized skill that provides domain-specific instructions and workflows.",
    // ...
    Skill.fmt(list, { verbose: false }),  // 格式化为紧凑的技能列表
  ].join("\n")
})
```

---

## 8. 插件工具定义转换钩子

在 `tools()` 方法中，每个工具定义在处理后触发 `tool.definition` 插件钩子：

```typescript
const output = {
  description: tool.description,
  parameters: tool.parameters,
}
yield* plugin.trigger("tool.definition", { toolID: tool.id }, output)
```

这允许插件在工具发送给 LLM 之前修改其描述和参数 JSON Schema。例如：
- 修改工具描述以添加插件特定的使用说明
- 调整参数 Schema 的约束
- 添加平台特定的提示信息

---

## 9. 权限检查流程

工具执行前的权限检查通过 `ctx.ask()` 触发：

```typescript
yield* ctx.ask({
  permission: "edit",        // 权限类别
  patterns: [relativePath],   // 受影响的具体路径
  always: ["*"],              // 始终可匹配的通配模式
  metadata: {                 // 面向用户的上下文信息
    filepath: filePath,
    diff: diff,
  },
})
```

- 各工具在操作实际执行前调用 `ctx.ask()`
- 权限系统根据用户规则（allow/deny/ask）决定是否允许
- 如果被拒绝，工具执行会被中断
- 不同工具的权限类别：`edit`、`read`、`glob`、`grep`、`shell`、`task`、`webfetch`、`websearch`、`codesearch`、`repo_clone`、`repo_overview`、`lsp`、`skill`、`todowrite`

---

## 10. 工具 ID Schema

工具 ID 通过 `schema.ts` 定义：

```typescript
const toolIdSchema = Schema.String
  .check(Schema.isStartsWith("tool"))
  .pipe(Schema.brand("ToolID"))
```

- 所有工具 ID 必须以 `tool` 前缀开头
- 截断系统中的文件 ID 使用 `ToolID.ascending()` 生成

---

## 11. 目录结构

```
tool/
├── tool.ts              # Tool.Def / Tool.Info / Tool.define / Tool.init 核心类型
├── registry.ts          # ToolRegistry 服务（入口）
├── schema.ts            # ToolID schema
├── truncate.ts          # 输出截断系统
├── truncation-dir.ts    # 截断文件目录常量
├── external-directory.ts # 外部目录访问检查
├── shell/               # Shell 工具子模块
│   ├── prompt.ts        # Shell 提示和参数
│   └── id.ts            # Shell 工具 ID
├── *.ts                 # 各内置工具实现
├── *.txt                # 各工具的描述文本文件
├── mcp-websearch.ts     # MCP WebSearch 协议实现
└── plan-enter.txt       # plan 模式进入提示
```
