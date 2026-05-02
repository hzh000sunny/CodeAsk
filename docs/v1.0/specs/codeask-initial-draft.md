# CodeAsk 设计文档

- **状态**：Draft（待评审）
- **创建日期**：2026-04-27
- **范围**：一期 MVP 整体架构 + 各子系统接口；具体实现细节留给后续每个子系统的子设计文档

---

## 0. 背景与目标

### 0.1 背景

研发日常排障的痛点不是"知识库找不到答案"，而是：

- Bug 与日志高度依赖**当前 commit** 的代码状态，传统全量 RAG 系统对代码无能为力
- 多人重复排查同一类问题，经验无法沉淀和复用
- 排障是一个**多步推理**过程（猜→查代码→验证→再猜），传统"一次检索 + 一次生成"的 RAG 范式只能给出表面答案
- 通用 AI 工具不了解项目业务上下文

### 0.2 目标

CodeAsk 是一个**面向小团队私有部署**的、**Agentic 架构**的研发排障问答系统：

1. **Agent 主导推理**：模型通过工具调用（grep / read_file / search_wiki / ask_user 等）迭代验证假设，而不是被动读拼接的上下文
2. **统一会话 + 自动定界**：会话不预绑特性；Agent 第一步根据问题和各特性摘要自动选择涉及的特性
3. **检索优先级强约束**：先查已验证报告 → 再查特性知识库 → 最后才进入代码推理
4. **代码状态绝对实时**：会话级 git worktree 按 commit 检出，不维护过期向量库
5. **经验闭环**：定位结果产出报告，**人工验证后**才入知识库参与未来检索，避免错误经验污染

### 0.3 非目标（一期）

- 多用户精细权限/SSO（小团队场景，单 master token）
- 模型大小杯分流
- 问题指纹去重 / 假设证据面板（推到二期）
- 可执行 skill（一期 skill 仅为 Markdown 提示词模板）
- npm 一键安装（推到二期，但架构上预留）
- 文档向量检索（一期用 FTS5；二期视需要再加）

---

## 1. 整体架构

### 1.1 子系统划分

CodeAsk 一期是**单进程 FastAPI 应用**，按 7 个子系统做模块边界：

| 子系统 | 职责 | Python package |
|---|---|---|
| Web 前端 | 会话 UI、Wiki 管理、特性配置、全局配置、辅助面板 | `web/`（独立项目） |
| API 网关层 | FastAPI 路由、SSE 流、master token 鉴权、定时任务 | `codeask.api` |
| Agent 编排器 | 跑 Agent 主循环：定界、组装提示、调 LLM、分发工具调用、收集观察、迭代 | `codeask.agent` |
| 工具集服务 | 一组独立 Tool 类，统一接口；Agent 与世界唯一的交互通道 | `codeask.tools` |
| Wiki 库服务 | 特性、文档、报告、skill CRUD；目录上传；导航索引；FTS5 全文检索 | `codeask.wiki` |
| 代码索引服务 | Git 仓库管理（全局池）、按会话 worktree 检出、ctags 缓存、ripgrep 包装 | `codeask.code_index` |
| LLM 网关 | OpenAI 兼容协议封装、流式、工具调用解码、重试 | `codeask.llm` |

### 1.2 关键边界约束

- **工具集是 Agent 与外部世界的唯一交互通道**。Agent 不能直接读数据库、不能直接读文件
- **代码索引服务对 Agent 透明**。底层 ripgrep 还是 ctags，Agent 不感知
- **Wiki 库 vs 代码索引完全分离**
- **跨模块只走 protocol 接口**，不允许直接访问对方的数据库表/文件目录
- **代码仓和特性解耦**：仓库注册在全局；特性通过勾选关联仓库

### 1.3 部署形态演进

| 阶段 | 形态 |
|---|---|
| 一期 | 单进程 `uvicorn` + `start.sh`；前端构建产物挂在 FastAPI 静态资源 |
| 二期 | npm 包 `@codeask/cli` 启动器（要求本地预装 Python 3.11+） |
| 视负载 | 拆出 `code-index` 独立服务，其他不动 |

### 1.4 拓扑图

```
                       ┌─────────────────────┐
                       │   Web 前端 (React)  │
                       │  会话 / Wiki /       │
                       │  特性配置 / 全局配置 │
                       └──────────┬──────────┘
                              HTTP + SSE
                                  │
                       ┌──────────▼──────────┐
                       │  API 网关层 (FastAPI)│
                       │  路由 / SSE / 鉴权 / │
                       │  定时任务调度        │
                       └──────────┬──────────┘
                                  │
        ┌─────────────────────────┼──────────────────────────┐
        │                         │                          │
┌───────▼────────┐    ┌───────────▼──────────┐    ┌──────────▼─────────┐
│ Agent 编排器   │───▶│      工具集服务      │───▶│   Wiki 库服务      │
│                │    │  select_feature      │    │  特性 / 文档 /     │
│  - 定界        │    │  search_wiki         │    │  报告 / skill CRUD │
│  - 提示组装    │    │  read_wiki_doc       │    │  目录上传          │
│  - 工具循环    │    │  search_reports      │    │  FTS5 全文检索     │
│  - 终止条件    │    │  read_report         │    │  导航索引 / 摘要   │
└───────┬────────┘    │  grep_code           │    └────────────────────┘
        │             │  read_file           │
        │             │  list_symbols        │    ┌────────────────────┐
        │             │  read_log            │───▶│  代码索引服务      │
        │             │  ask_user            │    │  仓库全局池        │
        │             └──────────────────────┘    │  worktree 检出     │
        │                                          │  ctags / ripgrep   │
┌───────▼────────────┐                            └────────────────────┘
│   LLM 网关         │ ──▶ 私有部署的 OpenAI 兼容模型服务
│  OpenAI 协议       │
└────────────────────┘

                  ┌──────────────────────────────┐
                  │   持久化（~/.codeask/）       │
                  │   data.db                     │
                  │   wiki/ sessions/ repos/      │
                  └──────────────────────────────┘
```

