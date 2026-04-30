# 代码索引与仓库管理设计

> 本文档属于 v1.0 SDD，描述全局仓库池、Feature 与代码仓的关联、worktree 隔离和代码检索工具。
>
> 产品契约见同版本 `prd/codeask.md`。当 SDD 与 PRD 冲突时，以 PRD 为准。

## 1. 目标

代码索引服务负责让 Agent 在明确范围内读取实时代码。它需要支持多语言、多仓库和按 commit 的代码一致性。

落地 PRD §4.2 的两条产品承诺：

- **全局仓库池**：配置页填写仓库名称 + URL，后端**异步下载到公共目录**，用户无感等待
- **会话级代码访问隔离**：使用 **git worktree** 把代码仓挂载到会话独立空间，多人多会话不互相干扰；轻量、共享 git 数据、不重复占磁盘

一期不做代码向量库。代码定位以 Git worktree、ripgrep、universal-ctags 和文件片段读取为主。

## 2. 全局仓库池

仓库注册到**全局池**（公共目录），任意特性都可以勾选关联同一个仓库——不重复 clone、不重复占磁盘。

支持来源：

| 来源 | 说明 |
|---|---|
| `git` | 远程 Git URL，注册后异步 clone bare repo 到全局池 |
| `local_dir` | 本机已有 Git 工作目录，通过 `git clone --bare --local` 建缓存到全局池 |

### 2.1 公共目录布局

```text
~/.codeask/repos/<repo_id>/
├── bare/                     ← clone --bare 出来的 git 数据，全局池共享
└── worktrees/                ← 会话级 worktree（详见 §5）
    └── <session_id>/
```

`bare/` 是仓库底层 git 数据库，所有特性、所有会话共享。这是 worktree "轻量、不重复占磁盘"承诺的物理基础。

### 2.2 异步 clone 状态

仓库注册后立即返回 `repo_id`，clone 在后台进行。状态机：

```text
registered → cloning → ready
                ↓
              failed   （UI 必须可见错误，否则用户无感知）
```

`ready` 之前关联到该仓库的特性可以照常工作（仅文档级回答），但代码工具会返回结构化 `tool_result`：

```json
{ "ok": false, "error_code": "REPO_NOT_READY", "message": "仓库仍在预取" }
```

详见 `agent-runtime.md` §12 错误回收。

## 3. Feature 与仓库的关联

**Feature 定义**（与 PRD §4.1 对齐，见 `wiki-search.md` §2）：

> Feature 是"用户自定义粒度的、有 owner 的、关联代码仓的知识集合"。

- **粒度不强制**：可以是业务模块、微服务、跨服务能力
- **可不互相关联**：特性之间不要求层级或上下游关系
- **关联方式**：在特性管理页**勾选**全局池中的仓库（多对多）

```text
全局仓库池：[order-service]  [payment-gateway]  [settlement-service]
                  ↑↑                ↑↑                  ↑
                  ││                ││                  │
特性"订单":      勾选              勾选                 ✗
特性"结算":      勾选              ✗                   勾选
```

同一个仓库可被多个特性勾选；特性 vs 仓库是多对多关系；删除特性不影响仓库本身（仓库仍在全局池）。

## 4. 版本模型

代码证据最终以 commit 为准。

输入可以是：

- commit sha
- branch
- tag
- 默认分支
- 日志中识别的构建号或镜像 tag 映射结果

branch/tag 需要解析为 commit 后使用。

## 5. 默认分支预查

当用户未提供版本时，系统可以用默认分支做探索性预查。

限制（与 `debugging-workflow.md` §6 一致）：

- UI 明确展示当前使用默认分支。
- 回答标注"未确认故障版本"。
- 正式报告必须重绑定明确 commit。

## 6. Worktree（会话级隔离）

每个会话按 `repo_id + commit` 准备独立 worktree：

```text
~/.codeask/repos/<repo_id>/worktrees/<session_id>/
```

使用 `git worktree add --detach <commit>`。

### 6.1 为什么用 worktree 不用 clone

PRD §4.2 锁定的三条性质：

| 性质 | worktree 怎么做到 |
|---|---|
| **轻量** | worktree 只是 checkout 工作树，不复制 git 历史 |
| **共享 git 数据** | 所有 worktree 指向同一个 `bare/` git 数据库 |
| **不重复占磁盘** | 文件系统层只存 checkout 出来的工作文件，commit/tree 数据全局唯一 |

普通 `git clone` 会复制整个 git 历史，多个会话 = 多倍空间；worktree 则只占一份 + checkout。

### 6.2 生命周期

```text
会话开始用代码工具
→ 按需创建 worktree（懒加载）
→ Agent 通过工具读取
→ 会话 24h 未活跃
→ 定时任务清理 worktree（详见 deployment-security.md §7）
→ 用户后续重新提问 → 按需重建 worktree
```

清理 worktree 不影响 DB 中的对话记录、轨迹日志、证据；只是把工作树文件从磁盘删除。

## 7. 检索工具

| 能力 | 实现 |
|---|---|
| 全文搜索 | `rg --json` |
| 文件读取 | 路径白名单 + 行号片段 |
| 符号查找 | universal-ctags |
| 缓存 | 按 repo + commit 缓存 tags |

工具接口详见 `tools.md`。所有工具调用都通过 `code-index` 服务，Agent 不直接访问文件系统（详见 `agent-runtime.md` §7 代码调查）。

## 8. 多语言策略

一期以 universal-ctags 覆盖多语言符号定位。未来可扩展：

- tree-sitter：更稳定的结构化语法解析。
- LSP：定义、引用、类型信息。
- 调用图：跨文件或跨服务影响分析。

扩展不应改变 Agent 的工具接口，只替换 `CodeIndexService` 内部实现。

## 9. 与 PRD 的对齐

本文已按 `prd/codeask.md` §9 对齐表更新，主要变化：

- §3 新增 Feature 定义和"特性 ↔ 仓库 多对多关联"显式描述（落地 PRD §4.1 / §4.2）
- §1 / §2 显式标注"全局仓库池"+"公共目录"+"用户无感的异步 clone"，落地 PRD §4.2 三条承诺
- §2.1 / §2.2 新增公共目录布局和异步 clone 状态机
- §6 worktree 新增 §6.1"为什么用 worktree"小节，把 PRD §4.2 锁定的三条性质（轻量 / 共享 git 数据 / 不重复占磁盘）显式映射到实现
- §6.2 worktree 生命周期与 `deployment-security.md` §7 定时任务对齐
