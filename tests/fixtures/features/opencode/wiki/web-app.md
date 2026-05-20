# Web 应用架构文档 (@opencode-ai/app)

## 概览

`@opencode-ai/app` (版本 1.14.48) 是 OpenCode 的前端 Web 应用，采用 **SolidJS** 作为 UI 框架，**Vite** 作为构建工具，部署为纯静态单页应用 (SPA)。它通过 HTTP/SSE 与后端 OpenCode Server 通信，提供完整的 AI 编程助手交互界面。

- **包名**: `@opencode-ai/app`
- **入口文件**: `src/index.ts`
- **开发服务器**: `vite`（端口 3000）
- **构建目标**: `esnext`，输出 ES Module
- **测试框架**: Bun Test (单元测试) + Playwright (E2E 测试)

---

## 一、应用架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                      entry.tsx                               │
│  PlatformProvider → AppBaseProviders → AppInterface          │
├─────────────────────────────────────────────────────────────┤
│                      app.tsx                                  │
│  MetaProvider → Font → ThemeProvider → LanguageProvider →    │
│  UiI18nBridge → ErrorBoundary → QueryProvider →              │
│  DialogProvider → MarkedProvider → FileComponentProvider     │
│                                                               │
│  ServerProvider → ConnectionGate → ServerKey →               │
│  QueryProvider → GlobalSDKProvider → GlobalSyncProvider →    │
│  Router(/) → Route("/", Home) → Route("/:dir", Directory)    │
│    → Route("/:dir/session/:id?", Session)                    │
├─────────────────────────────────────────────────────────────┤
│              Context Provider 层级                             │
│  Platform → Language → Settings → Permission → Layout →      │
│  Notification → Models → Command → Highlights                │
│  SDK → Sync → Terminal → File → Prompt → Comments           │
│  Local → Server → GlobalSDK → GlobalSync                     │
└─────────────────────────────────────────────────────────────┘
```

### 1.1 入口点 (`src/entry.tsx`)

这是 Web 平台的独立入口（桌面端使用 Tauri webview，有独立的入口）。其主要职责：

1. **Sentry 初始化**: 根据环境变量 `VITE_SENTRY_DSN` 配置错误追踪
2. **语言检测**: 从 `navigator.languages` 自动检测用户语言（支持中文/英文）
3. **平台抽象创建**: 构建 `Platform` 对象，提供 `"web"` 平台的各实现：
   - `notify`: 使用浏览器 Notification API 发送系统通知
   - `openLink`: 通过 `window.open` 打开链接
   - `back/forward`: 调用 `window.history`
   - `restart`: 使用 `window.location.reload()`
4. **服务端连接解析**:
   - 从 URL 查询参数中提取 `auth_token` 进行认证
   - 自动检测当前环境：本地开发 (`localhost`)、生产 (`opencode.ai`)
   - 从 `localStorage` 读取默认服务器 URL
5. **组件树挂载**:
   ```
   PlatformProvider(value=webPlatform)
     └─ AppBaseProviders
          └─ AppInterface(defaultServer, servers=[httpServer])
   ```

### 1.2 根应用组件 (`src/app.tsx`)

`app.tsx` 定义了整个应用的组件树和路由结构，是架构的核心。

#### AppBaseProviders

提供全局基础 Context，适用于所有平台：

```
MetaProvider (管理 document head)
  └─ Font (字体加载)
      └─ ThemeProvider (主题管理，暗色/亮色)
          └─ LanguageProvider (国际化)
              └─ UiI18nBridge (将Language context桥接到UI库的I18nProvider)
                  └─ ErrorBoundary (全局错误边界 → ErrorPage)
                      └─ QueryProvider (TanStack Query)
                          └─ DialogProvider (对话框管理)
                              └─ MarkedProvider (Markdown渲染)
                                  └─ FileComponentProvider (文件组件提供)
```

#### AppInterface

应用的主要入口组件，责任链式连接服务器和路由：

```
ServerProvider (服务器连接)
  └─ ConnectionGate (健康检查门控)
      └─ ServerKey (确保 server key 存在)
          └─ QueryProvider (TanStack Query，重新实例化)
              └─ GlobalSDKProvider (全局 SDK 事件流)
                  └─ GlobalSyncProvider (全局状态同步)
                      └─ Dynamic(Router) (动态路由组件)
                          ├─ Route "/" → HomeRoute (首页，懒加载)
                          └─ Route "/:dir" → DirectoryLayout
                              ├─ Route "/" → SessionIndexRoute (重定向)
                              └─ Route "/session/:id?" → SessionRoute
