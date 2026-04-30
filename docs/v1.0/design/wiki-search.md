# Wiki 与知识检索设计

> 本文档属于 v1.0 SDD，描述 Wiki 检索的实现方式。
>
> 产品契约见同版本 `prd/codeask.md`。当 SDD 与 PRD 冲突时，以 PRD 为准。

## 1. 目标

Wiki 服务管理特性、文档、skill 和报告，并为 Agent 提供可检索、可回源引用的项目知识。

知识库的两类内容：

- **文档**：人工维护的文档、规范、排障手册 —— 常青描述。
- **已验证报告**：人工验证后的定位报告 —— 具体案例。

CodeAsk 的 Wiki RAG 不是"文档切块 + 单路向量检索"。一期也不只依赖中文分词。设计目标是：

- 研发信号能精确命中，例如错误码、接口、配置 key、符号名。
- 中文自然语言能通过 FTS/BM25 召回。
- 分词失败时有字符 n-gram / trigram 兜底。
- 检索结果只是候选，最终回答必须回源读取原文。
- 向量检索是后续可选增强，不是一期核心依赖。

**报告与文档在两个层面有不同位置**（详见 §11）：

- **检索层**：报告作为知识库内的高优先级条目进入索引；查询命中时排序靠前。
- **基础上下文层**：每个会话的基础上下文 digest **只含文档摘要，不含报告** —— 避免具体案例污染常青背景。报告只通过查询命中的方式参与回答。

## 2. 内容模型

```text
Feature
├── 关联代码仓
├── 文档区
├── 报告区
└── 特性 skill

Global
├── 全局 skill
└── 全局代码仓池
```

**Feature 定义**（与 PRD §4.1 对齐）：

> Feature 是"用户自定义粒度的、有 owner 的、关联代码仓的知识集合"。

- **粒度不强制**：可以是业务模块、微服务、跨服务能力，由用户自定。
- **可不互相关联**：特性之间不要求层级或上下游关系。
- **owner 是社会契约**：一期不通过权限强制（详见 `deployment-security.md`）。

Wiki 中的每份文档/报告保留原文。索引、摘要和 chunk 只是检索辅助数据，不能替代原文成为事实来源。

## 3. 文档上传与流水线

一期支持：

- 单个 Markdown / 文本文件上传。
- 目录或 zip/tar 归档上传。
- 保留相对路径。
- 解析 Markdown 相对链接和图片引用。

上传后异步执行入库流水线：

```text
保存原文
→ Markdown / 文本解析
→ 标题、heading、path、tags 提取
→ 按 heading 和段落切 chunk
→ 正文规范化
→ 研发精确信号抽取
→ jieba 分词
→ 字符 n-gram / trigram 生成
→ 写入 FTS5 和结构化索引
→ 重算特性 summary_text（仅文档参与，详见 §11）
→ 重算 navigation_index（仅文档参与，详见 §11）
```

报告走另一条入库流（生成 → 验证 → 索引），详见 `evidence-report.md`。报告进入索引后参与检索，但**不触发** digest 重算。

## 4. Chunk 策略

chunk 以 Markdown heading 为优先边界，避免把一个小节切碎。一个 chunk 应保存：

- 所属文档。
- chunk 序号。
- heading path。
- 原始文本。
- 规范化文本。
- 分词文本。
- n-gram 文本。
- 起止 offset 或行号。
- 从 chunk 中抽取出的研发信号。

切分原则：

- 优先保持同一 heading 下的段落完整。
- 代码块、表格和列表尽量不从中间切断。
- chunk 过大时按段落继续切分。
- chunk 过小时可以与相邻段落合并。

## 5. 研发精确信号

研发文档包含大量不适合中文分词的信号。入库时应抽取并单独索引：