---

## 2. 核心数据流

### 2.1 会话 / 特性 / 仓库的关系（重要）

```
用户会话           ──不预绑特性──     全局特性池
   │                                       │
   │ Agent 第一轮                          │ 每个特性勾选关联：
   │ select_feature(...)                   │  - 全局代码仓（多个）
   ↓                                       │  - 全局 skill（多个，可 fallback 到全局）
本轮上下文：                               │  - 文档区
 - 选定特性的导航索引                      │  - 报告区
 - 选定特性勾选的代码仓                    │
 - 选定特性的 skill（特性优先；缺则用全局） │
                                           │
                                    全局代码仓池（注册即下载缓存）
                                    全局 skill 池
```

### 2.2 时序

以典型场景串起来：用户在统一会话页提问"为什么下单时偶尔抛 NullPointerException"，附一份崩溃日志。

```
[前端]            [API]              [Agent 编排器]        [工具集/索引]      [LLM 网关]
  │                 │                       │                     │                │
  │─POST /sessions─>│                       │                     │                │
  │<─session_id─────│                       │                     │                │
  │                 │                       │                     │                │
  │─POST /messages─>│ 保存日志附件          │                     │                │
  │ (问题+附件+         │ 创建任务、连 SSE      │                     │                │
  │  可选 feature_ids)  │                       │                     │                │
  │<==SSE 流开启===│                       │                     │                │
  │                 │                       │                     │                │
  │                 │  [若 feature_ids 为空] │                     │                │
  │                 │─run_agent_phase0────▶│                     │                │
  │                 │                       │ 系统提示注入特性清单+各摘要         │
  │                 │                       │ 调 LLM → select_feature(...) ──────▶│
  │                 │                       │<──tool_call─────────────────────────│
  │<──"定界中..."───│                       │                     │                │
  │                 │                       │                     │                │
  │                 │  [phase 1: 预检索]    │                     │                │
  │                 │  search_reports / search_wiki              │                │
  │                 │                       │                     │                │
  │                 │─run_agent_phase1────▶│                     │                │
  │                 │                       │ 组装系统提示:        │                │
  │                 │                       │  · 选定特性的摘要   │                │
  │                 │                       │  · 文档导航索引     │                │
  │                 │                       │  · 选定特性的 skill │                │
  │                 │                       │  · 关联代码仓+commit│                │
  │                 │                       │  · 预检索结果       │                │
  │                 │                       │  · 工具定义         │                │
  │                 │                       │  · 用户问题+日志    │                │
  │                 │                       │                     │                │
  │                 │                       │─call(messages)─────────────────────▶│
  │                 │<──token 流＋tool_use─────────────────────────────────────────│
  │<──流式渲染──────│                       │                     │                │
  │                 │                       │ 解析 tool_use:      │                │
  │                 │                       │  grep_code(...) ──▶│                │
  │                 │                       │<──匹配片段──────────│                │
  │<──"正在 grep..."（前端可视化）          │                     │                │
  │                 │                       │ ... 反复迭代 ...    │                │
  │                 │                       │ 模型给出最终回答+stop                │
  │                 │<──finish──────────────│                     │                │
  │<══SSE 关闭══════│                       │                     │                │
  │                 │ 持久化轮次记录        │                     │                │
```

### 2.3 自动定界

第一阶段 `select_feature` 工具调用：

```python
schema = {
  "type": "object",
  "properties": {
    "feature_ids": {"type": "array", "items": {"type": "string"}},
    "reason": {"type": "string"}
  }
}
```

**调用约束**（写在系统提示里）：

```
你需要先调用 select_feature 选择本次问题涉及的特性。
- 可以选 0 个（确认与所有特性无关，例如通用问题）、1 个、或多个
- 选择依据：用户问题、附件中关键报错、堆栈类名 vs 各特性摘要
- 只能调用一次

如果用户在请求里已显式指定 feature_ids（如前端手动选了），跳过 select_feature。
```

定界后才挂载该特性的：导航索引、关联代码仓、特性 skill。Skill 的拼接规则：**特性 skill 优先注入，特性没有该类 skill 时 fallback 到全局 skill**。

### 2.4 检索优先级策略

不靠 Agent 自由决策。两层强制：

**第一层：API 网关侧的预检索（同步、Phase 1 开始前）**

```python
async def preflight_retrieval(user_query, feature_ids, attachments):
    composite_q = build_query(user_query, attachments)
    reports = await wiki.search_reports(composite_q, feature_ids, top_k=5)
    docs    = await wiki.search(composite_q, feature_ids, kind="doc", top_k=5)
    return PreflightHits(reports=reports, docs=docs)
```

预检索结果作为初始系统消息注入 Agent，附带策略指令：

```
=== 预检索结果 ===
【已验证的历史定位报告】（优先级最高，命中即可直接引用）
[1] R-2026-031: 下单流程 NPE - User 字段未初始化  [score: 0.87]
[2] ...

【特性知识库匹配文档】
[1] 订单服务架构.md  [score: 0.72]
[2] ...

=== 回答策略（必须遵守）===
1. 先判断【报告】中是否有直接命中的同类问题。如有，直接引用报告结论。结束。
2. 若报告未直接命中，判断【知识库文档】是否能解答。如能，基于文档作答
   并标明引用，可调用 read_wiki_doc 取全文。结束。
3. 仅当上述两步都不足以解答，才进入代码检索推理阶段。
4. 任何时候发现代码线索与已知报告结论冲突，要明确指出。
```

**第二层：Agent 循环中的二次检索**

Agent 仍可调 `search_reports` / `search_wiki` 用更精炼的查询词，不依赖一次预检索结果。

**辅助面板进度展示**：

