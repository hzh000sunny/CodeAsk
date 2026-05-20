# OpenCode 插件系统 (Plugin System)

## 概述

OpenCode 的插件系统提供了一套完整的扩展 API，允许开发者通过 npm 包或本地文件注册自定义工具、认证方式、模型提供方、TUI 渲染组件以及各种生命周期钩子。插件由 `@opencode-ai/plugin` 包定义 API 接口，由 `packages/opencode/src/plugin/` 负责发现、加载和管理。

核心文件：
- 插件 API 定义：`/home/hzh/wiki/opencode/packages/plugin/src/index.ts`
- 工具定义：`/home/hzh/wiki/opencode/packages/plugin/src/tool.ts`
- TUI 插件：`/home/hzh/wiki/opencode/packages/plugin/src/tui.ts`
- Shell 集成：`/home/hzh/wiki/opencode/packages/plugin/src/shell.ts`
- 插件发现与加载：`/home/hzh/wiki/opencode/packages/opencode/src/plugin/`
- 插件配置与安装：`/home/hzh/wiki/opencode/packages/opencode/src/config/plugin.ts`

---

## 1. 插件包结构

`@opencode-ai/plugin` 包的导出结构：

```json
{
  "name": "@opencode-ai/plugin",
  "exports": {
    ".": "./src/index.ts",
    "./tool": "./src/tool.ts",
    "./tui": "./src/tui.ts"
  }
}
```

该包依赖 `@opencode-ai/sdk`、`effect`、`zod`，并可选依赖 `@opentui/core`、`@opentui/keymap`、`@opentui/solid`（仅在开发 TUI 插件时需要）。

---

## 2. 插件模块类型

插件模块分为两种类型，通过 `default export` 导出，且一个模块只能导出一个类型的入口函数。

### 2.1 Server 插件 (`PluginModule`)

导出 `server` 函数的模块，运行在服务端，可注册工具、认证、Provider、生命周期钩子等：

```typescript
export type PluginModule = {
  id?: string
  server: Plugin
  tui?: never
}
```

### 2.2 TUI 插件 (`TuiPluginModule`)

导出 `tui` 函数的模块，运行在终端 UI 层，可注册自定义路由、组件、对话框、快捷键等：

```typescript
export type TuiPluginModule = {
  id?: string
  tui: TuiPlugin
  server?: never
}
```

> **严格规则**：一个插件必须只导出 `server()` 或 `tui()` 之一，不能同时导出两者。系统在加载时会进行严格校验。

---

## 3. 插件定义结构 (Plugin API)

### 3.1 Plugin 函数签名

```typescript
export type Plugin = (input: PluginInput, options?: PluginOptions) => Promise<Hooks>
```

### 3.2 PluginInput -- 插件输入上下文

插件初始化时接收的上下文对象，提供所有与服务端交互的能力：

```typescript
export type PluginInput = {
  client: ReturnType<typeof createOpencodeClient>  // OpenCode 客户端
  project: Project                                   // 当前项目信息
  directory: string                                  // 当前项目目录
  worktree: string                                   // 当前项目 worktree 根目录
  experimental_workspace: {                          // 工作区适配器注册（实验性）
    register(type: string, adapter: WorkspaceAdapter): void
  }
  serverUrl: URL                                     // 服务端 URL
  $: BunShell                                        // Bun Shell 实例（仅 Bun 运行时可用）
}
```

### 3.3 PluginOptions -- 插件选项

```typescript
export type PluginOptions = Record<string, unknown>
```

插件选项从配置文件中读取，用户在 `config.plugin` 列表中使用 `[spec, options]` 元组格式传递。

### 3.4 Hooks -- 插件钩子集合

插件通过返回 `Hooks` 对象来注册各种扩展能力。`Hooks` 接口定义如下（详见各节说明）：

```typescript
export interface Hooks {
  event?: (input: { event: Event }) => Promise<void>
  config?: (input: Config) => Promise<void>
  tool?: { [key: string]: ToolDefinition }
  auth?: AuthHook
  provider?: ProviderHook
  "chat.message"?: (input, output) => Promise<void>
  "chat.params"?: (input, output) => Promise<void>
  "chat.headers"?: (input, output) => Promise<void>
  "permission.ask"?: (input, output) => Promise<void>
  "command.execute.before"?: (input, output) => Promise<void>
  "tool.execute.before"?: (input, output) => Promise<void>
  "tool.execute.after"?: (input, output) => Promise<void>
  "shell.env"?: (input, output) => Promise<void>
  "tool.definition"?: (input, output) => Promise<void>
  "experimental.chat.system.transform"?: (input, output) => Promise<void>
  "experimental.chat.messages.transform"?: (input, output) => Promise<void>
  "experimental.session.compacting"?: (input, output) => Promise<void>
  "experimental.compaction.autocontinue"?: (input, output) => Promise<void>
  "experimental.text.complete"?: (input, output) => Promise<void>
}
```

### 3.5 Config -- 插件配置接口

```typescript
export type Config = Omit<SDKConfig, "plugin"> & {
  plugin?: Array<string | [string, PluginOptions]>
}
```

---

## 4. 工具创建 API (`tool()`)

工具系统允许插件注册可被 LLM 调用的自定义工具。定义位于 `@opencode-ai/plugin/tool`。

### 4.1 tool() 函数

