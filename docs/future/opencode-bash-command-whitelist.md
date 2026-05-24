# OpenCode Bash 命令白名单规划

> 状态：Future / 未排入具体版本
> 背景：v1.0.4 已接入 OpenCode 作为 Agent Backend，当前默认禁用 `bash`。后续源码调查场景需要支持 `git log`、`git diff`、`git show` 等只读命令，但不能直接放开任意 shell。
> 关联：`docs/v1.0.4/design/opencode-backend.md`、`docs/future/opencode-integration.md`

## 1. 问题背景

CodeAsk 使用 OpenCode 后，模型具备 `read`、`grep`、`glob` 等文件调查能力，但当前默认禁用 `bash`。这能避免模型通过 shell 绕过 CodeAsk 的工具边界，但也限制了真实源码调查中的常见动作：

- 查看提交历史：`git log`
- 查看提交内容：`git show`
- 查看差异：`git diff`
- 查看文件归属：`git blame`
- 查看仓库状态：`git status`
- 查看文件清单：`git ls-files`
- 查看当前提交：`git rev-parse`

这些能力对问题定位和代码考古有价值，尤其是用户要求“看源码”“分析最近变更”“定位这个行为从哪个提交引入”时。

但是直接设置 `bash = allow` 风险过大。即使每个会话都有自己的 workspace，shell 也不是目录级安全边界。仅设置 cwd 不能阻止命令访问会话目录外的文件、环境变量、网络、系统临时目录或执行破坏性操作。

因此未来能力应采用“管理员可配置的 bash 命令白名单”，而不是开放全部 bash。

## 2. 设计目标

1. 默认仍然禁用任意 bash。
2. admin 可以在全局设置中配置允许的 bash 命令白名单。
3. 白名单第一版重点覆盖只读 Git 调查命令。
4. 白名单命令必须限制在当前 OpenCode 会话 workspace 内执行。
5. 白名单配置必须可审计、可关闭、可恢复默认。
6. Agent 行动轨迹需要展示命令、工作目录、耗时、退出码、截断状态和拒绝原因。
7. 前端展示和接口返回不能泄露宿主机绝对路径，只展示 session workspace 相对路径。
8. 不把白名单能力写成模型或厂商特判，不根据用户问题关键字强行触发；是否使用命令仍由模型通过 OpenCode 自主决策。

## 3. 非目标

1. 不开放任意 shell。
2. 不允许用户级配置第一版直接覆盖全局安全策略。
3. 不允许新增复杂的用户自定义脚本能力。
4. 不把 command whitelist 做成代码仓类型、特性名称或模型名称的特判。
5. 不通过前端过滤掩盖敏感信息；后端返回给前端的事件数据也需要脱敏。
6. 不保证第一版覆盖所有命令。未列入白名单的命令应明确拒绝，而不是静默失败。

## 4. 风险边界

即使 OpenCode 的 `bash` 在 session workspace 下运行，也不能把 workspace 当作 OS 级沙箱。以下行为需要被拒绝或避免：

- 文件破坏：`rm`、`mv`、`cp` 覆盖、`sed -i`、`python -c` 写文件
- Git 破坏：`git reset`、`git clean`、`git checkout`、`git switch`、`git rebase`、`git merge`
- 网络访问：`curl`、`wget`、`ssh`、`scp`、`nc`
- 环境探测：`env`、`printenv`、读取 home 目录敏感文件
- 进程控制：`kill`、后台常驻进程、长时间运行命令
- 系统探测：读取 `/etc`、`/proc`、`/home`、`/root`

后续如果需要更强能力，应优先引入 OS 级隔离，例如容器、seccomp、namespace、chroot、Firejail 或专用 sandbox，而不是通过字符串规则假装安全。

## 5. 第一版建议白名单

第一版只开放只读 Git 调查命令，且限制输出长度和执行超时。

建议默认允许：

```text
git status
git status *
git log
git log *
git show
git show *
git diff
git diff *
git blame
git blame *
git ls-files
git ls-files *
git rev-parse
git rev-parse *
```

建议显式拒绝：

```text
git reset *
git clean *
git checkout *
git switch *
git restore *
git add *
git commit *
git push *
git pull *
git fetch *
git merge *
git rebase *
git apply *
git am *
git config *
git update-index *
git submodule *
```

