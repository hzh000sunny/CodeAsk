# 12 — 文档管理系统

## 概述

文档管理系统处理文件上传、解析、向量化、缓存和同步的完整生命周期。

## 文档存储路径

| 路径 | 用途 |
|------|------|
| `storage/documents/` | 已处理的文档 JSON 文件 |
| `storage/documents/custom-documents/` | 用户上传的文件 |
| `storage/vector-cache/` | 向量缓存（避免重复嵌入） |
| `collector/hotdir/` | 热目录（临时上传文件） |
| `storage/direct-uploads/` | 直接上传的文件 |

## 文件工具

**文件**: `server/utils/files/index.js` (520 行)

### 核心函数

- `fileData(filePath)`: 读取并解析文档 JSON 文件（路径遍历保护）
- `viewLocalFiles()`: 递归构建文件选择器树，含缓存向量信息和工作区引用状态
- `getDocumentsByFolder(folderName)`: 按文件夹获取文档
- `cachedVectorInformation(filename, checkOnly)`: 检查/获取缓存的向量块
- `storeVectorResult(vectorData, filename)`: 缓存向量结果
- `purgeDocument(filename)`: 清除向量缓存、源文件和所有工作区记录
- `purgeFolder(folderName)`: 递归删除文件夹（不能删除 custom-documents）
- `purgeEntireVectorCache()`: 删除并重建向量缓存目录
- `normalizePath(filepath)`: 路径清理（移除 `../`）
- `sanitizeFileName(fileName)`: Windows 字符清理 + 智能引号处理
- `isWithin(outer, inner)`: 路径遍历检查
- `hasVectorCachedFiles()`: 检查是否有缓存向量文件

### 文件上传中间件

**文件**: `server/utils/files/multer.js`

| 存储配置 | 用途 |
|----------|------|
| `fileUploadStorage` | GUI 上传到 hotdir |
| `fileAPIUploadStorage` | API 上传到 hotdir |
| `assetUploadStorage` | 上传 Logo 到 assets |
| `pfpUploadStorage` | 上传头像到 assets/pfp |

## DocumentManager 类

**文件**: `server/utils/DocumentManager/index.js`

### pinnedDocs()
- 加载工作区中 `pinned: true` 的文档
- 累积 `pageContent` 直到达到 `maxTokens` 限制
- 过滤缺少 `pageContent` 或 `token_count_estimate` 的条目
- 限制最多填充上下文窗口的 80%

## CollectorApi 类

**文件**: `server/utils/collectorApi/index.js` (298 行)

与 Collector 服务（`0.0.0.0:8888`）通信的客户端：

| 方法 | 功能 |
|------|------|
| `online()` | 健康检查 |
| `acceptedFileTypes()` | 获取支持的文件类型 |
| `processDocument(filename, metadata)` | 处理文档文件 |
| `processLink(link, scraperHeaders, metadata)` | 处理 URL |
| `processRawText(textContent, metadata)` | 处理原始文本 |
| `parseDocument(filename, options)` | 仅解析不嵌入 |
| `getLinkContent(link, captureAs)` | 获取链接内容 |
| `forwardExtensionRequest({endpoint, method, body})` | 代理到扩展端点 |

- 使用基于加密的请求签名（X-Integrity + X-Payload-Signer）
- 自定义调度器，15 分钟超时
- 支持 OCR 和 Whisper 选项

## 文档同步系统

### Document Sync Queue
**文件**: `models/documentSyncQueue.js`

- `staleDocumentQueues()`: 获取需要同步的过期队列
- `calcNextSync()`: 计算下次同步时间（基于 `staleAfterMs`）
- `validFileTypes`: 支持监视的文件类型列表
- `unwatch()`: 取消监视文档
- `maxRepeatFailures`: 连续失败取消阈值

### 同步触发
1. 文档标记为 `watched: true`
2. 创建 `DocumentSyncQueue` 记录
3. `BackgroundService` 定期运行 `sync-watched-documents` job
4. 对每种来源类型调用 Collector 重新抓取
5. 内容变化时更新所有引用该文档的工作区

## 工作区文件解析

### WorkspaceParsedFiles
- 上传文件到工作区或线程的解析内容
- 在聊天时注入为上下文
- `getContextFiles(workspace, thread, user)`: 获取工作区/线程/用户的所有解析文件
- `totalTokenCount()`: 计算文件 Token 消耗

## 文档来源类型解析

`Document.parseDocumentTypeAndSource()`:
```
chunkSource: "type://source"
示例: "link://https://example.com"
      "youtube://https://youtube.com/watch?v=..."
      "confluence://https://wiki.example.com"
      "github://https://github.com/user/repo"
```

## 嵌入进度管理

**文件**: `server/utils/EmbeddingWorkerManager.js` (203 行)

- `runningWorkers`: 按工作区跟踪运行中的嵌入 Worker
- `sseConnections`: 按工作区跟踪 SSE 连接
- `eventHistory`: 缓冲区用于即时重放（10 秒 TTL）
- `embedFiles()`: 启动 Worker 或向现有 Worker 添加文件
- `emitProgress()`: 向所有 SSE 连接发送进度事件
- `isNativeEmbedder()`: 检测是否使用本地嵌入器

### SSE 进度事件
- `batch_starting`: 批次开始
- `doc_starting`: 文档开始处理
- `chunk_progress`: 块处理进度
- `doc_complete`: 文档完成
- `doc_failed`: 文档失败
- `all_complete`: 全部完成
