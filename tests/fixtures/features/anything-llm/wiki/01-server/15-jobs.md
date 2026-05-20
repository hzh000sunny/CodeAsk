# 15 — 后台任务系统

## 概述

后台任务系统基于 `@mintplex-labs/bree`（Bree fork）实现，提供进程级任务调度。包含常驻任务、定时同步和定时工作流。

## BackgroundService（后台服务单例）

**文件**: `server/utils/BackgroundWorkers/index.js` (396 行)

### 常驻任务

| 任务 | 间隔 | 功能 |
|------|------|------|
| `cleanup-orphan-documents` | 12 小时 | 清理孤立的直接上传文件 |
| `cleanup-generated-files` | 8 小时 | 清理 Agent 生成的文件 |
| `sync-watched-documents` | 1 小时（如果启用） | 同步被监视的文档 |

### 启动流程（`boot()`）
1. 检查文档同步是否启用（`DocumentSyncQueue.enabled()`）
2. 标识孤儿 `scheduled_job_runs`为失败（崩溃恢复）
3. 初始化 Bree 调度器
4. 启动所有常驻任务
5. 启动定时 job 调度器

### 停止流程（`stop()`）
1. 清理计划 job 定时器
2. 优雅关闭 Bree
3. 使用 `@ladjs/graceful` 处理进程信号

### Worker 管理
- `spawnWorker(scriptPath)`: 启动一次性 Bree job
- `removeJob(jobId)`: 移除 job 注册
- `killRun(jobId, runId)`: 杀死运行中的 worker

### 定时 Job 调度
- 使用 `@breejs/later` 解析 cron 表达式
- 每个 job ID 的独立 `later.setInterval` 定时器
- `enqueueScheduledJob()`: 原子排队（通过 `p-queue` 控制并发）
- `syncScheduledJob()`: 重新同步（移除+添加）定时器
- `#runScheduledJobWorker()`: 生成并通信 worker 进程

## Job 文件详解

### Embedding Worker
**文件**: `jobs/embedding-worker.js` (200 行)

隔离的子进程嵌入循环：
- 维护队列和取消集合
- IPC 协议:
  - 输入: `embed`, `add_files`, `remove_file`
  - 输出: `batch_starting`, `doc_starting`, `chunk_progress`, `doc_complete`, `doc_failed`, `all_complete`
- 处理流程: `fileData()` → `VectorDb.addDocumentToNamespace()` → `prisma.workspace_documents.create()`
- 在 `all_complete` 时退出进程
- 支持运行时动态添加文件

### Sync Watched Documents
**文件**: `jobs/sync-watched-documents.js` (210 行)

- 处理所有过期文档队列
- 对每种来源类型调用 Collector 的 `/ext/resync-source-document`
- 内容未变化: 更新同步时间，跳过
- 内容已变化: 删除旧向量 → 添加新向量 → 更新源文件
- Bloom 扩散: 更新引用同一文档的所有工作区
- 连续失败阈值: 达到 `maxRepeatFailures` 后取消监视
- 支持类型: link, youtube, confluence, github, gitlab, drupalwiki

### Run Scheduled Job
**文件**: `jobs/run-scheduled-job.js` (158 行)

- 通过 IPC 接收 `{jobId, runId}`
- 处理 SIGTERM 优雅终止（标记为 killed）
- 创建 `EphemeralAgentHandler` 执行用户定义的提示词
- 自动批准所有工具调用
- `Promise.race` 实现执行超时（默认 5 分钟）
- 捕获输出: textResponse, thoughts, toolCalls, outputs, metrics
- 发送 Web Push 通知

### Cleanup Generated Files
**文件**: `jobs/cleanup-generated-files.js`

- 扫描 Agent 生成的输出目录
- 从活跃聊天和已完成 job 运行中收集引用的文件名
- 分批删除（50 条/批）未引用的文件/文件夹
- 跳过 UUID 命名模式的文件

### Cleanup Orphan Documents
**文件**: `jobs/cleanup-orphan-documents.js`

- 扫描 `direct-uploads` 目录
- 与 `WorkspaceParsedFiles` 记录比对
- Slug 化文件名以匹配上传命名约定
- 批量并行删除（500 文件/批）

### Handle Telegram Chat
**文件**: `jobs/handle-telegram-chat.js`

- 由电报 webhook 触发的子进程
- 创建 Telegram Bot 实例
- 调用 Telegram 聊天流式响应模块

## Job 辅助工具

### helpers/index.js
- `log()`: 通过 `parentPort.postMessage`（worker 线程）或 `process.send`（子进程）发送日志
- `conclude()`: 通知父进程完成或退出
- `updateSourceDocument()`: 写入 JSON 文件到文档路径
- `stripThinkingFromText()`: 移除 `<thinking>/<thought>` 等标签

### helpers/scheduled-job-helper.js
- `SCHEDULED_JOB_TIMEOUT_MS`: 超时配置（默认 5 分钟）
- `agentActionCb()`: 创建 Agent 动作回调和状态容器，捕获 thoughts、toolCalls、textResponse、metrics
- `sendWebPushNotification()`: 发送 Web Push 通知给主要用户，正文去除思考标签并截断到 100 字符
