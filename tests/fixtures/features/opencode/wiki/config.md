# OpenCode 配置系统文档

## 概述

OpenCode 的配置系统是一个多层级的配置加载与合并框架，支持从多个来源加载配置，并按照优先级规则进行深度合并。配置文件中可使用变量替换语法（`{env:VAR}` 和 `{file:path}`），且对插件的来源（本地/全局、文件路径/作用域）进行追踪，以便在执行安装、写入和诊断时做出位置敏感的决策。

所有配置项均为可选字段，未显式设置时使用内置默认值。

---

## 配置加载流程

配置加载遵循严格的优先级顺序，后加载的配置会覆盖先加载的配置。以下是完整的加载流程：

```
┌──────────────────────────────────────────────────────────────────┐
│                      配置合并 (高优先级在上，覆盖低优先级)          │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [最低优先级]                                                     │
│     │                                                            │
│     ▼                                                            │
│  1. 远程 Well-Known 配置                                          │
│     对于每个已认证的 wellknown 类型 provider，请求:                 │
│     GET {baseURL}/.well-known/opencode                           │
│     如果返回中包含 remote_config，则进一步请求远程配置文件           │
│     支持通过 headers 进行鉴权                                       │
│     对 remote_config.url 应用 ConfigVariable 变量替换              │
│     scope: global                                                │
│     │                                                            │
│     ▼                                                            │
│  2. 全局配置文件                                                  │
│     按以下顺序合并（后加载的文件覆盖先加载的）:                      │
│     a. ~/.config/opencode/config.json                            │
│     b. ~/.config/opencode/opencode.json                          │
│     c. ~/.config/opencode/opencode.jsonc                         │
│     scope: global                                                │
│     │                                                            │
│     ▼                                                            │
│  3. OPENCODE_CONFIG 环境变量覆盖                                   │
│     如果设置了此环境变量，指定的配置文件将作为额外的全局配置加载       │
│     scope: 取决于是否在项目目录内（通常为 global）                    │
│     │                                                            │
│     ▼                                                            │
│  4. 项目配置文件 (从工作区根目录向上遍历)                            │
│     从当前目录向上搜索到 worktree 根目录，查找:                       │
│     - opencode.jsonc                                             │
│     - opencode.json                                              │
│     注意: 如果设置了 OPENCODE_DISABLE_PROJECT_CONFIG 则跳过        │
│     scope: local                                                 │
│     │                                                            │
│     ▼                                                            │
│  5. .opencode 目录内的配置文件                                     │
│     从当前目录向上遍历查找 ,opencode 目录:                           │
│     - .opencode/opencode.json                                    │
│     - .opencode/opencode.jsonc                                   │
│     同时加载目录中的:                                              │
│     - {command,commands}/**/*.md     (自定义 slash 命令)           │
│     - {agent,agents}/**/*.md        (自定义 agent)               │
│     - {mode,modes}/*.md             (自定义 mode, @deprecated)    │
│     - {plugin,plugins}/*.{ts,js}    (本地插件)                    │
│     并自动执行 npm install 安装 @opencode-ai/plugin 依赖            │
│     scope: local                                                 │
│     │                                                            │
│     ▼                                                            │
│  6. OPENCODE_CONFIG_CONTENT 环境变量                               │
│     直接提供 JSONC 格式的配置字符串，而非文件路径                      │
│     scope: local                                                 │
│     │                                                            │
│     ▼                                                            │
│  7. 账户/组织远程配置 (Console)                                    │
│     如果用户已登录且有活跃组织:                                     │
│     GET {consoleUrl}/api/config                                  │
│     从 console 获取的 provider 被标记为 consoleManagedProviders     │
│     scope: global                                                │
│     │                                                            │
│     ▼                                                            │
│  8. 托管配置目录 (Managed Config)                                  │
│     系统级托管配置目录中的文件:                                     │
│     - macOS:  /Library/Application Support/opencode               │
│     - Windows: {ProgramData}/opencode                            │
│     - Linux:   /etc/opencode                                     │
│     可被 OPENCODE_TEST_MANAGED_CONFIG_DIR 环境变量覆盖             │
│     scope: global                                                │
│     │                                                            │
│     ▼                                                            │
│  [最高优先级]                                                     │
│  9. macOS 托管偏好设置 (MDM .mobileconfig)                          │
│     仅 macOS 平台，通过 plist 文件提供:                             │
│     - /Library/Managed Preferences/{user}/ai.opencode.managed.plist│
│     - /Library/Managed Preferences/ai.opencode.managed.plist     │
│     使用 plutil 工具转换为 JSON                                    │
│     这是最高优先级的配置来源，通常由企业 IT 通过 MDM 推送              │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 合并流程中的后处理

上述加载完成后，配置系统还会执行以下后处理步骤：

1. **Agent 配置合并**: `mode` 字段中定义的每个 mode 配置被合并到 `agent` 字段中，mode 名称作为 agent 名称，并强制设置 `mode: "primary"`。

2. **权限转换**: 如果配置中包含已弃用的 `tools` 字段（`{ toolName: boolean }` 映射），会被自动转换为 `permission` 字段。`write`/`edit`/`patch` 工具合并为 `permission.edit`。

3. **用户名回退**: 如果未设置 `username`，自动使用系统用户名。

4. **autoshare 兼容**: 如果设置了已弃用的 `autoshare: true` 但未设置 `share`，则自动将 `share` 设为 `"auto"`。

5. **Flag 覆盖**:
   - `OPENCODE_PERMISSION` — 原生的 permission JSON，合并到配置的 permission 中
   - `OPENCODE_DISABLE_AUTOCOMPACT` — 强制 `compaction.auto = false`
   - `OPENCODE_DISABLE_PRUNE` — 强制 `compaction.prune = false`

---

## 配置文件发现规则

### 项目配置文件搜索

`ConfigPaths.files()` 函数负责搜索项目配置文件。搜索规则：

1. **起点**: 从当前工作目录 (`ctx.directory`) 开始
2. **终点**: 到工作区根目录 (`ctx.worktree`) 停止
3. **目标文件**: `opencode.jsonc` 和 `opencode.json`（按此顺序查找）
4. **搜索方向**: 自下而上（从子目录向父目录遍历）
5. **返回顺序**: 反转后返回（从根向叶，最上层优先）
6. **标志控制**: 如果设置了 `OPENCODE_DISABLE_PROJECT_CONFIG`，则不搜索项目配置文件

### .opencode 目录搜索

`ConfigPaths.directories()` 函数负责搜索配置目录。返回的唯一排序列表：

1. `~/.config/opencode` (全局配置目录)
2. 从当前目录向上到 worktree 根目录中发现的 `.opencode` 目录（如果未禁用项目配置）
3. `~/.opencode` (home 目录中的 `.opencode`，但仅在 home 目录本身搜索)
4. `OPENCODE_CONFIG_DIR` 环境变量指定的目录（如果设置）

### 全局配置文件选择

`globalConfigFile()` 函数按以下顺序查找第一个存在的全局配置文件：

1. `~/.config/opencode/opencode.jsonc`
2. `~/.config/opencode/opencode.json`
3. `~/.config/opencode/config.json`

如果都不存在，返回 `opencode.jsonc` 的路径（用于后续创建）。

### Legacy 配置文件迁移

如果全局配置目录中存在名为 `config` 的旧格式 TOML 文件，系统会自动读取并转换为 JSON 格式（`config.json`），然后删除旧文件。转换期间，`provider` 和 `model` 字段会合并为 `provider/model` 格式的字符串。

---

## 配置合并策略

### 深度合并

使用 `remeda` 库的 `mergeDeep` 函数进行深度合并：

- **普通字段**: 后来的值覆盖先前的值
- **嵌套对象**: 递归深度合并（而非整层替换）
- **instructions 数组**: 特殊处理 —— 使用 `new Set()` 去重后进行拼接合并，而非覆盖

### 合并函数

配置系统使用两种合并策略：

1. **`mergeConfig(target, source)`**: 标准的 `mergeDeep` 合并，用于所有常规配置字段。

2. **`mergeConfigConcatArrays(target, source)`**: 在标准合并的基础上，对 `instructions` 数组字段执行去重拼接。这是配置加载流程中实际使用的合并函数。

### 插件来源追踪 (Plugin Origin Tracking)

插件配置在加载过程中具有特殊的处理逻辑：

1. **声明时归一化**: 当从配置文件中读取插件定义时，路径形式的 plugin spec（如 `./plugin.ts`）会被立即解析为相对于配置文件的绝对 `file://` URL。这避免了后续在不同目录上下文中重新解析导致的错误。

