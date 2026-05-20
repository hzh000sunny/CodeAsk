# @opencode-ai/core 包文档

## 概述

`@opencode-ai/core` 是 OpenCode 项目的**基础工具库**，其核心约束是**零内部工作空间依赖（ZERO internal workspace dependencies）**。所有其他包（CLI、TUI、Server 等）都依赖此包提供的共享原语，但它自身不依赖项目中任何其他包。

该包以 **Effect-TS** 作为核心范式，封装了文件系统、日志、进程管理、包管理、Schema 定义等常用功能，并为上层提供统一的依赖注入（DI）Service/Layer 模式。

**版本**: 1.14.48 | **许可**: MIT

---

## 模块详解

### 1. 全局路径管理 (`src/global.ts`)

**用途**: 基于 XDG 标准定义 opencode 应用的所有文件系统路径，并提供 Effect Service 包装以支持依赖注入。

**路径定义**:

遵循 XDG Base Directory Specification：

| 路径属性 | XDG 变量 | 典型位置 | 用途 |
|---------|---------|---------|------|
| `home` | - | `~` 或 `$OPENCODE_TEST_HOME` | 用户主目录 |
| `data` | `XDG_DATA_HOME` | `~/.local/share/opencode` | 持久化应用数据 |
| `cache` | `XDG_CACHE_HOME` | `~/.cache/opencode` | 缓存数据 |
| `config` | `XDG_CONFIG_HOME` | `~/.config/opencode` | 配置文件 |
| `state` | `XDG_STATE_HOME` | `~/.local/state/opencode` | 运行时状态 |
| `tmp` | 系统临时目录 | `/tmp/opencode` | 临时文件 |
| `bin` | - | `<cache>/bin` | 二进制工具（NPM 安装的 package binaries） |
| `log` | - | `<data>/log` | 日志文件 |
| `repos` | - | `<data>/repos` | 代码仓库存放 |

**关键导出**:

```typescript
// 单例路径对象 - 模块加载时立即创建所有目录
export const Path = { home, data, bin, log, repos, cache, config, state, tmp }

// Effect Context Service - 用于依赖注入
export class Service extends Context.Service<Service, Interface>()("@opencode/Global") {}

// Layer 构造器
export const layer = Layer.effect(Service, Effect.sync(() => Service.of(make())))
export const layerWith = (input: Partial<Interface>) => /* 自定义路径 */

// 接口定义
export interface Interface {
  readonly home: string
  readonly data: string
  readonly cache: string
  readonly config: string
  readonly state: string
  readonly tmp: string
  readonly bin: string
  readonly log: string
  readonly repos: string
}
```

**特殊行为**:
- 模块顶层使用 `await Promise.all([...])` 导入时**同步创建所有目录**
- `config` 路径可通过 `Flag.OPENCODE_CONFIG_DIR` 环境变量覆盖
- `home` 路径在测试中可通过 `OPENCODE_TEST_HOME` 环境变量覆盖
- `Flock.setGlobal({ state })` 将 state 目录注册为全局文件锁的根目录

---

### 2. 文件系统 (`src/filesystem.ts`)

**用途**: 在 Effect `FileSystem` 之上提供增强文件系统抽象，包含安全读写、JSON 操作、路径遍历和 Glob 匹配等功能。

**核心抽象**:

```typescript
export namespace AppFileSystem {
  // 自定义错误类型
  export class FileSystemError extends Schema.TaggedErrorClass<FileSystemError>()("FileSystemError", {
    method: Schema.String,
    cause: Schema.optional(Schema.Defect),
  }) {}

  // 服务接口（继承标准 FileSystem 并扩展）
  export interface Interface extends FileSystem.FileSystem {
    readonly isDir: (path: string) => Effect.Effect<boolean>
    readonly isFile: (path: string) => Effect.Effect<boolean>
    readonly existsSafe: (path: string) => Effect.Effect<boolean>     // 永不失败，返回布尔
    readonly readFileStringSafe: (path: string) => Effect.Effect<string | undefined>
    readonly readJson: (path: string) => Effect.Effect<unknown>
    readonly writeJson: (path: string, data: unknown, mode?: number) => Effect.Effect<void>
    readonly ensureDir: (path: string) => Effect.Effect<void>
    readonly writeWithDirs: (path: string, content, mode?) => Effect.Effect<void>
    readonly findUp: (target, start, stop?) => Effect.Effect<string[]>
    readonly up: (options: { targets, start, stop? }) => Effect.Effect<string[]>
    readonly globUp: (pattern, start, stop?) => Effect.Effect<string[]>
    readonly glob: (pattern, options?) => Effect.Effect<string[]>
    readonly globMatch: (pattern, filepath) => boolean
  }
}
```

**关键操作说明**:

