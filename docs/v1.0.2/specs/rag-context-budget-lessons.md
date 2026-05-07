# RAG 与长上下文预算优化参考

> 状态：Draft
> 版本：v1.0.2
> 日期：2026-05-07
> 范围：AnythingLLM 的上传资料 RAG 管线、Claude Code 的长会话上下文压缩，以及它们对 CodeAsk v1.0.2 的落地约束

## 1. 目标

CodeAsk v1.0.2 的 Agent 会话已经从固定调查流水线迁移到模型决策的工具化运行时。随着 Wiki、报告、附件和代码工具逐步接入，新的核心风险变成：

- 上传资料、Wiki 文档、代码搜索结果和附件内容过大。
- 工具结果被完整塞入下一轮模型上下文。
- 长会话多轮推进后，历史、RAG 片段和工具结果不断膨胀。
- 模型因为上下文噪音过多而误判是否需要继续查 Wiki 或查代码。

本文件把两个参考项目中的有效经验翻译成 CodeAsk v1.0.2 的优化项。这里的目标不是照搬实现，而是把可复用的架构原则落到当前版本。

## 2. AnythingLLM 的 RAG 资料处理链路

AnythingLLM 对上传资料的处理可以拆成 6 个阶段。

### 2.1 上传与解析

上传文件先进入 Collector。Collector 根据文件扩展名选择 converter；如果扩展名没有预置 converter，但文件可被识别为文本，会降级按文本处理；非文本且不支持的文件会拒绝。

这种设计的关键点是：上传文件不会直接进入 LLM。它必须先变成统一的文档对象。

### 2.2 标准化 Document

不同类型的文件最终都会转成统一结构，典型字段包括：

```text
id
url
title
docAuthor
description
docSource
chunkSource
published
wordCount
pageContent
token_count_estimate
```

`pageContent` 保存抽取后的纯文本，metadata 保存来源、标题、作者、发布时间等信息。

对 CodeAsk 的启发：

- Wiki、会话附件、上传日志、问题报告和代码片段都应转成统一的 `KnowledgeDocument` / `EvidenceDocument` 内部结构。
- 原始文件和模型上下文之间必须有一层标准化和治理，不能把原始文件全文直接注入模型。

### 2.3 加入 Workspace 后再向量化

AnythingLLM 并不是“上传即对所有空间生效”。资料被加入 workspace 后，才按 workspace namespace 写入向量库。

对 CodeAsk 的启发：

- Wiki 文档应以 feature 为一级 namespace。
- 问题报告、Wiki、附件和代码索引可以进入不同逻辑 namespace，但召回时要统一成 evidence。
- 特性删除后转入历史特性时，向量 namespace 也要能迁移或重建，而不是直接丢失。

### 2.4 文本切分

AnythingLLM 使用 TextSplitter，将文档切成 chunk：

- 默认 chunk size 约 1000。
- 默认 overlap 约 20。
- chunk size 会受 embedding 模型最大输入限制约束。
- chunk 可以带 metadata header，例如标题、发布时间、来源链接。

对 CodeAsk 的启发：

- Wiki 索引必须按 Markdown 结构切分，优先保留 heading 层级。
- 日志和附件要按语义或行范围切分，并保留文件名、客户重命名、原始文件名和路径映射。
- 代码索引不能只按普通文本切分，应保留 repo、commit、path、symbol、line range。
- chunk metadata 应成为证据引用的一部分。

### 2.5 向量写入

AnythingLLM 会对每个 chunk 生成 embedding，写入 workspace namespace，并记录 `docId -> vectorId` 映射。

对 CodeAsk 的启发：

- 需要记录 `document_id -> chunk_id -> vector_id` 的映射。
- 删除、重命名、移动 Wiki 节点时，需要能定位并更新对应 chunk。
- 用户口语化文件名和实际存储文件之间的映射也要进入 metadata，否则 Agent 无法理解“刚刚那个数据库日志”指向哪个文件。

### 2.6 查询时检索和注入

用户提问时，AnythingLLM 根据 workspace namespace 做相似度检索，得到 `contextTexts` 和 `sources`。`contextTexts` 注入模型上下文，`sources` 用于引用展示。

对 CodeAsk 的启发：

- `contextTexts` 和 UI 引用源可以分离。模型可以获得必要上下文，UI 只展示当前真正参与回答的证据。
- RAG 召回不应输出“知识足够 / 不足”的后端结论，只提供候选证据给模型判断。
- `topN`、相似度阈值、rerank 和来源去重必须成为召回服务参数。

## 3. Claude Code 的长上下文压缩逻辑

Claude Code 的上下文管理分层明显，核心不是“无限塞上下文”，而是在每轮模型调用前做预算和压缩。

### 3.1 工具结果微压缩

Claude Code 的 microcompact 会关注工具结果，尤其是搜索、读取文件、长命令输出等容易膨胀的内容。

关键原则：