| 信号 | 示例 |
|---|---|
| 错误码 | `ERR_ORDER_CONTEXT_EMPTY`, `SQLSTATE 40001` |
| 异常名 | `NullPointerException`, `TimeoutError` |
| 接口路径 | `/api/order/submit` |
| 配置 key | `order.payment.retry.enabled` |
| 代码符号 | `OrderService`, `submitOrder`, `UserContextInterceptor` |
| 文件路径 | `src/order/service.py` |
| 数据库对象 | `orders`, `payment_callback_log` |
| 消息 topic | `payment_callback`, `order_created` |
| trace 字段 | `trace_id`, `request_id`, `span_id` |

这些信号进入结构化字段或独立索引。查询时如果命中，权重高于普通正文分词命中。

## 6. 多路召回

`search_wiki` 不应只执行一次 FTS 查询。它应执行多路召回，再合并去重排序。

一期默认召回通道：

| 通道 | 作用 |
|---|---|
| 精确信号召回 | 错误码、接口、配置 key、符号、路径等强信号 |
| 元数据召回 | 标题、heading、path、tags、feature 摘要 |
| FTS/BM25 召回 | jieba 分词后的中文关键词检索 |
| n-gram 兜底召回 | 分词失败或词序变化时补充召回 |
| 报告召回 | 已验证报告，作为知识库内高优先级条目（实现上可独立 FTS 表加速，但概念上是统一知识库） |

查询输入应先结构化：

```json
{
  "raw_query": "线上订单偶发失败，日志里有 ERR_ORDER_CONTEXT_EMPTY",
  "terms": ["线上", "订单", "偶发", "失败"],
  "exact_signals": ["ERR_ORDER_CONTEXT_EMPTY"],
  "feature_hints": ["订单"],
  "symbols": [],
  "routes": [],
  "version_hints": []
}
```

来自日志的 `LogAnalysis` 也应参与查询构造，例如异常类型、错误码、文件路径、符号名、trace_id。

## 7. 分词与 n-gram

中文文本写入 FTS5 前做 jieba 预分词，但分词不是唯一索引。

分词风险：

- 业务词典不完整，例如"库存预占""灰度回放"。
- 用户问法和文档写法不同。
- 错误码、符号、路径不适合自然语言分词。

兜底策略：

- 保留原文。
- 保存 jieba 分词字段。
- 保存字符 2-gram / 3-gram 字段。
- 标题、路径、tags 单独加权。
- 研发精确信号单独索引。

如果 SQLite 环境支持合适的 trigram tokenizer，可以使用 FTS5 trigram；否则由应用生成 n-gram 文本写入独立 FTS 表。

## 8. 排序融合

多路召回后执行合并去重和综合排序。排序信号包括：

- 精确信号命中数量和类型。
- feature 是否匹配。
- 标题、heading、path、tags 命中。
- FTS/BM25 分数。
- n-gram 命中分数。
- 文档更新时间。
- 报告是否 verified。
- 报告适用条件是否匹配。

建议权重原则：

```text
已验证报告直接命中 > 错误码/接口/配置 key 命中 > 标题/heading 命中
> FTS 正文命中 > n-gram 兜底命中
```

n-gram 主要用于兜底召回，默认权重不宜过高，避免噪音文档超过精确结果。

## 9. 回源引用

检索结果只作为候选。Agent 不能直接基于索引摘要作答。

标准流程：

```text
search_wiki / search_reports
→ 返回候选 chunk、文档路径、heading、摘要和分数
→ Agent 调 read_wiki_doc / read_report 回源读取原文
→ 基于原文段落回答
→ 引用文档路径、heading、段落或行号
```

摘要、导航索引、chunk snippet 都不是最终事实来源。

## 10. 数据结构方向

建议核心表：

```text
documents
  id, feature_id, kind, title, path, tags_json,
  raw_file_path, summary, created_at, updated_at

document_chunks
  id, document_id, chunk_idx, heading_path,
  raw_text, normalized_text, tokenized_text, ngram_text,
  signals_json, start_offset, end_offset
```

