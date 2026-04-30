# 日志排障工作流设计

> 本文档属于 v1.0 SDD，描述日志排障作为**复杂查询特例**的处理流程。
>
> 产品契约见同版本 `prd/codeask.md`。当 SDD 与 PRD 冲突时，以 PRD 为准。

## 1. 目标

日志排障**不是 CodeAsk 的独立优先级场景**，而是 PRD §3 主链路在"输入是日志 + 现象"时的一种走向 —— 属于"复杂问答"分支的特例（`prd/codeask.md` §3.2）。

它复用同一套主链路：知识库（含已验证报告）→ 代码深入。本文不重复主链路本身，只描述日志输入的特定处理：

- 日志输入的形态（§2）
- 日志线索抽取（§3、§4）
- 主链路在该输入形态下的具体走向（§5）
- 代码版本策略（§6）
- 输出要求（§7）

### 1.1 一期对 oncall 场景的诚实定位

引自 `prd/codeask.md` §8.4：

> CodeAsk **不承诺**帮你解决 oncall 事故。它承诺：
>
> - 第一次事故：帮你少走几步（自动检索知识库、扫一眼相关代码、给出 medium 置信度的方向）
> - 第一次事故的副产品：留下一份可被沉淀为报告的会话记录
> - 第二次同类事故：在 30 秒内直接命中已验证报告 → 这才是真正的价值

设计取舍服务于这个定位 —— 不把 CodeAsk 包装成"自动 oncall 救火工具"。

一期不绑定具体语言或框架。系统通过通用日志分析器提取线索；语言/平台特定解析器作为扩展点接入，不进入核心流程。

## 2. 输入形态

一次排障请求由以下部分组成：

```text
用户问题文本
+ 可选粘贴日志
+ 可选日志文件附件
+ 可选上下文字段
+ 可选 feature_ids
+ 可选 repo ref / commit 信息
```

用户可以只粘贴日志，也可以上传文件。系统不强制用户一开始提供 commit/ref，避免提问门槛过高。

建议的一期上下文字段：

| 字段 | 必填 | 说明 |
|---|---|---|
| `description` | 是 | 用户描述的问题、现象或目标 |
| `environment` | 否 | prod、staging、dev、region 等 |
| `service` | 否 | 服务名、应用名、模块名 |
| `time_range` | 否 | 故障发生时间段 |
| `impact` | 否 | 影响范围、比例、用户群体 |
| `recent_changes` | 否 | 最近发布、配置变更、数据变更 |
| `version_hint` | 否 | 用户已知的 tag、branch、commit、镜像 tag、构建号 |

## 3. 日志分析

一期内置 `GenericLogAnalyzer`，从任意文本中提取语言无关线索。

```python
class LogAnalyzer(Protocol):
    name: str

    def detect(self, text: str) -> float:
        """返回该 analyzer 对文本的适配置信度。"""

    def extract(self, text: str) -> LogAnalysis:
        """返回结构化日志线索。"""
```

`GenericLogAnalyzer` 输出：

```json
{
  "time_candidates": [],
  "level_candidates": [],
  "error_types": [],
  "error_codes": [],
  "trace_ids": [],
  "request_ids": [],
  "http_signals": [],
  "file_paths": [],
  "symbol_candidates": [],
  "line_candidates": [],
  "version_candidates": [],
  "raw_highlights": []
}
```

通用提取规则覆盖：

- 时间戳。
- `error`、`exception`、`failed`、`timeout`、`panic`、`traceback` 等错误信号。
- 错误码、HTTP 状态码、数据库错误码。
- trace_id、request_id、span_id。
- 文件路径、包路径、类名、函数名、方法名候选。
- 行号和堆栈片段。
- commit sha、镜像 tag、构建号、版本号候选。

## 4. Analyzer 扩展

后续语言和平台解析器通过同一接口接入：

| Analyzer | 方向 |
|---|---|
| `JavaStackTraceAnalyzer` | Java / Spring / JVM 异常栈 |
| `PythonTracebackAnalyzer` | Python traceback |
| `NodeStackAnalyzer` | Node.js / TypeScript stack |
| `GoPanicAnalyzer` | Go panic / goroutine stack |
| `RustPanicAnalyzer` | Rust panic |
| `KubernetesLogAnalyzer` | Pod、namespace、container、restart 信号 |
| `NginxAccessLogAnalyzer` | access log、状态码、URL、耗时 |
| `SqlErrorAnalyzer` | SQLState、deadlock、constraint、timeout |

核心 Agent 不依赖具体 Analyzer 类型，只消费标准 `LogAnalysis`。

## 5. 主链路在日志输入下的走向

主链路本身见 PRD §3 + `agent-runtime.md` §2。本节只列日志场景下的具体走向。

```text
接收日志 + 现象描述
→ 通用日志分析器抽取线索（§3）
→ ScopeDetection（自动定界，使用日志中的服务名、符号、错误码等线索）
→ KnowledgeRetrieval（统一检索知识库，报告与文档同表，报告权重高）
→ SufficiencyJudgement（Agent 判断证据是否足够）
   ├─ 已验证报告直接命中且适用 → 合成答案
   ├─ 文档+报告组合够答（少见）→ 合成答案
   └─ 不够 → CodeInvestigation（用日志线索做精确入口检索）
→（必要时）VersionConfirmation
→ EvidenceSynthesis + AnswerFinalization
→（可选）ReportDrafting
→ 人工验证后入库（详见 evidence-report.md）
```

