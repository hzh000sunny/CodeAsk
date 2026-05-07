# CodeAsk Agent 工具体系设计草案

> 日期：2026-05-07
> 状态：草稿，等待用户审阅
> 范围：基于 Claude Code 工具源码学习，翻译成 CodeAsk v1.0.2 自己的工具体系

## 1. 目标

本文不是复制 Claude Code 的工具实现，而是把它的工具工程模式翻译成适合 CodeAsk 的设计。

CodeAsk v1.0.2 要把默认会话从固定调查流水线改成正常 Agent 聊天。要做到这一点，工具不能再是散落在 service 里的函数，也不能继续被旧状态机当作固定阶段调用。工具必须成为模型可理解、后端可校验、前端可渲染、审计可回放的稳定能力单元。

一句话：

```text
工具是 CodeAsk Agent harness 的行动接口。
模型决定是否调用工具，后端保证工具调用安全、可控、可审计。
```

## 2. 从 Claude Code 工具源码得到的抽象

源码学习后，可以抽象出 Claude Code 工具体系的几个关键机制：

| 机制 | 含义 | CodeAsk 借鉴方式 |
|---|---|---|
| 工具注册表 | 所有工具集中注册，模型只看到当前可用工具 | 建立 `tool_registry.py`，统一导出 CodeAsk Agent 工具 |
| schema 校验 | 每个工具有严格输入 schema，模型参数错了也不会直接执行 | 每个工具使用 Pydantic / JSON Schema 定义输入输出 |
| 默认 fail-closed | 工具默认不是并发安全，默认不是只读，必须显式声明 | CodeAsk 工具默认保守，只有明确声明才可并发和默认读取 |
| 权限 / 边界校验 | 工具执行前经过路径、权限、模式、危险动作判断 | CodeAsk 做 repo、ref、session、wiki、权限和写操作确认 |
| 工具错误回传模型 | 工具失败变成结构化 tool result，让模型继续处理 | 不让工具错误直接打断整轮会话 |
| 结果预算 | 大结果截断、摘要、保存原始结果引用 | 工具摘要进入上下文，原始结果进审计存储 |
| 并发编排 | 连续只读工具可以并发，不安全工具串行 | v1.0.2 先保留契约，后续支持只读并发 |
| 用户交互工具 | 模型可调用工具向用户提问 | CodeAsk 用 `ask_user` 承载澄清和选择 |
| 按需知识工具 | Skill/策略不常驻全文，模型需要时加载 | CodeAsk 的分析策略和 Wiki 全文按需读取 |

这些机制的本质是：工具不是阶段，工具是模型可选择的行动。

## 3. CodeAsk 工具契约

建议 v1.0.2 引入统一工具契约。

### 3.1 ToolSpec

每个工具至少声明：

```text
name
description
input_schema
output_schema
read_only
concurrency_safe
requires_confirmation
requires_user_interaction
max_result_size_chars
```

字段含义：

| 字段 | 含义 |
|---|---|
| `name` | 模型调用的工具名，稳定且 kebab/snake 风格一致 |
| `description` | 给模型看的能力说明，说明什么时候用、什么时候不用 |
| `input_schema` | 工具输入 schema |
| `output_schema` | 工具输出 schema |
| `read_only` | 是否只读；只读工具默认允许模型调用 |
| `concurrency_safe` | 是否可以和其它同类只读工具并发 |
| `requires_confirmation` | 是否必须用户确认后执行 |
| `requires_user_interaction` | 是否会暂停等待用户输入 |
| `max_result_size_chars` | 进入模型上下文的结果最大字符数 |

默认值必须保守：

```text
read_only = false
concurrency_safe = false
requires_confirmation = true
requires_user_interaction = false
```

只有明确声明为只读的工具，才可以默认交给模型自由调用。

### 3.2 ToolResult

工具结果应统一为结构化对象：

```json
{
  "ok": true,
  "tool": "search_code",
  "summary": "在 codeask@main 命中 3 个文件",
  "items": [],
  "evidence_refs": [],
  "warnings": [],
  "truncated": false,
  "raw_result_ref": "tool_result_01H...",
  "version_info": {
    "repo": "codeask",
    "ref": "main",
    "commit": null,
    "status": "default_or_current"
  }
}
```

失败结果：

```json
{
  "ok": false,
  "tool": "read_code_file",
  "summary": "无法确定要读取的仓库",
  "error_type": "needs_clarification",
  "message": "当前会话没有明确 repo，候选特性也没有关联仓库。",
  "suggested_user_question": "你希望我查看哪个仓库？如果不清楚，我可以先按默认仓库和默认分支查看。"
}
```

