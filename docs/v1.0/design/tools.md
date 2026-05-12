# 工具系统设计

## 1. 目标

工具系统是 Agent 与外部世界的唯一交互通道。Agent 不能直接访问数据库、文件系统、代码仓库或附件目录。

工具系统负责：

- 暴露统一 Tool Protocol。
- 校验工具参数和访问范围。
- 执行业务服务调用。
- 截断和结构化工具结果。
- 把错误作为可恢复结果回填给 Agent。

## 2. Tool Protocol

```python
class Tool(Protocol):
    name: str
    description: str
    schema: dict

    async def call(self, args: dict, ctx: ToolContext) -> ToolResult:
        ...
```

`ToolContext` 携带：

- `session_id`
- `turn_id`
- `feature_ids`
- `repo_bindings`
- `user_context`
- `phase`
- `limits`

## 3. 一期工具清单

| 工具 | 用途 |
|---|---|
| `select_feature` | 自动定界相关特性 |
| `search_reports` | 搜索已验证报告 |
| `read_report` | 读取已验证报告 |
| `search_wiki` | 搜索知识库文档 |
| `read_wiki_doc` | 读取知识库文档 |
| `grep_code` | 在选定仓库和版本中搜索代码 |
| `read_file` | 读取代码文件片段 |
| `list_symbols` | 查找符号定义 |
| `read_log` | 读取日志附件片段 |
| `ask_user` | 暂停 Agent 并向用户追问 |

## 4. 访问控制

- `grep_code`、`read_file`、`list_symbols` 只能访问当前会话允许的仓库。
- `read_log` 只能读取当前 session 的附件。
- `read_wiki_doc` 只能读取 Wiki 根目录下的文档。
- `read_report` 只能读取 `verified=true` 的报告，除非当前用户在报告管理页面显式打开草稿。
- 所有路径必须通过 `resolve_within(base, user_path)` 校验。

## 5. 工具结果

`ToolResult` 标准结构：

```json
{
  "ok": true,
  "data": {},
  "summary": "命中 3 处",
  "evidence": [],
  "truncated": false,
  "hint": null
}
```

错误结果：

```json
{
  "ok": false,
  "error_code": "INVALID_REPO_SCOPE",
  "message": "该仓库未关联到当前特性",
  "recoverable": true
}
```

## 6. 截断策略

- 单条工具结果默认不超过 4KB。
- 搜索类工具返回 top_k 结果和摘要。
- 文件读取默认读取片段，不默认返回整文件。
- 结果被截断时返回 `truncated=true` 和下一步建议。

## 7. 工具 Schema

每个工具的完整 JSON Schema 在实施前固化。本设计阶段先确定边界和字段方向，具体字段以 `api-data-model.md` 和实施计划为准。

工具 schema 必须同时服务后端校验和模型理解：

- 必填字段必须在 schema 中清晰标注，并写明字段来源。
- 不能让模型通过标题、路径、目录名或列表顺序猜测内部 ID；读取类工具需要 ID 时，schema 必须说明 ID 只能来自候选上下文或搜索工具返回结果。
- 流式工具参数 JSON 解析失败不能被静默吞掉。适配层必须保留解析错误和原始参数片段，运行时把它转换成可恢复的工具错误。
- 参数校验失败必须作为结构化 `ToolResult` 回填给模型，并进入行动轨迹；模型需要看到字段缺失、类型错误或 JSON 解析失败的具体原因，才能在下一次 tool call 中修正。
- 前端行动轨迹不能只显示“工具失败”。展开详情至少应能看到工具名、参数摘要、错误类型、错误 message；参数 JSON 解析失败时还应展示解析错误和原始参数片段。

## 8. 一期 / 二期边界

v1.0 工具系统先追求**协议稳定、访问受控、结果结构化**，不在一期实现成熟 Agent IDE 的完整上下文管理能力。

一期工具应该做到：

- 参数 schema 明确。
- 访问范围可校验。
- 结果可截断。
- 错误可恢复。
- 轨迹可记录。

一期工具不负责：

- 自动决定下一轮应该调用哪个工具。
- 对搜索结果做语义重排。
- 管理跨轮 token budget。
- 汇总多次 `grep_code` / `read_file` 的长期上下文。

这些能力属于后续 `tool-intelligence` / `agent-runtime` 优化范围。二期可以参考许可证兼容的开源 Agent 工具实现，重点吸收搜索排序、文件分块、上下文裁剪、重复上下文去重和错误恢复提示等局部策略；不得引入未明确授权的内部源码，也不得破坏 CodeAsk 自研状态机和低部署门槛。