```

#### ConnectionGate - 服务器健康检查门控

应用挂载后会先执行服务器健康检查：

1. **阻塞模式** (`blocking`): 初始阶段，反复检查直到成功或超时
2. **后台模式** (`background`): 超时后切换，允许用户手动重试或切换服务器
3. **超时时间**: 10 秒 (`Effect.timeoutOrElse`)
4. **降级体验**: 健康检查失败显示 `ConnectionError` 组件，提供重试和切换服务器能力

#### 路由结构

| 路径 | 组件 | 说明 |
|------|------|------|
| `/` | `HomeRoute` (懒加载) | 首页，显示项目列表 |
| `/:dir` | `DirectoryLayout` | 目录布局包装 |
| `/:dir/` | `SessionIndexRoute` | 重定向到 session 页 |
| `/:dir/session/:id?` | `SessionRoute` | 会话页 |

---

## 二、Context Provider 层级详解

### 2.1 Provider 初始化顺序

应用中有两组 Provider 层级：

**全局 Provider 链** (由 `AppBaseProviders` 和 `AppInterface` 组合):
1. `PlatformProvider` - 平台抽象
2. `MetaProvider` - document head 管理
3. `ThemeProvider` - 主题
4. `LanguageProvider` - i18n
5. `ErrorBoundary` - 错误边界
6. `QueryProvider` - TanStack Query
7. `DialogProvider` - 对话框
8. `MarkedProvider` - Markdown
9. `FileComponentProvider` - 文件组件
10. `ServerProvider` - 服务器连接
11. `GlobalSDKProvider` - 全局 SDK 事件流
12. `GlobalSyncProvider` - 全局数据同步

**目录级 Provider 链** (由 `DirectoryLayout` 包装):
1. `SDKProvider` - 目录级 SDK
2. `SyncProvider` - 目录级数据同步
3. `DataProvider` - UI 数据桥接
4. `LocalProvider` - 本地 Agent/Model 选择状态

**会话级 Provider 链** (由 `AppShellProviders` 和 `SessionProviders` 包装):
1. `SettingsProvider` - 用户设置
2. `PermissionProvider` - 权限管理
3. `LayoutProvider` - 布局状态
4. `NotificationProvider` - 通知管理
5. `ModelsProvider` - 模型列表
6. `CommandProvider` - 命令注册/快捷键
7. `HighlightsProvider` - 版本亮点
8. `TerminalProvider` - 终端状态
9. `FileProvider` - 文件查看
10. `PromptProvider` - 提示输入
11. `CommentsProvider` - 行评论

### 2.2 各 Provider 详细说明

#### PlatformProvider (`context/platform.tsx`)

平台抽象层，支持 `"web"` 和 `"desktop"` 两种平台类型，提供统一接口：

```typescript
type Platform = {
  platform: "web" | "desktop"
  os?: "macos" | "windows" | "linux"
  version?: string
  openLink(url: string): void
  openPath?(path: string, app?: string): Promise<void>
  restart(): Promise<void>
  back(): void
  forward(): void
  notify(title: string, description?: string, href?: string): Promise<void>
  openDirectoryPickerDialog?(opts?): Promise<string | string[] | null>
  openFilePickerDialog?(opts?): Promise<string | string[] | null>
  saveFilePickerDialog?(opts?): Promise<string | null>
  storage?(name?: string): SyncStorage | AsyncStorage
  checkUpdate?(): Promise<UpdateInfo>
  updateAndRestart?(): Promise<void>
  fetch?: typeof fetch
  getDefaultServer?(): Promise<ServerConnection.Key | null>
  setDefaultServer?(url: ServerConnection.Key | null): Promise<void> | void
  getWslEnabled?(): Promise<boolean>
  setWslEnabled?(config: boolean): Promise<void> | void
  getDisplayBackend?(): Promise<DisplayBackend | null>
  setDisplayBackend?(backend: DisplayBackend): Promise<void>
  parseMarkdown?(markdown: string): Promise<string>
  webviewZoom?: Accessor<number>
  checkAppExists?(appName: string): Promise<boolean>
  readClipboardImage?(): Promise<File | null>
}
```

Web 平台的实现使用浏览器 API（`localStorage`, `window.open`, `window.history`, Notification API），桌面平台通过 Tauri 调用原生能力。

#### ServerProvider (`context/server.tsx`)

管理服务器连接的核心 Provider：

- **连接类型**:
  - `Http`: HTTP 直连（Web 和桌面通用）
  - `Sidecar`: 本地 sidecar 进程（桌面专用，支持 WSL）
  - `Ssh`: SSH 隧道连接（桌面专用）
- **连接管理**:
  - `add(url)`: 添加服务器连接
  - `remove(key)`: 移除服务器
  - `setActive(key)`: 切换活跃服务器
- **健康检查**: 每 10 秒轮询 (`HEALTH_POLL_INTERVAL_MS`)
- **项目列表**: 管理目录项目（打开、关闭、展开/折叠、拖拽排序）
- **持久化**: 服务器列表、项目列表、最后访问项目均通过 `persisted` 持久化到 localStorage

#### GlobalSDKProvider (`context/global-sdk.tsx`)

全局 SDK 客户端和 SSE 事件流管理：

- **事件流连接**: 通过 `eventSdk.global.event()` 建立 SSE 长连接
- **事件批处理**: 使用帧缓冲区（16ms 刷新间隔）批量分发事件，避免频繁更新
- **事件去重**: 对 `session.status`、`lsp.updated`、`message.part.updated` 事件进行合并去重
- **delta 优化**: 当 `message.part.updated` 事件到达时，将之前的 `message.part.delta` 标记为过期跳过
- **断线重连**: 250ms 延迟重连，页面可见性恢复时触发心跳检测
- **心跳机制**: 15 秒无事件自动断开重连

#### GlobalSyncProvider (`context/global-sync.tsx`)

全局数据同步中心，管理跨目录的项目、配置、Provider 数据：

- **Bootstrap**: 启动时通过 `bootstrapGlobal` 拉取全局配置、项目列表、Provider 列表和路径信息
- **子 Store 管理**: 通过 `createChildStoreManager` 为每个目录创建独立的 Store
- **实例引导**: `bootstrapInstance(directory)` 为目录拉取配置、VCS、权限等数据
- **会话加载**: `loadSessions()` 分页加载会话列表
- **事件驱动更新**: 监听 `globalSDK.event`，实时更新项目状态和子 Store 数据
- **配置变更**: 通过 `updateConfigMutation` 提交配置变更并重新 Bootstrap

#### SDKProvider (`context/sdk.tsx`)

目录级 SDK 客户端封装：

- 基于 `GlobalSDKProvider` 创建特定目录的 SDK 客户端
- 使用全局事件发射器按目录过滤事件
- 提供 `createClient` 方法创建额外客户端实例

#### SyncProvider (`context/sync.tsx`)

会话级数据同步，管理消息、Diffs、Todos：

- **消息加载**: 初始 80 条，历史加载 200 条/页
- **乐观更新**: 在服务器确认前立即在 UI 中显示用户发送的消息
- **会话 Diff**: 按需拉取 session diffs
- **Todo 管理**: 拉取和缓存会话 Todo 列表
- **内容驱逐**: 通过 LRU 策略驱逐旧会话缓存（上限 `SESSION_CACHE_LIMIT`）
- **预取优化**: 支持 session prefetch，减少切换会话时的等待时间

#### LanguageProvider (`context/language.tsx`)

国际化支持，基于 `@solid-primitives/i18n`:

- **支持语言**: en, zh, zht, ko, de, es, fr, da, ja, pl, ru, ar, no, br, th, bs, tr (17 种)
- **语言检测**: 自动检测浏览器语言偏好
- **字典加载**: 英文内联，其他语言按需动态加载
- **UI 桥接**: 通过 `UiI18nBridge` 桥接到 `@opencode-ai/ui` 的 `I18nProvider`
- **持久化**: 语言选择通过 `Persist.global` 持久化

#### SettingsProvider (`context/settings.tsx`)

用户设置管理，分为多个类别：

| 类别 | 配置项 |
|------|--------|
| **general** | autoSave, releaseNotes, followup(steer/queue), showFileTree, showNavigation, showSearch, showStatus, showTerminal, showReasoningSummaries, shellToolPartsExpanded, editToolPartsExpanded, showSessionProgressBar |
| **appearance** | fontSize(默认14), mono字体, sans字体, terminal字体 |
| **updates** | startup(启动时检查更新) |
| **keybinds** | 自定义快捷键映射 |
| **permissions** | autoApprove(自动批准) |
| **notifications** | agent/permissions/errors 通知开关 |
| **sounds** | agent/permissions/errors 音效配置 |

设置通过字体大小设置 CSS 变量 `--font-family-mono` 和 `--font-family-sans` 实时生效。

#### PermissionProvider (`context/permission.tsx`)

权限请求和自动应答管理：

- **自动同意检测**: 根据 config 中的 `permission: "allow"` 自动启用目录级自动同意
- **会话级自动同意**: 支持对特定会话开启自动同意
- **目录级自动同意**: 支持对整个目录开启自动同意
- **SSE 监听**: 监听 `permission.asked` 事件，符合条件的自动发送 `respondOnce`
- **持久化**: 自动同意状态通过 `Persist.global` 持久化

#### CommandProvider (`context/command.tsx`)

命令注册和快捷键管理：

- **Command Palette**: 默认快捷键 `mod+shift+p`
- **命令注册**: 组件通过 `register()` 注册命令选项
- **快捷键解析**: 支持多平台 (`meta` 在 macOS 是 Cmd，在其他平台是 Ctrl)
- **冲突检测**: 开发模式下检测重复注册的命令 ID
- **可编辑目标检测**: 在 input/textarea/contenteditable 元素中不触发快捷键
- **建议命令**: 自动将标记 `suggested` 的命令提前显示

#### ModelsProvider (`context/models.tsx`)

模型列表和可见性管理：

- **Provider 聚合**: 从所有已连接的 Provider 聚合模型列表
- **可见性控制**: 默认隐藏旧模型（发布超过 6 个月），只显示最新模型
- **手动覆盖**: 用户可手动 show/hide 任意模型
- **最近使用**: 维护最近使用的 5 个模型
- **Model Variant**: 支持模型变体选择

#### LayoutProvider (`context/layout.tsx`)

应用布局状态管理：

- **侧边栏**: 打开/关闭/宽度调整（默认 344px）
- **文件树**: 打开/关闭/宽度（默认 200px）/Tab切换(changes/all)
- **终端面板**: 高度调整（默认 280px）/打开/关闭
- **会话面板宽度**: 默认 600px
- **Review 面板**: Diff 样式/打开状态
- **会话标签页**: 每个会话的文件标签页管理
- **会话视图**: 滚动位置持久化、Review 展开状态
- **Workspace**: 项目展开折叠状态
- **头像颜色**: 自动为项目分配颜色

#### TerminalProvider (`context/terminal.tsx`)

终端模拟器状态管理：

- **Workspace 级别**: 终端在 Workspace 级别管理，切换会话保持不变
- **终端列表**: 创建/关闭/克隆/切换终端
- **PTY 同步**: 通过 SDK 事件 (`pty.exited`) 监听 PTY 退出
- **服务器隔离**: 非本地服务器通过 scope 隔离终端状态
- **内容裁剪**: 支持 trim terminal buffer 节省存储
- **持久化**: 终端列表通过 `Persist.workspace` 持久化

#### FileProvider (`context/file.tsx`)

文件读取和查看管理：

- **文件读取**: 通过 SDK `file.read` 拉取文件内容
- **LRU 缓存**: 文件内容使用 LRU 驱逐策略管理内存
- **文件树**: 通过 `createFileTreeStore` 管理目录树结构
- **Watcher 集成**: 监听 `file.watcher.updated` 事件自动刷新
- **搜索**: 支持文件和目录搜索
- **文件视图**: 滚动位置、选中行持久化

#### PromptProvider (`context/prompt.tsx`)

用户输入提示管理：

- **Part 类型**: text, file, agent, image
- **附件管理**: 文件附件支持 selection range
- **上下文管理**: Context items（带 key 去重）
- **评论集成**: 支持文件评论的上下文
- **Session 级别**: 每个会话独立的 prompt 状态
- **持久化**: 通过 `Persist.scoped` 持久化

#### CommentsProvider (`context/comments.tsx`)

代码行评论管理：

- **按文件分组**: 评论按文件路径分组
- **Focus/Active 状态**: 支持焦点和活跃评论
- **Session 级别**: 每个会话独立
- **持久化**: 通过 `Persist.scoped` 持久化

#### LocalProvider (`context/local.tsx`)

Agent/Model/Variant 本地选择状态：

- **Agent 选择**: 从可用 Agent 列表中选择
- **Model 选择**: 支持最近使用的模型
- **Variant 选择**: 支持模型变体切换
- **Handoff 机制**: 跨目录传递 model 选择状态
- **Session 恢复**: 支持从消息恢复 model 选择
- **持久化**: 通过 `Persist.workspace` 持久化

#### LayoutProvider 的详细子模块

- **`layout-scroll.ts`**: 滚动位置持久化（250ms debounce）
- **`session-prefetch.ts`**: 会话预取逻辑
- **`session-cache.ts`**: 会话缓存驱逐
- **`bootstrap.ts`**: 全局和目录级引导数据加载
- **`event-reducer.ts`**: 目录级事件处理
- **`child-store.ts`**: 子 Store 创建和管理
- **`session-load.ts`**: 会话列表加载
- **`session-trim.ts`**: 会话裁剪
- **`queue.ts`**: 刷新队列

---

## 三、路由与页面组件

### 3.1 路由结构

```
/ (HomeRoute - 懒加载)
  ├─ 显示 OpenCode Logo
  ├─ 显示已连接的服务器名称和健康状态
  ├─ 近期项目列表 (最近5个)
  ├─ 提供"打开项目"按钮（本地用 native picker，远程用 DialogSelectDirectory）
  └─ 没有项目时显示引导提示