关键原则：

- 模型上下文里放摘要、证据引用、警告和必要片段。
- 原始完整结果进入审计存储。
- 前端行动轨迹消费同一份结构化结果。
- 工具失败不是会话失败，除非发生不可恢复系统错误。

### 3.3 ToolErrorType

统一错误类型：

```text
invalid_input
not_found
out_of_scope
permission_denied
needs_clarification
version_unknown
too_large
transient_error
internal_error
```

错误类型要给模型可行动的信息，而不是只返回异常字符串。

## 4. v1.0.2 第一批工具

第一批工具只覆盖默认 Agent 会话必需能力，不扩展到多 agent、代码修改或复杂后台任务。

| 工具 | 类型 | 默认可调用 | 说明 |
|---|---|---|---|
| `search_wiki` | 只读知识 | 是 | 搜索 Wiki 文档和标题 |
| `read_wiki_node` | 只读知识 | 是 | 读取指定 Wiki 文档或目录摘要 |
| `search_reports` | 只读知识 | 是 | 搜索已验证 / 历史问题报告 |
| `read_report` | 只读知识 | 是 | 读取指定报告 |
| `list_session_attachments` | 只读会话 | 是 | 列出当前会话附件 |
| `read_session_attachment` | 只读会话 | 是 | 读取附件摘要或截断内容 |
| `search_code` | 只读代码 | 是 | 在已解析仓库范围内搜索代码 |
| `list_code_paths` | 只读代码 | 是 | 按路径名列出文件和目录，用于通用代码导航 |
| `read_code_file` | 只读代码 | 是 | 读取代码文件片段 |
| `inspect_repo_tree` | 只读代码 | 是 | 查看仓库目录结构 |
| `ask_user` | 用户交互 | 是 | 模型向用户澄清问题或请求选择 |
| `load_analysis_policy` | 只读策略 | 是 | 按需读取全局/特性分析策略全文 |
| `propose_report` | 建议动作 | 是 | 模型建议生成报告，但不直接生成 |

需要用户确认的真实写动作不作为默认工具静默执行：

```text
generate_report
promote_to_wiki
write_wiki
rename_wiki
delete_wiki
clear_wiki_directory
delete_session
```

这些可以作为后续确认型工具暴露，但执行必须来自用户确认或明确 UI 操作。

## 5. 工具设计细节

### 5.1 `search_wiki`

用途：

- 用户问题可能被 Wiki 文档回答。
- 模型需要验证某个术语、流程、配置或历史描述。
- 轻量 RAG 召回结果不够，需要更精确搜索。

输入：

```json
{
  "query": "小米 肥大细胞瘤",
  "feature_ids": [3],
  "node_ids": [],
  "limit": 5,
  "offset": 0
}
```

输出：

```json
{
  "ok": true,
  "tool": "search_wiki",
  "summary": "命中 2 篇 Wiki",
  "items": [
    {
      "node_id": 10,
      "feature_id": 3,
      "title": "小米病历",
      "path": "小米 / 知识库 / 小米病历",
      "snippet": "右脚脚掌肥大细胞瘤...",
      "score": 0.82
    }
  ],
  "evidence_refs": [
    {
      "type": "wiki",
      "node_id": 10,
      "path": "小米 / 知识库 / 小米病历"
    }
  ],
  "truncated": false
}
```

边界：

- 默认只返回片段，不返回全文。
- 支持 `limit/offset`，避免一次返回大量结果。
- 不输出“知识足够 / 不足”的判断。

### 5.2 `read_wiki_node`

用途：

- 模型需要读取搜索命中的完整 Wiki。
- 用户明确点名某篇 Wiki 或目录。

输入：

```json
{
  "node_id": 10,
  "heading": "基本情况",
  "max_chars": 12000
}
```

输出：

```json
{
  "ok": true,
  "tool": "read_wiki_node",
  "summary": "读取小米 / 知识库 / 小米病历#基本情况",
  "content": "## 基本情况\n...",
  "evidence_refs": [
    {
      "type": "wiki",
      "node_id": 10,
      "heading": "基本情况"
    }
  ],
  "truncated": false,
  "raw_result_ref": "tool_result_..."
}
```

边界：

- 只读取正式内容，不读取未发布草稿。
- 内容过长时截断，并提示模型可按 heading 继续读取。
- Markdown 相对链接和图片不直接塞进模型全文，只保留可引用路径。

### 5.3 `search_reports` / `read_report`

报告和 Wiki 都是知识来源，但报告有状态和验证语义。

