# OpenCode 桌面应用架构文档

## 概述

OpenCode 桌面应用是一款基于 Electron 的跨平台桌面客户端，支持 macOS、Windows 和 Linux 三大平台。它将 OpenCode 的 Web 前端（`@opencode-ai/app`）封装为原生桌面体验，并通过本地 Sidecar 服务器进程运行 OpenCode 后端服务，形成一个完整的端到端桌面解决方案。

### 核心技术栈

| 层级 | 技术 |
|------|------|
| 桌面框架 | Electron 41.x / Node 24 |
| 构建工具 | electron-vite |
| 打包分发 | electron-builder |
| 前端框架 | SolidJS + `@opencode-ai/app`（Web 应用） |
| UI 组件库 | `@opencode-ai/ui` |
| 运行时 | Effect (Effect-TS) |
| 数据持久化 | electron-store (JSON 文件存储) |
| 数据库 | Drizzle ORM + SQLite（运行在 Sidecar 进程中） |
| 自动更新 | electron-updater |
| 日志 | electron-log |
| 错误追踪 | Sentry |

---

## 架构总览

桌面应用采用三层 Electron 架构，加上一个独立的 Sidecar 子进程：

```
┌─────────────────────────────────────────────────────────┐
│                    Electron 应用                         │
│                                                         │
│  ┌──────────────────┐    IPC     ┌───────────────────┐  │
│  │   Main Process   │◄─────────►│ Renderer Process  │  │
│  │  (Node.js)       │  context- │ (Chromium/SolidJS)│  │
│  │                  │  Bridge   │                   │  │
│  │  - 窗口管理       │           │  - UI 渲染         │  │
│  │  - Sidecar 管理   │           │  - 用户交互        │  │
│  │  - IPC 路由       │           │  - Platform 适配   │  │
│  │  - 自动更新       │           │  - CLI 集成        │  │
│  │  - 菜单系统       │           │                   │  │
│  │  - 系统集成       │           │                   │  │
│  └────────┬─────────┘           └───────────────────┘  │
│           │                                             │
│           │ utilityProcess.fork()                       │
│           ▼                                             │
│  ┌──────────────────┐                                  │
│  │ Sidecar 子进程    │                                  │
│  │ (sidecar.js)     │                                  │
│  │                  │                                  │
│  │  - HTTP 服务器    │                                  │
│  │  - SQLite 数据库  │                                  │
│  │  - 业务逻辑       │                                  │
│  └──────────────────┘                                  │
└─────────────────────────────────────────────────────────┘
```

### 构建系统

使用 `electron-vite` 构建三层代码：

- **Main** (`src/main/`): 打包为 `out/main/index.js` 和 `out/main/sidecar.js` 两个入口
- **Preload** (`src/preload/`): 打包为 CommonJS 格式的 `out/preload/index.js`
- **Renderer** (`src/renderer/`): 通过 Vite 打包为前端资源，包含 `index.html`（主窗口）和 `loading.html`（加载窗口）两个 HTML 入口

---

## Main Process 详解

### 入口文件 (`src/main/index.ts`)

整个 Main Process 的启动流程由一个 Effect Generator (`Effect.gen`) 编排，通过 `Effect.runFork(main)` 异步启动。核心流程如下：

#### 1. 启动初始化阶段

```
app.whenReady() 之前:
  ├── 设置工作目录为用户主目录 (macOS 上避免在 / 运行 ripgrep)
  ├── 配置环境变量 OPENCODE_DISABLE_EMBEDDED_WEB_UI (禁用内嵌 Web UI)
  ├── 确定应用标识 (dev/beta/prod 对应的 appId)
  ├── 设置 userData 路径 (支持 Onboarding 测试隔离)
  ├── 初始化日志系统 (electron-log)
  ├── 合并系统证书链
  ├── 确保 loopback 地址不走代理
  ├── 加载环境代理设置
  ├── 单实例锁检查 (requestSingleInstanceLock)
  ├── 加载 Shell 环境变量 (preferAppEnv)
  └── 注册系统事件监听:
      - second-instance (处理 Deep Links)
      - open-url (macOS 上处理 Deep Links)
      - before-quit / will-quit (清理 Sidecar)
      - SIGINT / SIGTERM (清理退出)
```

