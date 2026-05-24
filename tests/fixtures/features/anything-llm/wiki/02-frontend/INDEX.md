# 02 — Frontend 前端

> React 18 + Vite 4 + TailwindCSS 3 SPA 管理界面

## 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18.2 | UI 框架 |
| Vite | 4.3 | 构建工具 |
| TailwindCSS | 3.3 | 样式框架 |
| React Router | 6.3 | 路由管理 |
| i18next | 23.11 | 国际化 |
| Tremor | 3.15 | UI 组件库 |
| Recharts | 2.12 | 图表可视化 |
| Phosphor Icons | 2.1 | 图标库 |

## 项目结构

```
frontend/src/
├── App.jsx                    # 根组件
├── AuthContext.jsx            # 认证上下文
├── main.jsx                  # 入口文件
├── components/
│   ├── ChatBubble/           # 聊天气泡组件
│   ├── DefaultChat/           # 默认聊天界面
│   ├── WorkspaceChat/         # 工作区聊天
│   ├── Sidebar/               # 侧边栏
│   ├── Modals/                # 模态框集合
│   ├── EmbeddingSelection/    # 嵌入提供商选择
│   ├── LLMSelection/          # LLM 提供商选择
│   ├── VectorDBSelection/     # 向量数据库选择
│   ├── AgentConfig/           # Agent 配置
│   ├── CommunityHub/          # 社区中心
│   ├── DataConnectorOption/   # 数据连接器选项
│   ├── contexts/              # React Context (TTS)
│   └── ...                    # 100+ 组件
├── pages/
│   ├── Login/                 # 登录页
│   ├── OnboardingFlow/        # 新手引导
│   ├── Admin/                 # 管理面板
│   ├── Settings/              # 系统设置
│   └── GeneralSettings/       # 通用设置
├── hooks/                     # 自定义 Hooks
├── utils/                     # 工具函数
└── locales/                   # 国际化翻译文件
```

## 主要功能模块

### 认证系统
- 多用户登录/注册
- 密码恢复流程
- SSO 支持（Simple SSO）
- 多因素恢复码
- 会话管理（JWT）

### 工作区管理
- 工作区 CRUD
- 自定义头像
- 系统提示词编辑
- 聊天模式配置（chat/query/automatic）
- LLM/Agent 提供商和模型选择
- 相似度阈值和 TopN 设置
- 向量搜索模式（default/rerank）

### 聊天界面
- 流式 SSE 响应
- 多线程聊天
- Agent 模式（WebSocket 实时通信）
- 文件上传（拖放 + 粘贴）
- 语音输入（Speech Recognition）
- 文本转语音（TTS）
- 聊天历史导出（JSON/CSV/JSONL/Alpaca）
- 用户反馈评分
- 代码语法高亮（highlight.js）
- LaTeX 数学公式渲染（KaTeX）

### 文档管理
- 文件浏览器（文件夹树）
- 拖放上传
- URL 抓取
- 原始文本输入
- 文档固定/取消固定
- 文档监视同步
- 多文件管理

### 系统设置
- LLM 提供商配置（35+ 选项）
- Embedding 引擎选择
- 向量数据库配置
- TTS 提供商设置
- 语音识别提供商
- 用户管理（多用户模式）
- Agent 技能管理
- 定时任务配置
- MCP 服务器管理
- Agent Flows 管理
- 嵌入组件管理
- 系统日志查看

### 社区中心
- 浏览社区共享资源
- 导入 Agent 技能
- 导入 Slash Commands
- 导入 System Prompts
- 导入 Agent Flows

### 国际化
- 多语言支持（i18next）
- 翻译验证和规范化工具
- 未使用翻译清理

## 状态管理

- React Context（认证、TTS）
- 本地组件状态
- URL 参数状态
- LocalStorage 持久化偏好

## 构建配置

- Vite 开发服务器（host: 0.0.0.0）
- PostCSS + Autoprefixer
- Rollup 打包分析（rollup-plugin-visualizer）
- 生产构建后脚本（`scripts/postbuild.js`）
