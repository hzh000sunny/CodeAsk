# 10 — Agent 流程执行器

## 概述

Agent Flows 是预定义的多步骤工作流，通过 JSON 定义一系列处理步骤（开始、API 调用、LLM 指令、网页抓取），可以作为 @agent 的工具使用。

## 流程存储

- 路径: `storage/plugins/agent-flows/`
- 格式: JSON 文件，文件名 = UUID

## 流程结构

```json
{
  "uuid": "流程唯一标识",
  "name": "流程名称",
  "description": "流程描述",
  "enabled": true,
  "blocks": [
    { "type": "START", ... },
    { "type": "API_CALL", ... },
    { "type": "LLM_INSTRUCTION", ... },
    { "type": "WEB_SCRAPING", ... }
  ]
}
```

## 四种流程块类型

### 1. START — 初始化块
| 参数 | 说明 |
|------|------|
| `output_variable_name` | 输出变量名 |
| `input_type` | manual / text（从聊天提取） |
| `value` | 初始值 |

### 2. API_CALL — HTTP 请求块
| 参数 | 说明 |
|------|------|
| `url` | API 端点 |
| `method` | GET / POST / PUT / PATCH / DELETE |
| `headers` | 请求头对象 |
| `body` | JSON 或 Form-encoded 请求体 |
| `queryParams` | URL 查询参数 |
| `sslVerification` | SSL 证书验证（可选关闭） |
| `output_variable_name` | 存储响应的变量名 |

### 3. LLM_INSTRUCTION — LLM 处理块
| 参数 | 说明 |
|------|------|
| `provider` | LLM 提供商 |
| `model` | 模型名称 |
| `instruction` | 系统提示（描述如何处理输入） |
| `input_variable_name` | 输入变量名 |
| `output_variable_name` | 输出变量名 |
| `temperature` | LLM 温度 |

### 4. WEB_SCRAPING — 网页抓取块
| 参数 | 说明 |
|------|------|
| `url` | 抓取 URL（支持变量替换） |
| `output_variable_name` | 输出变量名 |
| `directOutput` | 如果为 true，直接返回抓取内容并停止流程 |

## 变量系统

### 变量替换
所有字符串参数支持 `${variableName}` 模式替换：
```javascript
// 点标记法支持嵌套对象
`${response.choices[0].text}`
```

### 变量来源
- START 块定义的初始变量
- API_CALL 的响应数据
- LLM_INSTRUCTION 的处理结果
- WEB_SCRAPING 的内容
- 用户调用时传入的变量

## AgentFlows 类

**文件**: `server/utils/agentFlows/index.js` (289 行)

### CRUD 操作
- `loadFlow(uuid)`: 从文件系统加载流程
- `saveFlow(uuid, flow)`: 保存流程（验证所有块类型）
- `listFlows()`: 列出所有流程（含摘要统计）
- `deleteFlow(uuid)`: 删除流程

### 执行与插件化
- `executeFlow(uuid, variables)`: 加载流程 → 创建 FlowExecutor → 执行
- `activeFlowPlugins()`: 返回所有启用流程的 `@@flow_{uuid}` 标识符
- `loadFlowPlugin(uuid)`: 将流程转换为 aibitat 兼容插件，
  - 净化工具名称（非字母数字 → 下划线，最长 64 字符）
  - 插件函数调用 `FlowExecutor.executeFlow()`

## FlowExecutor 类

**文件**: `server/utils/agentFlows/executor.js` (236 行)

### 执行流程
1. 合并传入的变量到状态
2. 按顺序迭代每个步骤
3. 对每个步骤执行 `executeStep()`
4. 支持提前终止（`directOutput: true`）

### 步骤执行
- 根据步骤类型路由到对应执行器
- 执行前对所有参数进行变量替换
- 结果存储在变量状态中

### 变量路径解析
`getValueFromPath(obj, path)` 支持深层嵌套路径：
```javascript
"response.choices[0].text" → obj.response.choices[0].text
```

## 步骤执行器

### api-call.js
- 使用 axios 发起 HTTP 请求
- 动态方法选择（GET/POST/PUT/PATCH/DELETE）
- 支持 JSON 和 Form-encoded 请求体
- SSL 验证可配置（自签名证书场景）

### llm-instruction.js
- 使用 `Provider.LangChainChatModel()` 创建模型
- 系统消息 = 指令，用户消息 = 输入变量内容
- 返回 LLM 处理结果

### web-scraping.js
- 使用 `CollectorApi` 抓取内容
- 支持 `directOutput` 提前终止流程

## API 端点

| 路由 | 方法 | 功能 |
|------|------|------|
| `/agent-flows/save` | POST | 创建或更新流程 |
| `/agent-flows/list` | GET | 列出所有流程 |
| `/agent-flows/:uuid` | GET | 获取单个流程 |
| `/agent-flows/:uuid` | DELETE | 删除流程 |
| `/agent-flows/:uuid/toggle` | POST | 切换启用/禁用 |

## 与 Agent 系统集成

Agent Flow 作为标准 aibitat 插件加载：
- 插件名称: `@@flow_{uuid}`
- 工具函数接收用户输入作为变量
- 执行流程的步骤序列
- 返回最终输出给 Agent