```typescript
export function tool<Args extends z.ZodRawShape>(input: {
  description: string
  args: Args
  execute(args: z.infer<z.ZodObject<Args>>, context: ToolContext): Promise<ToolResult>
}): ToolDefinition

tool.schema = z   // 提供对 zod 的便捷访问
```

参数说明：
- `description`: 传递给 LLM 的工具描述，帮助模型理解何时及如何调用该工具
- `args`: 使用 `tool.schema`（即 zod）定义的参数结构，每个参数需附加 `.describe()` 说明
- `execute`: 工具执行函数，接收解析后的参数和工具上下文，返回执行结果

### 4.2 ToolContext -- 工具执行上下文

```typescript
export type ToolContext = {
  sessionID: string        // 当前会话 ID
  messageID: string        // 当前消息 ID
  agent: string            // 当前 agent 名称
  directory: string        // 当前会话的项目目录（推荐用于解析相对路径）
  worktree: string         // 项目 worktree 根目录（建议用于生成稳定的相对路径）
  abort: AbortSignal       // 取消信号，用于响应中断请求
  metadata(input: { title?: string; metadata?: { [key: string]: any } }): void  // 推送流式元数据
  ask(input: AskInput): Effect.Effect<void>  // 触发权限询问
}
```

`metadata()` 方法允许工具在执行期间向外推送进度信息，例如当前正在处理某个文件的标题。

`ask()` 方法用于触发权限系统，当工具执行需要用户确认时调用：

```typescript
type AskInput = {
  permission: string     // 所需权限类型标识
  patterns: string[]     // 涉及的路径模式
  always: string[]       // 始终允许的路径
  metadata: { [key: string]: any }  // 附加元数据
}
```

### 4.3 ToolResult -- 工具返回结果

```typescript
export type ToolResult = string | { output: string; metadata?: { [key: string]: any } }
```

可以返回简单的字符串，或返回附带元数据的对象。元数据会被包含在 LLM 响应中，可用于传递工具执行的结构化信息。

### 4.4 工具定义示例

```typescript
import { tool } from "@opencode-ai/plugin/tool"

const mytool = tool({
  description: "执行自定义代码审查",
  args: {
    file: tool.schema.string().describe("要审查的文件路径"),
    severity: tool.schema.enum(["low", "medium", "high"]).describe("审查严格级别").optional(),
  },
  async execute(args, ctx) {
    // 推送流式状态
    ctx.metadata({ title: `正在审查 ${args.file}...` })

    const result = await reviewFile(args.file, args.severity)

    // 需要时触发权限询问
    if (result.needsConfirmation) {
      await ctx.ask({
        permission: "file_write",
        patterns: [result.targetPath],
        always: [],
        metadata: {}
      })
    }

    return {
      output: `审查完成：${result.summary}`,
      metadata: { issues: result.issueCount },
    }
  },
})
```

---

## 5. 认证插件 (Auth Plugins)

认证插件用于集成第三方认证服务（如 OAuth、API Key），让 OpenCode 能够以用户身份调用外部 API。

### 5.1 AuthHook 结构

```typescript
export type AuthHook = {
  provider: string    // 认证提供方标识
  loader?: (auth: () => Promise<Auth>, provider: Provider) => Promise<Record<string, any>>
  methods: (OAuthMethod | ApiMethod)[]
}
```

`loader` 是一个可选的回调，在认证成功后被调用，用于将认证信息转换为 Provider 可用的凭据格式。

### 5.2 OAuth 认证方法

```typescript
{
  type: "oauth"
  label: string                        // 用户界面上显示的标签
  prompts?: (TextPrompt | SelectPrompt)[]  // 认证前收集额外信息的输入提示
  authorize(inputs?): Promise<AuthOAuthResult>  // 发起 OAuth 授权
}
```

**输入提示 (Prompts)**：

文本输入提示：
```typescript
{
  type: "text"
  key: string            // 输入的键名
  message: string        // 提示信息
  placeholder?: string   // 占位文本
  validate?: (value: string) => string | undefined  // 校验函数，返回错误信息或 undefined
  when?: Rule            // 条件显示规则（推荐代替已弃用的 condition）
}
```

选择输入提示：
```typescript
{
  type: "select"
  key: string
  message: string
  options: { label: string; value: string; hint?: string }[]
  when?: Rule
}
```

**条件规则 `Rule`**：
```typescript
type Rule = { key: string; op: "eq" | "neq"; value: string }
```

**OAuth 授权结果 `AuthOAuthResult`**：
```typescript
export type AuthOAuthResult = { url: string; instructions: string } & (
  | {
      method: "auto"
      callback(): Promise<SuccessResult | FailedResult>
    }
  | {
      method: "code"
      callback(code: string): Promise<SuccessResult | FailedResult>
    }
)
```

- `method: "auto"`: 自动回调模式（如本地服务器的重定向回调）
- `method: "code"`: 验证码模式（用户手动输入授权码）
- 成功结果包含 `{ type: "success", provider?: string }` 以及凭据信息（`refresh` + `access` + `expires` 或 `key`）
- 失败结果：`{ type: "failed" }`

### 5.3 API Key 认证方法

```typescript
{
  type: "api"
  label: string
  prompts?: (TextPrompt | SelectPrompt)[]
  authorize?(inputs?): Promise<SuccessApiResult | FailedResult>
}
```