/:dir (DirectoryLayout)
  ├─ 解析 base64 编码的 dir 参数
  ├─ 创建 SDKProvider + SyncProvider + DataProvider
  └─ 子路由:
      ├─ / → 重定向到 session 页
      └─ /session/:id? → SessionRoute (懒加载)
```

### 3.2 Session 页面 (`pages/session.tsx`)

会话页面是应用中最复杂的页面，包含：

**核心状态**:
- 消息列表、用户消息、可见消息（支持 rollback/恢复）
- Diff 数据（Git/Branch/Turn 三种模式）
- Todo 任务列表
- Followup 队列（排队消息）
- 会话历史窗口（懒加载）

**子模块** (在 `pages/session/` 下):
- `composer.tsx` - 输入组合区域状态
- `helpers.ts` - 会话工具函数（Tab 管理、文件打开等）
- `message-timeline.tsx` - 消息时间线
- `review-tab.tsx` - 代码审查面板
- `session-layout.ts` - 会话布局逻辑
- `session-model-helpers.ts` - 模型同步辅助
- `session-side-panel.tsx` - 会话侧面板
- `terminal-panel.tsx` - 终端面板
- `use-session-commands.ts` - 会话命令注册
- `use-session-hash-scroll.ts` - URL hash 滚动定位
- `handoff.ts` - Tab 状态跨会话传递

**数据流**:
1. `sessionSync` resource 在路由参数变化时触发，调用 `sync.session.sync(id)`
2. 消息数据从 `sync.data.message[id]` 和 `sync.data.part[id]` 读取
3. Diff 数据从 `sync.data.session_diff[id]` 读取
4. Todo 从 `sync.data.todo[id]` 或 `globalSync.data.session_todo[id]` 读取

**历史窗口** (`createSessionHistoryWindow`):
- 初始渲染最近 10 个 turn
- 向上滚动时每批加载 8 个 turn
- 滚动到顶部附近 (200px) 时预取更多历史
- 预取冷却期 400ms，无增长限制 2 次

### 3.3 Layout 页面 (`pages/layout.tsx`)

主布局页面（复杂的 sidebar 管理，80+ 行导入）：

- 管理 sidebar 中的项目列表
- 支持项目拖拽重排
- Session 列表渲染和管理
- 新建 Session 创建
- Deep link 处理（桌面端 URL Scheme）
- 通知、权限、Provider 状态的 UI 集成
- 主题切换和调试栏

---

## 四、服务器连接流程

### 4.1 连接建立流程

```
1. entry.tsx
   ├─ 读取 URL 中的 auth_token
   ├─ 确定 current URL（开发环境读取 VITE_ 环境变量）
   ├─ 构建 ServerConnection.Http 对象
   └─ 传入 AppInterface