| 方法 | 行为 |
|------|------|
| `existsSafe` | `exists` 的安全包装，文件不存在时返回 `false` 而非抛出错误 |
| `readFileStringSafe` | `readFileString` 的安全包装，`NotFound` 时返回 `undefined` |
| `writeWithDirs` | 写入文件，若父目录不存在则自动递归创建 |
| `findUp(target, start, stop?)` | 从 `start` 向上查找名为 `target` 的文件 |
| `up({ targets, start, stop? })` | 从 `start` 向上查找多个目标文件名 |
| `globUp(pattern, start, stop?)` | 从 `start` 向上逐级执行 glob 匹配 |
| `glob(pattern, options?)` | 基于 `minimatch`/`glob` 库的模式匹配 |

**平台适配函数（纯函数，无需 Effect）**:

```typescript
// MIME 类型检测
export function mimeType(p: string): string

// 路径规范化（Windows 下将 WSL/MSYS/Cygwin 路径转为原生路径）
export function normalizePath(p: string): string
export function normalizePathPattern(p: string): string

// 路径解析（支持 Windows path 转换）
export function resolve(p: string): string

// Windows 路径格式转换
export function windowsPath(p: string): string

// 路径包含关系判定
export function overlaps(a: string, b: string): boolean
export function contains(parent: string, child: string): boolean
```

**Layer 构造**:

```typescript
export const layer = Layer.effect(Service, Effect.gen(function* () { ... }))
export const defaultLayer = layer.pipe(Layer.provide(NodeFileSystem.layer))
```

---

### 3. 日志系统 (`src/util/log.ts`)

**用途**: 提供结构化日志记录，支持按级别过滤、文件持久化和服务作用域隔离。

**日志等级**:

```typescript
export const Level = z.enum(["DEBUG", "INFO", "WARN", "ERROR"])
// 优先级: DEBUG=0 < INFO=1 < WARN=2 < ERROR=3
```

**初始化**:

```typescript
// 必须在应用启动时调用
export async function init(options: Options): Promise<void>

interface Options {
  print: boolean        // true=仅输出到stderr，不写文件
  dev?: boolean         // true=使用dev.log文件
  level?: Level         // 设置日志级别（默认 INFO）
}
```

**Logger 接口**:

```typescript
export type Logger = {
  debug(message?, extra?): void
  info(message?, extra?): void
  error(message?, extra?): void
  warn(message?, extra?): void
  tag(key: string, value: string): Logger    // 添加标记
  clone(): Logger                              // 克隆当前 logger
  time(message, extra?): {                     // 计时器
    stop(): void
    [Symbol.dispose](): void
  }
}
```

**关键行为**:
- **服务作用域**: `Log.create({ service: "name" })` 时，同名 logger 会被缓存并复用
- **日志格式**: `LEVEL ISO时间 +delta前缀 message\n`，例如 `INFO  2024-01-15T10:30:00 +150ms service=agent Starting...`
- **文件轮转**: 保留最近 10 个按时间命名的日志文件，旧文件自动清理
- **开发模式**: `init({ dev: true })` 时写入固定文件 `dev.log`
- **打印模式**: `init({ print: true })` 时仅输出到 `stderr`，不写文件

**默认 Logger**: `export const Default = create({ service: "default" })`，当 Effect logger 无法确定服务名时使用。

---

### 4. 特性开关 (`src/flag/flag.ts`)

**用途**: 纯环境变量驱动的特性开关系统，读取时对模块加载开销零影响。

**分类说明**:

#### 通用开关

| 开关 | 类型 | 说明 |
|------|------|------|
| `OPENCODE_AUTO_SHARE` | boolean | 自动共享会话 |
| `OPENCODE_AUTO_HEAP_SNAPSHOT` | boolean | 自动生成堆快照 |
| `OPENCODE_DISABLE_AUTOUPDATE` | boolean | 禁用自动更新 |
| `OPENCODE_DISABLE_PRUNE` | boolean | 禁用缓存清理 |
| `OPENCODE_DISABLE_TERMINAL_TITLE` | boolean | 禁用终端标题更新 |
| `OPENCODE_DISABLE_DEFAULT_PLUGINS` | boolean | 禁用默认插件 |
| `OPENCODE_DISABLE_LSP_DOWNLOAD` | boolean | 禁用 LSP 自动下载 |
| `OPENCODE_DISABLE_AUTOCOMPACT` | boolean | 禁用对话自动压缩 |
| `OPENCODE_DISABLE_MOUSE` | boolean | 禁用鼠标交互 |
| `OPENCODE_SHOW_TTFD` | boolean | 显示首次对话耗时 |
| `OPENCODE_ENABLE_QUESTION_TOOL` | boolean | 启用问题工具 |

#### Claude Code 集成相关

| 开关 | 说明 |
|------|------|
| `OPENCODE_DISABLE_CLAUDE_CODE` | 完全禁用 Claude Code 集成 |
| `OPENCODE_DISABLE_CLAUDE_CODE_PROMPT` | 仅禁用 CC 提示包含 |
| `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS` | 禁用 CC 技能发现 |
| `OPENCODE_DISABLE_EXTERNAL_SKILLS` | 禁用外部技能 |