FTS 表方向：

```text
docs_fts
  chunk_id UNINDEXED, title, heading_path, tokenized_text, tags, path

docs_ngram_fts
  chunk_id UNINDEXED, ngram_text

reports_fts
  report_id UNINDEXED, title, tokenized_text, error_signature, tags
```

`reports_fts` 与 `docs_fts` 物理独立便于权重和过滤独立调整，但**概念上**报告与文档同属知识库（详见 §11）。

结构化信号可以先放 `signals_json`，实现复杂度增加后再拆独立表和索引。

## 11. 基础上下文 digest 与导航索引

每个特性维护两份基础上下文产物，在新会话进入特性时作为 Prompt L2 注入（详见 `agent-runtime.md` §9）：

| 产物 | 内容 | 来源 | 是否含报告 |
|---|---|---|---|
| `summary_text` | 200-500 字特性摘要，用于自动定界（A2 输入） | 仅文档 | **否** |
| `navigation_index` | 文档标题、路径、摘要行 | 仅文档 | **否** |

### 11.1 为什么 digest 不含报告

报告是**案例记录**（"2026-04-29 某次 5xx 飙升根因是 timeout hardcode"），高度具体。文档是**常青描述**（"订单状态机怎么走"）。两者性质不同：

| 风险 | 说明 |
|---|---|
| 稀释主线 | 一个特性可能积累几十条报告，塞进 digest 会让架构/流程描述被淹没 |
| 跨问题污染 | 用户问日常文档级问题，Agent 因 digest 里有事故案例而把过去的事故掺到答案里 |
| 价值错位 | 报告的真正价值是"下次类似事故 30 秒命中"（PRD §8.4 旅程 4），靠的是查询匹配，不是预热所有报告 |

### 11.2 报告的接入路径

报告**只通过检索匹配**进入回答：

```text
报告创建 / 验证（详见 evidence-report.md）
→ 写入索引（与文档同属知识库，但带高优先级权重，详见 §8）
→ 不触发 digest 重算
→ Agent 主循环中被 search_reports / search_wiki 命中
→ Agent 调 read_report 回源
→ 进入证据链
```

### 11.3 重算时机

`summary_text` 和 `navigation_index` 在以下时机重算：

- 文档新增 / 修改 / 删除
- 特性元数据变更（名称、描述、关联仓库）

报告变更（新建草稿 / 验证通过 / 撤回验证）**不触发** digest 重算。

## 12. Skill

一期 skill 是 Markdown 提示词模板，不具备执行能力。

注入规则：

```text
全局 skill
→ 选中特性后的 feature skill
```

特性 skill 后注入，可以覆盖或细化全局规则。

## 13. 扩展方向

向量检索可以作为后续增强，但不作为一期核心依赖。

推荐扩展位置：

```python
class WikiRetriever(Protocol):
    async def search(self, query: WikiQuery) -> list[WikiHit]:
        ...
```

内部可组合：

```text
ExactSignalRetriever
MetadataRetriever
FtsRetriever
NgramRetriever
VectorRetriever
Reranker
```

向量检索只负责语义候选召回。任何向量命中的内容仍必须回源读取原文后，才能进入证据链。

## 14. 与 PRD 的对齐

本文已按 `prd/codeask.md` §9 对齐表更新，主要变化：

- §2 内容模型补充 Feature 定义（用户自定义粒度、有 owner、关联代码仓的知识集合；不强制粒度；可不互相关联）
- §1 / §11 明确"检索层"与"基础上下文层"两个层面：报告进检索层（高优先级），不进基础上下文 digest
- §11 新增"为什么 digest 不含报告"和"报告的接入路径"两个小节，并定义 digest 重算时机（仅文档变更触发）
- §3 上传流水线最后两步明确"仅文档参与"
- §6 报告召回通道说明：物理可独立 FTS，但概念属同一知识库
