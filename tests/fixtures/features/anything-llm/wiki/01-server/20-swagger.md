# 20 — Swagger API 文档

## 概述

使用 `swagger-autogen` 和 `swagger-ui-express` 自动生成 OpenAPI 规范文档。

## 文件结构

```
server/swagger/
├── index.js           # Swagger UI 初始化
├── init.js            # OpenAPI 规范生成器
├── openapi.json       # 生成的 OpenAPI 规范
├── utils.js           # 辅助工具
├── dark-swagger.css   # 暗色主题 CSS
└── index.css          # 自定义样式
```

## Swagger 配置

**文件**: `swagger/index.js`

- 使用 `swagger-ui-express` 提供 API 文档 UI
- 自定义 CSS（暗色主题 + 自定义样式）
- 挂载在开发者 API 路由上

## OpenAPI 规范生成

**文件**: `swagger/init.js`

- 使用 `swagger-autogen` 自动扫描端点
- 从 JSDoc 注释和路由定义生成规范
- 输出到 `openapi.json`

## API 文档访问

- 开发模式：`/api/docs`
- 通过 `useSwagger()` 初始化

## OpenAPI 规范内容

**文件**: `swagger/openapi.json`

自动生成的规范包括：
- API 基本信息（标题、版本、描述）
- 所有 `/v1/*` 端点定义
- 请求/响应 Schema
- 认证方式（API Key）