2. **来源标记**: 每个插件 spec 在合并时都会附带其 `source`（来源文件路径）和 `scope`（`"local"` 或 `"global"`）信息。scope 判定规则：
   - 如果 source 以 `http://` 或 `https://` 开头: `"global"`
   - 如果 source 是 `"OPENCODE_CONFIG_CONTENT"`: `"local"`
   - 如果 source 路径包含在当前项目目录内: `"local"`
   - 其他情况: `"global"`

3. **去重合并 (`deduplicatePluginOrigins`)**: 基于插件的加载标识符进行去重：
   - 对于 `file://` 协议的插件: 使用完整 file URL 作为标识
   - 对于 npm 包插件: 使用 `parsePluginSpecifier(spec).pkg` 提取的包名作为标识
   - 去重从最后一个（最高优先级）的配置源开始，保留先遇到（更高优先级）的版本
   - 最终结果存储在 `result.plugin_origins`（runtime 内部数据）和 `result.plugin`（精简后对外暴露）中

4. **自动插件发现**: `.opencode` 目录下的 `plugin/*.{ts,js}` 和 `plugins/*.{ts,js}` 文件会被自动发现并加载为本地插件。

---

## 变量替换 (ConfigVariable)

配置文件支持两种变量替换语法，在解析 JSONC 之前执行：