#### 2. app.whenReady() 之后

```
  ├── 数据迁移 (从 Tauri 迁移到 Electron, 非 Onboarding 测试模式)
  ├── 注册默认协议处理器 (opencode://)
  ├── 注册 oc:// 自定义协议 (Renderer 资源加载)
  ├── 设置 Dock 图标 (macOS)
  ├── 配置自动更新器 (electron-updater)
  ├── 动态分配空闲端口 (127.0.0.1, 通过 createServer 探测)
  ├── 生成随机密码 (randomUUID)
  ├── 启动 Sidecar 服务器 (后台 fork)
  │   ├── 如需数据库迁移 → 1秒后仍未完成 → 显示 Load 窗口
  │   ├── 等待 Sidecar 就绪 (健康检查, 30秒超时)
  │   └── 等待数据库迁移完成 (如需要)
  ├── 关闭 Load 窗口 (等待渲染进程确认 loadingComplete)
  ├── 创建主窗口 (Main Window)
  └── 创建应用菜单 (仅 macOS)
```

### 关键模块详解

#### server.ts — Sidecar 服务器管理

侧车服务器的生命周期管理模块，负责启动、停止和健康检查。

**主要函数：**

- **`spawnLocalServer(hostname, port, password, configureEnv, options)`**: 核心函数，通过 `utilityProcess.fork()` 启动 Sidecar 子进程。流程为：
  1. 通过 IPC 消息管道发送 `{ type: "start", hostname, port, password, ... }` 启动指令
  2. 等待子进程回复 `{ type: "ready" }` 消息（超时 60 秒则失败）
  3. 期间可接收 `{ type: "sqlite" }` 消息传递数据库迁移进度
  4. 返回 `SidecarListener`（含 `stop()` 方法）和 `HealthCheck`（含 `wait` Promise）

- **`checkHealth(url, password)`**: 向 Sidecar 的 `/global/health` 端点发送带 Basic Auth 的 GET 请求（3 秒超时），验证服务是否健康

- **`preferAppEnv(userDataPath)`**: 设置应用级环境变量，包括加载用户 Shell 环境、启用实验性功能（图标发现、文件监视器）、设置 `OPENCODE_CLIENT=desktop`

- **`getDefaultServerUrl()` / `setDefaultServerUrl()`**: 管理持久化的远程服务器 URL（用于连接远程 OpenCode 服务）

- **`getWslConfig()` / `setWslConfig()`**: 管理 WSL 功能开关配置

**Sidecar 停止流程：**
1. 发送 `{ type: "stop" }` 消息
2. 等待进程退出或 6 秒超时
3. 超时后强制 `child.kill()`

#### sidecar.ts — Sidecar 子进程入口

独立编译为 `sidecar.js` 的 Utility Process 入口。通过 Electron 的 `process.parentPort` 与 Main Process 通信。

**启动流程：**
1. 接收 `{ type: "start" }` 消息，解析并验证参数
2. `prepareSidecarEnv()`: 设置 Sidecar 环境变量（`OPENCODE_SERVER_USERNAME`, `OPENCODE_SERVER_PASSWORD`, `XDG_STATE_HOME`）
3. `ensureLoopbackNoProxy()`: 确保本地回环地址不被代理
4. `useSystemCertificates()`: 加载系统 CA 证书
5. `useEnvProxy()`: 加载环境代理设置
6. 动态导入 `virtual:opencode-server`（OpenCode 后端服务代码）
7. 如需迁移：执行 JSON 数据迁移，通过 `parentPort.postMessage` 报告进度
8. 启动 HTTP 服务：`Server.listen({ port, hostname, username, password, cors: ["oc://renderer"] })`
9. 发送 `{ type: "ready" }` 消息
10. 监听 `{ type: "stop" }` 消息，优雅关闭后 `process.exit(0)`