成功结果：`{ type: "success"; key: string; provider?: string }`
失败结果：`{ type: "failed" }`

---

## 6. Provider 插件 (Provider Plugins)

Provider 插件允许动态注册 AI 模型提供方，实现自定义模型列表的加载。

### 6.1 ProviderHook 结构

```typescript
export type ProviderHook = {
  id: string
  models?: (provider: ProviderV2, ctx: ProviderHookContext) => Promise<Record<string, ModelV2>>
}
```

- `id`: Provider 的唯一标识符
- `models`: 异步函数，接收 Provider 信息和认证上下文，返回模型 ID 到模型定义的映射

### 6.2 ProviderContext

```typescript
export type ProviderContext = {
  source: "env" | "config" | "custom" | "api"
  info: Provider
  options: Record<string, any>
}
```

### 6.3 ProviderHookContext

```typescript
export type ProviderHookContext = {
  auth?: Auth    // 认证信息（如果有）
}
```

### 6.4 Provider 插件示例

```typescript
const MyProviderPlugin: Plugin = async (_ctx, _options) => {
  return {
    provider: {
      id: "my-provider",
      async models(provider, ctx) {
        // ctx.auth 包含认证信息，可用于调用受保护的 API 获取模型列表
        const models = await fetchModelsFromAPI(ctx.auth)
        const result: Record<string, ModelV2> = {}
        for (const m of models) {
          result[m.id] = {
            id: m.id,
            name: m.name,
            // ... 其他模型属性
          }
        }
        return result
      },
    },
  }
}
```

---

## 7. TUI 插件系统

TUI 插件系统基于 `@opentui` 框架（`@opentui/core`、`@opentui/keymap`、`@opentui/solid`），提供终端 UI 的完整扩展能力。定义位于 `@opencode-ai/plugin/tui`。

### 7.1 TuiPlugin 函数签名

```typescript
export type TuiPlugin = (
  api: TuiPluginApi,
  options: PluginOptions | undefined,
  meta: TuiPluginMeta,
) => Promise<void>
```

`meta` 包含插件的加载元数据：
```typescript
export type TuiPluginMeta = TuiPluginEntry & {
  state: TuiPluginState   // "first" | "updated" | "same"
}
export type TuiPluginEntry = {
  id: string; source: "file" | "npm" | "internal"; spec: string; target: string
  requested?: string; version?: string; modified?: number
  first_time: number; last_time: number; time_changed: number
  load_count: number; fingerprint: string
}
```

### 7.2 TuiPluginApi -- 完整的 TUI API

TUI 插件可用的完整 API 概览：

| API 属性 | 类型 | 说明 |
|----------|------|------|
| `app` | `TuiApp` | 应用版本信息 |
| `client` | `OpencodeClient` | OpenCode SDK 客户端 |
| `command` | `TuiCommandApi` | （已弃用）旧版命令注册 API |
| `keys` | `TuiKeys` | 快捷键格式化工具 |
| `keymap` | `TuiKeymap` | 快捷键绑定管理器 |
| `route` | 路由对象 | 路由注册和导航 |
| `ui` | UI 组件集合 | 对话框、提示框、插槽等 UI 组件 |
| `tuiConfig` | `TuiConfigView` | 当前 TUI 配置（只读，已冻结） |
| `kv` | `TuiKV` | 键值存储（持久化） |
| `state` | `TuiState` | 全局状态（配置、Provider、会话、消息等） |
| `theme` | `TuiTheme` | 主题管理 |
| `event` | `TuiEventBus` | 事件总线 |
| `renderer` | `CliRenderer` | 终端渲染器 |
| `slots` | `TuiSlots` | UI 插槽注册 |
| `plugins` | 插件管理 | 列出、激活、停用、安装插件 |
| `lifecycle` | `TuiLifecycle` | 插件生命周期（AbortSignal、onDispose） |

### 7.3 路由系统

```typescript
api.route.register([
  {
    name: "my-view",
    render: ({ params }) => <MyComponent params={params} />,
  },
])

// 导航到自定义路由
api.route.navigate("my-view", { key: "value" })

// 只读的当前路由状态
api.route.current
// 类型为：
// { name: "home" }
// | { name: "session"; params: { sessionID: string; prompt?: unknown } }
// | { name: string; params?: Record<string, unknown> }
```

### 7.4 快捷键系统 (`keymap`)

`api.keymap` 的类型是 `Keymap<Renderable, KeyEvent>`。支持注册命令层、绑定快捷键、分发命令。

创建绑定查找表：
```typescript
import { createBindingLookup } from "@opencode-ai/plugin/tui"

const bindings = createBindingLookup({
  "my-command": { key: "Ctrl+k", command: "my.scope.my-command" }
})
```

导出的键盘工具：
- `stringifyKeySequence` / `stringifyKeyStroke` -- 将按键序列转为字符串
- `formatCommandBindings` / `formatKeySequence` -- 格式化快捷键显示

### 7.5 UI 组件

**对话框堆栈 (`api.ui.dialog`)**：
```typescript
export type TuiDialogStack = {
  replace: (render: () => JSX.Element, onClose?: () => void) => void
  clear: () => void
  setSize: (size: "medium" | "large" | "xlarge") => void
  readonly size: "medium" | "large" | "xlarge"
  readonly depth: number
  readonly open: boolean
}
```

