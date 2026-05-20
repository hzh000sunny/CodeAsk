# 03 — Collector 文档处理器

> 独立的文档摄取微服务，运行在 Port 8888

## 概述

Collector 是 AnythingLLM 的文档处理引擎，负责将各种格式的文件和 URL 内容转换为可用于向量嵌入的结构化文本。作为独立进程运行，与 Server 通过加密 API 通信。

## 架构

```
collector/
├── index.js                # Express 入口
├── processSingleFile/      # 文件处理模块
│   ├── index.js            # 主入口（文件类型检测和路由）
│   └── convert/            # 各格式转换器
├── processLink/            # URL 处理模块
│   ├── index.js            # processLink + getLinkText
│   ├── convert/            # URL 抓取转换
│   └── helpers/            # 链接处理辅助
├── processRawText/         # 原始文本处理
│   └── index.js            # 元数据提取 + 文档写入
├── extensions/             # 扩展集成（注册器）
│   ├── index.js            # 扩展路由注册
│   └── resync/             # 重新同步方法
├── middleware/              # 中间件
│   ├── verifyIntegrity.js  # 请求完整性验证（基于加密签名）
│   ├── httpLogger.js       # HTTP 日志
│   └── setDataSigner.js    # 数据签名设置
├── utils/                  # 工具
│   ├── constants.js        # 常量（ACCEPTED_MIMES, SUPPORTED_FILETYPE_CONVERTERS）
│   ├── shell.js            # Shell PATH 补丁
│   ├── files.js            # 文件操作（读写、清理）
│   ├── http.js             # HTTP 工具
│   ├── url.js              # URL 验证
│   ├── tokenizer.js        # Token 计数
│   └── extensions/         # 扩展实现
│       ├── RepoLoader.js   # GitHub/GitLab 仓库加载器
│       ├── ObsidianVault.js# Obsidian 保险库导入
│       ├── YoutubeTranscript.js # YouTube 字幕
│       ├── Confluence.js   # Confluence 集成
│       ├── DrupalWiki.js   # DrupalWiki 集成
│       ├── WebsiteDepth.js # 网站深度抓取
│       └── PaperlessNgx.js # Paperless-NGX 集成
└── hotdir/                 # 热目录（临时上传文件）
```

## 启动流程

1. 加载环境变量（开发: `.env.development`，生产: `.env`）
2. 初始化日志系统
3. 注册中间件（CORS, body-parser 3GB 限制）
4. 挂载路由
5. 监听 8888 端口
6. 启动时调用 `wipeCollectorStorage()` 清空临时存储

## 核心 API 端点

### `/process` — 文件处理
通过 `processSingleFile()` 处理上传的文件：
1. 路径规范化和遍历保护（`normalizePath` + `isWithin`）
2. 保留文件检查（`__HOTDIR__.md`）
3. 文件扩展名提取和验证
4. 无预设转换器的扩展名 → 检查是否为纯文本类型
5. 根据 `SUPPORTED_FILETYPE_CONVERTERS` 映射加载对应的转换器
6. 调用 `FileTypeProcessor({fullFilePath, filename, options, metadata})`
7. 支持 `parseOnly`（仅解析不保存）和 `absolutePath` 选项

### `/process-link` — URL 处理
通过 `processLink()` 抓取 URL 内容：
1. URL 验证（`validURL` + `validateURL`）
2. 调用 `scrapeGenericUrl()` 进行抓取
3. 支持自定义 `scraperHeaders`
4. 支持 `captureAs`: text / html / json
5. `saveAsDocument: true` 自动保存为文档

### `/process-raw-text` — 原始文本处理
通过 `processRawText()` 处理：
1. 文本内容非空验证
2. `METADATA_KEYS` 提取元数据：
   - `url`: web:// URL 或 file:// 路径
   - `title`, `docAuthor`, `description`, `docSource`, `chunkSource`
   - `published`: 日期格式化
3. Token 计数（`tokenizeString`）
4. `writeToServerDocuments()` 写入 JSON 文件
5. 文件名格式: `raw-{slugified-title}-{uuid}`

## 扩展集成系统

**文件**: `extensions/index.js` (240 行)

所有扩展端点的注册中心：

| 端点 | 功能 | 中间件 |
|------|------|--------|
| `/ext/resync-source-document` | 重新同步源文档 | verify + signer |
| `/ext/:repo_platform-repo` | 加载 GitHub/GitLab 仓库 | verify + signer |
| `/ext/:repo_platform-repo/branches` | 获取仓库分支列表 | verify |
| `/ext/youtube-transcript` | YouTube 字幕提取 | verify |
| `/ext/website-depth` | 网站深度抓取（depth + maxLinks） | verify |
| `/ext/confluence` | Confluence 空间导入 | verify + signer |
| `/ext/drupalwiki` | DrupalWiki 内容导入 | verify + signer |
| `/ext/obsidian/vault` | Obsidian 保险库导入 | verify + signer |
| `/ext/paperless-ngx` | Paperless-NGX 文档导入 | verify + signer |

### 重新同步方法（`extensions/resync/`）
支持对已监视文档的源重新抓取：
- `link`: 重新抓取 URL
- `youtube`: 重新获取字幕
- `confluence`, `github`, `gitlab`, `drupalwiki`: 使用 `chunkSource` 重新抓取

## 安全机制

### verifyIntegrity 中间件
所有处理端点使用 `verifyPayloadIntegrity`：
- 验证请求来源和数据完整性
- 基于加密签名的请求验证
- 使用 `CommunicationKey`（RSA 2048 密钥对）进行签名
- `X-Integrity` + `X-Payload-Signer` 头部

## 文件类型支持

### SUPPORTED_FILETYPE_CONVERTERS
预设的文件类型转换器映射（`.extension` → 转换器路径），包括：
- `.pdf`, `.docx`, `.txt`, `.csv`, `.md`
- `.html`, `.xml`, `.json`
- `.py`, `.js`, `.ts`, `.java`, `.go` 等代码文件
- 未匹配的扩展名 → 根据 isTextType() 判断是否作为 .txt 处理

## 与 Server 的通信

Server 通过 `CollectorApi` 类（`server/utils/collectorApi/index.js`）与 Collector 通信：
- 加密请求头: `X-Integrity` + `X-Payload-Signer`
- 使用 `CommunicationKey`（RSA 2048 密钥对）
- 自定义调度器，15 分钟超时
- 支持 Whisper 和 OCR 选项
