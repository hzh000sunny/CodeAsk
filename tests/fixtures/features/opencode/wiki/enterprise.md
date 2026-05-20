# Enterprise 包

Enterprise 包 (`@opencode-ai/enterprise`) 是一个基于 SolidStart + Vite 构建的全栈 Web 应用，为 OpenCode 提供团队和企业级功能，核心是会话分享系统。

## 技术栈

| 技术 | 用途 |
|------|------|
| SolidStart + SolidJS | SSR 能力的响应式 UI 框架 |
| Vite | 构建工具和开发服务器 |
| Hono | API 路由处理 |
| hono-openapi | API 文档自动生成 |
| Zod | 请求/响应数据校验 |
| Nitro | 服务端打包和部署预设 |
| Tailwind CSS | 样式系统 |
| aws4fetch | S3/R2 兼容的对象存储客户端 |
| @solidjs/router | 客户端路由 |
| @solidjs/meta | HTML meta 管理 |

## 架构总览

```
┌────────────────────────────────────────────────────┐
│                  SolidStart App                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │
│  │  entry-client │  │ entry-server │  │  app.tsx  │ │
│  │  (浏览器入口)  │  │  (SSR 入口)  │  │ (根组件)   │ │
│  └──────────────┘  └──────────────┘  └─────┬─────┘ │
│                                            │        │
│  ┌─────────────────────────────────────────┘──────┐ │
│  │                   路由层                        │ │
│  │  / (首页)  │  /share (分享布局)  │  /api/* (Hono) │
│  └──────────────────────┬────────────────────────┘ │
│                         │                           │
│  ┌──────────────────────┴────────────────────────┐ │
│  │                  核心模块                      │ │
│  │  Share (分享逻辑)  │  Storage (存储抽象)       │ │
│  └──────────────────────┬────────────────────────┘ │
│                         │                           │
│  ┌──────────────────────┴────────────────────────┐ │
│  │              存储后端 (S3 / Cloudflare R2)     │ │
│  └───────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────┘
```

## 应用入口与上下文

### app.tsx -- 根组件

`app.tsx` 是应用的根组件，负责组装全局 Provider 层级：

```
Router
 └── MetaProvider          ← HTML meta 标签管理
      └── DialogProvider   ← 全局弹窗状态
           └── MarkedProvider ← Markdown 渲染上下文
                └── Favicon
                └── Font
                └── UiI18nBridge ← 国际化桥接层
                     └── Suspense → FileRoutes
```

**国际化检测机制** (`UiI18nBridge`)：

1. SSR 阶段：读取请求头 `accept-language`，匹配 `zh` 或 `en`
2. 客户端阶段：依次检查 `document.documentElement.lang`、`navigator.language`
3. 兜底：默认返回 `en`

国际化的核心是模板字符串替换，表达式 `{{ key }}` 会被替换为对应语言的参数值。

### entry-client.tsx

客户端入口，调用 `mount()` 将 `StartClient` 挂载到 DOM 的 `#app` 节点：

```tsx
import { mount, StartClient } from "@solidjs/start/client"
mount(() => <StartClient />, document.getElementById("app")!)
```

### entry-server.tsx

服务端入口，使用 `createHandler` 渲染 `StartServer`。在 SSR 期间同样解析 `accept-language` 请求头设置 `<html lang>` 属性，并配置了主题色、视口等元信息。

## 路由系统

项目使用 SolidStart 的基于文件系统的路由 (`FileRoutes`)。

| 路由 | 文件 | 说明 |
|------|------|------|
| `/` | `src/routes/index.tsx` | 首页（当前为占位页面） |
| `/share` | `src/routes/share.tsx` | 分享布局页（渲染子路由） |
| `/share/[shareID]` | `src/routes/share/[shareID].tsx` | 分享详情页（会话展示核心） |
| `/api/[...path]` | `src/routes/api/[...path].ts` | API 路由（Hono 处理） |
| `/*` | `src/routes/[...404].tsx` | 404 兜底页面 |

### 分享详情页 (`[shareID].tsx`)

这是整个 Enterprise 应用最复杂的页面，实现了完整的分享会话渲染。

**数据加载**：通过 SolidStart 的 `query` 创建 `getData` 查询函数（标记为 `"use server"` 在服务端执行），具体流程：