#### 实验性开关（受 `OPENCODE_EXPERIMENTAL` 全局控制）

`dev`/`beta`/`local` 频道默认开启选项，`prod`/`latest` 默认关闭：

| 开关 | 说明 |
|------|------|
| `OPENCODE_EXPERIMENTAL_FILEWATCHER` | 实验性文件监控 |
| `OPENCODE_EXPERIMENTAL_ICON_DISCOVERY` | 实验性图标发现 |
| `OPENCODE_EXPERIMENTAL_DISABLE_COPY_ON_SELECT` | 禁用在选中时复制 |
| `OPENCODE_ENABLE_EXA` | 启用 Exa 搜索后端 |
| `OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX` | 令牌输出上限（数字） |
| `OPENCODE_EXPERIMENTAL_OXFMT` | 实验性 OX 格式化 |
| `OPENCODE_EXPERIMENTAL_LSP_TOOL` | 实验性 LSP 工具 |
| `OPENCODE_EXPERIMENTAL_PLAN_MODE` | 实验性计划模式 |
| `OPENCODE_EXPERIMENTAL_SCOUT` | 实验性 Scout 功能 |
| `OPENCODE_EXPERIMENTAL_MARKDOWN` | 默认启用（除非显式设 false） |
| `OPENCODE_EXPERIMENTAL_WORKSPACES` | 实验性多工作区 |
| `OPENCODE_EXPERIMENTAL_EVENT_SYSTEM` | 实验性事件系统 |
| `OPENCODE_ENABLE_PARALLEL` | 启用并行执行 |
| `OPENCODE_EXPERIMENTAL_CUSTOMIZE_SKILL` | 实验性自定义技能（dev/beta/local 默认开） |

#### 运行时求值的三项（getter 模式）

这些开关使用 getter 属性，在访问时才读取环境变量，允许测试和 CLI 在运行时动态设置：

```typescript
get OPENCODE_DISABLE_PROJECT_CONFIG(): boolean
get OPENCODE_TUI_CONFIG(): string | undefined
get OPENCODE_CONFIG_DIR(): string | undefined
get OPENCODE_PURE(): boolean
get OPENCODE_CLIENT(): string  // 默认 "cli"
```

---

### 5. Effect 工具集 (`src/effect/`)

#### 5.1 Runtime 工厂 (`runtime.ts`)

**用途**: 封装 ManagedRuntime 的创建，为每个 Service 提供便捷的同步/异步执行入口。

```typescript
export function makeRuntime<I, S, E>(
  service: Context.Service<I, S>,
  layer: Layer.Layer<I, E>
)

// 返回对象包含:
// - runSync(fn): 同步执行
// - runPromise(fn): 异步执行，返回 Promise
// - runPromiseExit(fn): 返回 Exit 结果
// - runFork(fn): 使用纤程异步执行
// - runCallback(fn): 回调模式执行
```

内部整合了 Observability layer 和 memoMap 优化。

#### 5.2 Effect 日志器 (`logger.ts`)

**用途**: 桥接 Effect 的 Logger 生态和本地的 `Log` 系统。

```typescript
// 作为 Effect.Logger.make 的实现
export const logger = Logger.make((opts) => { ... })

// 日志格式化层，支持 LogSpan 时长统计
export const layer = Logger.layer([logger], { mergeWithExisting: false })

// 便捷创建函数
export const create = (base: Fields = {}): Handle
// Handle 提供: debug(), info(), warn(), error(), with(extra)
```

**行为**: 
- 自动从 Effect annotations 中提取 `service` 字段分配给对应的 Log 实例
- 输出 Cause 信息（当 Effect.Cause 包含 reasons 时）
- 自动结合 LogSpans 输出耗时

#### 5.3 可观测性集成 (`observability.ts`)

**用途**: 集成 OpenTelemetry，提供 traces 和 logs 的 OTLP 导出。

```typescript
export const enabled: boolean  // 基于 OTEL_EXPORTER_OTLP_ENDPOINT 是否配置
export const layer: Layer      // 条件层: 配置了 OTLP 端点的 tracing+logging，否则仅本地 Effect logging
```

**关键行为**:
- 仅当 `OTEL_EXPORTER_OTLP_ENDPOINT` 环境变量设置时启用
- 自动注册 `AsyncLocalStorageContextManager` 作为 OpenTelemetry 全局 context manager
- Resource 属性包含: `service.name=opencode`, `service.version`, `deployment.environment.name`, `opencode.client`, `opencode.process_role`, `opencode.run_id`
- Traces 通过 `@opentelemetry/exporter-trace-otlp-http` 批量导出
- Logs 通过 `OtlpLogger` 以 JSON 格式导出

#### 5.4 记忆化映射 (`memo-map.ts`)

**用途**: 提供 Effect ManagedRuntime 共享的状态记忆化层，避免重复计算。