2. AppInterface → ServerProvider
   ├─ 合并 localStorage 中的服务器列表和 props 传入的服务器
   ├─ 去重（相同 URL 保留有 authToken 的）
   ├─ 初始化 active 服务器为 defaultServer
   └─ 输出: list, current, key, name, healthy, isLocal

3. ConnectionGate
   ├─ 执行健康检查 (useCheckServerHealth)
   ├─ 阻塞模式: 持续检查直到成功
   ├─ Effect.timeoutOrElse(10s): 超时切换到后台模式
   ├─ 成功 → 渲染子组件
   └─ 失败 → 显示 ConnectionError (自动每秒重试)

4. 健康检查通过后
   ├─ ServerKey 确保 server key 存在
   ├─ QueryProvider 实例化
   ├─ GlobalSDKProvider 建立 SSE 事件流
   └─ GlobalSyncProvider 拉取全局数据
```

### 4.2 SSE 事件流架构

```
GlobalSDKProvider
  ├─ eventSdk.global.event() → SSE Stream
  ├─ 事件循环:
  │   ├─ 接收事件 → 队列缓冲 (16ms 帧间隔)
  │   ├─ 批处理: 同 key 事件合并（session.status, lsp.updated, message.part.updated）
  │   ├─ delta 过期: 当 message.part.updated 到达，之前的 message.part.delta 被跳过
  │   └─ batch() 内 emit 到目录级事件总线
  ├─ 心跳: 15s 无事件自动重连
  └─ 重连: 250ms 延迟