**可用对话框组件 (`api.ui.DialogXxx`)**：
- `Dialog` -- 通用对话框（支持 `size`、`onClose`、`children`）
- `DialogAlert` -- 警告对话框（`title`、`message`、`onConfirm`）
- `DialogConfirm` -- 确认对话框（`title`、`message`、`onConfirm`、`onCancel`）
- `DialogPrompt` -- 文本输入对话框（`title`、`placeholder`、`value`、`onConfirm(value)`、`onCancel`）
- `DialogSelect<Value>` -- 选择列表对话框（`title`、`options`、`onSelect`、支持过滤）

**提示框组件 (`api.ui.Prompt`)**：
```typescript
export type TuiPromptRef = {
  focused: boolean
  current: TuiPromptInfo
  set(prompt: TuiPromptInfo): void
  reset(): void
  blur(): void; focus(): void
  submit(): void
}
```

支持 `normal` 和 `shell` 两种输入模式，可包含文件附件、Agent 引用等。

**提示信息 (`TuiPromptInfo`)**：
```typescript
export type TuiPromptInfo = {
  input: string
  mode?: "normal" | "shell"
  parts: (FilePart | AgentPart | TextPart)[]
}
```

**Toast 通知 (`api.ui.toast`)**：
```typescript
api.ui.toast({
  variant: "info" | "success" | "warning" | "error",
  title?: string,
  message: "操作完成",
  duration?: number,  // 显示时长，毫秒
})
```

### 7.6 UI 插槽系统 (`api.slots`)

插槽系统允许插件在预定义的主机 UI 位置注入自定义内容。通过 `api.slots.register()` 注册。

**主机插槽映射 (`TuiHostSlotMap`)**：

| 插槽名 | 说明 | 参数 |
|--------|------|------|
| `app` | 应用级别插槽 | `{}` |
| `app_bottom` | 应用底部插槽 | `{}` |
| `home_logo` | 主页 Logo 区域 | `{}` |
| `home_prompt` | 主页输入框 | `{ workspace_id?, ref? }` |
| `home_prompt_right` | 主页输入框右侧 | `{ workspace_id? }` |
| `home_bottom` | 主页底部 | `{}` |
| `home_footer` | 主页页脚 | `{}` |
| `session_prompt` | 会话页输入框 | `{ session_id, visible?, disabled?, on_submit?, ref? }` |
| `session_prompt_right` | 会话页输入框右侧 | `{ session_id }` |
| `sidebar_title` | 侧边栏标题 | `{ session_id, title, share_url? }` |
| `sidebar_content` | 侧边栏内容 | `{ session_id }` |
| `sidebar_footer` | 侧边栏页脚 | `{ session_id }` |

使用 `api.ui.Slot` 组件渲染插槽：
```typescript
api.ui.Slot({ name: "app_bottom", children: <MyComponent /> })
```

### 7.7 主题系统 (`api.theme`)

```typescript
export type TuiTheme = {
  readonly current: TuiThemeCurrent   // 当前主题的全部颜色值
  readonly selected: string           // 当前选择的主题名称
  has: (name: string) => boolean      // 检查主题是否存在
  set: (name: string) => boolean      // 切换主题
  install: (jsonPath: string) => Promise<void>  // 安装主题 JSON 文件
  mode: () => "dark" | "light"        // 获取当前明暗模式
  readonly ready: boolean             // 主题系统是否就绪
}
```

`TuiThemeCurrent` 包含 60+ 个颜色变量，涵盖：通用 UI 颜色、Diff 颜色、Markdown 颜色、语法高亮颜色等。详见源码中的完整定义。

### 7.8 键值存储 (`api.kv`)

跨会话的持久化键值存储：

```typescript
export type TuiKV = {
  get: <Value = unknown>(key: string, fallback?: Value) => Value
  set: (key: string, value: unknown) => void
  readonly ready: boolean
}
```

### 7.9 全局状态 (`api.state`)

```typescript
export type TuiState = {
  readonly ready: boolean
  readonly config: SdkConfig         // 当前 SDK 配置
  readonly provider: ReadonlyArray<Provider>  // 所有 Provider 列表
  readonly path: {                   // 关键路径
    state: string
    config: string
    worktree: string
    directory: string
  }
  readonly vcs: { branch?: string } | undefined
  session: {
    count: () => number
    diff: (sessionID) => ReadonlyArray<TuiSidebarFileItem>
    todo: (sessionID) => ReadonlyArray<TuiSidebarTodoItem>
    messages: (sessionID) => ReadonlyArray<Message>
    status: (sessionID) => SessionStatus | undefined
    permission: (sessionID) => ReadonlyArray<PermissionRequest>
    question: (sessionID) => ReadonlyArray<QuestionRequest>
  }
  part: (messageID) => ReadonlyArray<Part>
  lsp: () => ReadonlyArray<TuiSidebarLspItem>
  mcp: () => ReadonlyArray<TuiSidebarMcpItem>
}
```

### 7.10 事件总线 (`api.event`)

```typescript
export type TuiEventBus = {
  on: <Type extends Event["type"]>(
    type: Type,
    handler: (event: Extract<Event, { type: Type }>) => void
  ) => () => void  // 返回取消监听的函数
}
```

### 7.11 插件管理 (`api.plugins`)