注意：OpenCode permission 规则存在匹配顺序问题，具体配置时必须结合 OpenCode 当前版本的 permission 解析逻辑验证“最后匹配规则 wins”或等价行为，避免宽泛 allow 覆盖危险 deny。

## 6. Admin 配置能力

### 6.1 全局开关

全局设置中增加：

```text
OpenCode Bash 白名单：启用 / 禁用
```

默认：

```text
禁用
```

禁用时生成的 `opencode.json` 仍然保持：

```json
{
  "permission": {
    "bash": "deny"
  }
}
```

### 6.2 白名单配置

admin 页面提供一个独立设置页或设置分组：

```text
Agent Runtime / OpenCode 权限
```

字段建议：

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `bash_whitelist_enabled` | boolean | `false` | 是否启用 bash 白名单 |
| `allowed_patterns` | list[string] | 只读 Git 默认集 | 允许的命令 pattern |
| `denied_patterns` | list[string] | 危险 Git 默认集 | 显式拒绝的命令 pattern |
| `timeout_seconds` | integer | `10` | 单条命令最长运行时间 |
| `max_output_chars` | integer | `20000` | 返回给模型和前端的最大输出 |
| `working_directory_scope` | enum | `session_workspace` | 第一版固定为会话 workspace |

第一版可以只提供“启用白名单”和“恢复默认规则”两个按钮，规则编辑能力可以后置。这样能降低误配置风险。

### 6.3 配置存储

建议存入全局配置表，而不是写死在代码中。配置结构可以类似：

```json
{
  "enabled": false,
  "allowed_patterns": [
    "git status",
    "git status *",
    "git log",
    "git log *",
    "git show",
    "git show *",
    "git diff",
    "git diff *",
    "git blame",
    "git blame *",
    "git ls-files",
    "git ls-files *",
    "git rev-parse",
    "git rev-parse *"
  ],
  "denied_patterns": [
    "git reset *",
    "git clean *",
    "git checkout *",
    "git switch *",
    "git restore *",
    "git add *",
    "git commit *",
    "git push *",
    "git pull *",
    "git fetch *",
    "git merge *",
    "git rebase *",
    "git apply *",
    "git am *",
    "git config *",
    "git update-index *",
    "git submodule *"
  ],
  "timeout_seconds": 10,
  "max_output_chars": 20000
}
```

## 7. OpenCode 配置生成

启用白名单后，CodeAsk 生成 workspace 级 `opencode.json` 时，不再写：

```json
{
  "permission": {
    "bash": "deny"
  }
}
```

而是生成 OpenCode 支持的对象形式。示例：

```json
{
  "permission": {
    "bash": {
      "*": "deny",
      "git status": "allow",
      "git status *": "allow",
      "git log": "allow",
      "git log *": "allow",
      "git show": "allow",
      "git show *": "allow",
      "git diff": "allow",
      "git diff *": "allow",
      "git blame": "allow",
      "git blame *": "allow",
      "git ls-files": "allow",
      "git ls-files *": "allow",
      "git rev-parse": "allow",
      "git rev-parse *": "allow",
      "git reset *": "deny",
      "git clean *": "deny",
      "git checkout *": "deny",
      "git switch *": "deny",
      "git restore *": "deny",
      "git add *": "deny",
      "git commit *": "deny",
      "git push *": "deny",
      "git pull *": "deny",
      "git fetch *": "deny",
      "git merge *": "deny",
      "git rebase *": "deny",
      "git apply *": "deny",
      "git am *": "deny",
      "git config *": "deny",
      "git update-index *": "deny",
      "git submodule *": "deny"
    },
    "read": "allow",
    "grep": "allow",
    "glob": "allow",
    "edit": "deny",
    "write": "deny"
  }
}
```

正式实现前必须用当前固定的 OpenCode 版本做 spike，确认：

1. `bash` 对象语法可用。
2. 规则顺序符合预期。
3. deny catch-all 不会导致整个 bash tool 被 OpenCode UI/Agent 判定为完全 disabled。
4. 未匹配命令会被拒绝，不会 fallback 到 ask 或 allow。
5. `git diff -- path`、`git log -- path` 等常用形式可以正常执行。

## 8. 会话目录约束

白名单命令只允许在当前 session workspace 下执行。

