# 17 — 移动端 API

## 概述

移动端 API 提供 AnythingLLM 移动应用与桌面服务之间的连接接口，包括设备注册、Token 管理、命令处理。

## 数据库模型

### desktop_mobile_devices
| 字段 | 说明 |
|------|------|
| id | 设备 ID |
| deviceOs | 操作系统 |
| deviceName | 设备名称 |
| token | 唯一设备 Token |
| approved | 是否已批准 |
| userId | 关联用户 |

## 认证流程

### 设备注册
1. 用户在桌面端生成临时注册令牌（`TemporaryAuthToken`）
2. 移动端通过 `POST /mobile/register` 提交令牌
3. 验证令牌有效性
4. 创建设备记录（approved: false 或自动批准）
5. 返回设备 Token

### 设备认证
- 请求头: `x-anythingllm-mobile-device-token`
- 中间件: `validDeviceToken`
  - 查找设备记录
  - 检查 approved 状态
  - 检查关联用户是否 suspended

## API 端点

### 设备管理
| 路由 | 方法 | 功能 |
|------|------|------|
| `/mobile/devices` | GET | 列出所有设备（管理员） |
| `/mobile/:id` | POST | 更新设备属性 |
| `/mobile/:id` | DELETE | 删除设备记录 |
| `/mobile/auth` | GET | 验证设备令牌 |
| `/mobile/register` | POST | 注册新设备 |
| `/mobile/connect-info` | GET | 获取连接信息（含临时令牌） |

### 命令处理
| 路由 | 方法 | 功能 |
|------|------|------|
| `/mobile/send/:command` | POST | 发送移动命令 |

## 支持的命令

通过 `handleMobileCommand()` 函数分派：

| 命令 | 功能 | 参数 |
|------|------|------|
| `workspaces` | 列出可访问的工作区（含计数） | - |
| `workspace-content` | 获取工作区详情（线程、聊天） | slug |
| `model-tag` | 获取工作区模型名称 | slug |
| `reset-chat` | 重置聊天历史 | slug, threadSlug |
| `new-thread` | 创建工作区新线程 | slug |
| `stream-chat` | SSE 流式聊天 | slug, threadSlug, message |
| `unregister-device` | 删除设备记录 | - |

## 中间件

### validDeviceToken
- 从 `x-anythingllm-mobile-device-token` 头提取
- 数据库查找
- 检查 approved + 用户 suspended
- 设置 `response.locals`（设备和可选用户）

### validRegistrationToken
- `Authorization: Bearer <token>` 验证
- `MobileDevice.tempToken()` 按需验证
- 多用户模式下的用户验证

## 连接信息

`GET /mobile/connect-info` 返回：
- 服务器 URL
- 临时注册令牌
- 用于移动端扫码连接