```typescript
plugins: {
  list: () => ReadonlyArray<TuiPluginStatus>
  activate: (id: string) => Promise<boolean>
  deactivate: (id: string) => Promise<boolean>
  add: (spec: string) => Promise<boolean>
  install: (spec: string, options?: TuiPluginInstallOptions) => Promise<TuiPluginInstallResult>
}
```

### 7.12 旧版命令 API (`api.command`) -- 已弃用

```typescript
export type TuiCommandApi = {
  register: (cb: () => TuiCommand[]) => () => void   // 注册命令列表
  trigger: (value: string) => void                    // 触发命令
  show: () => void                                    // 显示命令面板
}
```

> **已弃用**：请使用 `api.keymap.registerLayer({ commands, bindings })`、`api.keymap.dispatchCommand(name)` 和 `api.keymap.dispatchCommand("command.palette.show")` 替代。

---

## 8. 工作区适配器 (Workspace Adapter)

工作区适配器允许插件注册自定义的 workspace 类型，定义 workspace 的创建、配置、删除和目标解析逻辑。

### 8.1 WorkspaceAdapter 接口

```typescript
export type WorkspaceAdapter = {
  name: string
  description: string
  configure(config: WorkspaceInfo): WorkspaceInfo | Promise<WorkspaceInfo>
  create(config: WorkspaceInfo, env: Record<string, string | undefined>, from?: WorkspaceInfo): Promise<void>
  remove(config: WorkspaceInfo): Promise<void>
  target(config: WorkspaceInfo): WorkspaceTarget | Promise<WorkspaceTarget>
}
```

### 8.2 WorkspaceInfo

```typescript
export type WorkspaceInfo = {
  id: string
  type: string
  name: string
  branch: string | null
  directory: string | null
  extra: unknown | null
  projectID: string
}
```

### 8.3 WorkspaceTarget

```typescript
export type WorkspaceTarget =
  | { type: "local"; directory: string }
  | { type: "remote"; url: string | URL; headers?: HeadersInit }
```

### 8.4 注册方法

通过 `PluginInput.experimental_workspace.register()` 注册：

```typescript
const FolderWorkspacePlugin: Plugin = async ({ experimental_workspace }) => {
  experimental_workspace.register("folder", {
    name: "Folder",
    description: "基于文件夹的工作区",
    configure(config) {
      return { ...config, directory: `/tmp/workspace-${Date.now()}` }
    },
    async create(config) {
      await mkdir(config.directory!, { recursive: true })
    },
    async remove(config) {
      await rm(config.directory!, { recursive: true, force: true })
    },
    target(config) {
      return { type: "local", directory: config.directory! }
    },
  })
  return {}
}
```

---

## 9. Shell 集成

插件可以访问 BunShell 实例来执行 shell 命令。

### 9.1 BunShell 接口

```typescript
export interface BunShell {
  (strings: TemplateStringsArray, ...expressions: ShellExpression[]): BunShellPromise
  braces(pattern: string): string[]                         // Bash 风格的大括号展开
  escape(input: string): string                             // 字符串转义
  env(newEnv?: Record<string, string | undefined>): BunShell  // 设置环境变量
  cwd(newCwd?: string): BunShell                            // 设置工作目录
  nothrow(): BunShell                                       // 非零退出码不抛异常
  throws(shouldThrow: boolean): BunShell
}
```

### 9.2 BunShellPromise

```typescript
export interface BunShellPromise extends Promise<BunShellOutput> {
  readonly stdin: WritableStream
  cwd(newCwd: string): this       // 设置工作目录
  env(newEnv): this                // 设置环境变量
  quiet(): this                    // 静默模式（不输出到终端，仅缓冲）
  lines(): AsyncIterable<string>   // 逐行读取 stdout（自动静默）
  text(encoding?): Promise<string> // 读取 stdout 文本（自动静默）
  json(): Promise<any>             // 读取 stdout 为 JSON（自动静默）
  arrayBuffer(): Promise<ArrayBuffer>
  blob(): Promise<Blob>
  nothrow(): this
  throws(shouldThrow: boolean): this
}
```

### 9.3 BunShellOutput

```typescript
export interface BunShellOutput {
  readonly stdout: Buffer
  readonly stderr: Buffer
  readonly exitCode: number
  text(encoding?): string
  json(): any
  arrayBuffer(): ArrayBuffer
  bytes(): Uint8Array
  blob(): Blob
}
```

### 9.4 使用示例

```typescript
export const ShellPlugin: Plugin = async ({ $ }) => {
  // 执行 shell 命令（仅在 Bun 运行时可用）
  if ($) {
    const result = await $`ls -la ${$.escape(worktree)}`
    console.log(result.text())
  }
  return {}
}
```

> 注意：`$` 仅在 Bun 运行时环境中非 undefined，在其他运行时（如 Node.js）中为 `undefined`。

---

## 10. 生命周期钩子详解

所有钩子遵循统一的 `(input, output) => Promise<void>` 模式，即插件接收输入并修改输出对象。

### 10.1 全局事件钩子

| 钩子 | 触发时机 | 输入 | 输出 |
|------|----------|------|------|
| `event` | 任何系统事件 | `{ event: Event }` | 无 |
| `config` | 插件初始化后（加载配置完毕时） | `Config` | 无 |

`event` 钩子在插件初始化时自动订阅所有总线事件，每次事件发生时遍历调用所有插件的该钩子。

### 10.2 聊天消息钩子

