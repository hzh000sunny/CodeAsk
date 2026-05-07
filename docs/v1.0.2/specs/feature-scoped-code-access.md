# v1.0.2 特性范围代码检索设计

> 日期：2026-05-07
> 状态：第一版已实现，浏览器 live E2E 待补齐
> 范围：Agent 代码检索范围收敛、特性 RAG 候选注入、交叉特性检索

## 1. 背景

v1.0.2 早期实现里，生产代码工具直接暴露了全局 ready 仓库池。这样做虽然方便调试 `claude-code`、`anything-llm` 等参考仓库，但会让 Agent 绕过特性边界直接读源码，和 CodeAsk 的产品边界不一致。

CodeAsk 的目标不是“任意全局仓库随便搜”，而是：

```text
模型先根据上下文判断问题更像属于哪些特性
→ 后端只开放这些特性关联的仓库
→ 模型在允许范围内选择是否搜索 / 读取代码
```

这条规则既能保留“用户不需要先知道特性”的 Agent 体验，也能让代码检索变成可治理的能力。

同时需要保留用户显式指定仓库的能力：如果用户明确要求“通过某个仓库查询 / 查看某个仓库”，即使该仓库没有关联特性，也允许作为本轮显式代码范围读取。显式仓库范围应写入会话上下文，工具结果和行动轨迹必须标注来源是 `explicit_user_repo`，并继续提示版本是否明确。

## 2. 核心原则

1. 默认代码检索必须通过特性范围进入。
2. 用户显式指定仓库时，该仓库可以作为本轮显式范围，即使没有关联特性。
3. 模型负责判断相关特性，允许单特性和交叉特性。
4. 后端不根据用户自然语言直接把仓库当作全局开放池暴露给模型。
5. 如果没有足够的特性候选，也没有用户显式仓库范围，模型应先回答、追问或要求补充上下文，而不是直接读全局仓库。
6. 工具只做范围校验，不做业务语义特判。

## 3. 需要提供给模型的 RAG 信息

为了让模型自己判断特性，不能只给它空的“feature_ids”。

每轮上下文里应注入一份轻量的 **Feature RAG Pack**，内容包括：

- 特性 id、名称、别名。
- 特性描述。
- 当前会话已选特性。
- Wiki 命中摘要。
- 已验证问题报告摘要。
- 当前会话附件摘要。
- 与特性关联的仓库摘要。
- 仓库状态、默认分支或默认 ref、最近同步时间。
- 必要时的版本不确定提示。

这些信息不应是全文，而应是轻量候选上下文，让模型判断：

- 这个问题是否属于某个特性。
- 是否可能是多个特性交叉问题。
- 是否应该优先查看 Wiki / 报告 / 附件 / 代码。
- 是否需要追问用户补充特性线索。

当前第一版实现：

- `DatabaseRetrievalService` 从真实数据库召回 active features、Wiki 命中、问题报告命中和特性关联 ready 仓库。
- `ChatRuntime` 会把 Feature RAG Pack 注入实际 LLM messages，位于当前用户问题之前。
- 注入内容只包含候选摘要、snippet 和引用元数据，不包含 Wiki / 报告全文。
- 代码工具说明要求模型默认将判断相关的 `feature_id` 填入 `feature_ids`；只有用户明确要求查询某个仓库时，才使用 `explicit_repo_scope=true`。

## 4. 候选特性召回

每轮消息进入 runtime 时，后端先做一个轻量候选特性召回，而不是直接进入全局仓库搜索。

候选特性来源：

1. 用户显式选择的特性。
2. 会话历史里已经出现的特性。
3. 当前消息命中的特性别名、描述、Wiki 片段、报告片段、附件线索。
4. 与当前问题语义相近的特性摘要。

输出给模型的内容应尽量紧凑，但要足够区分特性：

```text
- 小⽶：宠物病历、治疗记录、日志、图片目录、问题定位报告
- Claude Code：源码学习、工具能力、上下文压缩、TUI 行为
- AnythingLLM：RAG 文档处理、workspace、chunk、embedding、向量召回
```

如果候选特性为多个，模型可以同时选择多个特性参与后续代码检索。

## 5. 代码访问范围

代码工具不再把全局 ready 仓库池作为默认范围。允许范围由两类来源组成：

- 用户显式指定的仓库范围。
- 模型选择的候选特性关联仓库。

### 5.1 范围解析顺序

1. 用户在当前消息或会话历史中明确指定的仓库。
2. 当前会话已显式绑定的特性。
3. 模型从 Feature RAG Pack 中选择的候选特性。
4. 这几个特性关联仓库的并集。

允许的行为：

- 单特性检索。
- 多特性交叉检索。
- 同一仓库被多个特性关联时只保留一份。
- 用户显式指定某个全局 ready 仓库时，允许读取该仓库，即使它没有关联特性。

不允许的行为：

- 直接从全局 ready 仓库池检索源码。
- 用户没有明确指定仓库时，仅因 repo_name 或 query 模糊命中全局仓库就绕过特性范围。

### 5.2 工具契约建议

建议代码工具至少带一个 `feature_ids` 入参，表示当前允许访问的特性范围。

示例：

```json
{
  "query": "CompanionSprite",
  "feature_ids": [31, 44],
  "repo_id": null,
  "repo_name": null,
  "ref": null
}
```

如果 `feature_ids` 为空且没有显式 `repo_id` / `repo_name`，工具应返回结构化错误：

```json
{
  "ok": false,
  "error_type": "needs_feature_scope",
  "summary": "当前没有可用于代码检索的特性范围"
}
```