```
[阶段 0] 自动定界……      ✓ 选中 OrderService
[阶段 1] 检索历史报告……   ✓ 命中 2 条候选
[阶段 2] 模型判断……       ✗ 未直接匹配
[阶段 3] 检索知识库……     ✓ 命中 1 篇相关文档
[阶段 4] 模型判断……       ✗ 文档不足以解答
[阶段 5] 进入代码检索推理 ↓
[阶段 6] grep_code(...) ……
...
```

### 2.5 系统提示分层（Prompt Cache 友好）

从最稳定到最易变拼装，便于未来接 prompt caching：

```
[L0] 全局静态：Agent 角色定义、工具清单与协议        ← 跨所有会话不变
[L1] 特性切片：选定特性的摘要 + 导航索引 + 分析策略  ← 切特性才变
[L2] 仓库切片：每个绑定仓库的根目录、commit、语言    ← 切 commit 才变
[L3] 会话历史：先前轮次（含 tool 调用与结果）        ← 每轮追加
[L4] 本轮输入：用户问题 + 上传附件摘要               ← 每轮变
```

### 2.6 工具结果回填策略

- **截断**：单条工具结果 ≤ 4KB；超出返回前 N 条 + `truncated: true, hint: "用 read_file 取完整内容"`，把展开决策交还给模型
- **去重**：同一轮里同输入命中的工具结果直接复用缓存（编排器层）

### 2.7 SSE 事件类型

```
event: text_delta    data: {"text": "..."}
event: tool_call     data: {"name": "grep_code", "args": {...}}
event: tool_result   data: {"name": "grep_code", "summary": "命中 3 处", "truncated": false}
event: stage_transition data: {"from": "knowledge_retrieval", "to": "sufficiency_judgement"}
event: done          data: {"turn_id": "...", "stop_reason": "..."}
event: error         data: {"code": "...", "message": "..."}
```

### 2.8 终止条件

- **硬上限**：单轮最多 N 次工具调用（默认 N=20，可配置）。超出后强制让模型输出"目前能给出的最佳推断 + 仍未确认的点"
- **软上限**：上下文长度逼近模型窗口的 80% 时直接截断早期工具结果 + 提示告知（一期）；二期可上小模型总结
- **错误回收**：工具抛异常 → 异常作为 `tool_result` 回填，让模型尝试别的路径，不挂会话

### 2.9 持久化模型

每轮存 SQLite 一行：

```
turn_id, session_id, turn_idx, role('user'|'assistant'|'tool'),
content_json, tool_name?, tool_call_id?, created_at
```

历史会话恢复 = 按 `session_id, turn_idx` 拉记录重放气泡 + 工具调用记录。继续对话时把这些 turns 作为 message history 喂给 LLM；系统提示重新现场组装。

---

## 3. 关键组件 & 接口

### 3.1 Agent 编排器（`codeask.agent`）

```python
class AgentRunner:
    async def run(
        self,
        session_id: str,
        user_input: UserInput,            # 文本 + 附件 ID 列表
        feature_ids: list[str] | None,    # None=触发自动定界
    ) -> AsyncIterator[AgentEvent]:
        """运行 Agent 主循环：可能含 phase 0（定界）+ phase 1+（推理）"""
```

**职责边界**：只负责"定界 → 组装提示 → 调 LLM → 解析工具调用 → 派发到工具集 → 回填 → 迭代"。不直接读数据库、不直接读文件。

### 3.2 工具集（`codeask.tools`）

```python
class Tool(Protocol):
    name: str
    description: str          # 给 LLM 看的说明
    schema: dict              # JSON Schema for arguments

    async def call(self, args: dict, ctx: ToolContext) -> ToolResult: ...
```

`ToolContext` 携带 `session_id` / `feature_ids` / 当前会话可访问的 `repo_bindings`，工具据此做范围限定。

**一期工具清单（10 个）**：

| 工具 | 用途 | 范围限定 |
|---|---|---|
| `select_feature(feature_ids, reason)` | 自动定界（仅 phase 0 调用一次） | 必须从全局特性池选 |
| `search_wiki(query, feature_ids?)` | 关键词搜知识库文档（FTS5） | 默认本会话特性，可跨 |
| `read_wiki_doc(path)` | 取完整文档 | 路径必须在 wiki 树下 |
| `search_reports(query, feature_ids?)` | 搜历史定位报告（FTS5） | 仅返回**已验证**的报告 |
| `read_report(report_id)` | 取完整报告 | 必须 verified=true |
| `grep_code(pattern, repo, path_glob?)` | ripgrep 包装 | repo 必须在选定特性的关联仓库内 |
| `read_file(repo, path, line_start?, line_end?)` | 读代码文件片段 | 同上；默认按片段 |
| `list_symbols(repo, name?)` | 查符号定义位置（类/函数） | 走 ctags 索引 |
| `read_log(attachment_id, line_start?, line_end?)` | 分页读用户上传的日志 | 必须属当前 session |
| `ask_user(question, options?)` | 暂停 Agent，向用户提问 | 单会话最多 3 次 |

**`ask_user` 提示约束**：

```
仅在以下情况调用 ask_user：
1. 已有信息无法收敛到 ≤ 2 个候选根因
2. 你需要的事实只有用户能回答（如"最近改了什么"、"环境状态"），
   grep 代码无法得知
3. 单次会话最多 3 次主动提问，超过即被禁用
```

### 3.3 Wiki 库服务（`codeask.wiki`）

#### 内容模型

```
特性 (Feature)
├── 关联代码仓（多对多，从全局仓库池勾选）
├── 特性分析策略（在 skills 表中 scope='feature' 且 feature_id 指向本特性的所有记录）
├── 知识库文档区  ← 用户持续添加：业务文档、技能手册、配置说明…
└── 定位报告区    ← AI 生成 + 人工验证后归档；特性内共享、可跨特性搜索

全局分析策略池      ← 默认始终加载到 Agent；通用排障流程
全局代码仓池        ← 注册即缓存，特性按需勾选

分析策略注入规则：
  Agent 系统提示中先注入所有 global analysis policy（通用规则在前）
  → 选中特性后再追加该特性的 feature analysis policy（特定规则在后，可覆盖通用规则）
  没有"勾选关联"动作；特性分析策略保存到该特性后即自动生效
```