#### windows.ts — 窗口管理

**窗口类型：**

- **Loading Window（加载窗口）**: 640x480 固定大小，居中显示，不可调整大小。在需要数据库迁移且预计耗时较长时（超过 1 秒）显示。渲染 `loading.html`，展示迁移进度条和状态文字。

- **Main Window（主窗口）**: 默认 1280x800，支持调整大小。使用 `electron-window-state` 记忆窗口位置和尺寸。渲染 `index.html`，加载完整的 OpenCode 应用界面。

**平台适配：**
- **macOS**: `titleBarStyle: "hidden"`，自定义交通灯位置 (12, 14)
- **Windows**: `frame: false` + `titleBarStyle: "hidden"` + 自定义 `titleBarOverlay`（支持明暗主题，高度 40px）
- 所有平台：`contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`

**自定义协议：**
- 注册 `oc://` 协议，以安全的方式加载本地 Renderer 资源
- 仅允许在 `oc://renderer/` 主机名下访问 `rendererRoot` 目录内的文件（路径遍历防护）

**安全措施：**
- 剪贴板权限：仅对受信任的 Renderer URL 授予 `clipboard-sanitized-write` 权限
- CORS 头部注入：在所有请求和响应中添加 `Access-Control-Allow-Origin: *` 和 `Access-Control-Allow-Headers: *`

#### ipc.ts — IPC 通信

在 Main Process 中注册所有 IPC Handler，桥接 Renderer Process 请求到相应的 Main Process 功能。

**IPC 通道分类：**

| 类别 | 通道 | 功能 |
|------|------|------|
| 初始化 | `await-initialization` | 等待 Sidecar 就绪，通过 `init-step` 推送初始化状态 |
| 窗口 | `get-window-count`, `get-window-focused`, `set-window-focus`, `show-window`, `get-zoom-factor`, `set-zoom-factor`, `set-titlebar` | 窗口状态查询与操作 |
| 存储 | `store-get`, `store-set`, `store-delete`, `store-clear`, `store-keys`, `store-length` | 持久化键值存储（支持多命名空间） |
| 文件选择器 | `open-directory-picker`, `open-file-picker`, `save-file-picker` | 原生文件/目录选择对话框 |
| 系统集成 | `open-link`, `open-path`, `read-clipboard-image`, `show-notification`, `relaunch` | 打开外部链接/文件、读取剪贴板、通知、重启 |
| WSL | `get-wsl-config`, `set-wsl-config`, `wsl-path` | WSL 配置与路径转换 |
| 应用解析 | `check-app-exists`, `resolve-app-path` | 检测和解析应用路径（跨平台） |
| 更新 | `run-updater`, `check-update`, `install-update` | 应用更新检查与安装 |
| 其他 | `parse-markdown`, `set-background-color`, `kill-sidecar`, `get-window-config`, `consume-initial-deep-links` | Markdown 解析、主题背景、Sidecar 终止等 |

**Push 消息（Main → Renderer）：**
- `init-step`: 初始化步骤更新
- `sqlite-migration-progress`: SQLite 迁移进度
- `menu-command`: 菜单命令触发
- `deep-link`: Deep Link 接收

#### menu.ts — 应用菜单

仅对 macOS 创建原生应用菜单（`Menu.setApplicationMenu`）。

**菜单结构：**

