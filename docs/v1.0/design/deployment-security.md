# 部署、安全与运维设计

> 本文档属于 v1.0 SDD，描述部署形态、鉴权策略和安全边界。
>
> 产品契约见同版本 `prd/codeask.md`。当 SDD 与 PRD 冲突时，以 PRD 为准。

## 1. 目标

CodeAsk 面向小团队私有部署，默认优先简单可靠，同时保护代码、日志和模型密钥。

一期取舍（PRD §4.4.1）：

> 放弃权限隔离换取**极低的部署门槛和上手成本**。一个新部署的团队 30 秒内能让所有人开始用，不需要先做账号体系对接——这对"任意团队都能部署的开源/商业产品"定位是关键。

## 2. 部署

一期部署形态：

- Python 3.11+
- FastAPI + uvicorn
- React 构建产物由后端挂载
- `start.sh` 启动
- 默认监听 `127.0.0.1`

私有部署边界（PRD §4.2 承诺）：

- 数据 / 索引 / 会话 / 报告 / 轨迹日志默认只存本机私有目录
- 不向外部上报任何调查内容
- 仅 LLM 调用经由网关访问外部模型供应商（用户配置时显式同意）

## 3. 鉴权（一期）

**一期完全无鉴权，但有"自报身份"软识别。**

| 项 | 一期决策 |
|---|---|
| 登录 | 无 |
| 鉴权 | 无（监听 `127.0.0.1` + 私有部署 = 物理隔离） |
| 身份 | "自报身份"软识别（PRD §4.2 / §4.4.1）：首次访问生成 `client_id` 存 localStorage；用户菜单可选填昵称；`subject_id = nickname@client_id`（无昵称时为 `device@client_id`） |
| 读写权限 | 所有人可读、所有人可写（含修改特性、上传文档、删除报告、验证报告） |
| 会话归属 | 会话 / 报告 / 文档等写操作记录 `subject_id`；UI 默认按 `subject_id` 分组显示"我的会话"，"全部会话"视图永远存在 |

**与旧版差异**：旧设计有"单一 master token"鉴权，一期完全删除。原因（PRD §4.4.1）：

- 单 token 不解决多人识别问题，反而拉高了部署门槛
- 真正的隔离来自"127.0.0.1 + 私有内网"，token 只是表演性安全
- 团队需要真鉴权时应直接走 §4 扩展通道接 OIDC / LDAP，不要靠 token 凑合

风险与缓解（PRD §4.4.1）：

| 风险 | 缓解 |
|---|---|
| 恶意 / 无意误删 | 所有写操作走数据库，定期备份；UI 提供"撤销" |
| 报告被错误验证后污染检索 | UI 展示"由谁验证、何时验证"（一期记 `subject_id = nickname@client_id`），可一键回退到 draft（详见 `evidence-report.md` §7.4） |
| 自报身份可被冒用 | 内网物理隔离使外部冒用不可能；UI 在身份显示处加"自报"标识让团队成员心知肚明；写操作内部同时记录 `client_id` 便于事后排查 |

## 4. 鉴权扩展通道（未来）

CodeAsk 是面向"任意团队都能部署的开源 / 商业产品"，每家公司的员工账号体系不同（AD、LDAP、Google Workspace、自建 SSO、企业微信、飞书、钉钉……）。**未来加鉴权时不能绑定特定供应商**——这是 PRD §4.4.2 锁定的扩展约束。

### 4.1 后端 `AuthProvider` 抽象

```python
class Identity(BaseModel):
    subject_id: str            # 稳定标识，不依赖 email / 姓名
    display_name: str | None
    email: str | None
    roles: list[str]           # 一期之后从简："member" / "admin"
    raw_claims: dict           # 原始 claims，用于二开扩展


class AuthProvider(Protocol):
    name: str

    async def authenticate(self, request: Request) -> Identity | None:
        """从请求中提取并验证身份。返回 None 表示当前请求未鉴权。"""

    async def get_login_url(self, return_to: str) -> str | None:
        """返回登录跳转 URL（OIDC / OAuth 类适用）；不需要登录页的 Provider 返回 None。"""

    async def logout(self, identity: Identity) -> None:
        """撤销会话。"""
```

请求中间件 hook 槽位：

```python
app.add_middleware(AuthMiddleware, provider=load_provider_from_config())
```

二开者实现 `AuthProvider` 子类即可，**不改核心代码**：