#### 接口

```python
class WikiService:
    # 特性
    def create_feature(name, description) -> Feature
    def list_features() -> list[Feature]
    def update_feature_repos(feature_id, repo_ids: list[str]) -> None

    # 文档/报告（CRUD）
    def add_document(feature_id, file, kind: Literal["doc", "report"]) -> Document
    def add_documents_from_dir(feature_id, dir_or_archive) -> list[Document]
    def list_documents(feature_id, kind?) -> list[Document]
    def update_document(...) / delete_document(...)

    # Skill（CRUD）
    def add_skill(scope: Literal["global", "feature"], feature_id?, file) -> Skill
    def list_skills(feature_id?) -> list[Skill]

    # 检索（FTS5；被工具集调）
    def search(query, feature_ids?, kind?, top_k=5) -> list[Hit]
    def get_navigation_index(feature_id) -> str   # 给系统提示用
    def get_feature_summary(feature_id) -> str    # 给系统提示用
    def get_features_brief() -> str               # phase 0 定界用：所有特性的简介

    # 报告专用
    def archive_report(session_id, content, feature_ids) -> Report
    def verify_report(report_id, verifier_id) -> None   # 闸门
```

#### 目录上传 + Markdown 相对引用

- 上传目录或 zip/tar 归档 → 服务器解包 → 保留原始相对路径存到 `wiki/<feature_id>/docs/<relative_path>`
- 上传时扫描 markdown：
  - `[xxx](./other.md)` `![](./img/x.png)` 等相对链接 → 落库时转成"内部引用"记录
  - Agent 调 `read_wiki_doc(path)` 取到的文档若含相对引用，工具结果元数据里附带"展开建议路径"
  - 前端预览时按内部引用图渲染（点击跳转）
- 引用图存表 `document_references(src_doc_id, target_doc_id, link_text, raw_target)`

#### 索引（一期：FTS5）

- SQLite FTS5 虚拟表：`docs_fts(title, body, tags)`、`reports_fts(title, body, error_signature)`
- 中文分词：`unicode61` + 程序内 `jieba` 预分词写入（避免长词检索不到）
- `search()` 内部用 BM25 排序；可选 AI 重排（一期不做，留接口）
- 报告：`verify_report` 时才写 `reports_fts`；取消验证时删除对应行

#### 索引重建时机

- 文档 / 知识库：上传/修改时异步任务：
  - 重算该文档的导航索引行（一句话摘要）→ 重算该特性摘要（200-500 字）→ 写 `docs_fts`
- 报告：`verify_report` 时入 `reports_fts`

### 3.4 代码索引服务（`codeask.code_index`）

#### 仓库全局池

仓库注册和特性解耦——所有仓库注册到全局，特性配置时勾选使用哪些。

```python
class CodeIndexService:
    # 全局仓库管理
    def register_repo(name, source_kind, git_url?, local_path?, default_branch) -> Repo
    def list_repos() -> list[Repo]
    async def prefetch_repo(repo_id) -> None       # 注册后触发后台 clone

    # 检索
    async def ensure_commit(repo_id, ref, session_id) -> str   # 返回 commit sha + worktree 路径
    async def grep(repo_id, commit, pattern, path_glob?) -> list[Match]
    async def read_file(repo_id, commit, path, lines?) -> str
    async def list_symbols(repo_id, commit, name?) -> list[Symbol]
```

#### 仓库源（两种）

**`source_kind = 'git'`**：
- 注册后异步 `git clone --bare <url> ~/.codeask/repos/<id>/.git`
- 缓存完成才标记 `ready=true`，前端可见

**`source_kind = 'local_dir'`**：用户预先放好的 git 工作目录：
- `git clone --bare --local <user_path> ~/.codeask/repos/<id>/.git`
- `--local` 让 git 自动用硬链接共享 .git 内 object 文件（只读，安全），不复制工作树，秒级完成

#### ensure_commit（每会话独立 worktree）

```python
async def ensure_commit(repo, commit, session_id):
    target = f"~/.codeask/repos/{repo.id}/worktrees/{session_id}"
    if not exists(target):
        run(["git", "-C", repo_git_dir(repo), "worktree", "add",
             "--detach", target, commit])
    else:
        run(["git", "-C", target, "checkout", commit])
    return target
```

**为什么走 `git worktree`**：

- 原方案 `cp -al` 硬链接复制有 inode 共享问题：多会话并发 git 操作时行为未定义
- `git worktree` 是 git 原生机制，**并发安全**；每会话一份独立工作树
- `local_dir` 模式仍然秒级（依靠 `git clone --local` 的 .git 内 object 硬链接）

**清理**：会话超期/删除 → `git worktree remove --force <session_path>`，由定时任务负责（见 §6）。

#### 实现策略（一期）

- `grep`：直接 shell out `rg --json` 解析
- `list_symbols`：`universal-ctags` 生成 tags，按 commit sha 缓存到 `~/.codeask/index/<repo>/<sha>.tags`，命中复用、未命中现建
- 大型 monorepo（50万+ 行）：
  - 系统提示告诉 Agent："这是 monorepo，先用 `list_symbols` 定位再 `grep`，并尽量指定 `path_glob`"
- LRU 清理：`index/<repo>/<commit>.tags` 默认保留最近 20 个

### 3.5 LLM 网关（`codeask.llm`）

```python
class LLMClient(Protocol):
    async def stream(
        messages: list[Message],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[LLMEvent]:
        """统一流式接口。"""

class OpenAICompatibleClient(LLMClient): ...    # 一期内网模型走这个
class AnthropicClient(LLMClient): ...           # 二期再实现
```