### 5.1 报告作为知识库高优先级条目（不是单独一层）

与旧设计的差异：旧版主链路把"已验证报告检索"作为独立一层，现在合并入知识库。已验证报告与日志线索高度匹配时，通过 `wiki-search.md` §8 的排序权重自动靠前，**不是**主链路的独立阶段。

报告命中信号包括：

- 异常类型一致。
- 错误码一致。
- trace 或堆栈关键符号一致。
- 业务特性一致。
- 报告适用版本与当前线索不冲突。

`SufficiencyJudgement` 判定"够"时不进入代码层；判定"不够"时由 Agent 进入 `CodeInvestigation`。

### 5.2 代码调查的入口

日志场景下代码调查有天然的精确入口（不需要靠模糊检索）：

- 用错误码、异常类型、函数名、类名、文件路径 grep。
- 用 `list_symbols` 定位符号定义。
- 用 `read_file` 读取关键代码片段。
- 必要时扩大到配置文件、SQL、路由、消息 topic 等。

详见 `agent-runtime.md` §7 代码调查策略。

## 6. 代码版本策略

当用户没有提供版本信息，且日志里也无法可靠识别版本时，系统可以先使用仓库默认分支或特性配置的默认 ref 做探索性预查。

探索性预查规则：

1. UI 和回答必须标注当前代码来自默认分支或默认 ref。
2. 预查结论只能作为初步判断。
3. 如果代码无法给出确定信息，Agent 应询问用户是否有指定版本。
4. 如果存在多个候选根因，Agent 应要求用户确认版本。
5. 生成正式报告前必须绑定明确 commit。

版本确认来源：

- 用户手动输入 branch、tag、commit。
- 日志中识别出的 commit sha、镜像 tag、构建号。
- 会话历史中已经确认过的版本。
- 特性或仓库配置的默认 ref。

## 7. 用户追问

Agent 只在信息不足时追问。常见追问：

- "这份日志对应哪个版本或构建号？"
- "故障发生在哪个环境？"
- "最近是否发布过相关服务？"
- "这是否只发生在某个租户、区域或流量入口？"

单轮会话主动追问次数默认上限为 3 次。超过上限后，系统应给出当前最佳判断和缺失信息。

## 8. 输出要求

排障回答必须包含：

- **结论**：当前最可能根因（醒目展示，oncall 凌晨 2 点要能 5 秒看懂）。
- **建议操作**：验证步骤、修复方向、回滚或配置检查。回答**绝不能**写成"按这样改就行了"——必须明确是"建议操作"，决策权在人（PRD §6.1 不假装自信）。
- **置信度**：high、medium、low。
- **不确定点**：需要用户补充或后续验证的信息。
- **证据**（默认折叠）：日志、知识库（含报告）、代码引用。

如果代码证据来自默认分支，必须写明"该代码证据尚未确认与故障版本一致"。

UI 摆放原则（来自 `prd/codeask.md` §8.4）：

> UI 必须把"结论 + 建议操作"放最前面，证据默认折叠 —— 凌晨 2 点没人读 5 屏证据。

## 9. MVP 验收案例

一期最小验收案例（与 PRD §8.4 旅程 4 一致）：

```text
1.  用户新建会话，粘贴一段日志或上传日志文件。
2.  用户补充一句现象描述，但不提供 feature 和 commit。
3.  系统通过 GenericLogAnalyzer 提取错误类型、符号、trace_id、时间等线索。
4.  Agent ScopeDetection 自动选择相关特性（A2 假设落地）。
5.  系统执行 KnowledgeRetrieval（合并检索知识库 + 报告高优先级）。
6.  SufficiencyJudgement 判定知识库不足（A3 假设落地，UI 通过 sufficiency_judgement 事件透明）。
7.  系统使用默认分支进入 CodeInvestigation，做探索性代码调查。
8.  Agent 找到候选根因，但提示代码版本未确认；展示结论 + 建议操作 + 不确定点。
9.  用户照建议先临时止血（不等版本确认）。
10. 用户提供 tag 或 commit；系统重跑关键代码证据读取，绑定明确 commit。
11. 系统输出 high 置信度回答。
12. 用户生成报告并人工验证（一期任意人可验证）。
13. 后续同类日志在 KnowledgeRetrieval 阶段直接命中该已验证报告 → 30 秒拿到答案，不进 CodeInvestigation。
```

第 13 步是本场景的真正价值兑现点，对应 PRD §8.4 末段"第二次同类事故 30 秒命中"。

## 10. 与 PRD 的对齐

本文已按 `prd/codeask.md` §9 对齐表更新，主要变化：

- §1 删除"一期 P0 主场景"框架，重定位为"复杂查询特例 / 主链路一种走向"
- §1.1 引入 PRD §8.4 的"诚实定位"，明确不承诺解决 oncall 事故
- §5 排障流程从"三层（报告 → 知识库 → 代码）"重写为"两层（知识库含报告 → 代码）"，与 `agent-runtime.md` 状态机对齐
- §5.1 报告"作为知识库高优先级条目"而非独立一层
- §8 输出要求强化"结论先 + 证据折叠"和"不假装自信"两个 PRD 承诺
- §9 验收案例对齐 PRD §8.4 旅程 4，标注 A2 / A3 假设落地点和报告飞轮的真正价值兑现点