- 先识别哪些工具结果可压缩。
- 保留最近 N 个关键工具结果。
- 旧工具结果不一定删除整条消息，可以替换为占位说明或使用缓存编辑。
- 压缩发生在模型调用前，而不是等模型报错后。

CodeAsk 已在 v1.0.2 补齐两层治理：

- `ToolExecutor` 对超大 `ToolResult` 进行真实裁剪，而不是只标记 `truncated=true`。
- `ChatRuntime` 在每次模型调用前进行 active context 估算；只有超过阈值时才把旧工具结果转成摘要，默认保留最近 3 个工具结果原文。

这不是每轮整体压缩，也不是随意删除历史。它对应 Claude Code 的 microcompact 思路：平时保留上下文，接近预算时优先压缩高膨胀、可重建的旧工具结果。

### 3.2 时间触发的微压缩

Claude Code 还有 time-based microcompact：当距离上次主循环 assistant 消息的时间超过阈值时，认为服务端 prompt cache 可能已经失效，于是在下次请求前清理旧工具结果，减少冷缓存重写成本。

CodeAsk 不需要立即实现 prompt cache 级别优化，但可以借鉴：

- 长时间闲置后恢复会话，应先重建紧凑上下文。
- 恢复时不应把历史工具结果全文重新塞给模型。
- 最近关键证据保留，旧工具结果转为摘要。

### 3.3 Auto Compact

Claude Code 会根据模型上下文窗口、当前 token 使用量和预留回答空间判断是否需要 auto-compact。触发后，会把旧会话压成 summary，并保留继续工作所需的状态。

CodeAsk v1.0.2 应采用更简单但方向一致的策略：

- 每轮请求前估算活跃上下文字符数 / token 数。
- 超过阈值时，生成或更新 `conversation_summary`。
- 保留最近若干轮原文、当前用户问题、关键证据、未解决问题和当前行动状态。
- 被摘要掉的完整历史仍保存在 session turns 和 traces 中，可用于审计和恢复。

### 3.4 手动 Compact

Claude Code 支持手动 `/compact`。这对于长任务很重要，因为用户或模型可能知道当前上下文已经不再需要大量历史细节。

CodeAsk v1.0.2 可以不做显式 UI 命令，但应预留：

- 前端后续可以提供“整理上下文”动作。
- 模型在长会话中可以建议整理上下文，但不能丢失原始审计记录。

### 3.5 压缩后的身份和任务状态再注入

Claude Code 的学习资料强调：压缩后 agent 可能丢失身份、角色、当前任务和未完成事项，因此需要重新注入身份和状态。

CodeAsk 的对应项：

- 压缩摘要中必须包含产品身份：CodeAsk 是研发知识定位 Agent。
- 必须保留当前用户问题、已确认事实、已上传附件、已选仓库/版本、已引用证据、未解决问题。
- 如果正在生成问题定位报告，必须保留报告目标和当前草稿状态。

## 4. CodeAsk v1.0.2 落地方案

### 4.1 RAG 数据模型约束

新增或调整内部抽象：

```text
EvidenceDocument
EvidenceChunk
EvidenceSource
EvidenceRef
```

第一版可以先在服务层落地，不必一次性迁移所有数据库表。

最低要求：

- 每个 chunk 必须知道来源类型：wiki、report、attachment、code。
- 每个 chunk 必须知道所属 feature / session / repo。
- 每个 chunk 必须有稳定 source id。
- 每个 chunk 必须能回到原始文档或原始文件。
- 用户重命名后的显示名和原始文件名都要保存。

### 4.2 RetrievalContext 约束

`retrieval_context` 只能提供候选证据，不提供后端结论。

建议结构：

```text
feature_candidates
wiki_hits
report_hits
attachment_hits
code_candidates
policy_candidates
warnings
```

每类 hit 只放：

- title / path / source type
- snippet
- score
- evidence_ref
- truncated

不放全文，不放大 JSON，不放“下一步应该查代码”的后端判断。

### 4.3 ToolResult 预算约束

所有工具结果进入模型前必须满足：

- `model_dump_json()` 不超过 `ToolSpec.max_result_size_chars`。
- 超过预算时真实裁剪 `items`，不能只设置 `truncated=true`。
- 完整原始结果后续应落审计存储，通过 `raw_result_ref` 回查。
- 前端行动轨迹展示摘要和证据，不展示超大原始结果。

已完成：

- `ToolExecutor` 对超大工具结果进行实际裁剪。
- 新增测试覆盖 oversized tool result 不会继续把大 payload 送入模型。

后续：

- 为生产工具补 `raw_result_ref`。
- 为工具结果裁剪增加更语义化的摘要，而不是只裁剪最长字符串。

### 4.4 会话级上下文压缩

v1.0.2 已新增 `src/codeask/agent/chat_runtime/compaction.py`，第一版职责如下：

```text
estimate_context_size_chars(messages)
calculate_context_budget_state(...)
compact_messages_if_needed(...)
reactive compact retry in ChatRuntime
```

