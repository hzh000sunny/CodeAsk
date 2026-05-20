# 21 — 测试系统

## 概述

使用 Jest 29 作为测试框架，覆盖模型层、工具函数、Agent 系统和向量数据库。

## 测试目录结构

```
server/__tests__/
├── models/
│   ├── systemPromptVariables.test.js
│   └── user.test.js
└── utils/
    ├── agentFlows/
    ├── agents/
    │   └── aibitat/
    │       └── providers/
    │           └── helpers/
    ├── chats/
    ├── helpers/
    ├── safeJSONStringify/
    ├── SQLConnectors/
    ├── TextSplitter/
    └── vectorDbProviders/
        └── pgvector/
```

## 测试覆盖范围

### 模型测试
- `systemPromptVariables.test.js`: 系统提示变量展开逻辑
- `user.test.js`: 用户模型（创建、验证、密码复杂度、角色）

### Agent 测试
- aibitat Provider 测试
- Provider helpers（Tooled/UnTooled）
- Agent Flow 执行器

### 聊天测试
- 聊天流程单元测试
- 消息压缩测试

### 工具函数测试
- `helpers/`: 核心工具函数测试
- `safeJSONStringify/`: JSON 序列化测试
- `TextSplitter/`: 文本分割测试

### 数据库测试
- `SQLConnectors/`: SQL 连接器测试
- `vectorDbProviders/pgvector/`: PGVector 专项测试

## 运行测试

```bash
# 根目录
yarn test

# 等同于
jest
```

## 测试配置

- 框架: Jest 29.7.0
- 测试文件命名: `*.test.js`
- 测试环境: Node.js
