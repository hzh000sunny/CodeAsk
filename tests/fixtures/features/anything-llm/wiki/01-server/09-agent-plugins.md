# 09 — Agent 插件系统

## 概述

Agent 插件系统提供 20+ 种工具能力，通过 AIbitat 的插件注册机制加载到 @agent 中。

## 插件加载机制

插件通过 `AgentHandler.#attachPlugins()` 加载：

```javascript
pluginInstance = { name, description, setup(aibitat) { ... } }
// setup() 中使用 aibitat.function() 注册工具
```

每个工具注册格式：
```javascript
aibitat.function(name, description, parameters, handler)
// parameters 格式: { paramName: { type, description, required } }
```

## 标准插件清单

### 1. Memory（记忆插件）
**文件**: `plugins/memory.js`

| 工具 | 参数 | 功能 |
|------|------|------|
| `search-memory` | query | 在工作区向量数据库中搜索相关信息 |
| `store-memory` | content | 将内容存入工作区（去重保护） |

- 使用工作区配置的嵌入器
- store-memory 写入 `agent-memory.txt`
- 支持去重器防止重复存储

### 2. Summarize（文档总结插件）
**文件**: `plugins/summarize.js`

| 工具 | 参数 | 功能 |
|------|------|------|
| `list-documents` | - | 列出工作区所有文档（名称、大小、类型、页数、日期） |
| `summarize-document` | filename | 总结指定文档内容 |

- 使用 LangChain map_reduce 链进行总结
- 大文档自动分割（10000 字符块，500 字符重叠）
- 检查 token 数决定是否总结（或返回截断预览）
- 支持 agentAllowlist 文件夹过滤

### 3. Web Browsing（网页搜索插件）
**文件**: `plugins/web-browsing.js` (1183 行)

| 工具 | 参数 | 功能 |
|------|------|------|
| `web-search` | query | 执行网络搜索 |

**支持 11 种搜索引擎**：

| 引擎 | 需要配置 | 特点 |
|------|----------|------|
| SerpApi | `SERPAPI_API_KEY` | getjson 端点 |
| SearchApi | `SEARCHAPI_API_KEY` | api.searchapi.io |
| Serper.dev | `SERPER_API_KEY` | google.serper.dev |
| Bing Web Search | `BING_SEARCH_API_KEY` | api.bing.microsoft.com |
| Baidu Search | `BAIDU_API_KEY/SECRET` | 百度 API |
| Serply.io | `SERPLY_API_KEY` | api.serply.io |
| SearXNG | `SEARXNG_BASE_URL` | 自托管实例 |
| Tavily | `TAVILY_API_KEY` | api.tavily.com |
| DuckDuckGo | 无需 Key | HTML 抓取，cheerio 解析 |
| Exa | `EXA_API_KEY` | api.exa.ai |
| Perplexity | `PERPLEXITY_API_KEY` | Sonar API |

- 搜索结果自动注册为 AI 引文
- 优先使用配置的引擎，否则回退到 DuckDuckGo

### 4. Web Scraping（网页抓取插件）
**文件**: `plugins/web-scraping.js`

| 工具 | 参数 | 功能 |
|------|------|------|
| `web-scraper` | url | 抓取网页内容 |

- 通过 CollectorApi 服务抓取
- 大内容自动总结
- 30 秒超时
- 自动注册引文

### 5. Rechart（图表可视化插件）
**文件**: `plugins/rechart.js`

| 工具 | 参数 | 功能 |
|------|------|------|
| `create-visualization` | chartType, title, data, dataKeys, xAxisKey | 创建图表 |

**支持 10 种图表类型**: area, bar, line, composed, scatter, pie, radar, radialBar, treemap, funnel

- 标记为 `unique`（每次对话仅一次）
- 通过 `_replySpecialAttributes` 存储图表配置
- 发送 `rechartVisualize` socket 事件到前端

### 6. Filesystem（文件系统插件）
**文件**: `plugins/filesystem/`（10 个子工具）