```text
<CODEASK_DATA_DIR>/agent_sessions/opencode/sessions/<session_id>/workspace
```

模型上下文中只展示相对路径：

```text
repos/<repo-name>
wiki/<feature-name>
reports/verified
```

如果 OpenCode 原始事件返回绝对路径，CodeAsk 返回给前端的 Agent 事件必须脱敏为 session workspace 相对路径。原始 trace 可以保留用于本地排障，但不能通过普通前端接口暴露宿主机路径。

## 9. Agent Prompt 补充

启用白名单后，可以在 OpenCode 会话上下文中加入简短说明：

```text
当前会话允许使用有限的只读 Git 命令辅助源码调查，例如 git log、git show、git diff、git blame、git status、git ls-files、git rev-parse。
这些命令只能用于调查，不应用于修改仓库、切换分支、清理文件或访问会话目录外的资源。
如需访问代码仓，先使用 CodeAsk 提供的 prepare_worktree 工具准备仓库，然后在 workspace/repos 下使用相对路径调查。
```

这段提示只描述能力边界，不替模型做关键字决策。

## 10. 事件与审计

Agent 行动轨迹中需要展示：

| 字段 | 说明 |
|---|---|
| `tool` | `bash` |
| `command` | 脱敏后的命令 |
| `cwd` | session workspace 相对路径 |
| `permission` | `allowed` / `denied` |
| `matched_rule` | 命中的白名单或拒绝规则 |
| `duration_ms` | 执行耗时 |
| `exit_code` | 退出码 |
| `output_chars` | 原始输出长度 |
| `truncated` | 是否截断 |
| `error_summary` | 失败摘要 |

拒绝的命令也要展示为事件，方便用户判断模型为何无法继续调查。

## 11. 测试计划

### 11.1 单元测试

- 默认配置下 `permission.bash == "deny"`。
- 启用白名单后生成对象形式 `permission.bash`。
- 默认 allow / deny 规则完整生成。
- 禁用后恢复 `bash = deny`。
- Admin 配置保存、读取、恢复默认。
- 绝对路径脱敏。
- 非 admin 不能修改全局白名单配置。

### 11.2 OpenCode Spike

使用项目固定的 OpenCode 版本验证：

- `git status` 可执行。
- `git log --oneline -5` 可执行。
- `git show --stat HEAD` 可执行。
- `git diff HEAD~1..HEAD -- <path>` 可执行。
- `git blame <path>` 可执行。
- `git reset --hard` 被拒绝。
- `git clean -fdx` 被拒绝。
- `python -c '...'` 被拒绝。
- `cat /etc/passwd` 被拒绝。

### 11.3 浏览器 E2E

使用真实浏览器和真实 OpenCode server 验证：

1. admin 登录。
2. 打开设置中的 OpenCode 权限页面。
3. 启用 bash 白名单。
4. 创建会话。
5. 提问一个需要源码历史的问题，例如“这个文件最近为什么改了，查看提交历史和 diff 后回答”。
6. 模型准备 worktree。
7. 模型使用允许的 git 命令。
8. Agent 行动轨迹显示命令、耗时、cwd 相对路径、输出截断状态。
9. 再诱导模型执行危险命令，确认被拒绝并展示拒绝事件。
10. 关闭白名单后重新提问，确认 bash 不再可用。

## 12. 待决问题

1. 第一版是否允许 admin 编辑任意 pattern，还是只允许启用内置只读 Git 白名单。
2. 是否需要每个特性或每个会话独立控制白名单。
3. 是否需要在未来改为 CodeAsk 自研 `codeask_git_inspect` MCP 工具，完全绕开 shell pattern。
4. 是否需要 OS 级 sandbox 才允许更宽的 bash 能力。
5. OpenCode 升级后 permission 规则是否存在兼容性变化，是否需要在启动时做能力探测。

## 13. 推荐落地顺序

1. Spike OpenCode 当前版本的 `permission.bash` 对象规则。
2. 新增全局配置结构，但 UI 第一版只暴露启用/禁用和恢复默认。
3. 生成 `opencode.json` 时按配置切换 `bash` permission。
4. 增强 Agent 事件映射，展示 bash 允许/拒绝/耗时/退出码。
5. 补充真实浏览器 E2E。
6. 若白名单 pattern 难以证明安全，再退回 `codeask_git_inspect` MCP 工具方案。
