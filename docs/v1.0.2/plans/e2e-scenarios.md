# v1.0.2 Agent Chat Runtime E2E 场景矩阵

> 状态：Draft
> 版本：v1.0.2
> 范围：默认 Agent 会话、连续上下文、工具行动轨迹、Feature-Scoped Code Access、RAG / Wiki / 报告 / 附件、停止回滚、长上下文压缩

## 0. 目标

本文承载 v1.0.2 后续开发阶段必须持续维护的 E2E 场景矩阵。它不是替代 `acceptance-checklist.md`，而是把每个核心用户路径展开成可执行的端到端验收脚本。

每个场景必须能回答：

- 前端是否真实可用。
- 后端是否真实持久化 / 回滚 / 恢复。
- 模型实际收到的上下文是否正确。
- 行动轨迹是否能解释发生了什么。
- 刷新、切换、删除、停止等状态变化后是否仍一致。

## 1. 当前能力总览

### 1.1 已完成或已有回归基础

- [x] 默认会话走 `ChatRuntime`。
- [x] 普通问答不强制旧固定调查流程。
- [x] 连续会话会加载最近 turns。
- [x] 连续会话会加载上一轮关键工具行动摘要。
- [x] 行动轨迹按真实 runtime 事件展示。
- [x] 同一会话发送新消息时行动轨迹不清空历史。
- [x] 生成中可以停止。
- [x] 停止后前端本轮 user message、partial assistant message、临时行动轨迹回滚。
- [x] 停止后显式 abort API 回滚持久化 turn / traces。
- [x] abort 后迟到 assistant turn 和迟到 trace 不再写入历史。
- [x] 工具结果进入模型前有预算裁剪。
- [x] 上下文超限时有 reactive compact retry。
- [x] 基础问答 30 题已有 live E2E 通道。
- [x] 源码工具和连续追问已有 live E2E 通道。
- [x] 特性上下文中的插入式技术问答已有 live E2E 通道，覆盖会话围绕 AnythingLLM 展开时，中途询问 `lancedb 和 sqlitedb 有什么区别` 仍应优先直接回答。

### 1.2 部分完成，必须继续收敛

- [x] 生产代码工具已从全局 ready 仓库池收敛为“特性范围仓库池 + 用户显式仓库范围”，已有后端集成测试覆盖。
- [x] Feature RAG Pack 第一版已接入生产 `ChatRuntime`，模型 messages 中可见候选特性、Wiki / 报告和关联仓库摘要。
- [x] `claude-code` / `anything-llm` 参考仓库已可用于源码工具链路验证；Feature-Scoped Code Access live E2E 通道已在真实 GLM-5.1 / OpenAI 协议配置下执行通过。
- [x] 长会话 micro compact 已实现；会话级 `conversation_summary` / auto compact 第一版已落地 extractive 持久化摘要。
- [x] Wiki 工作台能力已较完整，默认 Agent 生产 Wiki 工具已接入。

### 1.3 未完成

- [x] Feature-Scoped Code Access 浏览器 / live LLM E2E 已执行通过：`frontend/e2e/agent-feature-scoped-code-live.spec.ts`。
- [x] 显式仓库范围 `explicit_user_repo` 前端细节展示已有组件测试覆盖；live E2E 仍需补齐。
- [x] 生产 Wiki 工具已接入默认 `ChatToolRegistry`，已有后端集成测试覆盖。
- [x] 生产报告工具已接入默认 `ChatToolRegistry`，已有后端集成测试覆盖。
- [x] 生产附件工具已接入默认 `ChatToolRegistry`，已有后端集成测试覆盖会话隔离和重命名映射。
- [x] RAG 来源已在后端候选注入层按 `document_id` / `report_id` 做基础去重；工具结果进入模型前有预算裁剪，UI sources 只展示摘要、引用和 trace 详情。
- [x] 会话级 `conversation_summary` 第一版。
- [x] 历史 auto compact 第一版。
- [x] SSE error 前端统一提示；运行时错误会进入 assistant 错误气泡并显示顶部提示，已有前端组件测试覆盖。

## 2. 推荐新增 E2E 文件

建议新增以下 Playwright E2E：

