# 18 — 中间件系统

## 概述

Express 中间件提供认证、授权、多用户保护、请求验证、嵌入安全和功能门控。

## 认证中间件

### validatedRequest（主认证中间件）
**文件**: `server/utils/middleware/validatedRequest.js`

- **多用户模式**: JWT 解码 → `User.get` 查找 → 检查 suspended 状态
- **单用户模式**: bcrypt 校验 `AUTH_TOKEN` vs JWT 加密的 `p` payload
- 将用户对象挂载到 `response.locals.user`

### validApiKey
**文件**: `server/utils/middleware/validApiKey.js`

- `Authorization: Bearer <key>` 验证
- 通过 `ApiKey.get({ secret })` 查找
- 用于开发者 API（`/api/v1/*`）

### validBrowserExtensionApiKey
**文件**: `server/utils/middleware/validBrowserExtensionApiKey.js`

- 验证浏览器扩展专用 API Key
- 多用户模式中加载关联用户

### validDeviceToken & validRegistrationToken
**文件**: `server/endpoints/mobile/middleware/index.js`

- `validDeviceToken`: `x-anythingllm-mobile-device-token` 头部验证，检查 approved + 用户 suspended
- `validRegistrationToken`: `Authorization: Bearer <token>` 验证临时注册令牌

## 授权中间件

### multiUserProtected（角色保护）
**文件**: `server/utils/middleware/multiUserProtected.js`

定义了 `ROLES`: `all`, `admin`, `manager`, `default`

| 中间件 | 功能 |
|--------|------|
| `isSingleUserMode` | 多用户模式下返回 401 |
| `strictMultiUserRoleValid(roles)` | 需要多用户模式 + 特定角色 |
| `flexUserRoleValid(roles)` | 非多用户模式放行，否则检查角色 |
| `isMultiUserSetup` | 非多用户模式返回 403 |

### admin helpers
**文件**: `server/utils/helpers/admin/index.js`

- `validRoleSelection()`: 管理员可设置任何角色，manager 只能设置 manager/default
- `canModifyAdmin()`: 确保降级管理员时至少剩下一个管理员
- `validCanModify()`: 检查调用者是否可以修改目标用户

## 工作区验证

### validWorkspace
**文件**: `server/utils/middleware/validWorkspace.js`

- `validWorkspaceSlug`: 按 slug 解析工作区（可选多用户过滤）
- `validWorkspaceAndThreadSlug`: 按 slug 解析工作区 + 线程
- 将工作区/线程挂载到 `response.locals`

## 嵌入中间件

### embedMiddleware
**文件**: `server/utils/middleware/embedMiddleware.js`

| 中间件 | 功能 |
|--------|------|
| `validEmbedConfig` | 按 UUID 解析嵌入配置 |
| `validEmbedConfigId` | 按数字 ID 解析嵌入 |
| `setConnectionMeta` | 记录请求来源和 IP |
| `canRespond` | 检查: 启用状态、域名白名单、会话 ID、消息长度、每日限制、每会话限制 |

## 功能门控中间件

### featureFlagEnabled
**文件**: `server/utils/middleware/featureFlagEnabled.js`

- 检查 `SystemSettings` 中功能标志是否为 `"enabled"`
- 用于实验性功能（如 live sync）

### simpleSSOEnabled
**文件**: `server/utils/middleware/simpleSSOEnabled.js`

- 检查 `SIMPLE_SSO_ENABLED` 设置
- `simpleSSOLoginDisabled`: 额外检查 `SIMPLE_SSO_NO_LOGIN`
- 需要多用户模式

### chatHistoryViewable
**文件**: `server/utils/middleware/chatHistoryViewable.js`

- 如果 `DISABLE_VIEW_CHAT_HISTORY=true`，返回 422

### communityHubDownloadsEnabled
**文件**: `server/utils/middleware/communityHubDownloadsEnabled.js`

- 检查 `COMMUNITY_HUB_BUNDLE_DOWNLOADS_ENABLED`
- 限制已验证项目或私有项目（除非 `allow_all`）

### isSupportedRepoProviders
**文件**: `server/utils/middleware/isSupportedRepoProviders.js`

- 验证仓库平台参数（`github` 或 `gitlab`）

## HTTP 中间件

### httpLogger
**文件**: `server/middleware/httpLogger.js`

- 开发模式下的 HTTP 请求日志
- 可选时间戳
- 仅当 `ENABLE_HTTP_LOGGER=true` 启用

## 其他工具中间件

### setDataSigner（Collector）
**文件**: `collector/middleware/setDataSigner.js`

- 为 Collector 设置数据签名

### verifyIntegrity（Collector）
**文件**: `collector/middleware/verifyIntegrity.js`

- 验证 Collector 请求的数据完整性
- 基于加密签名验证