| 钩子 | 触发时机 | 输入 | 输出 |
|------|----------|------|------|
| `chat.message` | 收到新用户消息 | `{ sessionID, agent?, model?, messageID?, variant? }` | `{ message, parts }` |
| `chat.params` | 向 LLM 发送参数前 | `{ sessionID, agent, model, provider, message }` | `{ temperature, topP, topK, maxOutputTokens, options }` |
| `chat.headers` | 向 LLM 发送请求头前 | `{ sessionID, agent, model, provider, message }` | `{ headers }` |

### 10.3 实验性聊天钩子

| 钩子 | 触发时机 | 输入 | 输出 |
|------|----------|------|------|
| `experimental.chat.system.transform` | 系统提示词构建时 | `{ sessionID?, model }` | `{ system: string[] }` |
| `experimental.chat.messages.transform` | 消息列表构建时 | `{}` | `{ messages: { info, parts }[] }` |
| `experimental.session.compacting` | 会话压缩开始前 | `{ sessionID }` | `{ context: string[]; prompt?: string }` |
| `experimental.compaction.autocontinue` | 压缩成功后的自动继续判断 | `{ sessionID, agent, model, provider, message, overflow }` | `{ enabled: boolean }` |
| `experimental.text.complete` | 文本完成请求 | `{ sessionID, messageID, partID }` | `{ text: string }` |

### 10.4 权限钩子

| 钩子 | 触发时机 | 输入 | 输出 |
|------|----------|------|------|
| `permission.ask` | 权限请求发生时 | `Permission` | `{ status: "ask" \| "deny" \| "allow" }` |

### 10.5 命令与工具执行钩子

| 钩子 | 触发时机 | 输入 | 输出 |
|------|----------|------|------|
| `command.execute.before` | 命令执行前 | `{ command, sessionID, arguments }` | `{ parts: Part[] }` |
| `tool.execute.before` | 工具执行前 | `{ tool, sessionID, callID }` | `{ args: any }` |
| `tool.execute.after` | 工具执行后 | `{ tool, sessionID, callID, args }` | `{ title, output, metadata }` |
| `tool.definition` | 工具定义发送给 LLM 前 | `{ toolID }` | `{ description, parameters }` |

### 10.6 Shell 环境钩子

| 钩子 | 触发时机 | 输入 | 输出 |
|------|----------|------|------|
| `shell.env` | 构建 shell 环境变量时 | `{ cwd, sessionID?, callID? }` | `{ env: Record<string, string> }` |

### 10.7 钩子使用示例 -- 系统提示词转换

```typescript
export const CustomSystemPromptPlugin: Plugin = async (_ctx) => {
  return {
    "experimental.chat.system.transform": async (input, output) => {
      // 在现有系统提示词基础上追加自定义指令
      output.system.push("你是一个专注于代码安全的 AI 助手。")
      output.system.push("请在每次回答前先进行安全审查。")
    },
  }
}
```

### 10.8 钩子使用示例 -- 工具执行拦截

```typescript
export const ToolAuditPlugin: Plugin = async (_ctx) => {
  return {
    "tool.execute.before": async (input, output) => {
      console.log(`[审计] 工具 "${input.tool}" 即将执行，参数:`, output.args)
    },
    "tool.execute.after": async (input, output) => {
      console.log(`[审计] 工具 "${input.tool}" 执行完毕，结果:`, output.output)
    },
  }
}
```

### 10.9 钩子使用示例 -- 压缩流程控制

```typescript
export const CompactionPlugin: Plugin = async (_ctx) => {
  return {
    "experimental.session.compacting": async (input, output) => {
      // 添加自定义压缩上下文
      output.context.push("优先保留最近的代码变更相关的消息。")
      output.context.push("保留所有与安全问题相关的对话。")
    },
    "experimental.compaction.autocontinue": async (input, output) => {
      // 当上下文溢出时禁用自动继续，让用户手动确认
      if (input.overflow) {
        output.enabled = false
      }
    },
  }
}
```

---

## 11. 插件发现与加载

### 11.1 插件来源

插件通过配置中的 `plugin` 字段声明，支持两种来源：

**1. npm 包插件** -- 以 npm 包名形式声明：
```jsonc
{
  "plugin": [
    "@opencode-ai/plugin-example",
    ["@opencode-ai/plugin-with-options", { "setting": "value" }]
  ]
}
```

**2. 本地文件插件** -- 以相对路径、绝对路径或 `file://` 协议声明：
```jsonc
{
  "plugin": [
    "./my-plugin.ts",
    "file:///home/user/plugins/custom.js",
    "/absolute/path/to/plugin/index.ts"
  ]
}
```

### 11.2 自动发现

OpenCode 还会自动扫描项目目录下的 `.opencode/plugin/` 和 `.opencode/plugins/` 目录，加载其中的所有 `.ts` 和 `.js` 文件：

```
.opencode/
  plugin/
    my-tool.ts        # 自动加载为插件
    custom-auth.js    # 自动加载为插件
  plugins/
    another.ts        # 自动加载为插件
```

### 11.3 加载流程

`PluginLoader.loadExternal()` 是加载外部插件的核心函数，处理流程如下：

1. **解析阶段 (Plan)**: 从配置项解析出插件规范器 (specifier) 和选项
2. **解析目标 (Resolve)**: 确定插件在磁盘上的实际位置
   - npm 包：通过 `Npm.add()` 自动安装到缓存目录
   - 本地文件：解析相对路径、绝对路径和 `file://` URL
