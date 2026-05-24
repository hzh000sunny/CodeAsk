# CodeAsk 文档

## 当前版本

[**v1.0.5**](./v1.0.5/) — Wiki 与代码仓 RAG（Draft；引入 OpenViking 作为统一上下文数据库，让 opencode 通过 OpenViking MCP 检索 Wiki / 问题报告 / 代码仓候选；OpenViking 集成边界已声明，无许可证前置门槛）

## 上一稳定版本

[**v1.0.4**](./v1.0.4/) — OpenCode Agent Backend 对接（Manual Acceptance Completed；引入 opencode 作为新会话默认 Agent 执行引擎，CodeAsk 负责知识、权限、审计、workspace 和 MCP 适配，自动化、真实浏览器和人工验收已完成）

进入版本目录后请先读该目录下的 `README.md`。

## 基线版本

[**v1.0**](./v1.0/) — MVP 初始版本（Completed；作为当前产品和后续专项版本的基础设计快照保留）

## 未来能力规划

[**future/**](./future/) — 尚未正式排入具体版本号、但需要长期保留的未来功能方向（Active；用于沉淀版本待定的产品与架构规划，避免设计在后续讨论中丢失）

## 已完成专项版本

[**v1.0.1**](./v1.0.1/) — LLM Wiki 专项（Completed；独立 Wiki 工作台、导入会话、报告投影、全局搜索、目录树排序和特性页轻量预览已收口）

[**v1.0.2**](./v1.0.2/) — LLM Agent 会话运行时优化（Completed；默认会话切换为正常聊天优先、RAG 增强、工具调用由模型决策的统一运行时）

[**v1.0.3**](./v1.0.3/) — 鉴权与访问控制（Completed；匿名会话、登录注册、admin、特性管理员、全局配置权限和真实数据升级验收已收口）

（v1.0.4 见上方"上一稳定版本"段落，承载 opencode Agent Backend 对接。）

## 历史版本

（暂无）

## 文档约定

文档目录结构、版本命名、bump 规则、引用路径等约定见 **[STRUCTURE.md](./STRUCTURE.md)**。

开发验收阶段、E2E 基线、Agent 连续会话验收和证据记录规则见 **[DEVELOPMENT_ACCEPTANCE.md](./DEVELOPMENT_ACCEPTANCE.md)**。

### 速查

```text
docs/
├── README.md          ← 本文件（顶层版本索引）
├── STRUCTURE.md       ← 文档约定的权威来源
├── DEVELOPMENT_ACCEPTANCE.md ← 项目级开发验收阶段与证据基线
├── rules/             ← 跨版本通用规则
├── future/            ← 版本待定的未来功能规划
├── v1.0/              ← MVP 基线版本（Completed）
│   ├── README.md      ← 该版本元信息
│   ├── prd/           ← PRD
│   ├── design/        ← SDD
│   ├── plans/         ← 实现计划（拆 SDD → 可执行 task）
│   └── specs/         ← 早期草稿 / 过程性产物
├── v1.0.1/            ← LLM Wiki 专项（Completed）
├── v1.0.2/            ← LLM Agent 会话运行时优化（Completed）
├── v1.0.3/            ← 鉴权与访问控制（Completed）
├── v1.0.4/            ← OpenCode Agent Backend 对接（Manual Acceptance Completed）
├── v1.0.5/            ← 当前版本：Wiki 与代码仓 RAG（Draft）
├── v1.1/              ← 未来 minor 演进（尚未创建）
└── v2.0/              ← 未来 major 演进（尚未创建）
```

### 关键原则（详见 STRUCTURE.md）

- **旧版本目录一律不就地覆盖**——保留为历史
- **未排版本但已形成稳定方向的规划**放入 `docs/future/`，不要混入正在交付的版本目录
- **跨版本通用规则**放入 `docs/rules/`，不要埋进某个单独版本目录
- **同版本内引用**用相对路径（如 `design/overview.md`）
- **跨版本引用**用 `../vN.M/...`
- **PRD vs SDD 冲突**永远以 PRD 为准
- **开发验收不能只看局部组件**——必须区分 UI 展示、数据库持久化、模型上下文、工具行动摘要和真实用户链路
- **E2E 端到端测试是每个开发验收阶段的基本要求**——版本验收清单必须记录核心路径、测试通道、运行方式和执行结果
- **Agent 连续会话必须单独验收**——同一会话追问时，模型必须能看到必要历史和上一轮工具行动摘要
- **基础模型能力评测必须沉淀为可重复基线**——通用问答、工具触发偏差、真实 LLM live 通道都应记录在对应版本文档中，避免只靠临时手工判断
