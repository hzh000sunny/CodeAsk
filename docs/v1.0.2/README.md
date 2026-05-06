# CodeAsk 文档 — v1.0.2

| 字段 | 值 |
|---|---|
| 版本 | v1.0.2 |
| 状态 | Draft |
| 主题 | LLM Agent 会话运行时优化 |
| 基线版本 | `../v1.0.1/` |
| 目标 | 将默认 Agent 会话从固定调查流水线调整为正常聊天优先、RAG 增强、工具调用由模型决策的统一运行时 |

## 版本定位

v1.0.2 是 CodeAsk 的 LLM Agent 优化专项版本。

v1.0.1 已完成独立 LLM Wiki 工作台，补齐了团队知识的维护和引用基础。v1.0.2 的重点不是继续扩展 Wiki 管理界面，而是修正 Agent 会话的默认行为：CodeAsk 首先应该是一个正常的研发 Agent，会围绕用户当前问题多轮沟通；Wiki、报告、附件和代码检索是模型可调用的增强能力，而不是后端强制执行的固定流程。

本版本采用 `v1.0.2`，语义是：

> 在 v1.0 主产品方向和 v1.0.1 Wiki 基础设施不变的前提下，修正 Agent 默认会话运行时。

## 当前记录

| 文件 | 说明 |
|---|---|
| `specs/agent-chat-runtime.md` | v1.0.2 Agent Chat Runtime 头脑风暴收敛后的设计快照 |
| `specs/claude-code-reference-notes.md` | Claude Code 源码和学习资料的参考分析，提炼适合 CodeAsk 的 harness 设计借鉴点 |

后续进入实施规划后，应继续补齐：

| 文件 | 说明 |
|---|---|
| `prd/agent-chat.md` | v1.0.2 Agent 会话产品契约 |
| `design/agent-chat-runtime.md` | v1.0.2 Agent Chat Runtime 系统设计 |
| `plans/agent-chat-runtime.md` | v1.0.2 实施计划 |
| `plans/acceptance-checklist.md` | v1.0.2 验收清单 |

## 已确认方向

- 默认会话回归正常 Agent 聊天，不再让每条用户消息强制走完整调查闭环。
- 每轮默认执行轻量 Wiki / 报告 / 特性候选召回，并作为上下文注入模型。
- RAG 召回只提供候选证据，不产生“范围判断”“充分性判断”“下一步代码调查”等后端流程结论。
- 模型基于上下文和工具能力决定下一步动作：回答、追问、查 Wiki、读报告、读附件或查代码。
- 代码读取是默认只读能力；真正需要处理的是仓库范围和代码版本不明确时的追问或不确定性标注。
- 特性是候选上下文，不是用户提问前必须绑定的条件。
- 会话 UI 的右侧调查区改为可折叠 Agent 行动轨迹，只展示真实发生的动作和证据。
- 报告生成、写入 Wiki、删除 Wiki 等写操作仍然需要用户确认或明确 UI 动作。

## 推荐阅读顺序

1. `specs/agent-chat-runtime.md`
2. `specs/claude-code-reference-notes.md`
3. `../v1.0.1/README.md`
4. `../v1.0/design/agent-runtime.md`
5. `../v1.0/design/llm-gateway.md`
6. `../v1.0/design/wiki-search.md`
7. `../v1.0/design/frontend-workbench.md`