**配置**（SQLite 表，前端可改）：

```
id, name, protocol(openai/anthropic), base_url, api_key_encrypted,
model_name, max_tokens, temperature, is_default
```

支持多套配置切换，但一期不做大小杯分流（单一模型）。

### 3.6 API 网关（`codeask.api`）

```
# 会话
POST   /api/sessions                       创建会话
GET    /api/sessions                       列出
GET    /api/sessions/{id}                  详情+轮次（同时刷新 last_active_at）
POST   /api/sessions/{id}/messages         发消息（返回 SSE 流；可选 feature_ids）
DELETE /api/sessions/{id}                  删除
POST   /api/sessions/{id}/messages/{tid}/answer    用户答 ask_user

# 附件
POST   /api/sessions/{id}/attachments      上传日志

# 报告
POST   /api/sessions/{id}/report           从会话生成报告
POST   /api/reports/{id}/verify            验证报告（闸门）
GET    /api/reports?feature=&q=            搜报告（前端独立搜）

# Wiki / 特性
GET    /api/features                       特性列表
POST   /api/features                       新建特性
PUT    /api/features/{id}                  改名 / 描述
PUT    /api/features/{id}/repos            勾选关联代码仓
POST   /api/features/{id}/documents        上传单个文档
POST   /api/features/{id}/documents/bulk   上传目录或归档
GET    /api/features/{id}/documents
DELETE /api/documents/{id}

# Skill（提示词模板）
GET    /api/skills?scope=                  全局/特性 skill 列表
POST   /api/skills                         上传（scope=global 或 scope=feature&feature_id=）
DELETE /api/skills/{id}

# 全局代码仓
GET    /api/repos                          仓库列表（含 ready 状态）
POST   /api/repos                          注册仓库（git / local_dir，触发后台 prefetch）
DELETE /api/repos/{id}

# LLM 配置
GET    /api/llm-configs
POST   /api/llm-configs
PUT    /api/llm-configs/{id}

# 系统
GET    /api/healthz
GET    /api/metrics
```

---

## 4. 存储模型

### 4.1 文件目录布局

```
~/.codeask/                          # 部署根目录（可配置）
├── data.db                          # SQLite 主库（一期不再有 vectors.db）
├── wiki/
│   └── <feature_id>/
│       ├── docs/<原始相对路径>      # 保留目录结构存盘
│       └── reports/<report_id>.md
├── skills/
│   ├── global/<skill_id>.md         # 全局 skill
│   └── feature/<feature_id>/<skill_id>.md
├── sessions/
│   └── <session_id>/
│       ├── attachments/<att_id>.<ext>     # 用户上传的日志等附件
│       └── turns/<turn_id>.jsonl          # Agent 轨迹日志
├── repos/
│   └── <repo_id>/
│       ├── .git/                    # bare repo（git 仓库的中心）
│       └── worktrees/<session_id>/  # 每会话独立工作树
├── index/
│   └── <repo_id>/<commit>.tags      # ctags 缓存
└── logs/
    └── server.log                   # 应用日志
```

### 4.2 SQLite 主库（`data.db`）

```
features                  -- 特性
  id, name, description, summary_text, summary_updated_at, created_at

feature_repos             -- 特性 ↔ 代码仓 多对多
  feature_id, repo_id

documents                 -- 知识库文档（kind=doc 或 report 共用）
  id, feature_id, kind('doc'|'report'), title, file_path, file_ext,
  size_bytes, nav_index_line,
  uploaded_by, created_at, updated_at

document_references       -- Markdown 内部引用图
  src_doc_id, target_doc_id?, link_text, raw_target

reports                   -- 报告专用扩展（与 documents 一对一，kind='report'）
  document_id PK, session_id, verified, verified_by, verified_at,
  meta_json                           -- AI 抽取的结构化字段（错误码/异常类/模块）

skills                    -- 提示词模板
  id, scope('global'|'feature'), category, title, file_path,
  description, created_at

repos                     -- 代码仓库（全局池）
  id, name, source_kind('git'|'local_dir'),
  git_url?, local_path?, default_branch, ready, created_at

sessions                  -- 会话
  id, title, created_by, created_at, updated_at,
  last_active_at,                     -- 24h 清理依据
  cleaned, cleaned_at                 -- 软清理标记

session_features          -- 会话每次用户消息触发定界后选定的特性（user_turn_idx = 触发本次定界的用户消息 turn_idx）
  session_id, user_turn_idx, feature_id

session_repo_bindings     -- 会话挂载的仓库（含 commit）
  session_id, repo_id, ref, commit_sha

session_turns             -- 会话轮次（消息）
  id, session_id, turn_idx, role('user'|'assistant'|'tool'),
  content_json, tool_name?, tool_call_id?, created_at

session_attachments       -- 会话附件
  id, session_id, file_name, file_path, content_type, size_bytes,
  cleaned, created_at

llm_configs               -- LLM 配置
  id, name, protocol, base_url, api_key_encrypted, model_name,
  max_tokens, temperature, is_default, created_at

system_settings           -- 全局设置（KV）
  key, value_json
```

#### FTS5 虚拟表

```
docs_fts(document_id UNINDEXED, title, body, tags, tokenize='unicode61')
reports_fts(document_id UNINDEXED, title, body, error_signature, tokenize='unicode61')
```

**写入时机**：

- 文档：上传/更新后异步任务写 `docs_fts`
- 报告：`verify_report` 时写 `reports_fts`；取消验证时删除

**`session_turns.content_json` 内容形态**：

```json
// 用户消息
{"text": "...", "attachments": ["att_1", "att_2"]}

// 助手消息
{"text_chunks": ["...", "..."], "tool_calls": [{"id": "tc_1", "name": "grep_code", "args": {...}}]}

// 工具结果
{"tool_call_id": "tc_1", "result": "...", "truncated": false}
```

### 4.3 Schema 版本控制

走 **Alembic**：