```typescript
export const memoMap = Layer.makeMemoMapUnsafe()
```

---

### 6. 工具模块 (`src/util/`)

#### 6.1 文件锁 (`flock.ts`)

**用途**: 基于文件系统的分布式进程锁，使用 POSIX `mkdir` 的原子性作为锁定原语。

**核心概念**:

```
lockRoot/<hash-of-key>.lock/
  ├── heartbeat    ← 心跳文件（定期更新 mtime，防止被误判为过期）
  └── meta.json    ← 锁元数据（token, pid, hostname, 创建时间）
```

**过期检测**: 三者按需检测：心跳文件 > meta.json > 锁目录本身，mtime 超过 `staleMs`（默认 60s）视为过期。

**Breaker 机制**: 当检测到过期锁时，多个竞争者通过 `mkdir <lock>.breaker` 竞选"打破者"角色，只有一个竞争者获得删除过期锁的权限。

**API**:

```typescript
// 获取锁（通过 await using 自动释放）
export async function acquire(key: string, options?: Options): Promise<Lease>

interface Options {
  dir?: string        // 锁目录，默认使用 Global.state/locks
  signal?: AbortSignal
  staleMs?: number    // 过期时间（默认 60000ms）
  timeoutMs?: number  // 等待超时（默认 5 分钟）
  baseDelayMs?: number // 重试初始延迟（默认 100ms）
  maxDelayMs?: number  // 重试最大延迟（默认 2000ms）
  onWait?: Wait       // 等待回调
}

// 带锁执行回调
export async function withLock<T>(key: string, fn: () => Promise<T>, options?: Options): Promise<T>

// Effect 集成版本
export const effect = Effect.fn("Flock.effect")(function* (key, options) { ... })
```

**安全性**:
- Token 校验: 释放时校验 meta.json 中的 token 与获取时的 token 一致
- 心跳机制: 持有锁时定期更新 heartbeat 的 mtime（间隔 = staleMs/3）
- AbortSignal 支持: 可在等待中和持有中中断

#### 6.2 快速哈希 (`hash.ts`)

```typescript
export namespace Hash {
  export function fast(input: string | Buffer): string {
    return createHash("sha1").update(input).digest("hex")
  }
}
```

#### 6.3 Slug 生成 (`slug.ts`)

**用途**: 生成 URL 友好的随机 ID，采用 `<形容词>-<名词>` 格式。

```typescript
export namespace Slug {
  export function create(): string  // 如 "cosmic-rocket", "brave-tiger"
}
```

共 29 个形容词 + 31 个名词，提供 899 种组合。

#### 6.4 编码工具 (`encode.ts`)

```typescript
// URL-safe Base64 编解码
export function base64Encode(value: string): string
export function base64Decode(value: string): string

// SHA-256 哈希（异步，使用 Web Crypto）
export async function hash(content: string, algorithm?: string): Promise<string>

// FNV-1a 32-bit 校验和
export function checksum(content: string): string | undefined

// 采样校验和（用于大文件，选取 5 个采样点各取 4096 字符）
export function sampledChecksum(content: string, limit?: number): string | undefined
```

#### 6.5 错误类型 (`error.ts`)

**用途**: 带有 schema 的结构化错误基类。

```typescript
export abstract class NamedError extends Error {
  abstract schema(): z.core.$ZodType
  abstract toObject(): { name: string; data: any }

  static hasName(error: unknown, name: string): boolean
  static create<Name extends string, Data extends z.core.$ZodType>(name, data): NamedError 子类
}

// 示例: 创建带 Zod schema 的错误类
const MyError = NamedError.create("MyError", z.object({ code: z.number() }))
```

#### 6.6 Glob 模式匹配 (`glob.ts`)

**用途**: 封装 `glob` 和 `minimatch` 库。

```typescript
export namespace Glob {
  interface Options {
    cwd?: string
    absolute?: boolean   // 返回绝对路径
    include?: "file" | "all"
    dot?: boolean
    symlink?: boolean
  }

  export function scan(pattern: string, options?: Options): Promise<string[]>
  export function scanSync(pattern: string, options?: Options): string[]
  export function match(pattern: string, filepath: string): boolean
}
```

#### 6.7 重试逻辑 (`retry.ts`)

**用途**: 带指数退避的重试机制，内置瞬态错误识别。

```typescript
export async function retry<T>(
  fn: () => Promise<T>,
  options?: RetryOptions
): Promise<T>

interface RetryOptions {
  attempts?: number    // 默认 3
  delay?: number       // 默认 500ms
  factor?: number      // 默认 2（指数退避因子）
  maxDelay?: number    // 默认 10000ms
  retryIf?: (error) => boolean  // 默认识别常见网络错误
}
```

**内置错误识别**: `"load failed"`, `"network connection was lost"`, `"econnreset"`, `"econnrefused"`, `"etimedout"`, `"socket hang up"` 等。

#### 6.8 路径工具 (`path.ts`)