### 环境变量替换 `{env:NAME}`

```jsonc
{
  "provider": {
    "my-provider": {
      "options": {
        "apiKey": "{env:MY_API_KEY}"
      }
    }
  }
}
```

- 语法: `{env:VAR_NAME}`
- 如果环境变量不存在，替换为空字符串

### 文件内容替换 `{file:path}`

```jsonc
{
  "agent": {
    "custom-agent": {
      "prompt": "{file:~/templates/custom-agent-prompt.md}"
    }
  }
}
```

- 语法: `{file:path}`
- 路径类型:
  - 以 `~/` 开头: 相对于用户 home 目录
  - 绝对路径: 直接使用
  - 相对路径: 相对于配置文件所在目录
- 读取的文件内容会被自动 trim 并通过 `JSON.stringify` 转义后嵌入
- 如果 `{file:xxx}` 出现在被 `//` 注释的行中（之前只有空白和 `//`），则该语法不会被替换
- 默认行为（`missing: "error"`）: 如果文件不存在则抛出异常
- 可以设置 `missing: "empty"` 使文件不存在时返回空字符串（用于 well-known remote config 的场景）

### Well-Known Remote Config 变量替换

对于远程配置的 URL 和 headers 值，系统会自动应用变量替换，允许在远程配置 URL 中使用 `{env:TOKEN}` 等语法。

---

## 服务接口 (Service Interface)

### get()

获取当前实例（项目作用域）的配置。

```typescript
const config = await Config.get()
```

返回经过完整合并后的 `Info` 类型配置对象。

### getGlobal()

获取全局配置（不包含项目级配置和远程配置的合并）。

```typescript
const globalConfig = await Config.getGlobal()
```

全局配置会被缓存（TTL = Infinity），可通过 `invalidate()` 清除缓存。

### getConsoleState()

获取 Console 状态信息：

```typescript
const state = await Config.getConsoleState()
// { consoleManagedProviders: string[], activeOrgName?: string, switchableOrgCount: number }
```

- `consoleManagedProviders`: 从 Console 远程配置获取的 provider ID 列表
- `activeOrgName`: 当前活跃组织名称
- `switchableOrgCount`: 可切换的组织数量

### update(config)

将配置写入当前项目的 `config.json`：

```typescript
await Config.update({ model: "anthropic/claude-sonnet-4" })
```

- 写入位置: `{projectDir}/config.json`
- 会先读取现有配置，与之深度合并后再写入

### updateGlobal(config)

更新全局配置文件：

```typescript
const { info, changed } = await Config.updateGlobal({ logLevel: "DEBUG" })
```

- 对于 `.jsonc` 文件: 使用 `jsonc-parser` 的 `modify`/`applyEdits` 进行精确修补，保留原始格式和注释
- 对于 `.json` 文件: 重新序列化整个配置
- 如果 `shell` 被设为空字符串，写入时会自动忽略（避免残留空键）
- 修改成功后会自动调用 `invalidate()` 使全局配置缓存失效
- 返回 `{ info, changed }` 指示是否实际发生了变更

### invalidate()

清除全局配置缓存，下次调用 `getGlobal()` 时会重新加载：

```typescript
await Config.invalidate()
```

### directories()

获取当前实例的所有配置目录：

```typescript
const dirs = await Config.directories()
// [Global.Path.config, ...project .opencode dirs, ~/.opencode, OPENCODE_CONFIG_DIR?]
```

### waitForDependencies()

等待所有异步依赖安装（npm install）完成：

```typescript
await Config.waitForDependencies()
```

---

## 配置 Schema 完整参考

### 顶层字段