```
codeask/
└── migrations/
    ├── env.py
    └── versions/
        ├── 0001_initial_schema.py
        ├── 0002_add_reports_meta.py
        └── ...
```

启动时自动 `alembic upgrade head`。SQLite `alembic_version` 表记录当前版本。

JSON 字段（如 `reports.meta_json`）的内部结构变更也走 migration 搬数据，避免运行时兼容判断让代码越来越脏。

### 4.4 加密 / 敏感字段

- `llm_configs.api_key_encrypted`：Fernet 对称加密（master key 走 `CODEASK_MASTER_KEY` 环境变量）
- 其他字段不加密——内网部署、SQLite 文件本身依靠服务器文件权限保护

---

## 5. 一期范围（MVP）

### 5.1 In Scope（必须有）

**端到端推理回路**

- Agent 编排器（含 phase 0 定界） + LLM 网关（OpenAI 兼容协议，单一模型）
- 工具集 10 个：`select_feature` / `search_wiki` / `read_wiki_doc` / `search_reports` / `read_report` / `grep_code` / `read_file` / `list_symbols` / `read_log` / `ask_user`
- 预检索（报告 → 知识库 → 代码）+ 提示约束
- 终止条件（硬上限 20 次工具调用、软上限上下文 80%、错误回收）

**Wiki 库**

- 特性 CRUD + 关联代码仓勾选 + 上传特性专属 skill
- 文档单个 + 目录/归档批量上传，保留目录结构
- Markdown 相对引用解析（落库 + 前端跳转）
- 文档导航索引 + 特性级摘要（AI 生成）
- 文档+报告 FTS5 全文检索
- 报告人工验证闸门
- 报告搜索 API（前端独立搜索框）
- 全局 skill 池（始终加载）+ 特性专属 skill（选中特性后追加）

**代码索引**

- 仓库全局池（`git` 与 `local_dir` 两种来源；注册即异步 prefetch）
- 每会话独立 worktree 检出（`git worktree add`）
- ctags 符号表按 commit 缓存
- ripgrep 包装

**会话**

- 创建 / 列表 / 删除 / 历史恢复
- **不预绑特性**：用户可手动选 / Agent 自动定界
- 附件上传（文本/日志类，二进制 reject）
- 流式 SSE（含 stage 事件给辅助面板）
- 报告生成 + 下载 + 提交验证

**前端**

- 主页面：统一会话页 / Wiki 库管理 / 特性详情（含其代码仓与 skill 勾选） / 全局配置（LLM、代码仓池、全局 skill 池）
- 会话页：左会话列表 / 中聊天流 / 右辅助面板（特性显示 + 附件 + 工具调用流 + ask_user 交互）
- Markdown 渲染 + 代码高亮 + 内部引用跳转
- 简易 master token 鉴权

**定时任务**

- 24h 未活跃会话自动清理（worktree + 附件）
- 磁盘水位线保护（软 10GB / 硬 20GB，可配置）

**部署**

- `start.sh` 启动脚本
- Alembic 自动迁移
- 配置 + 日志写到 `~/.codeask/`

### 5.2 Out of Scope（明确不做）

| 推迟到 | 项 |
|---|---|
| 二期 | npm 包 `@codeask/cli` 一键安装 |
| 二期 | 文档向量检索（一期 FTS5 够用，二期视需要） |
| 二期 | 可执行 skill（一期仅 Markdown 提示词模板） |
| 二期 | 大小杯模型分流 / Anthropic 协议适配 |
| 二期 | 问题指纹去重（同型问题预警） |
| 二期 | 假设/证据面板（前端复杂交互） |
| 二期 | `find_references` 调用图工具 |
| 二期 | 增量代码索引（一期按 commit 全量重建） |
| 二期 | prompt caching 适配 |
| 二期 | 软上限触发的"小模型总结早期工具结果" |
| 二期 | 日志脱敏 |
| 二期 | AI 重排序（FTS5 检索后） |
| 三期 | 多用户精细权限 / SSO |
| 三期 | 操作审计 / 监控仪表 |
| 三期 | 检索权重可视化调参 |

### 5.3 一期不做但留扩展点

- `LLMClient` 是 protocol，二期可挂 `AnthropicClient`
- `Tool` 注册表机制，加新工具不动 Agent
- 仓库 `source_kind` 已留枚举位
- DB 走 Alembic
- 后端默认从 `~/.codeask/` 读配置，**不依赖工作目录**
- 前端构建产物固定输出 `web/dist/`，FastAPI 已能挂静态资源
- `WikiService.search` 内部一期是 FTS5，二期切到向量只动一处实现
- Skill 表已留 `category` 字段，二期可执行 skill 的 manifest 字段可加 migration 扩展

### 5.4 一期完成定义（DoD）

走完这条端到端路径才算 MVP 上线：

```
1. ./start.sh  → 浏览器打开 http://localhost:7100，输入 master token
2. 全局配置：注册 LLM；注册 2 个代码仓（1 个 git 模式 + 1 个 local_dir 模式）
3. 等代码仓 prefetch 完成（前端 ready=true）
4. 创建特性 "OrderService"，勾选关联 1 个代码仓；上传 1 个文档目录（含相对引用的 markdown）；
   上传 1 个特性 skill；再创建一个全局 skill
5. 新建会话，不选特性，上传一份崩溃日志，提问
6. 看到流式回答 + 辅助面板的工具调用过程：
   - phase 0 select_feature → ✓ 选中 OrderService
   - 预检索 → 报告未命中 → 文档未命中 → 进入代码推理
   - grep_code / read_file / list_symbols 调用可见
7. Agent 触发一次 ask_user，前端正确渲染并能回答
8. 一键生成报告 → 验证 → 下载
9. 关闭浏览器 25 小时后回来：会话仍可看历史记录；附件标记已清理；继续提问会自动重建 worktree
10. 重启 codeask → 历史会话仍在
```

---