1. 根据 URL 中的 `shareID` 调用 `Share.get()` 获取分享元信息
2. 调用 `Share.data()` 获取所有同步数据
3. 按类型分类重组数据：`session`、`message`、`part`、`session_diff`、`model`
4. 使用二分查找定位对应 session
5. 返回结构化的数据对象供 UI 消费

**缓存策略**：响应头设置为 `Cache-Control: public, max-age=30, s-maxage=300, stale-while-revalidate=86400`，结合 CDN 提供高效的缓存层。

**UI 布局**：

```
┌──────────────────────────────────────────┐
│  Header (Logo + GitHub/Discord 链接)      │
├────────────────────┬─────────────────────┤
│  消息导航栏        │  Session 会话轮次    │
│  (MessageNav)     │  (SessionTurn)       │
│  (当消息数 >1)     │                     │
│                   │  代码变更审查区       │
│                   │  (SessionReview)     │
│                   │  (当有文件差异时)      │
├────────────────────┴─────────────────────┤
│  Footer (Logo)                           │
└──────────────────────────────────────────┘
```

**响应式设计**：在窄屏/移动端，使用 `Tabs` 组件将 Session 和 Review 切换显示；宽屏时左右并排。根据是否有 diff 数据 (`wide()`) 决定断点（无 diff 时 `md:` 即可并排，有 diff 时需 `lg:`）。

**OG 图片生成**：动态构造 `og:image` URL，包含标题（Base64 编码）、模型名称和版本号，由 `social-cards.sst.dev` 服务渲染社交分享卡片。

**Worker Pool**：通过 `clientOnly` 动态导入 `@opencode-ai/ui/pierre/worker`，确保 Worker 池仅在客户端初始化。

### API 路由 (`[...path].ts`)

所有 `/api/*` 请求统一由 Hono 实例处理，暴露 GET/POST/PUT/DELETE 四个 HTTP 方法。使用了以下中间件：

- `cors()` -- 跨域支持
- `hono-openapi` 的 `describeRoute`、`validator`、`resolver` -- API 文档和参数校验

**API 端点**：

| 方法 | 路径 | 说明 | 校验 |
|------|------|------|------|
| `GET` | `/api/doc` | OpenAPI 文档页面 | 无 |
| `POST` | `/api/share` | 创建分享链接 | `{ sessionID: string }` |
| `POST` | `/api/share/:shareID/sync` | 同步分享数据 | `{ secret, data: Share.Data[] }` |
| `GET` | `/api/share/:shareID/data` | 获取分享数据 | 路径参数 `shareID` |
| `DELETE` | `/api/share/:shareID` | 删除分享 | `{ secret: string }` |

分享创建时会从请求头 `x-forwarded-proto` / `x-forwarded-host` 推断完整 URL 返回给客户端。

## 分享系统 (Share)

`src/core/share.ts` 是分享系统的核心模块，提供完整的 CRUD 和数据同步能力。

### 数据结构

**Share.Info** -- 分享元信息：
```typescript
{ id: string, secret: string, sessionID: string }
```

**Share.Data** -- 分享数据类型（鉴别联合）：
- `{ type: "session", data: Session }` -- 会话信息
- `{ type: "message", data: Message }` -- 消息记录
- `{ type: "part", data: Part }` -- 消息片段（文本/工具调用等）
- `{ type: "session_diff", data: SnapshotFileDiff[] }` -- 文件差异快照
- `{ type: "model", data: Model[] }` -- 模型配置

### 核心 API

| 函数 | 签名 | 说明 |
|------|------|------|
| `create` | `({ sessionID }) => Info` | 创建新分享，生成随机 secret，ID 取 sessionID 后 8 位 |
| `get` | `(id) => Info \| undefined` | 根据 ID 查询分享信息 |
| `remove` | `({ id, secret }) => void` | 删除分享及其所有关联数据（snapshot/compaction/event/data） |
| `sync` | `({ share, data }) => void` | 合并同步数据到快照（需 secret 校验） |
| `data` | `(shareID) => Data[]` | 读取分享的全部数据 |

### 数据合并策略

`Share.sync` 采用**快照合并**模式：

1. 读取当前快照 (`share_snapshot/{id}`)
2. 如果没有快照，尝试从旧版 compact 格式迁移 (`legacy`)
3. 将新数据与现有快照按 key 合并（相同 key 的数据会被新数据覆盖）
4. 写回快照