3. **入口检测**: 读取 `package.json` 的 `exports["./server"]` 或 `exports["./tui"]` 确定入口
4. **兼容性检查** (仅 npm 包): 校验 `package.json` 的 `engines.opencode` 版本约束
5. **动态导入**: 使用 `import()` 加载插件模块
6. **模块校验**: 
   - 检查 `default export` 结构
   - 验证导出的函数类型（只包含 `server()` 或 `tui()` 之一）
   - 检查 `id` 字段
7. **重试机制** (仅本地文件): 如果本地文件插件首次加载失败，在依赖安装完成后会进行一次重试

### 11.4 插件去重

当多个配置文件（全局和本地）中声明了同名插件时，采用后声明的优先（latter wins），按以下规则去重：
- npm 包：按包名去重
- 本地文件：按文件 URL 去重

### 11.5 插件元数据

插件加载后，元数据记录在 `plugin-meta.json` 文件中（位于状态目录），包含：
- 加载次数、首次加载时间、最后加载时间、修改时间
- 文件指纹（用于检测变更）
- npm 包的请求版本和实际安装版本

### 11.6 Deprecated 插件过滤

部分旧 npm 包名已变为内置功能，插件系统会自动忽略这些包：

```
opencode-openai-codex-auth  -> 已内置
opencode-copilot-auth       -> 已内置
```

---

## 12. 内置插件

OpenCode 内置了多个认证相关的内部插件，在启动时自动加载（无需在配置中声明）：

| 插件 | 功能 |
|------|------|
| `CodexAuthPlugin` | OpenAI Codex 认证 |
| `CopilotAuthPlugin` | GitHub Copilot 认证 |
| `GitlabAuthPlugin` | GitLab 认证 |
| `PoeAuthPlugin` | Poe 认证 |
| `CloudflareWorkersAuthPlugin` | Cloudflare Workers 认证 |
| `CloudflareAIGatewayAuthPlugin` | Cloudflare AI Gateway 认证 |
| `AzureAuthPlugin` | Azure 认证 |

这些内部插件在外部配置插件之前加载，且执行顺序是顺序的（sequential），保证钩子注册和执行顺序在多次运行中保持一致。

---

## 13. 完整示例

### 13.1 最小化 Server 插件

```typescript
// my-plugin.ts
import type { Plugin } from "@opencode-ai/plugin"
import { tool } from "@opencode-ai/plugin/tool"

const myPlugin: Plugin = async (_ctx) => {
  return {
    tool: {
      hello: tool({
        description: "向指定的人打招呼",
        args: {
          name: tool.schema.string().describe("对方的名字"),
        },
        async execute(args, ctx) {
          ctx.metadata({ title: `正在向 ${args.name} 打招呼...` })
          return `你好，${args.name}！今天是美好的一天。`
        },
      }),
    },
    "chat.params": async (input, output) => {
      output.temperature = 0.5
    },
  }
}

export default { id: "my-plugin", server: myPlugin }
```

### 13.2 TUI 插件完整示例

```typescript
import type { TuiPlugin } from "@opencode-ai/plugin/tui"
import { createBindingLookup } from "@opencode-ai/plugin/tui"

const myTuiPlugin: TuiPlugin = async (api, options) => {
  // 注册快捷键
  const bindings = createBindingLookup({
    "my-action": { key: "Ctrl+g", command: "my-plugin.action" },
  })

  // 注册自定义路由
  const unregister = api.route.register([
    {
      name: "my-dashboard",
      render: ({ params }) => {
        // 返回 JSX 组件（需 @opentui/solid）
        return null
      },
    },
  ])

  // 注册 UI 插槽
  api.slots.register({
    name: "home_footer",
    render: () => {
      // 在主页底部渲染自定义内容
      return null
    },
  })

  // 监听事件
  const unlisten = api.event.on("session.created", (event) => {
    api.ui.toast({ message: "新会话已创建" })
  })

  // 持久化存储
  api.kv.set("last-visit", Date.now())

  // 生命周期清理
  api.lifecycle.onDispose(() => {
    unregister()
    unlisten()
  })
}

export default { id: "my-tui-plugin", tui: myTuiPlugin }
```

### 13.3 认证 + Provider 插件完整示例

```typescript
import type { Plugin } from "@opencode-ai/plugin"

const MyAuthProviderPlugin: Plugin = async (_ctx, _options) => {
  return {
    auth: {
      provider: "my-service",
      methods: [
        {
          type: "oauth",
          label: "使用 OAuth 登录",
          prompts: [
            {
              type: "text",
              key: "enterprise_domain",
              message: "企业域名",
              placeholder: "example.com",
              validate: (value) => value ? undefined : "域名不能为空",
            },
          ],
          async authorize(inputs) {
            const domain = inputs?.enterprise_domain
            const authUrl = `https://${domain}/oauth/authorize`
            return {
              url: authUrl,
              instructions: `请在浏览器中打开链接完成认证`,
              method: "auto",
              callback: async () => {
                // 等待 OAuth 回调
                const token = await waitForCallback()
                return {
                  type: "success",
                  provider: "my-service",
                  access: token.access,
                  refresh: token.refresh,
                  expires: token.expires,
                }
              },
            }
          },
        },
        {
          type: "api",
          label: "使用 API Key 登录",
          prompts: [
            {
              type: "text",
              key: "api_key",
              message: "API Key",
              validate: (value) => value?.length > 10 ? undefined : "API Key 格式不正确",
            },
          ],
          async authorize(inputs) {
            if (!inputs?.api_key) return { type: "failed" }
            // 验证 API Key 有效性
            const valid = await validateApiKey(inputs.api_key)
            if (!valid) return { type: "failed" }
            return { type: "success", key: inputs.api_key, provider: "my-service" }
          },
        },
      ],
      loader: async (auth, provider) => {
        const creds = await auth()
        return { Authorization: `Bearer ${creds.access}` }
      },
    },
    provider: {
      id: "my-service",
      async models(provider, ctx) {
        return {
          "my-model-1": {
            id: "my-model-1",
            name: "My Custom Model",
            // ... 模型定义 ...
          },
        }
      },
    },
  }
}