- **OpenCode 菜单**: 关于、检查更新、设置 (Cmd+,)、重新加载 Webview、重启、隐藏/退出
- **File 菜单**: 新建会话 (Shift+Cmd+S)、打开项目 (Cmd+O)、新建窗口 (Cmd+Shift+N)、关闭
- **Edit 菜单**: 撤销/重做、剪切/复制/粘贴、全选
- **View 菜单**: 切换侧边栏 (Cmd+B)、切换终端 (Ctrl+\`)、切换文件树、重新加载、开发者工具、缩放、全屏
- **Go 菜单**: 前进/后退 (Cmd+[/])、上一个/下一个会话 (Option+Up/Down)、上一个/下一个项目 (Cmd+Option+Up/Down)
- **Window 菜单**: 标准窗口菜单
- **Help 菜单**: 文档、支持论坛、反馈、报告 Bug

菜单命令通过 `sendMenuCommand(win, id)` 将菜单项的标识符发送给 Renderer，由 Renderer 的 `useCommand().trigger(id)` 分发处理。

#### updater.ts — 自动更新

基于 `electron-updater` 实现，仅在打包版本且非 dev 渠道时启用（`UPDATER_ENABLED`）。

**更新流程：**

1. **setupAutoUpdater()**: 配置更新器，设置 `autoDownload: false`（手动控制下载），`allowDowngrade: true`

2. **checkUpdate()**: 检查更新 → 如有新版本 → 下载更新 → 缓存版本号。返回 `{ updateAvailable, version? }`

3. **checkForUpdates(alertOnFail, killSidecar)**: 用户手动触发检查 → 展示结果对话框：
   - 无更新 → 错误弹窗或"已是最新"提示
   - 有更新 → "更新已下载，是否立即重启？" → 用户确认后安装

4. **installUpdate(killSidecar)**: 先 `killSidecar()` → `autoUpdater.quitAndInstall()`

更新渠道对应关系：
| CHANNEL | 仓库 | 用途 |
|---------|------|------|
| dev | 无（禁用更新） | 本地开发 |
| beta | anomalyco/opencode-beta | 公测版 |
| prod | anomalyco/opencode | 正式版 |

#### migrate.ts — 数据迁移

处理从 Tauri 版 OpenCode 到 Electron 版的迁移：

1. 检查 `tauriMigrated` 标志位，已迁移则跳过
2. 根据平台定位 Tauri 数据目录（`~/Library/Application Support/<appId>`, `%APPDATA%/<appId>`, `~/.local/share/<appId>`）
3. 读取所有 `.dat` 文件（JSON 格式），逐项迁移到 `electron-store`
4. `opencode.settings.dat` 映射到 `opencode.settings` store，其他 `.dat` 文件保持原文件名
5. 不覆盖已存在的键值（保护用户已修改的设置）

#### shell-env.ts — Shell 环境检测

加载用户 Shell 环境的模块：

1. **`getUserShell()`**: 获取 `$SHELL` 或默认 `/bin/sh`
2. **`loadShellEnv(shell)`**: 优先尝试交互式 Shell (`-il`)，失败则尝试登录 Shell (`-l`)，5 秒超时
3. **`isNushell(shell)`**: 检测是否为 Nushell（当前版本跳过 Nushell 的环境探测）
4. 解析 `env -0` 的 null 分隔输出为键值对

#### apps.ts — 应用解析

跨平台的应用路径解析：

- **macOS**: 在 `/Applications/<name>.app`、`/System/Applications/`、`~/Applications/` 中查找，或使用 `which` 命令
- **Windows**: 使用 `where` 命令定位可执行文件，解析 `.cmd`/`.bat` 包装脚本中的 `.exe` 路径，模糊匹配邻近目录中的 `.exe`
- **Linux**: 默认认为应用存在
- **wslPath**: 通过 `wsl.exe` 在 Windows/Linux 路径格式之间转换

#### store.ts — 持久化存储

基于 `electron-store` 的延迟初始化模式：

- 使用 Map 缓存 store 实例，避免重复创建
- 延迟创建（非模块加载时），确保 `app.setPath("userData")` 已执行
- 文件存储在 `userData` 目录下，无扩展名
- 默认 store 名称为 `opencode.settings`

#### logging.ts — 日志系统

基于 `electron-log`，配置：
- 日志文件最大 5MB
- 控制台输出带断管（EPIPE）保护
- 自动清理 7 天前的旧日志
- `tail()` 导出最后 1000 行日志

#### markdown.ts — Markdown 解析

基于 `marked` 库，自定义链接渲染器：外链添加 `target="_blank"` 和 `rel="noopener noreferrer"` 属性，并添加 `external-link` CSS 类。

#### constants.ts — 常量与配置

- **CHANNEL**: 从环境变量 `OPENCODE_CHANNEL` 读取，可选 `dev`/`beta`/`prod`
- **UPDATER_ENABLED**: 仅当打包且非 dev 时为 true
- **SETTINGS_STORE**: `"opencode.settings"`
- **DEFAULT_SERVER_URL_KEY**: `"defaultServerUrl"`
- **WSL_ENABLED_KEY**: `"wslEnabled"`

---

## Preload Script (`src/preload/index.ts`)

Preload 脚本运行在 `contextIsolation: true` 的环境中，使用 `contextBridge.exposeInMainWorld` 将 `window.api`（`ElectronAPI`）暴露给 Renderer Process。

### 通信模式

所有 Renderer → Main 通信通过 `ipcRenderer.invoke`（双向，返回 Promise）或 `ipcRenderer.send`（单向，无返回）进行。

**Render → Main (invoke/send):**
- 调用型：`ipcRenderer.invoke("channel-name", ...args)` → 返回 Promise
- 通知型：`ipcRenderer.send("channel-name", ...args)` → 无返回值

**Main → Renderer (send):**
- `init-step`: 初始化步骤推送（通过 `ipcRenderer.on` 监听）
- `sqlite-migration-progress`: 迁移进度
- `menu-command`: 菜单命令
- `deep-link`: Deep Link

### 类型定义 (`src/preload/types.ts`)

定义了完整的 `ElectronAPI` 接口类型 (`InitStep`, `ServerReadyData`, `SqliteMigrationProgress`, `WslConfig`, `TitlebarTheme`, `WindowConfig`)，确保 Main/Preload/Renderer 三层之间的类型安全。

---

## Renderer Process 详解

### 入口文件 (`src/renderer/index.tsx`)

Renderer 是 SolidJS 应用，由 `src/renderer/index.html` 加载。核心功能：

#### 1. 初始化流程

```
  加载 index.html
    ├── Sentry 初始化 (条件性，依赖环境变量)
    ├── i18n 初始化 (多语言支持)
    ├── 监听 Deep Links
    │   ├── consumeInitialDeepLinks() → 消费缓存的 Deep Links
    │   └── onDeepLink() → 监听后续 Deep Links
    ├── 监听菜单命令 (menu-command)
    ├── 渲染 App 组件树
    │   ├── 创建 Platform 对象 (desktop platform)
    │   ├── 并行加载:
    │   │   ├── windowConfig (更新器开关)
    │   │   ├── sidecar credentials (awaitInitialization)
    │   │   ├── defaultServer (远程服务器 URL)
    │   │   ├── locale (语言设置)
    │   │   └── windowCount
    │   ├── 所有资源加载完毕 → 渲染 AppInterface
    │   │   ├── PlatformProvider (提供 platform 上下文)
    │   │   ├── AppBaseProviders (基础提供器，含 locale)
    │   │   └── AppInterface (传入 servers 列表为 Sidecar 服务器)
    │   └── Inner 组件:
    │       ├── 监听点击外部链接
    │       ├── 订阅主题变化 → 设置窗口背景色
    │       └── 绑定菜单触发回调
```

#### 2. Platform 适配层

Renderer 构建一个 `Platform` 对象，封装桌面平台特有的能力：

| 能力 | 实现方式 |
|------|----------|
| 文件/目录选择器 | 通过 `window.api` 调用原生 Electron 对话框 |
| WSL 路径转换 | 在 Windows 上自动转换路径（文件选择器结果 → Linux 路径） |
| 持久化存储 | 通过 IPC 调用 `electron-store`（支持多命名空间） |
| 外部链接 | `window.api.openLink(url)` → `shell.openExternal` |
| 文件路径打开 | `window.api.openPath(path, app?)` → `shell.openPath` |
| 通知 | 优先使用 Web Notification API，窗口失焦时才发送 |
| 剪贴板图片 | `window.api.readClipboardImage()` → `clipboard.readImage()` |
| 自动更新 | `window.api.checkUpdate()` / `window.api.installUpdate()` |
| Markdown 解析 | `window.api.parseMarkdownCommand()`（在 Main Process 中解析） |
| 应用检测 | `window.api.checkAppExists(appName)` |
| 主题同步 | 监听 CSS 变量 `--background-base` → 设置窗口背景色 |
| Webview 缩放 | Ctrl/Cmd + +/-/0 控制缩放因子 |

#### 3. Loading 窗口 (`src/renderer/loading.tsx`)

在数据库迁移期间显示的加载界面：

- 监听 `awaitInitialization` 获取 `InitStep` 状态
- 监听 `onSqliteMigrationProgress` 获取迁移进度百分比
- 分阶段展示文字：
  - 初始 → "Just a moment..."
  - sqlite_waiting → 逐渐显示 "Migrating your database" / "This may take a couple of minutes"
  - done → "All done"
- 3 秒 → "Migrating your database"，9 秒 → "This may take a couple of minutes"
- 迁移完成后 1 秒 → 调用 `loadingWindowComplete()` 通知 Main Process

#### 4. CLI 集成 (`src/renderer/cli.ts`)

`installCli()` 函数为终端命令提供安装路径：

1. 调用 `window.api.installCli()` → Main Process 处理安装逻辑
2. 成功：弹出提示显示 CLI 路径
3. 失败：弹出错误提示

---

## 应用生命周期完整流程

```
应用启动
│
├── Main Process 初始化
│   ├── 配置环境、路径、日志
│   ├── 注册事件监听
│   └── 单实例锁检查
│
├── app.whenReady()
│   ├── 执行数据迁移 (Tauri → Electron)
│   ├── 注册协议处理器
│   ├── 动态分配端口 + 生成密码
│   └── 启动 Sidecar
│       │
│       ├── [需要迁移 + 超过1秒] → 显示 Loading 窗口
│       │   └── Loading 窗口展示迁移进度
│       │       └── 迁移完成 → 显示 "All done"
│       │           └── [1秒后] → 通知 Main Process
│       │
│       └── Sidecar 就绪
│           ├── 健康检查通过 (30秒超时)
│           └── serverReady 信号发送
│
├── [Loading 窗口完成] → 关闭 Loading 窗口
│
├── 创建 Main 窗口
│   └── [macOS] 创建应用菜单
│
├── Main 窗口加载 index.html
│   ├── Renderer 初始化 (SolidJS)
│   ├── 并行加载所有资源
│   └── 渲染 AppInterface
│
└── 应用进入正常运行状态
    │
    ├── 系统事件处理 (Deep Links, 菜单命令, ...)
    ├── 用户交互 (文件选择, 通知, 缩放, ...)
    └── 更新检查 (手动触发)

应用退出
├── 捕获退出信号 (before-quit, will-quit, SIGINT, SIGTERM)
├── killSidecar() → 发送 stop 消息 → 等待或强杀
└── 进程退出
```

---

## 与 Web 应用的差异

桌面应用与纯 Web 版本的关键差异：

| 维度 | Web 应用 | 桌面应用 |
|------|---------|----------|
| 运行环境 | 浏览器 / WebView | Electron (Chromium + Node.js) |
| 后端服务 | 本地运行 opencode 命令 或连接远程服务 | Sidecar 子进程自动管理 |
| 文件系统 | 通过 File System Access API | Node.js 原生文件操作 + 原生文件对话框 |
| 持久化存储 | localStorage / IndexedDB | electron-store (文件系统) |
| 原生通知 | Web Notification API | Electron Notification + 窗口失焦判断 |
| 系统集成 | 有限 (PWA) | 完整 (Dock 图标, 原生菜单, 文件协议注册, Deep Links) |
| 进程管理 | 无 | 单实例锁, 子进程生命周期管理 |
| 自动更新 | Service Worker | electron-updater (GitHub Releases) |
| 网络 | 浏览器网络栈 | 完整代理支持 + 系统证书链 |
| 平台代码 | 无 | 跨平台适配 (shell 环境检测, WSL 路径转换, 应用路径解析) |
| 剪贴板 | Web Clipboard API | 原生剪贴板读取 (PNG 图片) |
| 资源加载 | HTTPS / HTTP | 自定义 `oc://` 协议 (本地文件, 安全性更高) |
| 窗口管理 | 浏览器标签 | 窗口状态记忆, 缩放控制, 主题同步背景色, 标题栏定制 |
| 构建 | Vite / Webpack | electron-vite (Main + Preload + Renderer 三入口) |
| 打包 | 无 | electron-builder (dmg / nsis / AppImage / deb / rpm) |
| 分发 | 静态部署 | GitHub Releases 跨平台二进制 |

### 关键区别说明

1. **Sidecar 架构**: 桌面应用不需要用户手动启动 `opencode` 命令行，而是自动在后台以 Utility Process 的形式 fork 出一个子进程运行后端服务。Main Process 负责管理该子进程的完整生命周期。

2. **Platform Provider**: 桌面应用使用专门的 `platform: "desktop"` 提供器，替换了 Web 平台的浏览器 API 实现，通过 IPC 桥接调用 Electron 原生能力。

3. **Deep Links**: 桌面应用支持 `opencode://` 协议，可以响应来自浏览器或其他应用的外部链接。

4. **多实例管理**: 使用 `app.requestSingleInstanceLock()` 确保同一时间只有一个应用实例运行，第二个实例的请求会被转发到已有实例。

5. **WSL 集成**: 桌面应用在 Windows 上提供完整的 WSL 支持，包括路径自动转换（Windows ↔ Linux）和功能开关。

6. **Shell 环境继承**: 启动时探测并继承用户 Shell 的环境变量（如 PATH、HOME 等），确保 Sidecar 进程运行在正确的开发环境中。

7. **Tauri 迁移**: 支持从旧版 Tauri 应用平滑迁移用户数据（设置、会话等）到新的 Electron 版本。

---

## 构建与分发

### 构建命令

```bash
# 开发模式
bun dev                    # 启动 electron-vite 开发服务器

# 构建
bun run build             # 使用 electron-vite 构建

# 分平台打包
bun run package:mac       # macOS (dmg, zip)
bun run package:win       # Windows (nsis 安装程序)
bun run package:linux     # Linux (AppImage, deb, rpm)
```

### 渠道配置

| 渠道 | appId | 产品名称 | 更新源 | 用途 |
|------|-------|----------|--------|------|
| dev | `ai.opencode.desktop.dev` | OpenCode Dev | 无 | 本地开发 |
| beta | `ai.opencode.desktop.beta` | OpenCode Beta | opencode-beta 仓库 | 公测 |
| prod | `ai.opencode.desktop` | OpenCode | opencode 仓库 | 正式发布 |

### 分发产物

- **macOS**: DMG 安装盘 + ZIP 归档，已公证 (notarized) 且启用 Hardened Runtime
- **Windows**: NSIS 一键安装程序，包含代码签名
- **Linux**: AppImage + deb 包 + rpm 包

---

## 安全模型

1. **进程隔离**: `contextIsolation: true` — Renderer 无法直接访问 Node.js API
2. **沙箱**: `sandbox: true` — Renderer 运行在 Electron 沙箱中
3. **自定义协议**: 使用 `oc://` 协议加载本地资源，带路径遍历防护
4. **剪贴板权限**: 仅受信任的 Renderer URL 可写入剪贴板
5. **CORS 配置**: Renderer 可访问 Sidecar 的 HTTP 端点（CORS origin: `oc://renderer`）
6. **Basic Auth**: Sidecar 服务使用 Basic Auth（用户名: `opencode`, 密码: 随机 UUID）进行认证
7. **进程单实例**: 通过 `requestSingleInstanceLock` 防止多实例运行导致资源冲突