Key 的生成规则：
- `session` 类型 → key = `"session"`
- `message` 类型 → key = `"message/{id}"`
- `part` 类型 → key = `"part/{messageID}/{id}"`
- `session_diff` 类型 → key = `"session_diff"`
- `model` 类型 → key = `"model"`

合并后按 key 字母序排序，保证数据确定性。

### 数据迁移路径

旧版系统使用 `share_event/{shareID}/{eventID}` 存储增量事件，通过 `share_compaction/{shareID}` 维护压缩点。`legacy()` 函数负责将旧格式迁移到新快照格式：

1. 读取 compact 基准数据
2. 列出 compact 时间点之后的所有 event
3. 合并所有增量数据
4. 同时更新 compact 和 snapshot

### 安全模型

- 每个分享有一个随机生成的 `secret`（使用 `crypto.randomUUID()`）
- `sync`、`remove` 操作都需要提供正确的 secret
- 密码不匹配时抛出 `InvalidSecret` 错误
- 测试环境（`sessionID` 以 `test_` 开头）使用固定前缀的 ID

### 错误处理

```typescript
Share.Errors.NotFound       // 分享不存在
Share.Errors.InvalidSecret  // 密码无效
Share.Errors.AlreadyExists  // 分享 ID 已存在
```

## 存储抽象 (Storage)

`src/core/storage.ts` 提供统一的键值存储抽象层。

### 适配器接口

```typescript
interface Adapter {
  read(path: string): Promise<string | undefined>
  write(path: string, value: string): Promise<void>
  remove(path: string): Promise<void>
  list(options?): Promise<string[]>
}
```

### 后端实现

通过环境变量 `OPENCODE_STORAGE_ADAPTER` 选择存储后端：

| 值 | 后端 | 认证方式 |
|-----|------|---------|
| `"r2"` | Cloudflare R2 | Account ID + Access Key + Secret Key |
| `"s3"` | AWS S3 | Region + Access Key + Secret Key |

AwsClient (`aws4fetch`) 负责 AWS Signature V4 签名。R2 和 S3 共享相同的 S3 兼容 API，区别仅在于 endpoint URL 格式：
- S3: `https://s3.{region}.amazonaws.com/{bucket}`
- R2: `https://{accountId}.r2.cloudflarestorage.com/{bucket}`

list 操作解析 S3 的 XML 响应（ListObjectsV2 格式），使用正则提取 `<Key>` 标签内容。

### 存储层 API

| 函数 | 说明 |
|------|------|
| `read<T>(key: string[])` | 读取 JSON 反序列化后的数据 |
| `write<T>(key, value)` | 将值 JSON 序列化后写入 |
| `remove(key: string[])` | 删除指定 key |
| `list({ prefix?, limit?, after?, before? })` | 列出符合条件的 key |
| `update<T>(key, fn)` | 读取、修改、写回的原子化更新 |

Key 采用路径数组 (`string[]`) 形式，内部转换为 `key1/key2/key3.json` 的文件路径。`list` 返回反序列化后的路径数组。

## 部署选项

### Cloudflare Pages

通过 `OPENCODE_DEPLOYMENT_TARGET=cloudflare` 环境变量启用 Cloudflare 部署模式：

```bash
OPENCODE_DEPLOYMENT_TARGET=cloudflare vite build
```

构建时 Nitro 使用 `cloudflare_module` 预设，启用 `nodeCompat` 以支持 Node.js API 在 Cloudflare Workers 运行时中运行。

### 通用部署

默认构建输出适配 Node.js 服务端环境，使用 Nitro 默认预设。开发模式：

```bash
vite dev     # 启动开发服务器
vite build   # 构建生产包
vite start   # 启动生产预览
```

### SST 集成

项目通过 SST（Serverless Stack）管理基础设施，可使用 `sst shell` 进入生产环境 shell：

```bash
sst shell --target Teams --stage production
```

## 测试

测试文件位于 `test/core/`，使用 Bun 测试框架：

- `share.test.ts` -- 分享系统的完整测试套件，覆盖创建、同步、多次同步、重复数据去重、secret 校验、旧数据迁移、多种数据类型等场景
- `storage.test.ts` -- 存储适配器的列表操作测试，验证前缀过滤、范围查询 (`after`/`before`)、分页限制等功能