`search_reports` 默认优先：

- 已验证报告。
- 当前候选特性的报告。
- 与错误码、日志、症状匹配度高的报告。

报告结果必须包含：

```text
report_id
feature_id
status
title
path
verified_at
snippet
evidence_refs
```

边界：

- 草稿报告可以按权限和场景作为候选，但不能伪装成已验证事实。
- 未通过报告默认不作为正向证据，只能作为历史排除线索。

### 5.4 `list_session_attachments`

用途：

- 模型知道当前会话有哪些用户上传材料。
- 避免模型不知道已有日志而反复要求用户上传。

输出示例：

```json
{
  "ok": true,
  "tool": "list_session_attachments",
  "summary": "当前会话有 3 个附件",
  "items": [
    {
      "attachment_id": "att_1",
      "display_name": "db-node-1.log",
      "original_filename": "server.log",
      "size": 248103,
      "purpose": "数据库节点 1 日志",
      "created_at": "2026-05-07T10:00:00+08:00"
    }
  ]
}
```

边界：

- 附件必须按 session 隔离。
- 工具不能跨会话读取附件。
- 同名原始文件必须依靠 `attachment_id` 和 metadata 区分。

### 5.5 `read_session_attachment`

用途：

- 读取日志摘要、关键片段或用户上传的 Markdown / 文本。
- 支持模型从附件中提取错误码、时间、版本、服务名。

输入：

```json
{
  "attachment_id": "att_1",
  "query": "ERROR timeout",
  "offset": 0,
  "limit": 200
}
```

边界：

- 大文件默认只返回摘要或匹配片段。
- 原始文件路径不暴露给模型，模型只看到附件 ID 和展示名。
- 读取结果必须保留 `original_filename`、`display_name` 和用户备注，维持用户口语描述到文件实体的映射。

### 5.6 `search_code`

用途：

- 模型需要实现细节、错误码来源、配置默认值、接口字段、真实行为。
- Wiki / 报告无法充分解释，但代码可能给出依据。

输入：

```json
{
  "query": "MastCell",
  "repo_id": null,
  "ref": null,
  "path_glob": "*.py",
  "case_insensitive": true,
  "output_mode": "content",
  "limit": 50,
  "offset": 0
}
```

代码范围解析：

1. 用户在当前消息或会话历史中明确指定的仓库。
2. 当前会话已显式绑定或历史中已确认的特性。
3. 模型基于 Feature RAG Pack 选择的一个或多个候选特性。
4. 这些特性关联仓库的并集。
5. 如果候选特性为空且没有显式仓库，返回 `needs_feature_scope`。
6. 如果 repo_id / repo_name 不属于候选特性的关联仓库，且用户没有明确指定该仓库，返回 `out_of_scope`。

代码工具不能直接从全局 ready 仓库池模糊检索源码。全局仓库池只用于管理员配置、特性关联和用户显式仓库解析，不作为默认 Agent 代码检索范围。

输出：

```json
{
  "ok": true,
  "tool": "search_code",
  "summary": "在 codeask@main 命中 3 个位置",
  "items": [
    {
      "repo_id": 1,
      "repo_name": "codeask",
      "ref": "main",
      "commit": null,
      "path": "src/codeask/wiki/search.py",
      "line": 42,
      "snippet": "..."
    }
  ],
  "version_info": {
    "repo_id": 1,
    "ref": "main",
    "commit": null,
    "status": "default_or_current",
    "warning": "代码证据基于默认分支，未确认线上故障版本。"
  },
  "truncated": false
}
```

边界：

- 默认排除 `.git` 等版本控制目录。
- 默认限制结果数量。
- 支持大小写不敏感搜索。
- 大结果截断并提示可用 offset 继续。
- 搜索不到不代表代码不存在，模型应结合上下文判断。

### 5.6.1 `list_code_paths`

用途：

- 模型初始关键词不准确，`search_code` 可能 0 命中时，先按路径名查看文件和目录。
- 在大仓库中先缩小目录范围，再读取具体文件或继续搜索。

输入：

```json
{
  "query": "buddy",
  "repo_id": null,
  "repo_name": null,
  "feature_ids": [3],
  "explicit_repo_scope": false,
  "ref": null,
  "root_path": ".",
  "include_dirs": true,
  "include_files": true,
  "limit": 100
}
```

边界：