GlobalSyncProvider
  ├─ 监听 globalSDK.event
  ├─ "global" 事件 → applyGlobalEvent
  │   ├─ session.created/updated/deleted → 刷新项目列表
  │   ├─ server.connected → 刷新所有目录
  │   └─ global.disposed → 刷新所有目录
  ├─ 目录事件 → applyDirectoryEvent
  │   ├─ session.* → 更新 session 列表
  │   ├─ file.watcher.updated → 触发 VCS/文件刷新
  │   └─ config.updated → 刷新配置
  └─ refreshQueue: 防抖刷新机制

SyncProvider (目录级)
  ├─ 消息同步: init 80条, history 200条/页
  ├─ 乐观更新: 用户消息立即显示
  ├─ Diff 拉取: 按需加载
  └─ Todo 拉取: 按需加载
```

### 4.3 连接类型详解

| 类型 | 使用场景 | 认证方式 |
|------|----------|----------|
| `Http` (直连) | Web 应用、本地开发 | URL 中的 `auth_token` 查询参数 |
| `Sidecar` (base) | 桌面本地 | 本地进程通信 |
| `Sidecar` (wsl) | 桌面 WSL | 指定 WSL distro |
| `Ssh` | 远程 SSH | SSH 隧道代理 HTTP |

---

## 五、平台抽象 (Desktop vs Web)

### 5.1 Platform 接口设计

通过 `Platform` 接口提供平台差异抽象：

| 能力 | Web 实现 | Desktop (Tauri) 实现 |
|------|----------|----------------------|
| 打开链接 | `window.open(url, "_blank")` | Tauri shell open |
| 通知 | Notification API | Tauri notification |
| 历史导航 | `window.history.back/forward` | Tauri webview API |
| 重启 | `location.reload()` | Tauri process restart |
| 目录选择 | 服务器端对话框 | 原生文件对话框 |
| 文件选择 | 服务器端对话框 | 原生文件对话框 |
| 文件保存 | 不支持 | 原生保存对话框 |
| 存储 | localStorage | Tauri store / localStorage |
| 更新检查 | 不支持 | Tauri updater API |
| Markdown 解析 | marked 库 | 原生 Rust markdown 解析器 |
| 剪贴板图片 | 不支持 | 原生剪贴板 API |
| Webview 缩放 | 不支持 | Tauri webview zoom |
| WSL 集成 | 不支持 | WSL 配置 |
| Display Backend | 不支持 | Wayland/X11 选择 |
| fetch 覆盖 | 无 | 可选平台级 fetch（解决 CORS） |

### 5.2 Scope 隔离

终端和 Prompt 状态需要根据服务器类型进行 scope 隔离：

- **本地服务器** (sidecar/base, localhost): 不需要 scope，使用默认 key
- **远程服务器** (HTTP 远程, SSH): 使用服务器 key 作为 scope，避免不同服务器的状态混淆

`getTerminalServerScope()` 函数判断是否需要 scope 隔离。

---

## 六、状态管理方案

### 6.1 分层架构

应用采用分层状态管理：

```
全局层 (Global State)
├─ GlobalSyncProvider: 项目列表、全局配置、Provider 列表、路径信息
├─ ServerProvider: 服务器连接列表、健康状态
├─ SettingsProvider: 用户偏好设置
├─ LanguageProvider: 语言选择
├─ LayoutProvider: UI 布局状态 (侧边栏宽度、面板展开状态等)
├─ ModelsProvider: 模型列表和可见性
├─ NotificationProvider: 通知列表
└─ HighlightsProvider: 版本亮点