```typescript
export function getFilename(path?: string): string
export function getDirectory(path?: string): string
export function getFileExtension(path?: string): string
export function getFilenameTruncated(path?: string, maxLength?: number): string
export function truncateMiddle(text: string, maxLength?: number): string
```

#### 6.9 函数工具 (`fn.ts`)

**用途**: 类型安全的 Zod 校验包装函数。

```typescript
export function fn<T extends z.ZodType, Result>(
  schema: T,
  cb: (input: z.infer<T>) => Result
): ((input: z.infer<T>) => Result) & {
  force: (input: z.infer<T>) => Result  // 跳过校验
  schema: T
}
```

#### 6.10 惰性求值 (`lazy.ts`)

```typescript
export function lazy<T>(fn: () => T): () => T
```

#### 6.11 立即调用 (`iife.ts`)

```typescript
export function iife<T>(fn: () => T): T  // Immediately Invoked Function Expression
```

#### 6.12 进程元数据 (`opencode-process.ts`)

**用途**: 管理运行 ID 和进程角色。

```typescript
export function ensureRunID(): string           // 如果没有，通过 crypto.randomUUID 生成
export function ensureProcessRole(fallback: "main" | "worker"): string
export function ensureProcessMetadata(fallback: "main" | "worker"): { runID, processRole }
export function sanitizedProcessEnv(overrides?): Record<string, string>
```

通过 `OPENCODE_RUN_ID` 和 `OPENCODE_PROCESS_ROLE` 环境变量持久化，确保同一应用的父子进程共享相同 ID。

#### 6.13 单调 ID 生成 (`identifier.ts`)

**用途**: 生成时间排序的唯一标识符，可用于数据库主键。

```typescript
export namespace Identifier {
  // 26字符长度 = 12字符(hex时间戳+计数器) + 14字符(base62随机)
  export function ascending(): string   // 时间正序
  export function descending(): string  // 时间倒序（适合反向索引）
  export function create(descending: boolean, timestamp?: number): string
}
```

#### 6.14 二分查找与插入 (`binary.ts`)

```typescript
export namespace Binary {
  export function search<T>(array: T[], id: string, compare: (item: T) => string): { found, index }
  export function insert<T>(array: T[], item: T, compare: (item: T) => string): T[]
}
```

#### 6.15 Node 模块解析 (`module.ts`)

```typescript
export namespace Module {
  export function resolve(id: string, dir: string): string | undefined
  // 等同于 require.resolve，但使用 createRequire 从给定目录解析
}
```

#### 6.16 数组工具 (`array.ts`)

```typescript
export function findLast<T>(items: readonly T[], predicate): T | undefined
```

#### 6.17 Effect 文件锁 (`effect-flock.ts`)

**用途**: 与 `flock.ts` 等价的纯 Effect 实现，提供 Effect 原生的错误类型和服务集成。

```typescript
export namespace EffectFlock {
  // Effect 原生错误类型（继承 Schema.TaggedErrorClass）
  export class LockTimeoutError extends Schema.TaggedErrorClass
  export class LockCompromisedError extends Schema.TaggedErrorClass

  export interface Interface {
    readonly acquire: (key: string, dir?: string) => Effect.Effect<void, LockError, Scope.Scope>
    readonly withLock: (key, dir?) => <A,E,R>(body) => Effect.Effect<A, E|LockError, R>
  }

  export class Service extends Context.Service<Service, Interface>()("EffectFlock") {}
  export const layer: Layer.Layer<Service, never, Global.Service | AppFileSystem.Service>
}
```

**与 `flock.ts` 的关键差异**:
- 全部使用 Effect 生态（`Effect.retry` + `Schedule` 替代手工重试循环）
- 错误类型是 Effect Schema 类型（而非普通 Error）
- 支持 `acquireRelease` 模式确保锁释放
- 心跳通过 `Effect.repeat` + `Effect.forkScoped` 实现

---

### 7. Schema 扩展 (`src/schema.ts`)

**用途**: 扩展 Effect Schema，提供自定义类型、工具和 Zod 桥接。

```typescript
// 正整数（> 0）
export const PositiveInt = Schema.Int.check(Schema.isGreaterThan(0))

// 非负整数（>= 0）
export const NonNegativeInt = Schema.Int.check(Schema.isGreaterThanOrEqualTo(0))

// 可选字段：类型系统允许 undefined 但编码时省略（兼容 JSON.stringify）
export const optionalOmitUndefined = <S>(schema: S) => ...

// 深度去除 readonly（自定义版本，修复了上游 unknown -> {} 的问题）
export type DeepMutable<T> = ...

// 给 Schema 附加静态方法
export const withStatics = <S, M>(methods: (schema: S) => M) => (schema: S): S & M

// Newtype 包装器：打造带名义类型的 Schema（类似 Haskell newtype）
export function Newtype<Self>() { return <Tag, S>(tag, schema) => ... }
```