| 实现 | 协议 |
|---|---|
| `OidcAuthProvider` | OIDC / OAuth 2.1（官方第一批适配） |
| `LdapAuthProvider` | LDAP / AD（官方第一批适配） |
| `WeComAuthProvider` | 企业微信（社区适配） |
| `FeishuAuthProvider` | 飞书（社区适配） |
| `DingTalkAuthProvider` | 钉钉（社区适配） |
| `NoAuthProvider` | 默认无鉴权（一期内置） |

### 4.2 前端槽位（UI slot）

前端预留以下 slot，二开者可在不改核心代码的前提下注入实现：

| slot | 默认（一期） | 用于 |
|---|---|---|
| `<LoginPage />` | 空（直接进首页） | 登录入口 |
| `<UserMenu />` | 显示"匿名访问"标识 | 顶栏用户菜单 |
| `<UserProfilePage />` | 空 | 用户资料页 |
| `<RoleGate role="admin" />` | 透明（任何人都通过） | 包裹需要管理员权限的操作 |

### 4.3 权限模型（未来）

| 阶段 | 权限模型 |
|---|---|
| 一期（MVP） | 无身份；所有人可读可写 |
| MVP+ | 两级：`member`（读 + 提问 + 验证报告）/ `admin`（删除特性 / 删除仓库 / 系统配置） |
| 未来 | 不在 v1.0 范围 — 多租户 / 多组织通过新版本演进 |

### 4.4 默认无鉴权可选

部署者可以**永远关闭鉴权**回到一期模式（自用、内网测试、demo 场景常用）。`NoAuthProvider` 是内置默认，配置切换无需重启核心代码。

## 5. 敏感信息

- LLM API Key 加密存储（数据库字段加密 + 密钥管理见下）。
- 加密主密钥 `CODEASK_DATA_KEY` 由环境变量提供，仅用于加密敏感字段（如 LLM API Key），**与鉴权无关**。
- 日志脱敏一期不做，但报告和轨迹日志默认只存本机私有目录。
- 用户输入的日志附件、代码片段不向外部上报；仅在 LLM 调用时按需作为 prompt 传给已配置的模型供应商。

## 6. 文件安全

- 所有路径读取做根目录校验（防止 `../` 越狱）。
- 上传文件做 MIME 和后缀检查。
- 二进制日志拒绝。
- shell 调用使用参数数组，不使用 `shell=True`。
- worktree 路径限制在配置的工作目录内（详见 `code-index.md`）。

## 7. 定时任务

使用 APScheduler：

- 24h 未活跃会话清理附件和 worktree。
- 磁盘水位线检查。
- ctags 缓存 LRU 清理。
- 全局仓库池中已配置但长时间未被任何特性引用的仓库提示用户确认（不自动删除）。

清理后保留 DB 对话记录和轨迹日志。用户继续提问时按需重建 worktree，附件需重新上传。

会话绑定**自报身份**（PRD §4.2 软识别）：`created_by` / `verified_by` 等字段一期记 `subject_id = nickname@client_id`（无昵称时 `device@client_id`）；未来接入 AuthProvider 后切换为来自 Identity 的 `subject_id`。已存在的自报 `subject_id` 在迁移时保留为历史归档（不强制改写）。

## 8. 与 PRD 的对齐

本文已按 `prd/codeask.md` §4.4 + §9 对齐表更新，主要变化：

- §3 一期鉴权从"单一 master token"改为**完全无鉴权**（127.0.0.1 + 私有部署 = 物理隔离）
- §3 引入**"自报身份"软识别**（PRD §4.2 / §4.4.1）：`client_id` + 可选昵称构成 `subject_id`，用于会话归属和 UI 分组；非鉴权
- §4 新增"鉴权扩展通道"完整设计：后端 `AuthProvider` 协议 + 前端 UI slot + 权限模型阶段演进 + 默认无鉴权可选 — 落地 PRD §4.4.2 五条约束
- §3 风险表落地 PRD §4.4.1 的三条缓解（写操作可撤销 / 报告一键回退 / 自报身份冒用通过物理隔离 + UI 标识缓解）
- §5 区分加密主密钥（`CODEASK_DATA_KEY`，仅用于敏感字段加密）与鉴权 token（一期无）
- §7 定时任务补一条"全局仓库池孤儿仓库提示"，与 `code-index.md` 全局仓库池设计对齐
