# 14 Rust CLI (crates/ov_cli)

## 1. 模块概览

`crates/ov_cli/` 是一个 Rust 二进制 crate, 提供 `ov` CLI 工具。它具有 30+ 个子命令、TUI 文件浏览器和交互式聊天功能。

**入口点**: `src/main.rs` → 解析 CLI 参数 → 分派到 `handlers.rs` → 调用命令模块

---

## 2. 核心架构

```
main.rs (参数解析 + 命令分发)
    │
    ├── config.rs        # 配置管理 (ovcli.conf)
    ├── error.rs         # 错误类型 (Error / CliError)
    ├── output.rs        # 输出格式化 (Table / JSON)
    ├── utils.rs         # 工具函数 (UTF-8 截断)
    ├── base_client.rs   # 底层 HTTP 客户端 (reqwest)
    ├── client.rs        # 高层 API 客户端 (HttpClient)
    ├── handlers.rs      # 命令调度处理器
    │
    ├── commands/        # 命令实现模块
    │   ├── admin.rs     # 账户/用户 CRUD
    │   ├── chat.rs      # 交互式聊天 (SSE)
    │   ├── content.rs   # 读/写/摘要/重索引
    │   ├── crypto.rs    # 密钥初始化
    │   ├── filesystem.rs# ls/tree/mkdir/rm/mv/stat
    │   ├── observer.rs  # 观察者状态
    │   ├── pack.rs      # 导出/导入/备份/恢复
    │   ├── privacy.rs   # 隐私配置
    │   ├── relations.rs # 关系链接
    │   ├── resources.rs # 资源/技能添加
    │   ├── search.rs    # find/search/grep/glob
    │   ├── session.rs   # 会话管理 + add_memory
    │   ├── system.rs    # wait/status/consistency/health
    │   └── task.rs      # 任务状态
    │
    └── tui/             # TUI 模式
        ├── app.rs       # 应用状态
        ├── event.rs     # 键盘事件处理
        ├── tree.rs      # 文件树状态
        ├── ui.rs        # ratatui 渲染
        ├── image_preview.rs  # 图片预览 (viuer)
        └── mod.rs       # TUI 启动器
```

---

## 3. 配置文件 (config.rs)

```rust
struct Config {
    url: String,              // 默认 "http://localhost:1933"
    api_key: Option<String>,
    root_api_key: Option<String>,
    account: Option<String>,  // 别名 account_id
    user: Option<String>,     // 别名 user_id
    agent_id: Option<String>,
    timeout: f64,             // 默认 60.0
    output: String,           // 默认 "table"
    echo_command: bool,       // 默认 true
    show_progress: bool,      // 默认 false
    verbose: bool,            // 默认 false
    upload: UploadConfig,
    extra_headers: Option<HashMap<String, String>>,
}

struct UploadConfig {
    ignore_dirs: Option<String>,
    include: Option<String>,
    exclude: Option<String>,
}
// 配置路径: ~/.openviking/ovcli.conf (OPENVIKING_CLI_CONFIG_FILE 覆盖)
```

---

## 4. HTTP 客户端

### 4.1 BaseClient

```rust
struct BaseClient {
    http: ReqwestClient,
    base_url: String,
    api_key: Option<String>,
    account: Option<String>,
    user: Option<String>,
    agent_id: Option<String>,
    extra_headers: HashMap<String, String>,
}
// 方法: new, build_headers, get<T>, post<T>, put<T>, delete<T>, delete_with_body<T>, post_with_timeout<T>
```

### 4.2 HttpClient

```rust
struct HttpClient { base: BaseClient }

// 完整 API 表面:
// Content: read, abstract_content, overview, write, reindex, consistency, get_bytes
// Filesystem: ls, tree, mkdir, rm, mv, stat
// Search: find, search, grep, glob
// Resources: add_resource, add_skill
// Tasks: get_task, list_tasks
// Relations: list_relations, link, unlink
// Pack: export, backup, import, restore
// Admin: 10 个管理方法
// Sessions: 8 个会话方法
// Privacy: 7 个隐私配置方法
```

### 4.3 动态超时

```rust
struct TimeoutConfig {
    fn calculate(file_path) -> Duration {
        // 基于文件大小动态计算超时
        // 公式: min(300s, max(60s, file_size_mb * 30s))
    }
}

struct FileUploader {
    fn zip_directory(dir_path, ignore_dirs) -> ZipArchive
    fn zip_directory_with_progress(dir_path, verbose, ignore_dirs) -> ZipArchive
    fn upload_temp_file(file_path) -> Result
    fn upload_temp_file_with_progress(file_path, verbose) -> Result
}
```

---

## 5. 输出格式化 (output.rs)

```rust
enum OutputFormat { Table, Json }

// 6 种渲染规则:
// 1. list[dict] → 多行表格
// 2. 多个 list[dict] → 扁平化 (含 type 列)
// 3. 单个 list[primitive] → 每行一个
// 4. 单个 dict → 水平键值表
// 5. ComponentStatus → "[name] (healthy)" 格式
// 6. SystemStatus → 组件表 + 系统行

// 特殊渲染器:
// - render_session_context: 消息历史格式化
// - render_session_archive: 档案格式化
// URI/abstract 列永不被截断 (MAX_COL_WIDTH=256)
// Unicode 宽度感知 (中文等宽字符)
```