```text
frontend/e2e/feature-scoped-code-access.spec.ts
frontend/e2e/explicit-repo-code-access.spec.ts
frontend/e2e/session-stop-rollback-live.spec.ts
frontend/e2e/agent-wiki-tools-live.spec.ts
frontend/e2e/agent-attachments-live.spec.ts
frontend/e2e/agent-report-tools-live.spec.ts
frontend/e2e/long-context-compact-live.spec.ts
```

现有 E2E 通道继续保留：

```text
frontend/e2e/admin-agent-source-live.spec.ts
frontend/e2e/agent-conversation-continuity-live.spec.ts
frontend/e2e/agent-contextual-technical-qa-live.spec.ts
frontend/e2e/basic-model-qa-live.spec.ts
frontend/e2e/happy-path.spec.ts
frontend/e2e/route-refresh.spec.ts
frontend/e2e/wiki-import.spec.ts
frontend/e2e/wiki-tail.spec.ts
```

## 3. 场景矩阵

### E2E-001 基础问答直答能力

目标：验证普通问题不被扩展成固定调查流程。

前置：

- 管理员已配置可用 LLM。
- 新建一个普通会话。

步骤：

1. 发送 `Python 中 list 和 tuple 的区别是什么？`
2. 继续发送 `什么是浅拷贝和深拷贝？`
3. 刷新页面。
4. 追问 `你刚刚解释了哪两个 Python 概念？`

验收：

- 回答自然、直接。
- 不展示 `范围判断`、`充分性判断`、`insufficient`、`下一步：代码调查`。
- 行动轨迹不出现无意义代码检索。
- 刷新后仍能回答上一轮上下文。
- 模型不能回答成“这是第一次交流”。

覆盖建议：

- live E2E：`frontend/e2e/basic-model-qa-live.spec.ts`。
- API + spy LLM：断言第二轮 messages 包含上一轮 user / assistant。

### E2E-002 连续会话工具行动可追问

目标：验证模型知道上一轮是否查过代码，并能区分列仓库、搜索代码、读取源码。

步骤：

1. 发送 `通过 anything-llm 仓库查一下 processSingleFile 是怎么处理上传资料的。`
2. 等待 Agent 完成代码工具调用。
3. 追问 `你刚刚有查询代码吗？区分列仓库、搜索代码、读取源码。`
4. 刷新页面。
5. 追问 `上一轮你说了什么？`

验收：

- 第一轮行动轨迹包含 `list_code_repos`、`search_code`、`read_code_file`。
- 第二轮回答能区分三类代码行为。
- 第三轮刷新后仍能复述上一轮内容。
- spy LLM 断言实际 messages 包含历史和工具行动摘要。

已有通道：

- `frontend/e2e/agent-conversation-continuity-live.spec.ts`
- `tests/integration/test_agent_chat_runtime.py`
- `tests/integration/test_agent_chat_runtime_sse.py`

### E2E-003 生成中断彻底回滚

目标：验证停止生成后 UI、DB、行动轨迹和模型上下文都回滚干净。

步骤：

1. 先完成一轮回答：`介绍 claude-code 里的 dragon buddy。`
2. 发送 `换一种。`
3. 在生成中点击停止。
4. 刷新页面。
5. 追问 `我刚刚让你介绍了几种宠物？`

验收：

- UI 不显示 `换一种` 这轮 user message。
- UI 不显示 partial assistant message。
- 行动轨迹不显示这一轮 trace。
- DB 中没有该轮 user turn、assistant turn、agent traces。
- 模型回答只基于停止前历史，例如“只介绍了一种”。
- 后端迟到完成的 assistant turn 不得写入 DB。

已有覆盖：

- `tests/integration/test_sessions_api.py`

需补：

- 浏览器级停止 + 刷新 + 追问 E2E。

### E2E-004 删除会话全链路清理

目标：验证删除会话后消息、附件、行动轨迹、存储目录都被清理。

步骤：

1. 创建会话。
2. 上传附件。
3. 发送一轮触发行动轨迹的问题。
4. 删除会话。
5. 刷新页面。
6. 检查 API 和存储目录。

验收：

- 会话列表移除。
- 当前聊天窗口清空。
- 右侧行动轨迹清空。
- 会话附件目录删除。
- 查询该 session 返回 404 或空。
- 不影响其他会话。

### E2E-005 Feature-Scoped 单特性代码检索

目标：验证模型选择单个特性后，代码工具只读取该特性关联仓库。

前置：

- 创建 `Claude Code` 特性。
- 将 `references/claude-code/claude-code` 仓库关联到该特性。
- Feature RAG Pack 能提供 `Claude Code` 特性摘要和关联仓库摘要。