**`DeepMutable` 与上游的区别**:
- 上游版本将 `unknown` 摊平为 `{}`
- 本版本在对象分支上增加 `extends object` 守卫
- Primitive bailout 保持一致
- Tuple 分支保留只读元组结构

---

### 8. 安装信息 (`src/installation/`)

**用途**: 在构建时通过全局常量注入版本和频道信息。

```typescript
declare global {
  const OPENCODE_VERSION: string  // 构建时替换为实际版本号
  const OPENCODE_CHANNEL: string  // 构建时替换为发布频道
}

export const InstallationVersion = typeof OPENCODE_VERSION === "string" ? OPENCODE_VERSION : "local"
export const InstallationChannel = typeof OPENCODE_CHANNEL === "string" ? OPENCODE_CHANNEL : "local"
export const InstallationLocal = InstallationChannel === "local"
```

---

### 9. NPM 包管理 (`src/npm.ts`, `src/npm-config.ts`)

#### 9.1 NPM 服务 (`npm.ts`)

**用途**: 基于 `@npmcli/arborist` 的程序化 NPM 包管理，支持安装、查询和二进制定位。

```typescript
export class Service extends Context.Service<Service, Interface>()("@opencode/Npm") {}

export interface Interface {
  readonly add: (pkg: string) => Effect.Effect<EntryPoint, InstallFailedError | LockError>
  readonly install: (dir: string, input?) => Effect.Effect<void, LockError | InstallFailedError>
  readonly which: (pkg: string, bin?: string) => Effect.Effect<Option.Option<string>>
}
```

**关键行为**:
- `add(pkg)`: 在 `cache/packages/<sanitized-name>` 中安装单个包，返回入口点目录和文件路径
- `install(dir, input)`: 对比 `package.json` 声明的依赖和 `package-lock.json` 锁定的依赖，仅在缺失时执行安装
- `which(pkg, bin?)`: 查找包的二进制入口路径，支持 `bin` hint 消歧义
- 所有操作受文件锁保护（通过 `EffectFlock`）
- 跳过所有 npm scripts（`ignoreScripts: true`），避免安全问题

**便捷函数（独立于 Effect Runtime）**:

```typescript
export async function install(dir, input?): Promise<void>
export async function add(pkg): Promise<{ directory, entrypoint }>
export async function which(pkg, bin?): Promise<string | undefined>
```

#### 9.2 NPM 配置 (`npm-config.ts`)

**用途**: 读取项目级别的 `.npmrc` 配置。

```typescript
export const load = (dir: string) => Effect.Effect<Record<string, unknown>>
export const registry = (dir: string) => Effect.Effect<string>
```

---

### 10. Cross-Spawn Spawner (`src/cross-spawn-spawner.ts`)

**用途**: 基于 `cross-spawn` 库实现 Effect ChildProcessSpawner 接口，提供跨平台进程生成能力。Windows 上对路径解析特别好（`cross-spawn` 会调用 `which` 查找可执行文件）。

```typescript
export const make: Effect.Effect<ChildProcessSpawner, never, FileSystem | Path>
export const layer: Layer.Layer<ChildProcessSpawner, never, FileSystem | Path>
export const defaultLayer: Layer
```

**关键特性**:
- 支持管道命令（`PipedCommand`）: 多个进程通过 stdio 连接
- 附加文件描述符: 通过 `additionalFds` 支持 `fd://3` 等额外 I/O
- 进程组管理: Linux/macOS 使用 `process.kill(-pid)` 杀进程组，Windows 使用 `taskkill /T`
- 优雅终止: 先发送 `SIGTERM`，超时后发送 `SIGKILL`
- Windows overlapped I/O: 管道 IO 类型自动转为 `"overlapped"` 以支持异步

---

### 11. Effect-Zod 桥接 (`src/effect-zod.ts`)

**用途**: 将 Effect Schema AST 自动转换为 Zod Schema，使 OpenCode 的 Schema 定义可以同时用于：
- Effect 的编解码管道
- Zod 的校验和 JSON Schema 导出（用于 LLM 工具调用 / API 输入验证）

```typescript
export function zod<S extends Schema.Top>(schema: S): z.ZodType<Schema.Schema.Type<S>>
export function zodObject<S extends Schema.Top>(schema: S): z.ZodObject<any>
export function toJsonSchema<S extends Schema.Top>(schema: S): JsonSchema
export const ZodOverride: unique symbol  // 注解键，允许为特定字段提供手工 Zod 定义
```

**转换能力**:

| Effect Schema AST 节点 | 对应 Zod 方法 |
|------------------------|-------------|
| `String` | `z.string()` |
| `Number` | `z.number()` |
| `Boolean` | `z.boolean()` |
| `Literal` | `z.literal()` |
| `Union`（全 String Literal） | `z.enum()` |
| `Union`（带 discriminator） | `z.discriminatedUnion()` |
| `Objects` | `z.object()` |
| `Arrays`（可变） | `z.array()` |
| `Arrays`（固定） | `z.tuple()` |
| `Objects`（index signature） | `z.record()` |
| `Objects`（index + properties） | `z.object().catchall()` |
| `isInt` filter | `.int()` |
| `isPattern` filter | `.regex()` |
| `isGreaterThan` filter | `.gt()` |
| `isUUID` filter | `.uuid()` |
| `isULID` filter | `.ulid()` |