- 范围规则与 `search_code` 一致，只允许特性范围仓库或用户显式仓库范围。
- 只做大小写不敏感的路径名匹配，不做自然语言语义映射。
- 工具层不能把“电子宠物”自动改写成 `buddy`、`companion` 等业务同义词。
- 默认过滤 `.git`、`node_modules`、构建产物和缓存目录。
- 返回结果受 `limit` 和工具结果预算约束。

### 5.7 `read_code_file`

用途：

- 读取 `search_code` 命中的具体文件片段。
- 用户明确要求查看某个文件。

输入：

```json
{
  "repo_id": 1,
  "ref": "main",
  "path": "src/codeask/wiki/search.py",
  "start_line": 40,
  "line_count": 120
}
```

边界：

- 必须通过 repo path sandbox，不能读取仓库外文件。
- 大文件必须要求分段读取。
- 结果应带行号，方便最终回答引用。
- 如果使用默认当前代码，必须输出版本警告。

### 5.8 `inspect_repo_tree`

用途：

- 模型不确定代码结构时，先看目录树。
- 用户只知道模块名，不知道文件路径。

输入：

```json
{
  "repo_id": 1,
  "ref": "main",
  "path": "src/codeask",
  "depth": 2,
  "limit": 200
}
```

边界：

- depth 和 limit 必须有限制。
- 目录树用于导航，不应返回大量文件内容。

### 5.9 `ask_user`

用途：

- 模型需要用户澄清环境、版本、仓库、特性归属、报告生成目标。
- 需要让用户在几个候选项中选择。

输入：

```json
{
  "question": "这次问题对应哪个代码版本？",
  "reason": "代码证据和线上版本可能不一致。",
  "options": [
    {"label": "使用默认分支", "value": "default_ref"},
    {"label": "我提供 commit", "value": "provide_commit"}
  ],
  "allow_free_text": true
}
```

边界：

- 一次只问最关键问题。
- 不要要求用户预先绑定特性。
- 如果用户不知道，可以提供默认继续选项。
- 前端可以渲染成轻量确认卡片。

### 5.10 `load_analysis_policy`

用途：

- 模型需要读取某个全局或特性分析策略的完整内容。
- 避免所有策略全文常驻 prompt。

输入：

```json
{
  "policy_id": 7,
  "scope": "feature"
}
```

边界：

- 默认 prompt 只列出启用策略的名称、scope、stage 和一句描述。
- 完整策略内容按需加载。
- 策略是指导，不是固定流程。

### 5.11 `propose_report`

用途：

- 模型认为当前会话已经具备生成报告的基础，可以向用户建议生成。
- 工具只产生建议，不直接写报告。

输出：

```json
{
  "ok": true,
  "tool": "propose_report",
  "summary": "当前会话已有问题现象、证据和建议操作，可生成问题定位报告。",
  "required_confirmation": true,
  "candidate_features": [
    {"feature_id": 3, "name": "小米", "confidence": "medium"}
  ],
  "missing_fields": []
}
```

边界：

- 如果特性不明确，必须让用户选择。
- 如果证据不足，必须说明缺什么。
- 真正 `generate_report` 由用户确认后执行。

## 6. 工具执行管线

CodeAsk 工具执行应采用统一管线：

```text
模型 tool_call
→ 查 ToolRegistry
→ 校验 input_schema
→ 执行 boundary guard
→ 判断是否需要用户确认 / 用户交互
→ 调用 tool.call()
→ 结果预算处理
→ 原始结果写审计存储
→ 摘要结果回填给模型
→ 前端行动轨迹事件
```

失败路径：

```text
工具失败
→ 映射 ToolErrorType
→ 生成结构化失败 ToolResult
→ 回填给模型
→ 模型决定追问 / 换工具 / 给有限结论
```

工具执行器不应该直接替模型决定下一步。

### 6.1 工具优化安全边界

工具优化的目标是提升执行质量，而不是替模型完成业务推理。CodeAsk 的原则是：用户问题、会话历史、RAG 候选、工具能力和工具结果都进入模型上下文，由模型决定回答、追问、查 Wiki、读报告、读附件或查代码。

工具层允许做：

- schema 校验、权限校验、路径校验、版本边界校验和写操作确认。
- 通用检索鲁棒性增强，例如大小写不敏感、分隔符归一、长 query 拆词 fallback、结果去重、分页和预算裁剪。
- 结果结构化，补齐 `node_id`、`document_id`、`repo_id`、`path`、`line`、`commit`、`version_info`、`raw_result_ref` 等可执行引用。
- 错误可解释化，把模糊异常拆成 `invalid_input`、`not_found`、`out_of_scope`、`needs_clarification`、`too_large`、`transient_error` 等模型可恢复类型。
- 行动轨迹折叠和摘要，但展开后仍能追溯原始参数、结果、错误和审计引用。