目录层 (Directory State)
├─ GlobalSync.children: 每个目录独立的 Store (session列表, 配置, VCS等)
├─ SDKProvider: 目录级 SDK 客户端
├─ SyncProvider: 目录级消息和 Diff 数据
└─ LocalProvider: Agent/Model 选择

会话层 (Session State)
├─ SyncProvider.session: 消息列表、Parts
├─ PromptProvider: 输入状态
├─ FileProvider: 文件内容和视图
├─ TerminalProvider: 终端状态
├─ CommentsProvider: 行评论
└─ LayoutProvider: Tab 状态、滚动位置
```

### 6.2 使用的状态管理库

| 库 | 用途 |
|----|------|
| `solid-js/store` (`createStore`) | 应用状态的核心方案，细粒度响应式更新 |
| `@tanstack/solid-query` | 服务端状态管理（配置、Provider 列表、项目列表、VCS diff）|
| `@solid-primitives/storage` | 持久化到 localStorage 的底层抽象 |
| `@solid-primitives/event-bus` | 全局事件总线 (SSE 事件分发) |
| `effect` | Effect runtime，用于健康检查的异步流程控制 |

### 6.3 持久化策略

通过 `Persist` 命名空间和 `persisted` 工具函数实现多层持久化：

| 持久化 Key | 数据 |
|------------|------|
| `Persist.global(key, versions)` | 跨会话/跨目录的全局数据 |
| `Persist.workspace(dir, key, legacy)` | 目录级数据（模型选择、终端、followup）|
| `Persist.scoped(dir, sessionID, key, legacy)` | 会话级数据（prompt、comments）|
| `Persist.session(dir, sessionID, key)` | 会话特有数据（文件视图等）|

持久化底层使用 `@solid-primitives/storage`，在 Web 平台映射到 `localStorage`，在桌面平台映射到 Tauri store。

### 6.4 优化技术

1. **乐观更新** (Optimistic Updates): 用户发送消息后，在服务器确认前立即在 UI 中显示
2. **事件批处理**: SSE 事件通过 16ms 帧缓冲批量分发
3. **事件去重**: 对高频更新事件（session.status, message.part.updated）进行合并
4. **LRU 缓存驱逐**: 文件内容和会话缓存均使用 LRU 策略管理内存
5. **懒加载**: 页面组件使用 `lazy()` 动态导入
6. **预取**: session prefetch 机制减少会话切换等待
7. **历史窗口**: 虚拟化渲染，只渲染最近的 turns

---

## 七、组件树总览

### 7.1 核心组件清单

```
components/
├── layout/              - 应用布局组件 (sidebar, 主区域等)
├── session/             - 会话查看和交互 UI
├── file/                - 文件显示 (file-viewer, file-tree)
├── prompt-input/        - 提示输入区 (附件、模型选择等)
├── server/              - 服务器连接和管理 UI
│
├── titlebar.tsx         - 标题栏 (会话信息、控制按钮、Traffic Lights)
├── terminal.tsx         - 终端模拟器组件 (ghostty-web)
├── prompt-input.tsx     - 主输入组件
├── file-tree.tsx        - 文件树组件
├── status-popover.tsx   - 状态弹出窗口
├── status-popover-body.tsx
├── debug-bar.tsx        - 调试工具栏
├── link.tsx             - 链接组件
├── model-tooltip.tsx    - 模型信息提示
├── session-context-usage.tsx - 上下文使用量显示
│
├── dialog-settings.tsx         - 设置对话框
├── dialog-custom-provider.tsx  - 自定义 Provider 对话框
├── dialog-custom-provider-form.ts
├── dialog-select-model.tsx     - 模型选择对话框
├── dialog-select-model-unpaid.tsx
├── dialog-select-provider.tsx  - Provider 选择对话框
├── dialog-select-directory.tsx - 目录选择对话框
├── dialog-select-server.tsx    - 服务器选择对话框
├── dialog-select-file.tsx      - 文件选择对话框
├── dialog-select-mcp.tsx       - MCP 配置对话框
├── dialog-manage-models.tsx    - 模型管理对话框
├── dialog-connect-provider.tsx - Provider 连接对话框
├── dialog-edit-project.tsx     - 项目编辑对话框
├── dialog-fork.tsx             - 分支对话框
├── dialog-release-notes.tsx    - 版本日志对话框
│
├── settings-general.tsx        - 通用设置面板
├── settings-models.tsx         - 模型设置面板
├── settings-providers.tsx      - Provider 设置面板
├── settings-keybinds.tsx       - 快捷键设置面板
├── settings-list.tsx           - 设置列表容器
│
├── titlebar-history.ts         - 标题栏历史管理逻辑
└── titlebar-history.test.ts
```

### 7.2 UI 组件库依赖

组件大量使用 `@opencode-ai/ui` 提供的 UI 组件：

- **布局**: ResizeHandle, Tabs
- **表单**: Button, IconButton, TextField, Select, Switch
- **反馈**: Toast, Tooltip, Dialog, DropdownMenu
- **数据**: DataProvider, File, FileComponentProvider
- **主题**: ThemeProvider, Icon, Font, Logo, Splash
- **工具**: MarkedProvider, DialogProvider, I18nProvider, createAutoScroll

---

## 八、国际化 (i18n)

### 8.1 语言支持

支持 17 种语言，字典文件位于 `src/i18n/` 和 `@opencode-ai/ui/i18n/`：

| 代码 | 语言 | Intl Code |
|------|------|-----------|
| en | English | en |
| zh | 简体中文 | zh-Hans |
| zht | 繁体中文 | zh-Hant |
| ko | 韩语 | ko |
| de | 德语 | de |
| es | 西班牙语 | es |
| fr | 法语 | fr |
| da | 丹麦语 | da |
| ja | 日语 | ja |
| pl | 波兰语 | pl |
| ru | 俄语 | ru |
| ar | 阿拉伯语 | ar |
| no | 挪威语 | nb-NO |
| br | 葡萄牙语(巴西) | pt-BR |
| th | 泰语 | th |
| bs | 波斯尼亚语 | bs |
| tr | 土耳其语 | tr |

### 8.2 加载策略

1. **英文内联**: 英文 (`en`) 字典在构建时内联，作为 fallback
2. **按需加载**: 其他语言通过 `import()` 动态加载
3. **预加载**: 在模块初始化时检测用户语言并预热对应字典
4. **UI 字典合并**: 应用字典和 `@opencode-ai/ui` 字典在加载时合并 (通过 `merge` 函数)
5. **Cookie 持久化**: 语言选择写入 cookie (`oc_locale`) 并设置 `document.documentElement.lang`

---

## 九、构建与部署

### 9.1 Vite 配置

```
vite.js (插件)
├── opencode-desktop:config
│   ├── resolve.alias: "@" → "./src"
│   └── worker.format: "es"
├── opencode-desktop:theme-preload
│   └── 内联 oc-theme-preload.js 避免 FOUC
├── tailwindcss (Tailwind CSS v4 via @tailwindcss/vite)
└── solidPlugin (SolidJS HMR 支持)

