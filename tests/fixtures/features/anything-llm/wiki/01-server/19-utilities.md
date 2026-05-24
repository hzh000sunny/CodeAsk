# 19 — 工具函数集

## 概述

`server/utils/` 目录包含各种支撑整个服务的工具模块。

## 工具模块清单

### EncryptionManager
**文件**: `utils/EncryptionManager/index.js`

- AES-256-CBC 加密
- 基于环境变量 `SIG_KEY` + `SIG_SALT`
- `encrypt(plainText)`: 随机 IV 加密，返回 `encrypted:iv` 格式
- `decrypt(encryptedString)`: 解析并解密
- 导出 `xPayload`（Base64 密钥）用于进程间通信

### CommunicationKey
**文件**: `utils/comKey/index.js`

- RSA 2048 密钥对管理
- 存储在 `storage/comkey/`
- 服务器启动时自动生成
- `sign(textData)`: RSA-SHA256 签名（十六进制）
- `encrypt(textData)`: 私钥加密（Base64）

### Logger
**文件**: `utils/logger/index.js`

- Winston 日志系统（生产环境）
- 彩色格式: `[service][origin]`
- 覆盖全局 `console.log/error/info`
- 开发环境使用原生 console

### HTTP 工具
**文件**: `utils/http/index.js`

- `reqBody(request)`: 解析请求体
- `queryParams(request)`: 解析查询参数
- `userFromSession(request, response)`: JWT 会话提取
- `multiUserMode(response)`: 多用户模式检测
- `makeJWT(payload, expiresIn)`: JWT 生成（30 天默认过期）
- `decodeJWT(token)`: JWT 解码
- `safeJsonParse(jsonString, fallback)`: 安全 JSON 解析（jsonrepair + extract-json-from-string 回退）
- `isValidUrl(url)`: URL 验证
- `decodeHtmlEntities(text)`: HTML 实体解码

### 聊天助手
**文件**: `utils/helpers/chat/index.js`

- `messageArrayCompressor()`: 消息数组压缩（Cannonball 方法）
- `messageStringCompressor()`: 字符串消息压缩
- `cannonball()`: 从中间截断文本
- `fillSourceWindow()`: 来源窗口回填

### TokenManager
**文件**: `utils/helpers/tiktoken.js`

- 单例模式（按模型）
- 使用 `js-tiktoken` 进行 Token 计数
- `tokensFromString()`, `bytesFromTokens()`, `countFromString()`, `statsFrom()`

### LLMPerformanceMonitor
**文件**: `utils/helpers/chat/LLMPerformanceMonitor.js`

- `countTokens(messages)`: Token 统计
- `measureAsyncFunction(func)`: 非流式性能测量
- `measureStream()`: 流式性能测量

### 聊天响应处理
**文件**: `utils/helpers/chat/responses.js`

- `handleDefaultStreamResponseV2()`: 默认流处理（20+ 提供商使用）
- `convertToChatHistory()`: 原始历史 → 前端格式
- `convertToPromptHistory()`: 原始历史 → LLM 格式
- `writeResponseChunk()`: 写入 SSE 块
- `safeJSONStringify()`: BigInt 安全序列化

### 自定义模型获取
**文件**: `utils/helpers/customModels.js` (1011 行)

- `SUPPORT_CUSTOM_MODELS`: 约 50 个支持模型获取的提供商
- 每个提供商的模型获取函数（从 API 或 SDK 获取模型列表）
- 返回 `{models, error}` 格式

### 环境变量更新
**文件**: `utils/helpers/updateENV.js` (1382 行)

- `KEY_MAPPING`: 所有设置键到环境变量的映射
- 每个键的 `checks`, `preUpdate`, `postUpdate`, `postSettled`
- `updateENV()`: 验证 + 写入 `.env` 文件
- `dumpENV()`: 将受保护的环境变量写入 `.env`
- 特殊处理: 向量存储重置、嵌入模型下载

### 搜索助手
**文件**: `utils/helpers/search.js`

- `searchWorkspaceAndThreads()`: 搜索工作区和线程
- 严格包含 + Levenshtein 距离模糊匹配（阈值 3）
- 多用户感知

### 管理员助手
**文件**: `utils/helpers/admin/index.js`

- `validRoleSelection()`: 角色选择验证
- `canModifyAdmin()`: 管理员降级保护
- `validCanModify()`: 修改权限检查

### Agent 助手
**文件**: `utils/helpers/agents.js`

- `skillIsAutoApproved()`: 检查技能是否自动批准

### 其他工具
| 文件 | 功能 |
|------|------|
| `utils/helpers/camelcase.js` | CamelCase 转换 |
| `utils/helpers/portAvailabilityChecker.js` | 端口可用性检查 |
| `utils/helpers/shell.js` | Shell PATH 补丁 |

### PushNotifications
**文件**: `utils/PushNotifications/index.js`

- 使用 `web-push` (VAPID)
- VAPID 密钥存储在 `storage/push-notifications/`
- 多用户模式：订阅存储在数据库
- 单用户模式：订阅存储在文件
- `sendNotification()`: 发送推送通知（按用户或 primary）

### PasswordRecovery
**文件**: `utils/PasswordRecovery/index.js`

- `generateRecoveryCodes(userId)`: 生成 4 个 UUIDv4 恢复码
- `recoverAccount()`: 验证恢复码 → 创建重置令牌
- `resetPassword()`: 验证令牌 → 更新密码 → 清理恢复码

### TextToSpeech
**文件**: `utils/TextToSpeech/`

| 提供商 | 特点 |
|--------|------|
| OpenAI TTS | 默认语音 alloy，模型 tts-1 |
| ElevenLabs | 默认语音 Rachel，模型 eleven_multilingual_v2 |
| Generic OpenAI TTS | 兼容 OpenAI 的 TTS 端点 |

### Prisma Client
**文件**: `utils/prisma/index.js`

日志级别: `["error", "info", "warn"]`

### Boot 工具
**文件**: `utils/boot/`

- `index.js`: HTTP/HTTPS 引导启动
- `MetaGenerator.js`: PWA manifest 和 index.html 生成
- `markOnboarded.js`: 新手引导标记
- `eagerLoadContextWindows.js`: 预加载上下文窗口