步骤：

1. 用户问 `claude code 里面有实现 TUI 电子宠物功能吗？`
2. 模型选择 `Claude Code` 特性。
3. Agent 调用代码工具搜索 / 读取源码。
4. 输出回答。

验收：

- 工具调用带 `feature_ids`。
- `list_code_repos` 只返回 `Claude Code` 特性关联仓库。
- `search_code` / `read_code_file` 只读取该仓库。
- 行动轨迹显示候选特性、最终选择特性、允许仓库。
- 回答包含源码路径和版本提示。

自动化基础：

- 后端集成测试已覆盖特性关联仓库范围允许检索。
- runtime spy LLM 测试已覆盖 Feature RAG Pack 注入。

### E2E-006 Feature-Scoped 交叉特性代码检索

目标：验证模型可同时选择多个特性，并访问这些特性仓库并集。

前置：

- `Claude Code` 特性关联 claude-code 仓库。
- `CodeAsk` 特性关联 CodeAsk 仓库。

步骤：

1. 用户问 `claude code 的工具权限设计，怎么借鉴到 CodeAsk 的工具体系？`
2. 模型选择 `Claude Code` 和 `CodeAsk` 两个特性。
3. 分别检索两个仓库。
4. 输出对比分析。

验收：

- 允许仓库 = 两个特性关联仓库并集。
- 代码工具不能访问第三个无关仓库。
- 行动轨迹标注交叉特性。
- 回答区分两个仓库的证据来源。

### E2E-006A 特性上下文中的插入式技术问答

目标：验证会话保持在特性主题内时，用户中途提出通用技术概念问题，模型能结合当前语境直接回答，而不是每一问都强制查 Wiki 或代码。

前置：

- 创建 `AnythingLLM` 相关特性。
- 将 `references/anything-llm` 仓库关联到该特性。
- 会话前几轮围绕 AnythingLLM / RAG / 召回展开。

步骤：

1. 用户问 `anything llm 是如何处理召回的？`
2. 用户插入技术问题：`lancedb 和 sqlitedb 有什么区别？`
3. 用户追问：`那放回刚才的 AnythingLLM / RAG 语境里，它们通常分别适合承担什么角色？`
4. 用户明确要求源码确认：`如果要确认 AnythingLLM 源码里具体有没有使用 sqlite 或 better-sqlite3，现在可以根据这个特性关联的仓库查一下代码。`

验收：

- 第 1 轮应围绕 AnythingLLM / RAG / 召回回答，可由模型直接回答，也可少量使用 Wiki / 代码工具。
- 第 2 轮应直接解释 LanceDB 与 SQLite 的区别，不要求用户重新确认特性，不要求用户显式指定仓库。
- 第 2 轮和第 3 轮不应频繁触发代码工具；允许少量模型工具决策偏差，但不能把概念插问变成完整源码调查。
- 第 3 轮应保留 AnythingLLM / RAG 会话语境，说明向量检索、embedding、元数据和关系型存储等角色差异。
- 第 4 轮用户明确要求源码确认后，应允许进入特性关联仓库代码检索，并返回具体路径。
- 任一轮都不能回答成“第一次交流”“无法跨对话”“请指定仓库”。

覆盖通道：

- `frontend/e2e/agent-contextual-technical-qa-live.spec.ts`

### E2E-007 无特性、无显式仓库时拒绝代码检索

目标：验证 Agent 不能从全局仓库池随便搜。

前置：

- 全局仓库池存在 claude-code、anything-llm。
- 当前没有候选特性或候选特性没有关联仓库。

步骤：

1. 用户问 `这个功能是不是有个电子宠物？`
2. 用户没有明确说仓库名。
3. 模型若尝试代码工具，工具返回 `needs_feature_scope`。

验收：

- 不能列出全部全局仓库。
- 不能直接搜索 claude-code。
- 模型应追问或说明需要更多特性 / 仓库线索。
- 行动轨迹显示 `needs_feature_scope`，不是内部错误。

自动化基础：

- 后端集成测试已覆盖无 `feature_ids` 且无 `explicit_repo_scope` 时，`list_code_repos` / `search_code` 返回 `needs_feature_scope`。

### E2E-008 用户显式仓库范围允许检索

目标：验证用户明确指定仓库时，即使仓库没有关联特性，也允许读取。