## 6. 非功能需求

### 6.1 测试策略

**单元测试**（pytest）—— 全跑 < 10s
- 工具集每个 Tool 独立测：传不同 args 验返回结构
- 提示词组装函数：固定输入 → 固定输出（snapshot test）
- 数据库迁移正向/逆向各跑一遍
- FTS5 切片函数、Markdown 引用解析等纯逻辑

**集成测试**（pytest + httpx）—— 全跑 < 60s
- 用 `tmp_path` 起一份临时 `~/.codeask/`，跑真 SQLite + FTS5
- 用真 ripgrep + ctags + git 对内置的小测试仓库（30 个文件）执行
- LLM 网关用 `MockLLMClient`：根据预录的 message → 输出脚本回放工具调用序列
- 端到端覆盖：创建特性 → 关联仓库/skill → 上传文档目录 → 创建会话 → phase 0 定界 → phase 1+ 推理 → 拿到回答 → 生成报告 → 验证报告 → 24h 清理任务跑通

**Agent 行为评估**（独立目录 `eval/`，不在 CI 默认跑）
- 一组金标准案例：日志 + 期望定位结论。跑真模型，人工评审输出
- 用例覆盖：定界正确 / 报告命中 / 文档命中 / 代码推理 / ask_user 触发 / 死循环边界
- 出 markdown 报告（每用例输入、Agent 轨迹、判定）放 `eval/reports/`

CI（一期最小）：单元 + 集成测试 + lint。

### 6.2 错误处理

**核心原则**：用户面前不出现 stack trace，但 SSE 通道必须把"出问题了"传到前端。

| 层 | 处理 |
|---|---|
| 工具调用失败 | 异常→`tool_result` 回填错误描述，Agent 继续；不挂会话 |
| LLM 调用超时/限流 | 网关层指数退避重试（最多 3 次），仍失败 → SSE `error` 事件 + 会话停在当前轮 |
| Agent 死循环 | 工具调用上限触发 → 让模型输出"目前能给出的最佳推断"再终止 |
| 仓库 prefetch 失败 | 注册时立即测试连通性 / 路径存在性；前端展示 `ready=false` 与失败原因 |
| 仓库 worktree 失败 | 工具结果给"代码暂不可达"，Agent 切别的方向 |
| Alembic 迁移失败 | 启动直接退出，错误日志显式写出（不允许"半迁移"状态进入服务） |
| 文件解析异常 | 单个文档失败不阻塞批量入库，写错误标记到 `documents` 行 |
| 上传超大 | 服务端硬限制（默认日志 10MB，目录归档 100MB） |

**日志策略**：

- 应用日志写 `~/.codeask/logs/server.log`，按天滚动
- 每个 Agent 运行写一份"轨迹日志" `sessions/<session_id>/turns/<turn_id>.jsonl`：每一步系统提示、工具调用、工具结果、模型输出原文都落盘

### 6.3 安全

| 项 | 一期 | 备注 |
|---|---|---|
| 部署模式 | 默认监听 `127.0.0.1`，跨机访问需显式配 host | 防默认 `0.0.0.0` 暴露 |
| 鉴权 | 单一 master token（部署时配置），前端登录输入 | 不做用户体系 |
| LLM API Key 加密 | Fernet 对称加密（master key 走 `CODEASK_MASTER_KEY`） | |
| 日志脱敏 | 一期不做（私有模型，数据不离内网） | 二期再做 |
| 文件类型校验 | 上传按 MIME + 后缀双重检查；二进制日志 reject | |
| 路径遍历 | 所有读文件接口走 `resolve_within(base_dir, user_path)` 校验 | 防 `../` 越权 |
| Agent 代码访问范围 | 工具集强制 `repo_id` 必须在选定特性的关联仓库内 | |
| Shell 注入 | ripgrep / ctags / git 调用一律 `subprocess` 列表参数，无 `shell=True` | |
| 上传 skill 内容 | 仅文本（Markdown），无执行能力 | 一期不引入沙箱风险 |

**主动留口子（二期补）**：

- 用户体系 / 多租户
- 操作审计表
- 模型流量配额（限速）
- 可执行 skill 的沙箱方案

### 6.4 性能预算

| 操作 | 一期目标 | 备注 |
|---|---|---|
| 文档上传后可被检索 | < 5s（小文档 < 100KB） | 异步入库 |
| 报告搜索（前端搜索框） | < 200ms | FTS5 |
| `grep_code` 单次调用 | < 1s（50万行 monorepo） | rg 本身够快 |
| `list_symbols` 命中缓存 | < 100ms | |
| `list_symbols` 未命中（首次建索引） | < 30s | 50万行 ctags 一次性 |
| 仓库 `local_dir` 注册到 ready | < 5s | `git clone --bare --local` |
| 仓库 `git` 首次 prefetch | 视网络 | 不做承诺 |
| `ensure_commit` 创建 worktree | < 5s | `git worktree add` |
| Agent 单轮端到端（含 5 次工具调用） | < 15s（不含模型推理） | 模型推理另算 |
| 历史会话恢复打开 | < 500ms | 按 turn_idx 拉记录 |
| 启动到能用 | < 5s（迁移已跑过） | |
| 24h 清理任务单次跑 | < 5s（小团队规模） | 每小时一次 |

**资源占用上限**（建议运行环境）：

- 内存：< 1GB（含 Python + 加载到内存的 ctags 索引）
- 磁盘：worktrees + 索引按 LRU + 24h 清理控制；软 10GB / 硬 20GB（可配置）

### 6.5 定时任务（APScheduler）

| 任务 | 频率 | 行为 |
|---|---|---|
| 会话清理 | 每小时 | `last_active_at < now-24h` 且未 cleaned 的会话：删 worktree + 删附件文件，标记 `cleaned=true`；保留 DB 对话记录 + 轨迹日志 |
| 磁盘水位线检查 | 每 30 分钟 | 占用 > 软上限 → 把 6h 未活跃的也清掉；> 硬上限 → 拒绝新会话直到清理 |
| ctags 缓存 LRU | 每天 | 保留最近 20 个 commit 的 tags |