**ZodOverride 注解**:

```typescript
// 示例：为 Schema.String 指定手工 Zod schema
const schema = Schema.String.annotate({ [ZodOverride]: z.string().startsWith("per") })
```

---

## 模块关系图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          @opencode-ai/core                              │
│                                                                         │
│  ┌──────────────┐    ┌──────────────────────────────────────────────┐  │
│  │  installation │    │                  util/                      │  │
│  │  ├─ version   │    │  ├─ log.ts         ├─ lazy.ts              │  │
│  │               │    │  ├─ flock.ts       ├─ iife.ts              │  │
│  └──────┬────────┘    │  ├─ effect-flock.ts├─ fn.ts                │  │
│         │             │  ├─ hash.ts        ├─ path.ts              │  │
│  ┌──────┴────────┐    │  ├─ slug.ts        ├─ glob.ts              │  │
│  │     flag/      │    │  ├─ encode.ts      ├─ retry.ts            │  │
│  │  ├─ flag.ts    │────│  ├─ error.ts       ├─ identifier.ts       │  │
│  │               │    │  ├─ binary.ts       ├─ module.ts           │  │
│  └──────────────┘    │  ├─ array.ts        ├─ opencode-process.ts │  │
│                       │  └─ ...                                    │  │
│  ┌──────────────┐    └──────────────────────────────────────────────┘  │
│  │   global.ts  │                                                      │
│  │  (XDG paths) │◄──── flag.ts (OPENCODE_CONFIG_DIR)                  │
│  └──────┬───────┘                                                      │
│         │              ┌──────────────────────────────────────────┐    │
│         ├──────────────│    filesystem.ts (AppFileSystem)         │    │
│         │              │    uses: glob.ts                          │    │
│         │              └──────────────────┬───────────────────────┘    │
│         │                                 │                             │
│         │              ┌──────────────────┴───────────────────────┐    │
│         ├──────────────│    npm.ts (Npm Service)                  │    │
│         │              │    uses: effect-flock.ts, npm-config.ts, │    │
│         │              │          AppFileSystem, Global            │    │
│         │              └──────────────────────────────────────────┘    │
│         │                                                              │
│  ┌──────┴───────┐    ┌──────────────────────────────────────────┐    │
│  │   effect/     │    │          schema.ts                        │    │
│  │ ├─ runtime.ts │    │  (Effect Schema extensions)              │    │
│  │ ├─ logger.ts  │────│    uses: effect-zod.ts                   │    │
│  │ ├─ observa-   │    └──────────────────────────────────────────┘    │
│  │ │  bility.ts  │                                                     │
│  │ ├─ memo-map   │    ┌──────────────────────────────────────────┐    │
│  │ └─ ...        │    │    cross-spawn-spawner.ts                 │    │
│  └───────────────┘    │    (implements ChildProcessSpawner)       │    │
│                       └──────────────────────────────────────────┘    │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │                    effect-zod.ts                               │     │
│  │   (Effect Schema AST → Zod bridge)                            │     │
│  └──────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────┘
```

**依赖流向说明**:

1. `global.ts` 是最底层：提供目录路径，被 `flag.ts`、`log.ts`、`flock.ts`、`effect-flock.ts` 使用
2. `filesystem.ts` 依赖 `glob.ts`，向上层提供增强文件操作
3. `log.ts` 独立运行，但 `effect/logger.ts` 作为其 Effect 桥接层
4. `effect/observability.ts` 依赖 `effect/logger.ts`、`flag.ts`、`installation/version.ts`
5. `npm.ts` 是最复杂的服务层，依赖 `effect-flock.ts`、`filesystem.ts`、`global.ts`、`npm-config.ts`
6. `effect/runtime.ts` 聚合 `observability.ts` 和 `memo-map.ts`
7. `schema.ts` 和 `effect-zod.ts` 是纯类型/Schema 层，无运行时外部依赖
8. `flag.ts` 是纯环境变量读取，仅依赖 `installation/version.ts`（用于不稳定频道判断）

---

## 代码示例

### 使用 Global Paths

```typescript
import { Path } from "@opencode-ai/core/global"

// 直接使用单例
const logFile = Path.log
const repoDir = Path.repos

// 通过 Effect Service (DI)
import { Global } from "@opencode-ai/core/global"
import { Effect } from "effect"

const program = Effect.gen(function* () {
  const global = yield* Global.Service
  yield* Effect.log(`Log directory: ${global.log}`)
})