前置：

- 全局仓库池存在 `claude-code`。
- `claude-code` 不关联任何特性。

步骤：

1. 用户问 `请通过 claude-code 仓库查一下有没有 TUI 电子宠物功能。`
2. 模型使用显式仓库范围。
3. 调用 `search_code` / `read_code_file`。
4. 输出回答。

验收：

- 工具结果包含 `scope_source=explicit_user_repo`。
- 行动轨迹显示“用户显式仓库”。
- 允许读取该仓库。
- 回答带版本提示。
- 不要求用户先创建特性。

自动化基础：

- 后端集成测试已覆盖 `explicit_repo_scope=true` 时可检索和读取未关联特性的全局 ready 仓库。

### E2E-009 repo 命中但越界 / 模糊匹配拒绝

目标：验证全局仓库不能被模型自己模糊选中绕过范围。

前置：

- 全局仓库池存在 `anything-llm`。
- 当前候选特性只关联 `CodeAsk` 仓库。

步骤：

1. 用户问一个没有明确指定 anything-llm 的问题。
2. 模型尝试 `repo_name=anything-llm`。
3. 工具执行 scope 校验。

验收：

- 返回 `out_of_scope` 或要求澄清。
- 行动轨迹显示范围错误。
- 模型不能继续读取该仓库源码。
- 用户后续明确说“就查 anything-llm 仓库”后，才能走显式仓库范围。

自动化基础：

- 后端集成测试已覆盖 repo 存在但不属于当前特性范围时返回 `out_of_scope`。

### E2E-010 Wiki 工具生产接入

目标：验证模型能搜索 / 读取 Wiki，并引用证据。

步骤：

1. 创建特性。
2. 导入 Wiki 文档和图片资源。
3. 用户问 Wiki 中已有答案的问题。
4. 模型调用 Wiki 工具。
5. 回答引用 Wiki 证据。

验收：

- 工具只读取 Wiki，不默认查代码。
- Markdown / 图片引用预览正常。
- 行动轨迹展示 Wiki evidence refs。
- 刷新后行动轨迹和回答可恢复。
- 模型上下文只注入 snippet，不注入全文。

### E2E-011 问题报告工具生产接入

目标：验证模型能引用已验证问题报告，而不是静默创建报告。

步骤：

1. 准备一个已验证问题报告。
2. 用户问相似问题。
3. 模型调用报告搜索 / 读取工具。
4. 回答引用报告。

验收：

- 只读报告，不静默创建报告。
- 报告状态必须可引用。
- 行动轨迹显示报告证据。
- 用户手动生成报告仍走确认流程。

### E2E-012 附件工具生产接入与隔离

目标：验证附件只属于当前会话，并且重命名映射保持正确。

步骤：

1. 会话 A 上传两个同名日志。
2. 重命名其中一个。
3. 会话 B 上传另一个文件。
4. 在会话 A 提问日志内容。
5. 模型调用附件工具。

验收：

- 只能看到会话 A 附件。
- 本轮实际 LLM messages 中必须包含会话 A 的附件候选，而不是只依赖前端附件列表。
- 同名文件能区分。
- 重命名后模型可通过用户口语化名称映射到真实文件。
- 删除附件后不能再被模型读取。
- 切换会话不串附件。

### E2E-013 RAG 来源去重与预算

目标：验证同一文档不会产生大量重复来源。

步骤：

1. 导入一个较长 Wiki 文档。
2. 提问命中文档多个 chunk 的问题。
3. 查看回答来源和行动轨迹。

验收：

- 同一文档来源合并展示。
- 模型上下文中 chunk 数量受预算限制。
- 不再出现同一文档十几个重复来源。
- 不触发 input length 超限。

### E2E-014 上下文超限 reactive compact

目标：验证长工具结果不会导致整轮失败。

步骤：

1. 准备可产生大量搜索结果的仓库。
2. 用户问一个会触发多次搜索的问题。
3. 工具返回大结果。
4. 模型请求接近或超过上下文限制。

验收：

- 工具结果进入模型前被裁剪。
- 若供应商返回 context length 错误，runtime 执行一次 reactive compact retry。
- retry 后能回答。
- 行动轨迹显示结果截断 / 压缩摘要。
- 不把内部异常直接展示给用户。

### E2E-015 会话级 Auto Compact

目标：未来实现 `conversation_summary` 后的端到端验收。