**激活定义**：

- 有新消息（用户提问 / Agent 回答 / ask_user 答复）
- 用户在前端打开过会话详情（GET `/api/sessions/{id}` 触发更新 `last_active_at`）

**重新激活已 cleaned 会话**：

- 自动重建所需 worktree（按需 ensure_commit）
- 提示用户"附件已清理，请重新上传"
- DB 对话记录可正常查看

配置项：`CODEASK_SESSION_INACTIVE_HOURS=24`、`CODEASK_DISK_SOFT_LIMIT_GB=10`、`CODEASK_DISK_HARD_LIMIT_GB=20`。

### 6.6 可观测性（一期最低限度）

- `/api/healthz` 健康检查
- `/api/metrics` 简单状态：会话数、活跃 Agent 数、最近错误数、磁盘占用、FTS5 行数、worktree 数
- 应用日志结构化（JSON Lines），关键事件打 trace_id 串起一次会话所有日志

二期再考虑接 Prometheus / OpenTelemetry。

---

## 7. 技术栈选型

| 层 | 选型 | 理由 |
|---|---|---|
| 后端 | Python 3.11+ + FastAPI + uvicorn | RAG / GitPython / tree-sitter 生态成熟 |
| ORM / Migration | SQLAlchemy 2.x + Alembic | 标准组合，schema 版本控制 |
| 全文检索 | SQLite FTS5 + jieba 中文分词 | 内置零依赖，团队级文档量够用 |
| 代码符号 | universal-ctags | 成熟、跨语言 |
| 全文/正则 | ripgrep | 快、生态成熟 |
| Git 操作 | shell out git CLI（含 worktree） | GitPython 性能不如直接 CLI |
| 配置加密 | cryptography (Fernet) | |
| 定时任务 | APScheduler | 嵌入进 FastAPI 进程 |
| 测试 | pytest + httpx + pytest-asyncio | |
| 前端 | React + Vite + TypeScript | 周边组件最齐 |
| 前端 UI 组件 | shadcn/ui 或同类轻量库 | |
| Markdown 渲染 | react-markdown + rehype-highlight | |
| 状态管理 | Zustand 或 React Query | 实施时再定具体边界 |
| 流式通信 | EventSource (SSE) | |

---

## 8. 演进路线

| 阶段 | 关键交付 |
|---|---|
| **一期 MVP（本文档主体）** | 端到端 Agent 排障；自动定界；统一会话；Wiki/报告/skill 管理；目录上传 + 内部引用；FTS5 检索；代码全局池 + worktree；24h 清理；`start.sh` 部署 |
| **二期** | npm 包一键安装；可执行 skill（沙箱）；文档向量检索（FTS5 不够时）；问题指纹去重；假设/证据面板；`find_references`；增量代码索引；prompt caching；大小杯模型分流；Anthropic 协议；日志脱敏；AI 重排序 |
| **三期** | 多用户体系 / 权限 / SSO；操作审计；监控仪表；检索权重调参 UI；视负载情况拆出 `code-index` 独立服务 |

---

## 9. 关键决策汇总（FAQ）

| 决策 | 选择 | 主要理由 |
|---|---|---|
| 推理回路 | Agentic Loop（工具调用迭代） | Bug 定位天然多步推理 |
| 模型部署 | 私有部署（OpenAI 兼容协议） | 内网代码/日志/文档安全 |
| 全局每日蒸馏 | 取消 | 改为"特性摘要 + 文档导航索引 + 按需检索" |
| 代码向量化 | 不做 | 堆栈关键字 → ripgrep 最准最快 |
| 文档向量化 | 一期不做 | 团队级文档量 FTS5 够；架构留扩展点 |
| 检索优先级 | 报告 → 知识库 → 代码（强约束） | 已沉淀经验优先复用 |
| 报告归档 | 人工验证闸门 | 防错误经验污染未来检索 |
| 会话与特性 | 不预绑，自动定界 | 用户体验：一个会话窗口跨特性 |
| 仓库与特性 | 解耦：全局池 + 特性勾选 | 仓库共享，配置不重复 |
| Skill 形态 | 一期 Markdown 提示词模板 | 安全简单；二期再上可执行 |
| Skill 层级 | 全局始终加载 + 特性专属在选中后追加 | 通用经验 + 特性专属，无勾选操作 |
| 仓库源 | git + local_dir 双模式 | local_dir 用 `git clone --bare --local` 秒级 |
| 工作树管理 | `git worktree add`，每会话独立 | 杜绝硬链接 inode 共享并发问题 |
| 会话清理 | 24h 未活跃自动清重资产 | 防磁盘打爆；保留 DB 记录 |
| 部署形态 | 一期 `start.sh`，二期 npm | 一期能用最优先 |
| 数据库 | SQLite + FTS5 | 小团队规模够用；零中间件 |
| Schema 版本 | Alembic | 升级兼容性标配 |
| 进程拓扑 | 单进程模块化（一期） | 减少运维成本；保留 protocol 接口便于二期拆 |

---

## 10. 待办（实施阶段细化）

下列点本文档不展开，留给"实施计划"阶段：

- 具体表字段类型 / 索引 / 外键约束
- 每个 Tool 的 JSON Schema 完整定义
- 系统提示完整文案（中文 + 各阶段指令）
- Markdown 引用解析的完整规则（图片、跨目录、锚点等）
- ctags 配置（语言扩展、过滤规则）
- 中文分词策略（jieba 词典、自定义词、停用词）
- 前端组件库与具体页面线框图
- start.sh / 部署脚本细节
- CI 配置（GitHub Actions / Gitea Actions 视部署环境）
- 一期 eval 金标准案例集
- 24h 清理的并发锁与冲突策略

---

**END**