| 子工具 | 功能 |
|--------|------|
| `read-text-file` | 读取文本文件 |
| `read-multiple-files` | 批量读取文件 |
| `write-text-file` | 写入文本文件 |
| `edit-file` | 编辑文件（diff 补丁模式） |
| `list-directory` | 列出目录内容 |
| `create-directory` | 创建目录 |
| `copy-file` | 复制文件 |
| `move-file` | 移动文件 |
| `search-files` | 搜索文件（ripgrep） |
| `get-file-info` | 获取文件信息 |

- 所有操作限制在 `AGENT_FILESYSTEM_PATHS` 环境变量指定的路径内
- 路径遍历保护
- 需 Agent 技能启用 + 路径配置

### 7. Create Files（文件创建插件）
**文件**: `plugins/create-files/`（5 个子工具）

| 子工具 | 输出格式 | 依赖 |
|--------|----------|------|
| `create-text-file` | .txt | 原生 fs |
| `create-docx-file` | .docx | officegen |
| `create-pdf-file` | .pdf | pdfkit |
| `create-pptx-file` | .pptx | pptxgenjs |
| `create-xlsx-file` | .xlsx | exceljs |

- 文件名安全化处理（`parseFilename()`）
- 文件存储在 `storage/plugins/agent-create-files/`
- MIME 类型映射输出
- 需 Agent 技能启用 + 存储目录可写

### 8. SQL Agent（数据库查询插件）
**文件**: `plugins/sql-agent/`（4 个子工具 + 3 连接器）

| 子工具 | 功能 |
|--------|------|
| `query` | 执行 SQL 查询 |
| `list-database` | 列出数据库 |
| `list-table` | 列出表 |
| `get-table-schema` | 获取表结构 |

**数据库连接器** (`SQLConnectors/`):
- **PostgreSQL**: `pg` 包，连接字符串配置
- **MySQL**: `mysql2` 包，连接池
- **MSSQL**: `mssql` 包

### 9. Gmail（Gmail 邮件插件）
**文件**: `plugins/gmail/`（14 个子工具）

| 类别 | 工具 |
|------|------|
| 账户 | `gmail-get-mailbox-stats` |
| 草稿 | create, get, list, update, delete, send |
| 搜索 | search, get-inbox, read-thread |
| 发送 | send-email, reply-to-thread |
| 线程 | mark-read, mark-unread, move-to-archive, move-to-inbox, move-to-trash |

- 通过 Gmail OAuth 2.0 认证
- 使用 Google APIs Node.js 客户端

### 10. Outlook（Outlook 邮件插件）
**文件**: `plugins/outlook/`（10 个子工具）

| 类别 | 工具 |
|------|------|
| 账户 | `outlook-get-mailbox-stats` |
| 草稿 | create, list, update, delete, send |
| 搜索 | search, get-inbox, read-thread |
| 发送 | send-email |

- 通过 Microsoft Graph API OAuth 认证

### 11. Google Calendar（Google 日历插件）
**文件**: `plugins/google-calendar/`（9 个子工具）

| 类别 | 工具 |
|------|------|
| 日历 | list-calendars, get-calendar |
| 事件 | create, get, list-for-day, list-upcoming, update, quick-add |
| 状态 | set-my-status |

- 通过 Google Calendar OAuth 2.0 认证

### 12. 其他插件

| 插件 | 文件 | 功能 |
|------|------|------|
| CLI | `plugins/cli.js` | 命令行交互（仅示例） |
| File History | `plugins/file-history.js` | 文件历史持久化（示例） |

## 技能白名单系统

**文件**: `server/models/agentSkillWhitelist.js`

- 管理员可配置哪些工具自动批准（无需用户确认）
- 支持 `AGENT_AUTO_APPROVED_SKILLS` 环境变量
- `<all>` 值自动批准所有技能

## 默认技能配置

**文件**: `server/utils/agents/defaults.js`

- 始终启用的技能：memory, document-summarizer, web-scraping
- 从 SystemSettings 加载额外配置的技能
- `SKILL_FILTER_CONFIG` 定义每个技能的可用性检查
