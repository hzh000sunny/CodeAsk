# 05 — Browser Extension 浏览器扩展

## 概述

Chrome 浏览器扩展，允许用户直接从浏览器抓取网页内容并保存到 AnythingLLM 工作区。

## 目录结构

```
browser-extension/
└── (Chrome 扩展源代码)
```

## 功能

### 页面保存
- 抓取当前浏览页面的内容
- 通过 API 保存到 AnythingLLM 工作区
- 使用专用 API Key 认证

## API 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/browser-extension/save-page` | POST | 保存网页内容 |

## 认证机制

使用 `browser_extension_api_keys` 模型：
- 每个用户可生成扩展专用 API Key
- 多用户模式下关联用户身份
- 通过 `validBrowserExtensionApiKey` 中间件验证

## API Key 管理

| 端点 | 方法 | 功能 |
|------|------|------|
| `/browser-extension/generate-key` | POST | 生成新 Key |
| `/browser-extension/keys` | GET | 列出所有 Key |
| `/browser-extension/keys/:id` | DELETE | 删除 Key |

## 数据模型

### browser_extension_api_keys
| 字段 | 说明 |
|------|------|
| id | Key ID |
| key | 唯一 API Key |
| user_id | 关联用户（多用户模式） |