工具层禁止做：

- 业务语义映射，例如 `电子宠物 -> buddy`、`sqlite -> schema.prisma`、`RAG -> contextTexts`、`AnythingLLM -> 某个固定 repo/path`。
- 按题型强制禁止或强制触发工具调用，例如“基础问答永远不查工具”或“源码问题必须先查代码”。
- 输出流程结论，例如“知识足够”“无需查代码”“应该读取某文件”。这些结论只能由模型在上下文中形成。
- 为了让 UI 看起来干净而吞掉失败；失败可以折叠，但不能不可见。
- 把预算压缩到只剩 summary，导致模型丢失继续推理所需的 evidence ref、错误类型、版本信息或恢复建议。

因此，每个工具优化 PR / 阶段任务都要同时包含正向测试和反向测试：正向证明工具更稳定、更可执行；反向证明没有把业务词、测试样例、仓库名或路径名硬编码进工具。

## 7. 工具编排

v1.0.2 第一版可以串行执行工具，降低实现风险。

但工具契约需要提前支持后续编排：

```text
连续 read_only + concurrency_safe 工具
→ 可并发

任意写操作 / 需要确认 / 需要用户交互工具
→ 串行

同一工具结果会修改上下文状态
→ 串行
```

第一版即使不并发，也要在测试里验证 metadata 正确。

## 8. 上下文和审计

进入模型上下文：

- 工具摘要。
- 关键片段。
- evidence refs。
- 版本警告。
- 截断提示。
- 模型下一步可用建议。

进入审计存储：

- 完整工具输入。
- 完整工具输出或原始结果引用。
- 执行时间。
- 错误类型。
- repo/ref/commit。
- 附件 ID、Wiki node ID、report ID。
- 是否截断。

前端行动轨迹读取结构化事件，不解析模型自然语言。

## 9. 测试要求

每个工具至少覆盖：

- schema 校验失败。
- 正常成功返回。
- 结果超限截断。
- 权限或边界失败。
- 错误类型映射。
- action trace 事件生成。

Agent runtime 级测试至少覆盖：

1. 模型直接回答，不调用工具。
2. 模型调用 `search_wiki` 后回答。
3. 模型调用 `search_code` 和 `read_code_file` 后回答。
4. 代码范围不明确，工具返回 `needs_clarification`，模型追问。
5. 模型建议生成报告，但不直接执行写操作。
6. 工具结果过大，只摘要进入上下文，原始结果保留审计引用。

必须优先使用 mock LLM 做确定性测试，再接真实 LLM 联调。

## 10. 实施建议

后端建议新增：

```text
src/codeask/agent/chat_runtime/tool_contracts.py
src/codeask/agent/chat_runtime/tool_registry.py
src/codeask/agent/chat_runtime/tool_executor.py
src/codeask/agent/chat_runtime/tools/
├── wiki.py
├── reports.py
├── attachments.py
├── code.py
├── user_interaction.py
├── policies.py
└── report_actions.py
```

前端建议新增或拆分：

```text
frontend/src/components/session/action-trace/
├── ActionTracePanel.tsx
├── ActionTraceEvent.tsx
├── ToolCallEvent.tsx
├── ToolResultEvent.tsx
├── EvidenceEvent.tsx
└── ClarificationEvent.tsx
```

实现顺序建议：

1. 定义工具契约和基础执行器。
2. 接入 Wiki / 报告只读工具。
3. 接入附件只读工具。
4. 接入代码只读工具和版本解析。
5. 接入 `ask_user` 和 `propose_report`。
6. 替换旧行动轨迹 UI。
7. 加 mock LLM 端到端测试。

## 11. 与 Claude Code 的差异

CodeAsk 不复制 Claude Code 的通用 coding agent 能力。

| Claude Code 能力 | CodeAsk v1.0.2 处理 |
|---|---|
| 文件写入和编辑 | 暂不作为 Agent 默认能力 |
| Bash 任意执行 | 不开放给模型 |
| Worktree 修改隔离 | 后续只在代码修改版本考虑 |
| 多 agent 团队 | 后续版本考虑 |
| MCP 生态 | 后续扩展，当前先做内置工具 |
| Skill forked agent | 当前先做按需读取分析策略，不做 forked skill executor |
| TUI 权限弹窗 | Web 前端通过确认卡片和弹窗承载 |

CodeAsk 的核心差异是：它服务研发知识问答和问题定位，默认工具应围绕 Wiki、报告、附件和代码只读调查建设。