如果 `repo_id` 不属于允许的特性范围，且用户没有显式指定该仓库，返回：

```json
{
  "ok": false,
  "error_type": "out_of_scope",
  "summary": "该仓库不在当前允许的特性范围内"
}
```

如果用户显式指定仓库，工具结果应包含：

```json
{
  "scope_source": "explicit_user_repo",
  "feature_ids": [],
  "repo_id": "repo_xxx",
  "warnings": ["该仓库未关联特性，本轮按用户显式指定仓库读取。"]
}
```

当前生产工具契约：

- `list_code_repos(query, feature_ids, explicit_repo_scope, limit)`
- `search_code(query, repo_id, repo_name, feature_ids, explicit_repo_scope, ref, path_glob, search_mode, limit)`
- `inspect_repo_tree(repo_id, repo_name, feature_ids, explicit_repo_scope, ref, path, depth, limit)`
- `list_code_paths(query, repo_id, repo_name, feature_ids, explicit_repo_scope, ref, root_path, include_dirs, include_files, limit)`
- `read_code_file(path, repo_id, repo_name, feature_ids, explicit_repo_scope, ref, start_line, line_count)`

`list_code_paths` 是通用路径导航能力，只做大小写不敏感的文件 / 目录路径匹配。它不能把用户自然语言映射成业务同义词，例如不能在工具层把“电子宠物”改写成 `buddy`；是否选择 `buddy`、`companion` 等搜索词必须由模型基于 Feature RAG Pack、仓库目录和对话上下文决定。

`inspect_repo_tree` 是通用目录树能力，帮助模型在若干次 `search_code` 0 命中后先确认目录结构。`search_code` 0 命中不能直接推出“功能不存在”；工具结果会提示模型先检查路径和命名，再基于证据谨慎回答。

工具边界：

- `feature_ids` 非空时，只从这些特性关联的 ready 仓库中解析 repo。
- `explicit_repo_scope=true` 时，允许按用户显式指定的 repo id / repo name 读取全局 ready 仓库。
- 两者都为空时返回 `needs_feature_scope`。
- repo 存在但不在当前特性范围内时返回 `out_of_scope`。
- 工具结果 `version_info.scope_source` 标记 `feature_scope` 或 `explicit_user_repo`，并随 `tool_result` SSE 事件透传给行动轨迹。

## 6. 交叉特性

当模型判断问题可能属于多个特性时，应该允许同时使用多个特性范围。

规则：

```text
allowed_repo_ids = union(repos(feature_a), repos(feature_b), ...)
```

模型可以据此：

- 搜索某个特性 A 的仓库。
- 读取特性 B 的实现细节。
- 将两个特性的证据一起拼装成回答。

这是为了支持真实研发问题中的交叉域场景，例如：

- CodeAsk 会话运行时 + 上下文压缩。
- Wiki 导入 + 附件引用路径。
- Claude Code 工具链 + CodeAsk 工具设计。

## 7. 版本不确定性

即使仓库范围确定，版本也可能不确定。

因此工具结果仍然需要输出：

- repo_id / repo_name。
- ref / commit。
- 当前选择来源。
- 版本不确定 warning。

如果没有明确版本，工具可以默认当前代码或默认 ref，但必须明确标注“不确定”。

## 8. 前端 / 行动轨迹展示

行动轨迹应当让用户看见模型是如何收敛特性的，但不应该展示全局仓库开放池。

建议展示：

- 候选特性摘要。
- 本轮最终选择的特性。
- 允许访问的仓库列表。
- 当前仓库版本是否明确。
- 是否发生交叉特性检索。

不要展示：

- “全局 ready 仓库池”这种对用户没有边界意义的内部实现。

## 9. 验收标准

- 没有特性范围且没有用户显式仓库时，代码工具必须拒绝访问。
- 用户显式指定全局 ready 仓库时，即使该仓库没有关联特性，也可以检索，但必须标注 `explicit_user_repo`。
- 候选特性范围内可以正常检索代码。
- 交叉特性范围内可以同时检索多个特性关联仓库。
- repo_name 模糊命中全局仓库但用户没有明确指定该仓库时，必须拒绝或要求澄清。
- 代码结果必须带版本不确定性标识。
- 行动轨迹应能看出模型是基于哪些特性候选做出代码检索决策。

已完成的自动化验收：

- `tests/integration/test_chat_runtime_live_code_tools.py`
  - 无特性范围 / 无显式仓库时拒绝全局仓库访问。
  - 用户显式仓库范围允许检索和读取，并标注 `explicit_user_repo`。
  - 特性关联仓库范围允许检索，并标注 `feature_scope`。
  - 特性范围外仓库返回 `out_of_scope`。
- `tests/integration/test_chat_runtime_retrieval.py`
  - 数据库检索服务返回特性、关联仓库、Wiki 和报告候选。
- `tests/integration/test_agent_chat_runtime.py`
  - Feature RAG Pack 进入实际 LLM messages。
  - `tool_result.version_info` 透传给 runtime 事件。

仍需补齐的验收：

- 真实浏览器 / live LLM 下的特性关联仓库检索。
- 真实浏览器 / live LLM 下的用户显式仓库检索。
- 行动轨迹 UI 对 `scope_source`、`feature_ids`、repo / ref / commit 的展示细节。

## 10. 后续扩展

后续如果要允许管理员调试仓库，可以单独做一个“调试模式”或“参考仓库”通道，但不要和默认 Agent 代码检索混在一起。