步骤：

1. 连续多轮长对话。
2. 多次工具调用。
3. 触发 auto compact。
4. 刷新页面。
5. 追问历史事实和工具行动。

验收：

- summary 进入实际 LLM messages。
- recent turns 不和 summary 大量重复。
- 模型知道当前任务状态。
- 模型知道历史工具是否读取代码。
- 删除会话清理 summary。

当前状态：未实现。

### E2E-016 SSE 错误前端提示

目标：验证运行错误不会静默失败。

步骤：

1. 模拟 LLM 返回 error event。
2. 模拟工具返回 `internal_error`。
3. 模拟网络断开。
4. 前端展示错误。

验收：

- 聊天消息中显示明确错误。
- 行动轨迹中对应事件为失败。
- 成功提示使用轻量 toast。
- 失败提示使用明显错误框或弹窗。
- 用户能继续下一轮输入。

### E2E-017 登录 / 管理员 / 全局配置

目标：验证 admin 才能看到全局 LLM / 仓库 / 策略。

步骤：

1. 未登录访问。
2. 登录 admin。
3. 访问设置。
4. 添加 LLM、仓库、策略。
5. 退出登录。
6. 再访问设置。

验收：

- 未登录只看到登录入口。
- admin 可见全局配置。
- 非 admin 不可见全局配置。
- LLM 配置失败有错误提示。
- 仓库同步失败有错误提示。
- 全局仓库只作为配置池，不直接等于 Agent 默认可读范围。

### E2E-018 Wiki 导入目录

目标：验证 Wiki 目录导入、资源引用、冲突处理。

已有通道：

- `frontend/e2e/wiki-import.spec.ts`
- `frontend/e2e/wiki-import-live.spec.ts`
- `frontend/e2e/wiki-tail.spec.ts`
- `frontend/e2e/wiki-tail-live.spec.ts`

验收：

- 只上传 Markdown 及其相对引用资源。
- `<img src="...">` 图片能上传和渲染。
- 二次上传冲突支持全部覆盖 / 全部跳过。
- 文件级进度条正确。
- 已忽略列表可查看。
- 导入到某目录时，不额外创建一层根目录。
- 文档可预览、编辑、删除、排序。

### E2E-019 路由刷新

目标：验证刷新不回到会话首页。

已有通道：

- `frontend/e2e/route-refresh.spec.ts`
- `frontend/e2e/route-refresh-live.spec.ts`

验收：

- `/wiki?...` 刷新仍在 Wiki 页面。
- `/settings` 刷新仍在设置页面。
- `/features` 刷新仍在特性页面。
- 会话页面刷新恢复当前会话、消息、行动轨迹。

### E2E-020 全链路参考仓库学习

目标：验证 `anything-llm` / `claude-code` 作为参考仓库的学习能力，同时遵守新的范围规则。

路径 A：特性关联路径。

1. 创建 `Claude Code` 特性。
2. 关联 claude-code 仓库。
3. 提问源码问题。
4. 验证 feature-scoped 检索。

路径 B：显式仓库路径。

1. 不关联特性。
2. 用户明确说 `通过 claude-code 仓库查询`。
3. 验证 `explicit_user_repo` 检索。

验收：

- 两条路径都能回答。
- 默认模糊路径不能绕过范围。
- 行动轨迹能区分 `feature_scope` 和 `explicit_user_repo`。

## 4. 执行优先级

1. 补 E2E-005 到 E2E-009 的浏览器 / live LLM 验收。
2. 优化行动轨迹中 `scope_source`、`feature_ids`、repo / ref / commit 的前端展示。
3. 补停止回滚浏览器级 E2E。
4. 做 RAG 来源去重和预算治理。
5. 实现会话级 auto compact。

## 5. 最低回归命令

每次修改 Agent runtime、工具、上下文、行动轨迹或会话持久化，至少执行：

```bash
uv run pytest tests/unit/chat_runtime -q
uv run pytest tests/integration/test_agent_chat_runtime.py tests/integration/test_agent_chat_runtime_sse.py -q
uv run pytest tests/integration/test_sessions_api.py -q
corepack pnpm --dir frontend test:run
corepack pnpm --dir frontend build
git diff --check
```

如果修改真实浏览器路径，还要执行对应 Playwright E2E。

如果修改模型上下文，必须增加或更新 spy LLM 测试，断言实际发送给模型的 `messages`。