| 字段 | 类型 | 描述 |
|------|------|------|
| `$schema` | `string` | JSON Schema 引用 URL，自动设为 `"https://opencode.ai/config.json"` |
| `shell` | `string` | 终端/bash 工具使用的默认 shell |
| `logLevel` | `"DEBUG" \| "INFO" \| "WARN" \| "ERROR"` | 日志级别 |
| `server` | `ServerConfig` | `opencode serve` 和 `web` 命令的服务器配置 |
| `command` | `Record<string, CommandInfo>` | 自定义 slash 命令定义 |
| `skills` | `SkillsInfo` | 额外的技能文件夹路径和 URL |
| `reference` | `Record<string, ReferenceEntry>` | 命名的 git 或本地目录引用，可通过 @ 提及 |
| `watcher` | `{ ignore?: string[] }` | 文件监视器忽略模式 |
| `snapshot` | `boolean` | 启用/禁用文件快照跟踪（默认 `true`） |
| `plugin` | `PluginSpec[]` | 插件规格数组 |
| `share` | `"manual" \| "auto" \| "disabled"` | 控制会话分享行为 |
| `autoshare` | `boolean` | **@deprecated** 使用 `share` 代替 |
| `autoupdate` | `boolean \| "notify"` | 自动更新行为 |
| `disabled_providers` | `string[]` | 禁用的 provider ID 列表 |
| `enabled_providers` | `string[]` | 当设置时，仅启用这些 provider |
| `model` | `string` (provider/model) | 默认模型 |
| `small_model` | `string` (provider/model) | 轻量任务的小模型 |
| `default_agent` | `string` | 默认 agent 名称（必须是 primary agent） |
| `username` | `string` | 自定义显示名称 |
| `mode` | `Record<string, AgentInfo>` | **@deprecated** 使用 `agent` 代替 |
| `agent` | `Record<string, AgentInfo>` | Agent 配置 |
| `provider` | `Record<string, ProviderInfo>` | 自定义 provider 配置和模型覆盖 |
| `mcp` | `Record<string, McpInfo \| { enabled: boolean }>` | MCP 服务器配置 |
| `formatter` | `boolean \| Record<string, FormatterEntry>` | 格式化器配置 |
| `lsp` | `boolean \| Record<string, LspEntry>` | LSP 服务器配置 |
| `instructions` | `string[]` | 额外的指令文件或模式 |
| `layout` | `LayoutConfig` | **@deprecated** 总是使用 stretch 布局 |
| `permission` | `PermissionConfig` | 权限规则配置 |
| `tools` | `Record<string, boolean>` | 遗留的工具启用/禁用（映射到 permission） |
| `attachment` | `AttachmentConfig` | 附件处理配置（图片大小限制等） |
| `enterprise` | `{ url?: string }` | 企业版 URL |
| `tool_output` | `{ max_lines?: number, max_bytes?: number }` | 工具输出截断阈值 |
| `compaction` | `CompactionConfig` | 压缩设置 |
| `experimental` | `ExperimentalConfig` | 实验性功能 |

### ServerConfig

| 字段 | 类型 | 描述 |
|------|------|------|
| `port` | `number` (PositiveInt) | 监听端口 |
| `hostname` | `string` | 监听主机名 |
| `mdns` | `boolean` | 启用 mDNS 服务发现 |
| `mdnsDomain` | `string` | 自定义 mDNS 域名（默认 `opencode.local`） |
| `cors` | `string[]` | 额外的 CORS 允许域名 |

### CommandInfo

> 也可从 `.opencode/{command,commands}/**/*.md` 文件（Markdown + frontmatter）加载。

| 字段 | 类型 | 描述 |
|------|------|------|
| `template` | `string` | 命令的提示词模板 |
| `description` | `string` | 命令描述 |
| `agent` | `string` | 执行该命令的 agent |
| `model` | `string` | 执行该命令使用的模型 |
| `subtask` | `boolean` | 是否作为子任务执行 |

### SkillsInfo

| 字段 | 类型 | 描述 |
|------|------|------|
| `paths` | `string[]` | 额外的技能文件夹路径 |
| `urls` | `string[]` | 从 URL 获取技能（如 `https://example.com/.well-known/skills/`） |

### ReferenceEntry

可以是以下任何形式：

- `string` — 简写的 git 仓库 URL 或本地路径
- `{ repository: string, branch?: string }` — git 仓库引用
- `{ path: string }` — 本地目录引用（支持绝对路径、`~/`路径和工作区相对路径）

### PluginSpec

- `string` — 插件标识符（npm 包名或 `file://` URL）
- `[string, Record<string, unknown>]` — 带内联选项的插件标识符