// program.pipe(Effect.provide(Global.layer), ...)
```

### 文件系统操作

```typescript
import { AppFileSystem } from "@opencode-ai/core/filesystem"
import { Effect } from "effect"

const program = Effect.gen(function* () {
  const fs = yield* AppFileSystem.Service

  // 安全读取（文件不存在时返回 undefined）
  const content = yield* fs.readFileStringSafe("/path/to/file")
  
  // 读取 JSON
  const config = yield* fs.readJson("/path/to/config.json")

  // 写入文件并自动创建目录
  yield* fs.writeWithDirs("/some/nested/path/data.txt", "hello")
  
  // Glob 匹配
  const tsFiles = yield* fs.glob("src/**/*.ts", { cwd: "/project", absolute: true })
})
```

### 日志使用

```typescript
import * as Log from "@opencode-ai/core/util/log"

// 初始化（应用启动时调用一次）
await Log.init({ level: "DEBUG", dev: true })

// 创建服务作用域的 logger
const logger = Log.create({ service: "agent" })
logger.info("Agent starting", { model: "claude-3-5-sonnet" })
logger.debug("Processing message", { messageId: "abc123" })
logger.warn("Token usage high", { tokens: 95000, limit: 100000 })

// 计时
using timer = logger.time("api_call", { endpoint: "/chat" })
// ... 执行操作 ...
// timer 在离开作用域时自动调用 stop()，输出耗时
```

### 文件锁

```typescript
import { Flock } from "@opencode-ai/core/util/flock"

// 使用 withLock 模式
const result = await Flock.withLock("critical-section", async () => {
  // 此代码块同一时间只有一个进程执行
  await doSomethingExclusive()
  return computeResult()
}, {
  timeoutMs: 30000,    // 30 秒超时
  staleMs: 10000,      // 10 秒过期
})

// 使用 acquire/release 模式
await using lock = await Flock.acquire("my-key")
// ... 持有锁进行操作 ...
// lock 在离开作用域时自动释放
```

### Effect 文件锁 (effect-flock)

```typescript
import { EffectFlock } from "@opencode-ai/core/util/effect-flock"
import { Effect } from "effect"

const program = Effect.gen(function* () {
  const flock = yield* EffectFlock.Service

  // 获取锁并执行
  yield* flock.withLock("package-install")(
    Effect.gen(function* () {
      yield* installPackages()
    })
  )
})

// program.pipe(Effect.provide(EffectFlock.defaultLayer), ...)
```

### NPM 包管理

```typescript
import { Npm } from "@opencode-ai/core/npm"

// 安装包并获取入口点
const { directory, entrypoint } = await Npm.add("@anthropic-ai/sdk")
// directory: ~/.cache/opencode/packages/@anthropic-ai__sdk
// entrypoint: ~/.cache/opencode/packages/@anthropic-ai__sdk/node_modules/@anthropic-ai/sdk/index.mjs

// 查找二进制路径
const binPath = await Npm.which("typescript", "tsc")
```

### 特性开关

```typescript
import { Flag } from "@opencode-ai/core/flag/flag"

if (Flag.OPENCODE_EXPERIMENTAL) {
  // 启用实验性功能
  enableExperimentalFeature()
}

if (Flag.OPENCODE_ENABLE_EXA) {
  // 使用 Exa 搜索后端
  setupExaSearch()
}

// 配置目录（运行时求值）
const configDir = Flag.OPENCODE_CONFIG_DIR ?? Path.config
```

### Schema 定义

```typescript
import { Schema } from "effect"
import { DeepMutable, withStatics, NonNegativeInt } from "@opencode-ai/core/schema"

// 使用工具类型
interface Config {
  readonly name: string
  readonly port: number
}
type MutableConfig = DeepMutable<Config>
// { name: string; port: number }

// 带静态方法的 Schema
const SessionId = Schema.String.pipe(
  withStatics((s) => ({
    generate: () => crypto.randomUUID(),
    zero: "00000000-0000-0000-0000-000000000000",
  }))
)
SessionId.generate() // 类型安全
```

### 重试逻辑

```typescript
import { retry } from "@opencode-ai/core/util/retry"

const data = await retry(
  () => fetch("https://api.example.com/data").then(r => r.json()),
  { attempts: 5, delay: 1000, maxDelay: 30000 }
)
```

---

## 关键设计原则

1. **零内部依赖**: 所有依赖都来自 npm 生态（effect, zod, glob, xdg-basedir 等），不依赖 workspace 中其他包
2. **Effect 优先**: 核心功能通过 Effect Service/Layer 模式暴露，支持依赖注入和可测试
3. **双模式 API**: 同时提供 Effect Service 接口和便捷的同步/异步函数（通过 `makeRuntime`），满足不同调用场景
4. **平台适配**: 原生处理 Windows 路径转换、跨平台进程 spawn、WSL/MSYS/Cygwin 路径
5. **安全设计**: 文件锁包含 token 校验、心跳检测、过期回收等安全机制；NPM 安装默认跳过 scripts