---

## 6. TUI 模式 (tui/)

### 6.1 启动

```rust
// ov tui 或 ov tree (别名)
// 通过 /health 端点探测, 然后启动 TUI
```

### 6.2 面板

```
┌─────────────┬──────────────────────────┐
│ Tree Panel  │ Content Panel            │
│ (35%)       │ (65%)                    │
│             │                          │
│ resources/  │ # README.md              │
│ ├─ projA/   │                          │
│ │  ├─ docs/ │ OpenViking is an open-   │
│ │  └─ src/  │ source Context Database  │
│ └─ projB/   │ for AI Agents...         │
│ user/       │                          │
│ agent/      │                          │
├─────────────┴──────────────────────────┤
│ [Tab] Focus  [j/k] Nav  [.] Expand     │
│ [d] Delete  [v] Vectors  [r] Refresh   │
└────────────────────────────────────────┘
```

### 6.3 键盘快捷键

| 键 | 操作 |
|---|---|
| `Tab` | 切换焦点 (Tree ↔ Content) |
| `q` | 退出 |
| `j/k` | 上/下导航 |
| `.` | 展开目录 / 加载待定图片 |
| `v` | 向量记录模式 (显示索引向量) |
| `n` | 加载下一页向量记录 |
| `c` | 显示向量计数 |
| `d` | 删除 URI (带确认) |
| `r` | 刷新树 |
| `L` | 切换调试日志 |

### 6.4 图片预览 (image_preview.rs)

```rust
struct ImagePreviewer {
    fn display_image(image_path) -> Result {
        // 6 种 viuer 回退配置:
        // 1. kitty + 透明
        // 2. kitty + 不透明
        // 3. iterm + 透明
        // 4. iterm + 不透明
        // 5. 自动调整大小
        // 6. image crate 后备
    }
}
```

---

## 7. 交互式聊天 (commands/chat.rs)

```rust
struct ChatCommand {
    endpoint: String,     // VIKINGBOT_ENDPOINT
    api_key: Option<String>, // VIKINGBOT_API_KEY
    stream: bool,
    no_format: bool,
    no_history: bool,
}

// SSE 流式解析:
// data: {"event":"reasoning","data":"思考中..."}
// data: {"event":"tool_call","data":{"name":"shell","args":{...}}}
// data: {"event":"tool_result","data":"..."}
// data: {"event":"response","data":"最终响应"}

// 交互模式: rustyline + ~/.ov_chat_history
// Markdown 渲染: termimad MadSkin
```

---

## 8. 所有命令一览

### 数据操作类 `[Data]`
```
ov add-resource <path>       # 添加资源
ov add-skill <file>          # 添加技能
ov write <uri>               # 写入内容
ov reindex <uri>             # 重索引
ov build-index <uri>         # 构建索引
ov summarize <uri>           # 生成摘要
ov link <from> <to>          # 创建关联
ov unlink <from> <to>        # 移除关联
```

### 交互类 `[Interactive]`
```
ov chat                       # 交互式聊天
ov chat --message "..."       # 单轮消息
ov tui / ov tree              # TUI 文件浏览器
```

### 查询类 `[Read]`
```
ov ls <uri>                   # 列出目录
ov tree <uri>                 # 树形浏览
ov read <uri>                 # 读取文件
ov abstract <uri>             # L0 摘要
ov overview <uri>             # L1 概览
ov stat <uri>                 # 文件状态
ov find <query>               # 语义搜索
ov search <query>             # 会话搜索
ov grep <pattern> --uri <uri> # 正则搜索
ov glob <pattern> --uri <uri> # Glob 匹配
ov relations <uri>            # 查看关联
```

### 状态类 `[Status]`
```
ov status                     # 系统状态
ov health                     # 健康检查
ov observer <component>       # 观察者状态
ov wait                       # 等待队列处理
ov consistency <uri>          # 一致性检查
ov task status <id>           # 任务状态
ov task list                  # 任务列表
```

### 会话类
```
ov session new                # 创建会话
ov session list               # 列出会话
ov session get <id>           # 获取会话
ov session context <id>       # 汇编上下文
ov session archive <id> <aid> # 获取存档
ov session delete <id>        # 删除会话
ov session add-message ...    # 添加消息
ov session commit <id>        # 提交会话
ov session add-memory ...     # 一键: 创建+消息+提交
```

### 管理类 `[Admin]`
```
ov admin accounts list/create/delete
ov admin users list/register/remove
ov admin agents list
ov admin set-role ...
ov admin regenerate-key ...
```

### 隐私类 `[Experimental]`
```
ov privacy categories
ov privacy list --category api_keys
ov privacy get --category api_keys --target openai
ov privacy versions --category api_keys --target openai
ov privacy activate --category api_keys --target openai --version 3
ov privacy upsert --category api_keys --target openai --key api_key=sk-xxx
```