### AgentInfo

> 也可从 `.opencode/{agent,agents}/**/*.md` 文件（Markdown + frontmatter）加载。

| 字段 | 类型 | 描述 |
|------|------|------|
| `model` | `string` | Agent 使用的模型 |
| `variant` | `string` | 默认模型变体 |
| `temperature` | `number` | 采样温度 |
| `top_p` | `number` | Top-p 采样 |
| `prompt` | `string` | 系统提示词 |
| `tools` | `Record<string, boolean>` | **@deprecated** 使用 `permission` |
| `disable` | `boolean` | 禁用该 agent |
| `description` | `string` | 描述何时使用该 agent |
| `mode` | `"subagent" \| "primary" \| "all"` | Agent 类型 |
| `hidden` | `boolean` | 在 @ 自动补全菜单中隐藏（仅对 `mode: subagent` 有效） |
| `options` | `Record<string, any>` | 额外选项 |
| `color` | `string` | 颜色（hex 如 `#FF5733` 或主题色如 `primary`） |
| `steps` | `number` (PositiveInt) | Agentic 迭代最大步数 |
| `maxSteps` | `number` | **@deprecated** 使用 `steps` |
| `permission` | `PermissionConfig` | Agent 级权限配置 |

内置 agent 名称为：`plan`、`build`（primary）；`general`、`explore`、`scout`（subagent）；`title`、`summary`、`compaction`（专用）。

### ProviderInfo

| 字段 | 类型 | 描述 |
|------|------|------|
| `api` | `string` | API endpoint URL |
| `name` | `string` | Provider 名称 |
| `env` | `string[]` | 需要的环境变量 |
| `id` | `string` | Provider ID |
| `npm` | `string` | npm 包名 |
| `whitelist` | `string[]` | 白名单模型 |
| `blacklist` | `string[]` | 黑名单模型 |
| `options` | `{ apiKey?, baseURL?, enterpriseUrl?, setCacheKey?, timeout?, chunkTimeout?, ... }` | Provider 选项 |
| `models` | `Record<string, ModelConfig>` | 模型配置覆盖 |

#### Provider Options

| 字段 | 类型 | 描述 |
|------|------|------|
| `apiKey` | `string` | API 密钥 |
| `baseURL` | `string` | API 基础 URL |
| `enterpriseUrl` | `string` | GitHub Enterprise URL（copilot 认证） |
| `setCacheKey` | `boolean` | 启用 promptCacheKey（默认 false） |
| `timeout` | `number \| false` | 超时时间（毫秒，默认 300000 = 5 分钟），设为 false 禁用 |
| `chunkTimeout` | `number` | SSE chunk 超时时间（毫秒） |

#### ModelConfig

| 字段 | 类型 | 描述 |
|------|------|------|
| `id` | `string` | 模型 ID |
| `name` | `string` | 模型名称 |
| `family` | `string` | 模型系列 |
| `release_date` | `string` | 发布日期 |
| `attachment` | `boolean` | 是否支持附件 |
| `reasoning` | `boolean` | 是否支持推理 |
| `temperature` | `boolean` | 是否支持温度参数 |
| `tool_call` | `boolean` | 是否支持工具调用 |
| `interleaved` | `boolean \| { field: "reasoning_content" \| "reasoning_details" }` | 交错内容配置 |
| `cost` | `{ input, output, cache_read?, cache_write?, context_over_200k? }` | 费用信息 |
| `limit` | `{ context, input?, output }` | 限制信息 |
| `modalities` | `{ input: Modality[], output: Modality[] }` | 模态支持 |
| `experimental` | `boolean` | 实验性模型 |
| `status` | `ModelStatus` | 模型状态 |
| `provider` | `{ npm?, api? }` | 模型所属 provider |
| `options` | `Record<string, any>` | 额外选项 |
| `headers` | `Record<string, string>` | 额外的请求头 |
| `variants` | `Record<string, { disabled?, ... }>` | 模型变体配置 |

### MCP 配置

MCP 服务器配置支持两种类型，通过 `type` 字段区分：

#### Local MCP

| 字段 | 类型 | 描述 |
|------|------|------|
| `type` | `"local"` | MCP 服务器连接类型 |
| `command` | `string[]` | 运行 MCP 服务器的命令和参数 |
| `environment` | `Record<string, string>` | 运行 MCP 服务器时设置的环境变量 |
| `enabled` | `boolean` | 启动时启用/禁用该 MCP 服务器 |
| `timeout` | `number` | MCP 请求超时（ms，默认 5000） |

#### Remote MCP

