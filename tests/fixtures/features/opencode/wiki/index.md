# OpenCode 知识库

> **版本**: v1.14.48 | **许可**: MIT | **仓库**: https://github.com/anomalyco/opencode

## 项目概述

OpenCode 是一个 AI 驱动的开发工具，提供终端 UI (TUI)、桌面应用 (Electron) 和 Web 界面三种交互方式。它通过 LLM 抽象层集成多种 AI 提供商（Anthropic、OpenAI、Google、AWS Bedrock 等），在会话中执行代码搜索、文件编辑、Shell 命令等工具调用。

## 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    用户界面层                            │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ TUI (CLI)│  │ Desktop (Electron)│  │  Web App (SolidJS)│  │
│  └────┬─────┘  └──────┬───────┘  └────────┬─────────┘  │
├───────┼───────────────┼──────────────────┼─────────────┤
│       │          packages/app        packages/web       │
│       │         packages/desktop                        │
├───────┴───────────────────────────────────────────────┤
│                    HTTP API 层                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │        packages/opencode/src/server/              │  │
│  │   Effect HTTP Server + OpenAPI + WebSocket        │  │
│  └──────────────────────┬───────────────────────────┘  │
├─────────────────────────┼──────────────────────────────┤
│                   核心逻辑层                             │
│  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌───────────┐  │
│  │ Session  │ │  Agent   │ │  Tool  │ │ Provider  │  │
│  │ 会话管理  │ │  智能体   │ │ 工具系统│ │  模型提供商 │  │
│  └────┬─────┘ └────┬─────┘ └───┬────┘ └─────┬─────┘  │
│       │            │           │             │        │
│  ┌────┴────────────┴───────────┴─────────────┴─────┐  │
│  │         packages/opencode/src/                   │  │
│  │  Config│MCP│Permission│Sync│LSP│PTY│Git│Plugin  │  │
│  └──────────────────────┬──────────────────────────┘  │
├─────────────────────────┼──────────────────────────────┤
│                   基础架构层                             │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │   LLM    │  │    Plugin    │  │     Core       │  │
│  │ LLM 抽象  │  │   插件 API   │  │  基础工具库     │  │
│  └──────────┘  └──────────────┘  └────────────────┘  │
│  ┌──────────┐  ┌──────────────┐                      │
│  │   SDK    │  │ HTTP Recorder│                      │
│  │   JS SDK │  │  HTTP 录制回放 │                      │
│  └──────────┘  └──────────────┘                      │
└─────────────────────────────────────────────────────────┘
```

## 包依赖关系

```
core ────────────────────────────────────── (零内部依赖)
  │
sdk ────────────────────────────────────── (仅依赖 cross-spawn)
  │
  ├── plugin ──────────────────────────── (依赖 sdk)
  │
llm ───────────────────────────────────── (依赖 effect, aws4fetch)
  │
  └── opencode (主包) ────────────────── (依赖 core, llm, sdk, plugin)
        │
        ├── ui ────────────────────────── (依赖 sdk, core)
        │   ├── app ──────────────────── (依赖 sdk, ui, core)
        │   │   └── desktop ──────────── (依赖 app, ui)
        │   ├── enterprise ──────────── (依赖 core, ui)
        │   └── storybook ────────────── (依赖 ui)
        │
        ├── slack ─────────────────────── (依赖 sdk)
        ├── function ─────────────────── (Cloudflare Workers)
        └── script ────────────────────── (构建/发布工具)
```

## 模块文档索引

### 基础层
- [Core - 基础工具库](./core.md) — 全局路径、文件系统、Effect 运行时、日志、标志位
- [LLM - 大语言模型抽象层](./llm.md) — 多提供商路由、协议适配、工具执行
- [Plugin - 插件系统 API](./plugin.md) — 插件接口定义、工具定义、TUI 扩展
- [SDK - JavaScript SDK](./sdk.md) — 客户端/服务端 API、v2 版本

### 核心逻辑层
- [CLI 入口 - 命令行启动流程](./cli.md) — yargs 命令注册、中间件、启动流程
- [Session - 会话管理](./session.md) — 会话 CRUD、消息管理、事件溯源
- [Agent - 智能体系统](./agent.md) — 内置/自定义 Agent、权限合并、子代理
- [Tool - 工具系统](./tool.md) — 内置工具注册、插件工具加载、工具执行
- [Provider - 模型提供商](./provider.md) — 多提供商管理、模型发现、SDK 加载
- [Config - 配置系统](./config.md) — 多源配置加载、合并策略、配置文件
- [Server - HTTP API 服务器](./server.md) — Effect HTTP 服务、OpenAPI、路由
- [Sync - 同步与事件溯源](./sync.md) — 事件定义、投影器、多设备同步
- [MCP - Model Context Protocol](./mcp.md) — MCP 客户端、OAuth 认证、工具发现
- [Permission - 权限系统](./permission.md) — 规则评估、请求/回复流程

### 辅助系统层
- [PTY - 伪终端管理](./pty.md) — PTY 生命周期、输入处理
- [LSP - 语言服务器协议](./lsp.md) — LSP 客户端、诊断信息

### 用户界面层
- [Desktop - 桌面应用](./desktop.md) — Electron 主进程、渲染进程、自动更新
- [Web App - Web 应用](./web-app.md) — SolidJS 前端、路由、状态管理
- [UI - 组件库](./ui.md) — 80+ UI 组件、主题系统、Markdown 渲染
- [Enterprise - 企业版](./enterprise.md) — 团队共享、SolidStart 应用

### 集成层
- [Slack - Slack 集成](./slack.md) — Slack Bot、Socket 模式
- [Function - Cloudflare Workers](./function.md) — 同步服务、Durable Objects

## 核心技术栈

| 技术 | 用途 |
|------|------|
| TypeScript | 主编程语言 |
| Effect | 类型安全的副作用管理、依赖注入 |
| Bun | 包管理器和运行时 |
| SQLite (Drizzle ORM) | 数据持久化 |
| SolidJS | 前端 UI 框架 |
| Vite | 前端构建工具 |
| Electron | 桌面应用框架 |
| yargs | CLI 参数解析 |
| Zod / Effect Schema | 运行时类型验证 |
| OpenTelemetry | 可观测性 |

## 关键设计模式

### 1. Effect 驱动的服务架构
所有核心服务（Config、Provider、Session、Agent、MCP 等）均定义为 Effect Context.Service，通过 Layer 系统进行依赖注入和组合。

### 2. 事件溯源 (Event Sourcing)
会话状态变更通过 SyncEvent 记录，由 Projector 投影到数据库和 Bus。支持多设备同步和事件重放。

### 3. LLM 抽象层
通过协议适配器模式（Anthropic Messages、OpenAI Chat、Bedrock Converse、Gemini），提供统一的模型调用接口。

### 4. 插件系统
支持外部插件定义工具、工作区适配器、TUI 组件和 Shell 集成。

### 5. 多 UI 表面
同一核心逻辑同时服务 TUI、Desktop (Electron) 和 Web (Vite) 三个前端。