vite.config.ts (主配置)
├── plugins: [desktopPlugin, sentryPlugin]
├── server: { host: "0.0.0.0", allowedHosts: true, port: 3000 }
└── build: { target: "esnext", sourcemap: true }
```

### 9.2 环境变量

| 变量 | 说明 |
|------|------|
| `VITE_OPENCODE_SERVER_HOST` | 开发时后端服务器主机（默认 localhost）|
| `VITE_OPENCODE_SERVER_PORT` | 开发时后端服务器端口（默认 4096）|
| `VITE_SENTRY_DSN` | Sentry DSN |
| `VITE_SENTRY_ENVIRONMENT` | Sentry 环境标识 |
| `VITE_SENTRY_RELEASE` | Sentry 发布版本 |
| `OPENCODE_CHANNEL` | 发布渠道 (prod/dev)，影响 Sentry 集成配置 |

### 9.3 外部依赖

| 依赖 | 用途 |
|------|------|
| `@opencode-ai/sdk` | API 客户端 (createOpencodeClient) |
| `@opencode-ai/ui` | UI 组件库 (Button, Dialog, Toast, etc.) |
| `@opencode-ai/core` | 核心工具 (编码、路径、二进制搜索) |
| `solid-js` | UI 框架 |
| `@solidjs/router` | 路由 |
| `@solidjs/meta` | Document head 管理 |
| `@tanstack/solid-query` | 服务端状态管理 |
| `@solid-primitives/*` | SolidJS 工具集 (i18n, storage, audio 等) |
| `@kobalte/core` | 无障碍 UI 基元 |
| `effect` | Effect 运行时 (异步流程控制) |
| `ghostty-web` | 终端模拟器 (Web 版) |
| `shiki` / `@shikijs/transformers` | 语法高亮 |
| `marked` / `marked-shiki` | Markdown 渲染 |
| `tailwindcss` | CSS 工具类框架 |
| `diff` | 文本差异计算 |
| `fuzzysort` | 模糊搜索 |
| `luxon` | 日期时间处理 |
| `remeda` | 函数式工具库 |
| `zod` | 数据校验 |
| `virtua` | 虚拟滚动 |
| `@thisbeyond/solid-dnd` | 拖拽排序 |