| 字段 | 类型 | 描述 |
|------|------|------|
| `type` | `"remote"` | MCP 服务器连接类型 |
| `url` | `string` | 远程 MCP 服务器 URL |
| `enabled` | `boolean` | 启动时启用/禁用该 MCP 服务器 |
| `headers` | `Record<string, string>` | 发送的请求头 |
| `oauth` | `OAuthConfig \| false` | OAuth 认证配置（设为 false 禁用自动检测） |
| `timeout` | `number` | MCP 请求超时（ms，默认 5000） |

**OAuth 配置字段**: `clientId`、`clientSecret`、`scope`、`redirectUri`（默认 `http://127.0.0.1:19876/mcp/oauth/callback`）

此外，MCP 还可以使用遗留格式 `{ enabled: false }` 来禁用特定服务器。

### FormatterInfo

支持两种形式：
- `boolean` — `false` 禁用所有格式化器，`true` 启用内置格式化器
- `Record<string, FormatterEntry>` — 按名称配置单个格式化器

#### FormatterEntry

| 字段 | 类型 | 描述 |
|------|------|------|
| `disabled` | `boolean` | 禁用该格式化器 |
| `command` | `string[]` | 自定义命令行 |
| `environment` | `Record<string, string>` | 环境变量 |
| `extensions` | `string[]` | 应用该格式化器的文件扩展名 |

### LSP 配置

支持两种形式：
- `boolean` — `false` 禁用所有 LSP，`true` 启用内置 LSP
- `Record<string, LspEntry>` — 按名称配置单个 LSP 服务器

#### LspEntry

| 字段 | 类型 | 描述 |
|------|------|------|
| `disabled` | `true` | 禁用该 LSP 服务器 |
| `command` | `string[]` | 启动命令 |
| `extensions` | `string[]` | 关联文件扩展名（自定义 LSP 必需） |
| `env` | `Record<string, string>` | 环境变量 |
| `initialization` | `Record<string, unknown>` | 初始化参数 |

### PermissionInfo

权限配置可以是：

1. **Action 简写**: `"ask" | "allow" | "deny"` — 对所有目标的默认行为
2. **Object 形式**: `{ [target]: Action }` — 按模式或路径配置每条规则

内置权限键：

| 键 | 类型 | 描述 |
|------|------|------|
| `read` | `Rule` | 文件读取 |
| `edit` | `Rule` | 文件编辑 |
| `glob` | `Rule` | 文件搜索 |
| `grep` | `Rule` | 文本搜索 |
| `list` | `Rule` | 目录列表 |
| `bash` | `Rule` | Bash 命令执行 |
| `task` | `Rule` | 任务执行 |
| `external_directory` | `Rule` | 外部目录访问 |
| `todowrite` | `Action` | Todo 写入 |
| `question` | `Action` | 向用户提问 |
| `webfetch` | `Action` | 网页获取 |
| `websearch` | `Action` | 网页搜索 |
| `codesearch` | `Action` | 代码搜索 |
| `repo_clone` | `Rule` | 仓库克隆 |
| `repo_overview` | `Rule` | 仓库概览 |
| `lsp` | `Rule` | LSP 操作 |
| `doom_loop` | `Action` | 循环检测 |
| `skill` | `Rule` | 技能调用 |

`Rule` 可以是 `Action` 或 `Object` — 支持深度嵌套配置，允许精确到路径/域名的规则。

### AttachmentConfig

| 字段 | 类型 | 描述 |
|------|------|------|
| `image` | `ImageConfig` | 图片附件配置 |

#### ImageConfig

| 字段 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `auto_resize` | `boolean` | `true` | 超限时自动调整图片大小 |
| `max_width` | `number` | `2000` | 最大图片宽度（像素） |
| `max_height` | `number` | `2000` | 最大图片高度（像素） |
| `max_base64_bytes` | `number` | `4718592` | 最大 base64 字节数 |

### ToolOutputConfig

| 字段 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `max_lines` | `number` (PositiveInt) | `2000` | 工具输出截断的最大行数 |
| `max_bytes` | `number` (PositiveInt) | `51200` | 工具输出截断的最大字节数 |

当输出超过任一限制时，完整文本被写入截断目录，返回预览。

### CompactionConfig

| 字段 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `auto` | `boolean` | `true` | 上下文满时自动压缩 |
| `prune` | `boolean` | `true` | 启用旧工具输出剪枝 |
| `tail_turns` | `number` (NonNegativeInt) | `2` | 压缩时保留的最近用户轮次数量 |
| `preserve_recent_tokens` | `number` (NonNegativeInt) | — | 压缩后保留的最大 token 数 |
| `reserved` | `number` (NonNegativeInt) | — | 压缩时的 token 缓冲区 |