压缩层级：

1. 工具结果预算：单个工具结果不能超预算。
2. 轮次级 micro-compact：每轮模型调用前估算 active context；低于阈值不压缩，高于阈值才把旧工具结果转摘要，只保留最近 N 个原文片段。
3. Reactive compact：如果供应商实际返回 input length / prompt too long / context length 错误，强制压缩工具结果并重试一次。
4. 会话级 auto-compact：历史超过阈值时生成 `conversation_summary`，当前仍是后续项。
5. 审计保留：原始 turns、traces、attachments 和 tool raw result 不删除。

第一版阈值体系参考 Claude Code：

```text
MAX_OUTPUT_TOKENS_FOR_SUMMARY → summary_output_reserve
AUTOCOMPACT_BUFFER_TOKENS    → autocompact_buffer
WARNING_THRESHOLD_BUFFER     → warning_buffer
ERROR_THRESHOLD_BUFFER       → error_buffer
MANUAL_COMPACT_BUFFER        → blocking_limit reserve
keepRecent                   → keep_recent_tool_results
```

差异说明：

- Claude Code 使用 token accounting，CodeAsk 当前使用 LLM message 序列化字符数作为执行单位。
- 这个字符预算是为了立刻解决 GLM-5.1 / LiteLLM 暴露的 `Input length ... exceeds maximum length ...` 问题，不是最终形态。
- 后续应把模型 context window、真实 usage、provider tokenizer 或近似 token counter 接入 `ContextBudgetPolicy`。

### 4.7 第二层 Auto Compact 计划

当前第一版 micro-compact 只解决“旧工具结果累计过大”的问题。第二层 auto compact 必须独立实现，目标是让长会话长期运行后仍能保持语义连续。

第二层必须包含：

```text
conversation_summary 持久化
+ summary 生成 prompt
+ covered turns / traces 范围记录
+ active context builder
+ auto compact 阈值触发
+ compact 失败熔断
+ prompt-too-long reactive fallback
+ live E2E 验收
```

摘要内容必须保留：

```text
当前用户目标
已确认事实
已上传附件
已检索 Wiki / 报告 / 代码
是否实际读取源码文件
工具失败和失败原因
证据来源
仓库 / 分支 / commit 状态
未解决问题
用户偏好和约束
事实 / 推断 / 未确认信息的边界
```

验收重点：

- summary 不能替代原始 turns 和 traces。
- summary 后仍能追问上一轮行动。
- summary 后仍能区分 `list_code_repos`、`search_code` 和 `read_code_file`。
- summary 后刷新页面继续追问，模型不能丢失上下文。
- compact 失败不能无限重试，默认连续失败 3 次后熔断。

### 4.5 RAG 注入预算

每轮模型上下文应有比例预算：

```text
system / policy: 10-15%
conversation summary: 10-20%
recent turns: 20-30%
retrieval snippets: 20-30%
tool results: 20-30%
response reserve: 固定预留
```

这是工程策略，不需要对用户暴露。真正比例可通过配置调优。

### 4.6 E2E 验收

v1.0.2 必须新增或保留以下验收：

- 基础问答 30 题：正常模型直答，不误触大量 Wiki / 代码工具。
- AnythingLLM RAG 问题：允许模型读取参考仓库，但不得因工具结果过大触发 input length 超限。
- 长会话多轮：多轮工具调用后仍能继续回答，不因历史膨胀失败。
- 刷新恢复：压缩后的会话仍能恢复原始 turns 和行动轨迹。

已新增后端回归：

- 多轮工具结果累计膨胀时，`ChatRuntime` 在发给模型前压缩旧工具结果。
- 供应商返回上下文超限错误时，`ChatRuntime` 执行一次 reactive compact retry。
- 低于阈值时不压缩，避免每轮无意义地丢失上下文。

## 5. 不纳入 v1.0.2 的内容

以下能力放到后续版本：

- 完整向量库重构。
- 多 namespace 迁移和历史特性向量搬迁。
- 复杂 reranker 管理界面。
- 用户手动 compact UI。
- Claude Code 级别的 prompt cache editing。
- 多 agent 独立上下文与身份再注入。

v1.0.2 只要求把上下文预算、RAG 注入边界和工具结果裁剪建立起来，避免 Agent 会话继续被超大上下文打爆。

## 6. 结论

AnythingLLM 证明：上传资料必须先标准化、切分、向量化，再按 workspace / namespace 召回片段。Claude Code 证明：长会话必须在每轮调用前做预算、微压缩和必要摘要。

CodeAsk v1.0.2 的优化方向应收敛为：

```text
资料标准化
+ 证据 chunk 化
+ RAG 候选召回
+ 工具结果预算
+ 会话级压缩
+ 原始审计保留
+ 模型决策动作
```

这能同时解决两个问题：既让 CodeAsk 拥有垂直知识增强能力，又避免把知识、代码和历史粗暴塞进模型上下文。