export default { id: "my-auth-provider-plugin", server: MyAuthProviderPlugin }
```

### 13.4 工作区插件完整示例

```typescript
import type { Plugin } from "@opencode-ai/plugin"
import { mkdir, rm, writeFile } from "node:fs/promises"
import { join } from "node:path"

const DockerWorkspacePlugin: Plugin = async ({ experimental_workspace, $ }) => {
  experimental_workspace.register("docker", {
    name: "Docker 工作区",
    description: "在 Docker 容器中创建工作区",
    configure(config) {
      const rand = Math.random().toString(36).slice(2, 8)
      return {
        ...config,
        directory: `/tmp/docker-workspace/${rand}`,
        extra: { containerName: `opencode-${rand}` },
      }
    },
    async create(config, env, from) {
      if (!config.directory) return
      await mkdir(config.directory, { recursive: true })
      // 启动 Docker 容器
      // ...
    },
    async remove(config) {
      if (!config.directory) return
      await rm(config.directory, { recursive: true, force: true })
      // 清理 Docker 容器
    },
    target(config) {
      return {
        type: "local",
        directory: config.directory!,
      }
    },
  })
  return {}
}

export default { id: "docker-workspace-plugin", server: DockerWorkspacePlugin }
```

---

## 14. 插件配置规范

### 14.1 配置文件中的插件声明

```jsonc
// opencode.json (全局) 或 .opencode/opencode.jsonc (项目)
{
  "plugin": [
    // 简单包名 -- 安装最新版本
    "@my-org/opencode-plugin",

    // 带版本约束
    "@my-org/opencode-plugin@^2.0.0",

    // 带选项
    ["@my-org/opencode-plugin", { "apiKey": "sk-..." }],

    // 本地文件
    "./plugins/my-tool.ts",

    // 绝对路径
    "/home/user/dev/custom-plugin/index.ts",

    // file:// 协议
    "file:///home/user/plugins/custom/index.ts"
  ]
}
```

### 14.2 插件选项的传递

插件选项以元组 `[spec, options]` 的形式传递，`options` 对象会被传递到插件的第二个参数：

```typescript
export type Plugin = (input: PluginInput, options?: PluginOptions) => Promise<Hooks>
```

### 14.3 主题配置

npm 插件可以在 `package.json` 中声明可安装的主题：

```json
{
  "name": "@my-org/my-tui-plugin",
  "oc-themes": [
    "./themes/dark.json",
    "./themes/light.json"
  ]
}
```

主题文件通过 `api.theme.install(jsonPath)` 安装，路径必须为相对路径且位于插件目录内。

---

## 15. 架构总结

```
用户配置 (opencode.json / .opencode/opencode.jsonc)
    |
    v
ConfigPlugin.load()  --> 读取 plugin 字段
    |
    v
PluginLoader.loadExternal()  --> 解析、安装、加载
    |                            |
    |                     [npm packages]     [local files]
    |                     自动安装到缓存      解析文件路径
    |                            |            |
    |                            v            v
    |                     读 package.json  exports
    |                     兼容性检查 (engines.opencode)
    |                            |
    |                            v
    |                     动态 import() 模块
    |                            |
    |                            v
    |                     校验 default export
    |                     server() 或 tui()
    |                            |
    v                            v
Plugin.index (Effect Service)   TUI Runtime
    |                            |
    |-- 内部插件                  |-- api.keymap (快捷键)
    |-- 外部插件                  |-- api.route (路由)
    |-- 顺序执行                  |-- api.ui (UI 组件)
    |-- 触发 config 钩子          |-- api.slots (插槽)
    |-- 订阅事件总线              |-- api.state (状态)
    |                            |-- api.plugins (管理)
    v                            v
Hooks[] 集合                    TUI 渲染
    |
    v
Plugin.trigger(name, input, output)
    --> 遍历所有 hook，调用匹配的钩子函数
```

插件系统的核心设计原则：
- **分离关注点**: Server 插件和 TUI 插件互斥，各司其职
- **钩子驱动**: 所有扩展点都通过 Hooks 集合统一管理
- **事件订阅**: Event 钩子自动连接到全局事件总线
- **顺序保障**: 内部插件和外部插件按顺序加载，保证确定性
- **隔离安全**: npm 包入口解析限制在包目录内；兼容性检查防止版本不匹配
- **自安装**: npm 插件无需手动安装，在首次加载时自动解析和安装