### ExperimentalConfig

| 字段 | 类型 | 描述 |
|------|------|------|
| `disable_paste_summary` | `boolean` | 禁用粘贴摘要 |
| `batch_tool` | `boolean` | 启用 batch 工具 |
| `openTelemetry` | `boolean` | 启用 OpenTelemetry spans（使用 `experimental_telemetry` 标志） |
| `primary_tools` | `string[]` | 仅对 primary agent 可用的工具 |
| `continue_loop_on_deny` | `boolean` | 工具调用被拒绝时继续 agent 循环 |
| `mcp_timeout` | `number` (PositiveInt) | MCP 请求超时时间（毫秒） |

---

## 配置示例

### 基础配置 — 设置模型和日志级别

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "model": "anthropic/claude-sonnet-4",
  "small_model": "anthropic/claude-haiku-4",
  "logLevel": "INFO"
}
```

### 自定义 Provider

```jsonc
{
  "provider": {
    "my-openai-compatible": {
      "name": "My Custom Provider",
      "api": "https://api.example.com/v1",
      "options": {
        "apiKey": "{env:CUSTOM_API_KEY}",
        "timeout": 120000
      },
      "models": {
        "my-model": {
          "name": "My Custom Model",
          "limit": {
            "context": 128000,
            "output": 8192
          }
        }
      }
    }
  },
  "model": "my-openai-compatible/my-model"
}
```

### MCP 服务器 (本地)

```jsonc
{
  "mcp": {
    "filesystem": {
      "type": "local",
      "command": ["npx", "-y", "@anthropic/mcp-filesystem"],
      "enabled": true,
      "timeout": 10000
    },
    "context7": {
      "type": "remote",
      "url": "https://mcp.context7.com/mcp",
      "enabled": false
    }
  }
}
```

### 权限配置

```jsonc
{
  "permission": {
    "edit": {
      "*.lock": "deny",
      ".env*": "deny",
      "*": "allow"
    },
    "bash": {
      "npm *": "allow",
      "git *": "allow",
      "*": "ask"
    },
    "webfetch": "allow",
    "websearch": "allow"
  }
}
```

也可以用简写形式（对所有目标生效）：

```jsonc
{
  "permission": "allow"
}
```

### Agent 配置

```jsonc
{
  "agent": {
    "build": {
      "model": "anthropic/claude-sonnet-4",
      "steps": 10,
      "description": "Your primary build agent"
    },
    "code-reviewer": {
      "mode": "subagent",
      "description": "Reviews code for bugs and style issues",
      "prompt": "You are a code reviewer. Focus on correctness and readability.",
      "model": "anthropic/claude-sonnet-4",
      "color": "#6C5CE7"
    },
    "plan": {
      "permission": {
        "edit": "deny",
        "bash": "deny"
      }
    }
  },
  "default_agent": "build"
}
```

### 指令和参考

```jsonc
{
  "instructions": [
    "CONVENTIONS.md",
    ".cursor/rules/*.md"
  ],
  "reference": {
    "docs": {
      "repository": "https://github.com/org/docs-repo",
      "branch": "main"
    },
    "shared-lib": {
      "path": "~/projects/shared-library"
    }
  }
}
```

### 插件和技能

```jsonc
{
  "plugin": [
    "@opencode-ai/plugin-mcp",
    ["./my-local-plugin.ts", { "option1": "value" }]
  ],
  "skills": {
    "paths": ["~/.opencode/skills", "./project-skills"],
    "urls": ["https://internal.company.com/.well-known/skills/"]
  }
}
```

### 完整生产级示例

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "shell": "/usr/bin/zsh",
  "logLevel": "WARN",
  "model": "anthropic/claude-sonnet-4",
  "small_model": "anthropic/claude-haiku-4",
  "default_agent": "build",
  "username": "Alice",

  "server": {
    "port": 8080,
    "mdns": true
  },

  "permission": {
    "edit": "allow",
    "bash": {
      "rm -rf *": "deny",
      "npm *": "allow",
      "git *": "allow",
      "*": "ask"
    },
    "webfetch": "allow",
    "websearch": "allow"
  },

  "agent": {
    "build": {
      "steps": 15,
      "temperature": 0.3
    },
    "plan": {
      "permission": {
        "edit": "deny",
        "bash": "deny"
      }
    }
  },

  "mcp": {
    "filesystem": {
      "type": "local",
      "command": ["npx", "-y", "@anthropic/mcp-filesystem"],
      "enabled": true
    }
  },

  "compaction": {
    "auto": true,
    "prune": true,
    "tail_turns": 3,
    "preserve_recent_tokens": 16000
  },

  "tool_output": {
    "max_lines": 3000,
    "max_bytes": 102400
  },

  "attachment": {
    "image": {
      "max_width": 1024,
      "max_height": 1024
    }
  },

  "experimental": {
    "batch_tool": true,
    "continue_loop_on_deny": true
  },

  "instructions": [
    "CONVENTIONS.md",
    ".cli/opencode-instructions.md"
  ]
}
```

---

## 解析与验证

### JSONC 解析

配置文件使用 `jsonc-parser` 库进行解析，支持 `allowTrailingComma: true`。如果解析遇到错误，系统会报告每个错误的：

- 错误码（如 `InvalidSymbol`、`PropertyNameExpected`）
- 发生位置（行号和列号）
- 问题所在行的内容及光标指示器

### Schema 验证

配置数据通过 Effect Schema 进行验证。验证规则包括：

- `strict()` 模式：未知的顶层键会被拒绝并报告为 `unrecognized_keys` 错误
- 所有字段都有严格的类型检查
- 整数类型字段（如 `max_lines`、`port`、`tail_turns`）使用 PositiveInt/NonNegativeInt 约束
- `mode` 字段中遗留的 `theme`、`keybinds`、`tui` 键会被检测并发出废弃警告

### $schema 自动注入

当配置文件不含 `$schema` 字段时，系统会自动注入 `"https://opencode.ai/config.json"` 并重写该文件。

---

## 配置写入行为

### 项目配置写入 (`update`)

1. 写入到 `<projectDir>/config.json`
2. 读取现有文件内容，与传入的配置深度合并
3. 写入前会剥离 `plugin_origins` 内部字段（该字段仅在运行时存在）

### 全局配置写入 (`updateGlobal`)

1. 根据文件扩展名选择策略：
   - **`.jsonc`**: 使用 `patchJsonc` 进行精确修补，保留注释、格式和缩进
   - **`.json`**: 重新序列化整个文件
2. `shell` 设为空字符串时自动忽略（避免残留 `"shell": ""`）
3. 写入成功后自动清除缓存

### patchJsonc 工作原理

对于 `.jsonc` 文件，系统不会重新序列化整个文件，而是使用 `jsonc-parser` 的 `modify`/`applyEdits` API 进行增量修改：

- 标量值更新: 只修改目标位置的值
- 对象更新: 递归展开为路径-值对，逐层修改
- 保留所有注释、尾逗号和原有格式
- 使用 2 空格缩进

---

## 兼容性与迁移

### 已弃用字段自动迁移

| 旧字段 | 新字段 | 处理方式 |
|--------|--------|----------|
| `theme` / `keybinds` / `tui` | TUI 配置文件 | 读取时删除并发出警告 |
| `autoshare: true` | `share: "auto"` | 自动设置 |
| `tools: { name: boolean }` | `permission: { name: action }` | 自动转换 |
| `mode.Name` | `agent.Name` (mode: "primary") | 合并到 agent 中 |
| `maxSteps` (agent) | `steps` | 自动迁移 |
| TOML 格式全局配置 | JSON 格式 | 自动转换并删除旧文件 |

### Enabled/Disabled Providers

- `disabled_providers`: 阻止特定 provider 的自动加载
- `enabled_providers`: 白名单模式 —— 设置后**仅**这些 provider 可用，其他全部忽略

---

## 环境变量参考

| 环境变量 | 用途 |
|----------|------|
| `OPENCODE_CONFIG` | 指定额外的配置文件的绝对路径 |
| `OPENCODE_CONFIG_CONTENT` | 直接传递 JSONC 格式的配置内容字符串 |
| `OPENCODE_CONFIG_DIR` | 指定额外的配置目录 |
| `OPENCODE_DISABLE_PROJECT_CONFIG` | 设为任意值以禁用项目配置文件加载 |
| `OPENCODE_DISABLE_AUTOCOMPACT` | 强制禁用自动压缩 |
| `OPENCODE_DISABLE_PRUNE` | 强制禁用输出剪枝 |
| `OPENCODE_PERMISSION` | 传递额外的权限规则（JSON 格式） |
| `OPENCODE_CONSOLE_TOKEN` | Console 认证令牌（由系统自动设置） |
| `OPENCODE_TEST_MANAGED_CONFIG_DIR` | 覆盖托管配置目录（测试用） |
