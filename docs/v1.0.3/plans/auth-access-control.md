# v1.0.3 鉴权与访问控制实现计划

> **给执行 Agent 的要求：** 实施本计划时必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，逐任务执行、逐任务验证、逐任务提交。本文所有步骤使用 checkbox（`- [ ]`）追踪进度。

**目标：** 在保留匿名会话能力的前提下，实现数据库用户体系、登录态、特性管理员授权、全局附件上传开关、审计日志，以及真实浏览器端到端验收。

**架构：** 后端新增正式用户和登录 session，但继续保留浏览器匿名 ID 作为未登录会话身份。所有写操作统一走服务端权限守卫，前端只负责显示合适的入口和反馈。实现按“持久化基础 → 登录和用户 API → 资源权限 → 前端交互 → 真实浏览器 E2E”推进。

**技术栈：** FastAPI、SQLAlchemy async、Alembic、SQLite、Pydantic、React 19、TanStack Query、Playwright、Vitest、pytest、uv、pnpm。

---

## 实施边界

本计划实现 [v1.0.3 鉴权与访问控制设计](../specs/auth-access-control.md)。本版本不修改 Agent 决策链路、RAG 策略、模型路由和 Wiki 内容模型，除非某处必须接入权限校验。

实现时要控制文件职责。身份识别、用户管理、特性权限、审计写入、前端权限 UI 必须拆开，不允许继续把所有逻辑堆进单个 API 或组件。

## 文件结构

后端新增或修改：

- `src/codeask/db/models/user.py`：`User`、`AuthSession`、`FeatureAdmin` ORM。
- `src/codeask/db/models/__init__.py`：导出新模型。
- `alembic/versions/20260510_0025_auth_users_feature_admins.py`：新增用户、登录 session、特性管理员表；必要时扩展审计字段。
- `src/codeask/auth/passwords.py`：PBKDF2 密码 hash 与校验。
- `src/codeask/auth/sessions.py`：登录 token 生成、hash、过期时间和续期判断。
- `src/codeask/auth/bootstrap.py`：默认 `admin` 用户初始化和环境变量兜底。
- `src/codeask/auth/actor.py`：统一请求 actor。
- `src/codeask/auth/guards.py`：后端权限守卫。
- `src/codeask/identity.py`：从“自报 subject + admin cookie”升级为“匿名浏览器 ID + 登录 cookie”解析。
- `src/codeask/api/auth.py`：统一登录、自动注册、退出、`me`。
- `src/codeask/api/users.py`：用户资料、改密码、用户搜索、清空密码。
- `src/codeask/api/feature_admins.py`：特性管理员列表、候选搜索、添加、删除。
- `src/codeask/features/permissions.py`：特性权限判断。
- `src/codeask/api/features.py`：创建/删除/更新/仓库关联权限。
- `src/codeask/wiki/actor.py`、`src/codeask/wiki/permissions.py`：Wiki 读写权限。
- `src/codeask/api/wiki/*.py`：所有 Wiki 写接口接入完整 actor。
- `src/codeask/api/sessions.py`：匿名会话保留、登录迁移、附件开关、报告草稿权限。
- `src/codeask/api/llm_configs.py`：全局 LLM admin-only，用户 LLM owner-only，访客 LLM 仅本次请求使用。
- `src/codeask/api/code_index.py`：全局仓库 admin-only。
- `src/codeask/api/skills.py`：全局 Skill admin-only，特性 Skill 走特性管理员权限。
- `src/codeask/audit/writer.py`：安全审计写入。
- `src/codeask/api/metrics.py` 或 `src/codeask/api/audit.py`：admin 审计查询。
- `src/codeask/app.py`：注册新 router，启动时初始化 admin。

前端新增或修改：

- `frontend/src/lib/identity.ts`：匿名浏览器 ID、访客 LLM 本地配置、登录后身份切换。
- `frontend/src/lib/api-auth.ts`：登录、退出、`me`、修改资料、修改密码。
- `frontend/src/lib/api-users.ts`：用户搜索和清空密码。
- `frontend/src/lib/api-feature-admins.ts`：特性管理员 API。
- `frontend/src/lib/api-client.ts`：继续发送匿名 `X-Subject-Id`，支持会话请求携带访客 LLM 配置。
- `frontend/src/lib/auth-cache.ts`：登录、退出、改用户名后清理 subject/role 相关缓存。
- `frontend/src/components/auth/AdminLoginPage.tsx`：改为通用登录页。
- `frontend/src/components/layout/TopBar.tsx`：显示登录状态、角色、设置入口。
- `frontend/src/components/settings/UserSettings.tsx`：访客 LLM、用户名、密码、用户级 LLM。
- `frontend/src/components/settings/GlobalSettings.tsx`：附件上传开关、用户管理。
- `frontend/src/components/settings/users/UserManager.tsx`：admin 用户管理。
- `frontend/src/components/features/FeatureTabs.tsx`：新增“管理员”tab。
- `frontend/src/components/features/FeatureAdminsPanel.tsx`：特性管理员列表和 admin 操作。
- `frontend/src/components/features/*.tsx`：按权限隐藏或阻止写入口。
- `frontend/src/components/wiki/*`、`frontend/src/lib/wiki/*`：Wiki 写入口按权限展示。
- `frontend/src/components/session/useSessionAttachments.ts`：附件开关前端提示。
- `frontend/src/components/feedback/AppFeedback.tsx`：继续使用居中失败弹窗和轻量成功提示。

测试新增：

- `tests/unit/test_auth_passwords.py`
- `tests/unit/test_auth_sessions.py`
- `tests/unit/test_feature_permissions.py`
- `tests/integration/test_auth_migration.py`
- `tests/integration/test_auth_users_api.py`
- `tests/integration/test_feature_admins_api.py`
- `tests/integration/test_authz_features_api.py`
- `tests/integration/test_authz_wiki_api.py`
- `tests/integration/test_attachment_upload_gate.py`
- `tests/integration/test_audit_authz_api.py`
- `frontend/tests/auth-cache.test.ts`
- `frontend/tests/guest-llm-config.test.ts`
- `frontend/tests/feature-admins-ui.test.tsx`
- `frontend/e2e/auth-access-control.spec.ts`

## 提交节奏

每个任务通过对应测试后提交一次，提交信息建议：

- `feat(auth): add user session persistence`
- `feat(auth): add unified login and migration`
- `feat(authz): enforce feature administrator permissions`
- `feat(ui): add v1.0.3 auth controls`
- `test(e2e): cover auth access control`

## Task 1：持久化与密码基础

**文件：**
- Create: `src/codeask/db/models/user.py`
- Modify: `src/codeask/db/models/__init__.py`
- Create: `alembic/versions/20260510_0025_auth_users_feature_admins.py`
- Create: `src/codeask/auth/__init__.py`
- Create: `src/codeask/auth/passwords.py`
- Create: `tests/unit/test_auth_passwords.py`
- Create: `tests/integration/test_auth_migration.py`

- [ ] **Step 1：写密码 hash 失败测试**

创建 `tests/unit/test_auth_passwords.py`：

```python
from codeask.auth.passwords import hash_password, verify_password


def test_hash_password_verifies_case_sensitive_password() -> None:
    encoded = hash_password("Secret123")

    assert verify_password("Secret123", encoded) is True
    assert verify_password("secret123", encoded) is False


def test_hash_password_uses_unique_salt() -> None:
    first = hash_password("Secret123")
    second = hash_password("Secret123")

    assert first != second
    assert verify_password("Secret123", first)
    assert verify_password("Secret123", second)


def test_verify_password_rejects_malformed_hash() -> None:
    assert verify_password("Secret123", "broken") is False
```

- [ ] **Step 2：确认测试失败**

Run: `uv run pytest tests/unit/test_auth_passwords.py -v`

Expected: FAIL，原因是 `codeask.auth.passwords` 还不存在。

- [ ] **Step 3：实现密码 hash**

创建 `src/codeask/auth/__init__.py`：

```python
"""Authentication domain services."""
```

创建 `src/codeask/auth/passwords.py`：

```python
"""Password hashing helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 210_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    salt_text = base64.urlsafe_b64encode(salt).decode().rstrip("=")
    digest_text = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return f"{_ALGORITHM}${_ITERATIONS}${salt_text}${digest_text}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, iterations_text, salt_text, expected_text = encoded.split("$", 3)
        iterations = int(iterations_text)
    except ValueError:
        return False
    if algorithm != _ALGORITHM or iterations <= 0:
        return False
    try:
        salt = _decode_unpadded(salt_text)
        expected = _decode_unpadded(expected_text)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _decode_unpadded(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode())
```

- [ ] **Step 4：确认密码测试通过**

Run: `uv run pytest tests/unit/test_auth_passwords.py -v`

Expected: 3 PASS。

- [ ] **Step 5：实现 ORM 和迁移**

创建 `src/codeask/db/models/user.py`，包含 `User`、`AuthSession`、`FeatureAdmin`。字段必须覆盖：

- `users.id`
- `users.username`
- `users.role`
- `users.password_hash`
- `users.auth_version`
- `users.last_login_at`
- `auth_sessions.id`
- `auth_sessions.token_hash`
- `auth_sessions.user_id`
- `auth_sessions.auth_version`
- `auth_sessions.expires_at`
- `auth_sessions.last_seen_at`
- `feature_admins.feature_id`
- `feature_admins.user_id`
- `feature_admins.created_by_user_id`
- `feature_admins.created_at`

修改 `src/codeask/db/models/__init__.py` 导出 `User`、`AuthSession`、`FeatureAdmin`。

创建 `alembic/versions/20260510_0025_auth_users_feature_admins.py`，`down_revision = "0024"`。迁移只建表和索引，不在 migration 里写入 admin 密码。

- [ ] **Step 6：写迁移测试**

创建 `tests/integration/test_auth_migration.py`：

```python
from pathlib import Path

from sqlalchemy import create_engine, inspect

from codeask.migrations import run_migrations


def test_auth_migration_creates_user_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "auth.db"
    run_migrations(f"sqlite:///{db_path}")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)

    assert "users" in inspector.get_table_names()
    assert "auth_sessions" in inspector.get_table_names()
    assert "feature_admins" in inspector.get_table_names()
```

- [ ] **Step 7：运行 Task 1 测试**

Run:

```bash
uv run pytest tests/unit/test_auth_passwords.py tests/integration/test_auth_migration.py -v
```

Expected: PASS。

- [ ] **Step 8：提交**

Run:

```bash
git add src/codeask/auth src/codeask/db/models/__init__.py src/codeask/db/models/user.py alembic/versions/20260510_0025_auth_users_feature_admins.py tests/unit/test_auth_passwords.py tests/integration/test_auth_migration.py
git commit -m "feat(auth): add user session persistence"
```

## Task 2：登录 session、admin 初始化与 actor 解析

**文件：**
- Create: `src/codeask/auth/actor.py`
- Create: `src/codeask/auth/sessions.py`
- Create: `src/codeask/auth/bootstrap.py`
- Modify: `src/codeask/identity.py`
- Modify: `src/codeask/app.py`
- Create: `tests/unit/test_auth_sessions.py`
- Modify: `tests/unit/test_identity.py`

- [ ] **Step 1：写 session helper 测试**

创建 `tests/unit/test_auth_sessions.py`：

```python
from datetime import UTC, datetime, timedelta

from codeask.auth.sessions import create_session_token, hash_session_token, should_renew


def test_session_token_hash_is_stable_and_does_not_equal_token() -> None:
    token = create_session_token()

    assert hash_session_token(token) == hash_session_token(token)
    assert hash_session_token(token) != token


def test_should_renew_when_half_lifetime_elapsed() -> None:
    now = datetime(2026, 5, 10, tzinfo=UTC)
    expires = now + timedelta(days=2)
    last_seen = now - timedelta(days=4)

    assert should_renew(now=now, expires_at=expires, last_seen_at=last_seen, ttl_days=7)


def test_should_not_renew_for_recent_session() -> None:
    now = datetime(2026, 5, 10, tzinfo=UTC)
    expires = now + timedelta(days=6)
    last_seen = now - timedelta(minutes=30)

    assert not should_renew(now=now, expires_at=expires, last_seen_at=last_seen, ttl_days=7)
```

- [ ] **Step 2：确认测试失败**

Run: `uv run pytest tests/unit/test_auth_sessions.py -v`

Expected: FAIL，原因是 `codeask.auth.sessions` 不存在。

- [ ] **Step 3：实现 actor 和 session helpers**

创建 `src/codeask/auth/actor.py`：

```python
"""Request actor resolved by identity middleware."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Actor:
    subject_id: str
    display_name: str
    role: str
    authenticated: bool
    user_id: str | None = None
    username: str | None = None
    anonymous_subject_id: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"
```

创建 `src/codeask/auth/sessions.py`：

```python
"""Login-session token helpers."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry(now: datetime | None = None, ttl_days: int = 7) -> datetime:
    current = now or datetime.now(UTC)
    return current + timedelta(days=ttl_days)


def should_renew(*, now: datetime, expires_at: datetime, last_seen_at: datetime, ttl_days: int) -> bool:
    ttl = timedelta(days=ttl_days)
    if expires_at <= now:
        return False
    return now - last_seen_at >= ttl / 2
```

- [ ] **Step 4：实现 admin 初始化**

创建 `src/codeask/auth/bootstrap.py`：

```python
"""Bootstrap the fixed admin user."""

from __future__ import annotations

from secrets import token_hex

from sqlalchemy import select

from codeask.auth.passwords import hash_password
from codeask.db.models import User

ADMIN_USERNAME = "admin"


async def ensure_admin_user(session_factory: object, default_password: str = "admin") -> None:
    async with session_factory() as session:
        row = (
            await session.execute(select(User).where(User.username == ADMIN_USERNAME))
        ).scalar_one_or_none()
        if row is None:
            session.add(
                User(
                    id=f"user_{token_hex(12)}",
                    username=ADMIN_USERNAME,
                    role="admin",
                    password_hash=hash_password(default_password),
                    auth_version=1,
                )
            )
        else:
            row.role = "admin"
            if row.password_hash is None:
                row.password_hash = hash_password(default_password)
                row.auth_version += 1
        await session.commit()
```

- [ ] **Step 5：升级 identity middleware**

修改 `src/codeask/identity.py`，行为必须满足：

- 没有登录 cookie 时，继续使用 `X-Subject-Id` 作为匿名浏览器 ID。
- 有登录 cookie 时，用 token hash 查询 `AuthSession`。
- 校验 `expires_at` 和 `auth_version`。
- 认证成功后设置 `request.state.actor`、`subject_id`、`user_id`、`username`、`display_name`、`role`、`authenticated`。
- 登录 cookie 无效时回退到匿名身份，不抛 500。
- 保留现有日志上下文绑定能力。

- [ ] **Step 6：启动时初始化 admin**

修改 `src/codeask/app.py`，在迁移完成并创建 session factory 后调用：

```python
from codeask.auth.bootstrap import ensure_admin_user

await ensure_admin_user(factory, default_password=settings.admin_password or "admin")
```

- [ ] **Step 7：运行 Task 2 测试**

Run:

```bash
uv run pytest tests/unit/test_auth_sessions.py tests/unit/test_identity.py -v
```

Expected: PASS。

- [ ] **Step 8：提交**

Run:

```bash
git add src/codeask/auth/actor.py src/codeask/auth/sessions.py src/codeask/auth/bootstrap.py src/codeask/identity.py src/codeask/app.py tests/unit/test_auth_sessions.py tests/unit/test_identity.py
git commit -m "feat(auth): resolve users and anonymous actors"
```

## Task 3：统一登录、自动注册与用户 API

**文件：**
- Modify: `src/codeask/api/auth.py`
- Create: `src/codeask/api/users.py`
- Create: `src/codeask/api/schemas/auth.py`
- Create: `src/codeask/api/schemas/user.py`
- Modify: `src/codeask/api/schemas/__init__.py`
- Modify: `src/codeask/app.py`
- Create: `tests/integration/test_auth_users_api.py`

- [ ] **Step 1：写 API 测试**

创建 `tests/integration/test_auth_users_api.py`，覆盖：

- 新用户名 + 6 位以上密码自动注册并登录。
- 短密码返回 422。
- 用户名和密码 trim 首尾空格。
- 用户名大小写敏感。
- 普通用户登录迁移当前浏览器匿名会话。
- admin 登录不迁移匿名会话。
- 修改用户名做唯一校验。
- admin 清空普通用户密码后，该用户下次登录可重新设置密码。

- [ ] **Step 2：确认测试失败**

Run: `uv run pytest tests/integration/test_auth_users_api.py -v`

Expected: FAIL，原因是新 API 还不存在。

- [ ] **Step 3：实现认证 API**

修改 `src/codeask/api/auth.py`：

- `GET /api/auth/me`
- `POST /api/auth/login`
- `POST /api/auth/logout`

登录规则：

- 用户名和密码都 trim。
- 密码长度小于 6 返回 422。
- 用户名不存在则创建普通用户并登录。
- 用户名存在则校验密码。
- 用户存在但 `password_hash` 为空时，用本次密码写入并登录。
- `admin` 用户名固定。
- `admin` 登录成功不迁移匿名会话。
- 普通用户登录成功迁移 `anonymous_subject_id` 或当前 `X-Subject-Id` 下的会话。
- 设置 HttpOnly cookie。

- [ ] **Step 4：实现用户 API**

创建 `src/codeask/api/users.py`：

- `GET /api/users/me`
- `PATCH /api/users/me`
- `PATCH /api/users/me/password`
- `GET /api/users/search`
- `POST /api/users/{user_id}/password/clear`

权限规则：

- `/me` 需要登录。
- `admin` 不能改用户名。
- 用户名唯一且大小写敏感。
- 密码至少 6 位。
- 用户搜索需要 admin。
- 清空密码需要 admin。
- 不允许清空 `admin` 密码。

- [ ] **Step 5：注册 router**

修改 `src/codeask/app.py`：

```python
from codeask.api.users import router as users_router

app.include_router(users_router, prefix="/api")
```

- [ ] **Step 6：运行 Task 3 测试**

Run:

```bash
uv run pytest tests/integration/test_auth_users_api.py tests/integration/test_sessions_api.py -v
```

Expected: PASS。

- [x] **Step 7：提交**

Run:

```bash
git add src/codeask/api/auth.py src/codeask/api/users.py src/codeask/api/schemas/auth.py src/codeask/api/schemas/user.py src/codeask/api/schemas/__init__.py src/codeask/app.py tests/integration/test_auth_users_api.py
git commit -m "feat(auth): add unified login and user APIs"
```

## Task 4：特性管理员权限

**文件：**
- Create: `src/codeask/features/__init__.py`
- Create: `src/codeask/features/permissions.py`
- Create: `src/codeask/api/feature_admins.py`
- Modify: `src/codeask/api/features.py`
- Modify: `src/codeask/api/schemas/wiki.py`
- Modify: `src/codeask/app.py`
- Create: `tests/unit/test_feature_permissions.py`
- Create: `tests/integration/test_feature_admins_api.py`
- Create: `tests/integration/test_authz_features_api.py`

- [ ] **Step 1：写权限单测**

创建 `tests/unit/test_feature_permissions.py`：

```python
from codeask.auth.actor import Actor
from codeask.features.permissions import can_manage_feature, can_manage_feature_admins


def test_admin_can_manage_every_feature() -> None:
    actor = Actor(
        subject_id="admin",
        display_name="Admin",
        role="admin",
        authenticated=True,
        user_id="user_admin",
        username="admin",
    )

    assert can_manage_feature(actor, feature_admin_user_ids=set())
    assert can_manage_feature_admins(actor)


def test_feature_admin_can_manage_assigned_feature() -> None:
    actor = Actor(
        subject_id="user_a",
        display_name="Alice",
        role="member",
        authenticated=True,
        user_id="user_a",
        username="Alice",
    )

    assert can_manage_feature(actor, feature_admin_user_ids={"user_a"})
    assert not can_manage_feature_admins(actor)


def test_anonymous_cannot_manage_feature() -> None:
    actor = Actor(subject_id="client_a", display_name="client_a", role="member", authenticated=False)

    assert not can_manage_feature(actor, feature_admin_user_ids=set())
    assert not can_manage_feature_admins(actor)
```

- [ ] **Step 2：确认测试失败**

Run: `uv run pytest tests/unit/test_feature_permissions.py -v`

Expected: FAIL。

- [ ] **Step 3：实现特性权限 helper**

创建 `src/codeask/features/__init__.py`：

```python
"""Feature domain helpers."""
```

创建 `src/codeask/features/permissions.py`：

```python
"""Feature permission helpers."""

from codeask.auth.actor import Actor


def can_manage_feature(actor: Actor, *, feature_admin_user_ids: set[str]) -> bool:
    return actor.is_admin or (actor.user_id is not None and actor.user_id in feature_admin_user_ids)


def can_manage_feature_admins(actor: Actor) -> bool:
    return actor.is_admin
```

- [ ] **Step 4：实现特性管理员 API**

创建 `src/codeask/api/feature_admins.py`：

- `GET /api/features/{feature_id}/admins`：公开只读。
- `GET /api/features/{feature_id}/admin-candidates?query=...&limit=10`：admin-only，过滤 `admin`。
- `POST /api/features/{feature_id}/admins`：admin-only，只能添加已存在用户。
- `DELETE /api/features/{feature_id}/admins/{user_id}`：admin-only。

- [ ] **Step 5：保护 feature API**

修改 `src/codeask/api/features.py`：

- `POST /features`：admin-only。
- `DELETE /features/{feature_id}`：admin-only。
- `PUT /features/{feature_id}`：admin 或该特性管理员。
- `POST /features/{feature_id}/repos/{repo_id}`：admin 或该特性管理员。
- `DELETE /features/{feature_id}/repos/{repo_id}`：admin 或该特性管理员。
- `GET` 列表和详情继续公开。

- [ ] **Step 6：运行 Task 4 测试**

Run:

```bash
uv run pytest tests/unit/test_feature_permissions.py tests/integration/test_feature_admins_api.py tests/integration/test_authz_features_api.py tests/integration/test_feature_repos_api.py -v
```

Expected: PASS。

- [ ] **Step 7：提交**

Run:

```bash
git add src/codeask/features src/codeask/api/feature_admins.py src/codeask/api/features.py src/codeask/api/schemas/wiki.py src/codeask/app.py tests/unit/test_feature_permissions.py tests/integration/test_feature_admins_api.py tests/integration/test_authz_features_api.py
git commit -m "feat(authz): add feature administrator permissions"
```

## Task 5：Wiki、报告、仓库、LLM、附件权限接入

**文件：**
- Modify: `src/codeask/wiki/actor.py`
- Modify: `src/codeask/wiki/permissions.py`
- Modify: `src/codeask/api/wiki/deps.py`
- Modify: `src/codeask/api/wiki/assets.py`
- Modify: `src/codeask/api/wiki/documents.py`
- Modify: `src/codeask/api/wiki/drafts.py`
- Modify: `src/codeask/api/wiki/imports.py`
- Modify: `src/codeask/api/wiki/maintenance.py`
- Modify: `src/codeask/api/wiki/nodes.py`
- Modify: `src/codeask/api/wiki/promotions.py`
- Modify: `src/codeask/api/wiki/reports.py`
- Modify: `src/codeask/api/wiki/sources.py`
- Modify: `src/codeask/api/wiki/tree.py`
- Modify: `src/codeask/api/wiki/versions.py`
- Modify: `src/codeask/api/sessions.py`
- Modify: `src/codeask/api/llm_configs.py`
- Modify: `src/codeask/api/code_index.py`
- Modify: `src/codeask/api/skills.py`
- Create: `tests/integration/test_authz_wiki_api.py`
- Create: `tests/integration/test_attachment_upload_gate.py`

- [x] **Step 1：写 Wiki 权限测试**

创建 `tests/integration/test_authz_wiki_api.py`，覆盖：

- 匿名用户可读 Wiki 树。
- 匿名用户创建 Wiki 节点返回 403。
- 普通用户导入 Wiki 返回 403。
- 特性管理员可写授权特性的 Wiki。
- 特性管理员写未授权特性返回 403。
- admin 可写所有特性 Wiki。

- [x] **Step 2：写附件开关测试**

创建 `tests/integration/test_attachment_upload_gate.py`，覆盖：

- 开关开启时匿名用户可上传附件到自己的会话。
- 开关关闭时匿名用户上传返回 403。
- 开关关闭时登录用户上传返回 403。
- 开关关闭不影响已有附件重命名和删除。

- [x] **Step 3：确认测试失败**

Run:

```bash
uv run pytest tests/integration/test_authz_wiki_api.py tests/integration/test_attachment_upload_gate.py -v
```

Expected: FAIL。

- [x] **Step 4：更新 Wiki actor 和权限**

修改 `src/codeask/wiki/actor.py`：

```python
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class WikiActor:
    subject_id: str
    role: str
    user_id: str | None = None
    authenticated: bool = False
    feature_admin_feature_ids: frozenset[int] = field(default_factory=frozenset)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"
```

修改 `src/codeask/wiki/permissions.py`：

```python
from codeask.db.models import Feature
from codeask.wiki.actor import WikiActor


def can_read_feature(actor: WikiActor, feature: Feature) -> bool:
    return True


def can_write_feature(actor: WikiActor, feature: Feature) -> bool:
    return actor.is_admin or feature.id in actor.feature_admin_feature_ids


def can_admin_feature(actor: WikiActor, feature: Feature) -> bool:
    return actor.is_admin


def can_maintain_feature(actor: WikiActor, feature: Feature) -> bool:
    return can_write_feature(actor, feature)
```

- [x] **Step 5：更新 Wiki API actor 构造**

修改 `src/codeask/api/wiki/deps.py`，构造 `WikiActor` 时查询当前用户授权的 `feature_admins.feature_id`。读接口继续公开，写接口通过已有 service `_require_write` 拦截。

- [x] **Step 6：接入其它资源权限**

- `src/codeask/api/sessions.py`：附件上传读取 `session_attachments_enabled`，关闭时返回 403 和“该功能已被禁用”。
- `src/codeask/api/sessions.py`：报告草稿生成只校验会话所有者；报告管理操作校验 admin 或特性管理员。
- `src/codeask/api/llm_configs.py`：全局配置 admin-only，用户配置 owner-only。
- `src/codeask/api/code_index.py`：全局仓库 admin-only。
- `src/codeask/api/skills.py`：全局 Skill admin-only，特性 Skill 走特性管理员权限。

- [x] **Step 7：运行 Task 5 测试**

Run:

```bash
uv run pytest tests/integration/test_authz_wiki_api.py tests/integration/test_attachment_upload_gate.py tests/integration/test_wiki_tree_api.py tests/integration/test_wiki_documents_api.py tests/integration/test_wiki_imports_api.py tests/integration/test_wiki_reports_api.py -v
```

Expected: PASS。

- [x] **Step 8：提交**

Run:

```bash
git add src/codeask/wiki src/codeask/api tests/integration/test_authz_wiki_api.py tests/integration/test_attachment_upload_gate.py
git commit -m "feat(authz): enforce wiki report and attachment permissions"
```

## Task 6：审计日志

**文件：**
- Create: `src/codeask/audit/__init__.py`
- Create: `src/codeask/audit/writer.py`
- Modify: `src/codeask/db/models/audit_log.py`
- Modify: `alembic/versions/20260510_0025_auth_users_feature_admins.py` 或新增连续 revision
- Modify: `src/codeask/api/metrics.py`
- Create: `tests/integration/test_audit_authz_api.py`
- Modify: `tests/unit/test_metrics_audit_writer.py`

- [x] **Step 1：写审计测试**

创建 `tests/integration/test_audit_authz_api.py`，覆盖：

- 匿名用户不能查询审计。
- 普通用户不能查询审计。
- admin 可以分页查询审计。
- 登录失败写入审计。
- 自动注册写入审计。
- 添加特性管理员写入审计。
- 附件关闭导致的上传拒绝写入审计。

- [x] **Step 2：确认测试失败**

Run: `uv run pytest tests/integration/test_audit_authz_api.py -v`

Expected: FAIL。

- [x] **Step 3：实现安全审计 writer**

创建 `src/codeask/audit/__init__.py`：

```python
"""Audit helpers."""
```

创建 `src/codeask/audit/writer.py`：

```python
"""Safe audit-log writer for auth and authorization events."""

from __future__ import annotations

from datetime import UTC, datetime
from secrets import token_hex

from codeask.db.models import AuditLog


async def write_audit(
    session: object,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    subject_id: str,
    result: str = "success",
    reason: str | None = None,
    request_id: str | None = None,
) -> None:
    session.add(
        AuditLog(
            id=f"audit_{token_hex(12)}",
            entity_type=entity_type[:64],
            entity_id=entity_id[:64],
            action=action[:64],
            from_status=reason[:32] if reason else None,
            to_status=result[:32],
            subject_id=subject_id[:128],
            at=datetime.now(UTC),
        )
    )
```

审计内容禁止写入密码、API Key、LLM 配置明文、原始聊天内容。

- [x] **Step 4：接入审计点**

接入以下事件：

- 登录成功。
- 登录失败。
- 自动注册。
- 修改用户名。
- 修改密码。
- admin 清空用户密码。
- 创建/删除/归档特性。
- 添加/删除特性管理员。
- 迁移访客 LLM 配置。
- 生成问题报告草稿。
- Wiki 写操作拒绝。
- 特性配置写操作拒绝。
- 附件上传因全局开关拒绝。

实现备注：权限拒绝通过全局 403 审计兜底记录 `authz.denied`，避免在每个业务模块重复写拒绝逻辑；附件关闭额外记录 `session_attachment.upload_denied` 专项事件。访客 LLM 迁移的审计入口随 Task 7 前端访客 LLM 配置迁移能力一起接入。

- [x] **Step 5：实现 admin 审计查询**

在 `src/codeask/api/metrics.py` 或 `src/codeask/api/audit.py` 中提供：

- `GET /api/audit-log`
- admin-only
- 支持 `action`、`subject`、`entity_id`、`limit`、`offset`
- 新记录在前

- [x] **Step 6：运行 Task 6 测试**

Run:

```bash
uv run pytest tests/integration/test_audit_authz_api.py tests/unit/test_metrics_audit_writer.py -v
```

Expected: PASS。

- [ ] **Step 7：提交**

Run:

```bash
git add src/codeask/audit src/codeask/api src/codeask/db/models/audit_log.py alembic/versions tests/integration/test_audit_authz_api.py tests/unit/test_metrics_audit_writer.py
git commit -m "feat(audit): record auth and authorization events"
```

## Task 7：前端登录、用户设置与访客 LLM

**文件：**
- Modify: `frontend/src/lib/identity.ts`
- Modify: `frontend/src/lib/api-auth.ts`
- Create: `frontend/src/lib/api-users.ts`
- Modify: `frontend/src/lib/api-client.ts`
- Modify: `frontend/src/lib/auth-cache.ts`
- Modify: `frontend/src/components/auth/AdminLoginPage.tsx`
- Modify: `frontend/src/components/layout/TopBar.tsx`
- Modify: `frontend/src/components/settings/UserSettings.tsx`
- Create: `frontend/src/components/settings/GuestLlmConfig.tsx`
- Modify: `frontend/src/types/api.ts`
- Create: `frontend/tests/auth-cache.test.ts`
- Create: `frontend/tests/guest-llm-config.test.ts`

- [ ] **Step 1：写前端缓存测试**

创建 `frontend/tests/auth-cache.test.ts`：

```ts
import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { resetSubjectScopedQueries } from "../src/lib/auth-cache";

describe("resetSubjectScopedQueries", () => {
  it("clears sessions and role scoped settings", () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(["sessions"], [{ id: "sess_1" }]);
    queryClient.setQueryData(["feature-admins", 1], [{ username: "alice" }]);
    queryClient.setQueryData(["auth", "me"], { username: "alice" });

    resetSubjectScopedQueries(queryClient);

    expect(queryClient.getQueryData(["sessions"])).toBeUndefined();
    expect(queryClient.getQueryData(["feature-admins", 1])).toBeUndefined();
    expect(queryClient.getQueryData(["auth", "me"])).toEqual({ username: "alice" });
  });
});
```

- [ ] **Step 2：确认测试失败**

Run: `corepack pnpm --dir frontend test:run auth-cache.test.ts`

Expected: FAIL。

- [ ] **Step 3：实现前端身份和 API**

修改：

- `identity.ts`：保留匿名浏览器 ID，新增访客 LLM localStorage helper。
- `api-auth.ts`：登录、退出、`me`、改用户名、改密码。
- `api-users.ts`：用户搜索、清空密码。
- `api-client.ts`：继续发送 `X-Subject-Id`，会话请求支持携带访客 LLM 配置。
- `auth-cache.ts`：清理 sessions、session-turns、session-traces、session-attachments、feature-admins、wiki-tree、wiki-documents、user-llm-configs 等身份相关缓存。

- [ ] **Step 4：实现登录页和用户设置**

修改：

- `AdminLoginPage.tsx`：改为通用登录，文案为“首次使用会自动创建账号”。
- `TopBar.tsx`：显示用户名、角色、登录/退出、设置入口。
- `UserSettings.tsx`：未登录显示浏览器 ID 和访客 LLM；登录用户显示用户名和密码修改；admin 用户名固定不可改。
- `GuestLlmConfig.tsx`：保存访客 LLM 到浏览器本地。

- [ ] **Step 5：运行 Task 7 测试**

Run:

```bash
corepack pnpm --dir frontend test:run auth-cache.test.ts guest-llm-config.test.ts
corepack pnpm --dir frontend typecheck
```

Expected: PASS。

- [ ] **Step 6：提交**

Run:

```bash
git add frontend/src/lib/identity.ts frontend/src/lib/api-auth.ts frontend/src/lib/api-users.ts frontend/src/lib/api-client.ts frontend/src/lib/auth-cache.ts frontend/src/components/auth/AdminLoginPage.tsx frontend/src/components/layout/TopBar.tsx frontend/src/components/settings/UserSettings.tsx frontend/src/components/settings/GuestLlmConfig.tsx frontend/src/types/api.ts frontend/tests/auth-cache.test.ts frontend/tests/guest-llm-config.test.ts
git commit -m "feat(ui): add unified auth and guest llm settings"
```

## Task 8：前端特性管理员、用户管理与权限 UI

**文件：**
- Create: `frontend/src/lib/api-feature-admins.ts`
- Modify: `frontend/src/components/features/FeatureTabs.tsx`
- Create: `frontend/src/components/features/FeatureAdminsPanel.tsx`
- Modify: `frontend/src/components/features/FeatureWorkbench.tsx`
- Modify: `frontend/src/components/features/FeatureSettings.tsx`
- Modify: `frontend/src/components/features/ReposPanel.tsx`
- Modify: `frontend/src/components/features/KnowledgePanel.tsx`
- Modify: `frontend/src/components/features/ReportsPanel.tsx`
- Modify: `frontend/src/components/settings/GlobalSettings.tsx`
- Create: `frontend/src/components/settings/users/UserManager.tsx`
- Create: `frontend/tests/feature-admins-ui.test.tsx`

- [ ] **Step 1：写 UI 测试**

创建 `frontend/tests/feature-admins-ui.test.tsx`，先验证非 admin 只能看管理员列表，看不到添加/删除按钮。

- [ ] **Step 2：确认测试失败**

Run: `corepack pnpm --dir frontend test:run feature-admins-ui.test.tsx`

Expected: FAIL。

- [ ] **Step 3：实现特性管理员前端**

- `api-feature-admins.ts`：实现 list/search/add/remove。
- `FeatureAdminsPanel.tsx`：所有人可查看列表；只有 admin 显示搜索、添加、删除。
- `FeatureTabs.tsx`：新增“管理员”tab。
- 添加和删除成功使用轻量 toast，失败使用居中弹窗。

- [ ] **Step 4：实现权限 UI**

- `FeatureWorkbench.tsx`：创建特性按钮保留；非 admin 点击弹窗“请联系管理员添加”。
- `FeatureSettings.tsx`：非授权用户看只读内容。
- `ReposPanel.tsx`：只有 admin 或特性管理员显示关联/取消关联。
- `KnowledgePanel.tsx` 和 Wiki 入口：只读保留，上传/编辑跳转只对授权用户显示。
- `ReportsPanel.tsx`：报告查看开放，编辑/删除/验证只对授权用户显示。

- [ ] **Step 5：实现全局用户管理**

- `GlobalSettings.tsx`：新增附件上传开关和 `UserManager`。
- `UserManager.tsx`：admin 搜索用户、查看密码状态、清空普通用户密码；不显示清空 admin 密码按钮。

- [ ] **Step 6：运行 Task 8 测试**

Run:

```bash
corepack pnpm --dir frontend test:run feature-admins-ui.test.tsx
corepack pnpm --dir frontend typecheck
```

Expected: PASS。

- [ ] **Step 7：提交**

Run:

```bash
git add frontend/src/lib/api-feature-admins.ts frontend/src/components/features frontend/src/components/settings/GlobalSettings.tsx frontend/src/components/settings/users/UserManager.tsx frontend/tests/feature-admins-ui.test.tsx
git commit -m "feat(ui): add feature admin and user management controls"
```

## Task 9：真实浏览器 E2E

**文件：**
- Create: `frontend/e2e/auth-access-control.spec.ts`
- Read: `frontend/playwright.config.ts`

- [ ] **Step 1：新增 Playwright 场景**

创建 `frontend/e2e/auth-access-control.spec.ts`，覆盖：

- 匿名用户能发起会话。
- 匿名用户能看特性和 Wiki。
- 匿名用户不能写特性和 Wiki。
- 普通用户自动注册后迁移匿名会话。
- admin 登录不迁移匿名会话。
- 非 admin 点击创建特性显示“请联系管理员添加”。
- admin 能创建特性。
- admin 能添加/删除特性管理员。
- 特性管理员能写授权特性 Wiki，不能写未授权特性 Wiki。
- 附件上传开关关闭时，点击上传显示“该功能已被禁用”。
- API 直接请求未授权写接口返回 401 或 403。

- [ ] **Step 2：运行 v1.0.3 E2E**

Run:

```bash
corepack pnpm --dir frontend test:e2e -- auth-access-control.spec.ts --project=chromium
```

Expected: PASS，必须是真实 Chromium 浏览器。

- [ ] **Step 3：运行关键回归 E2E**

Run:

```bash
corepack pnpm --dir frontend test:e2e -- route-refresh.spec.ts wiki-tail.spec.ts auth-session-switch.spec.ts --project=chromium
```

Expected: PASS。

- [ ] **Step 4：提交**

Run:

```bash
git add frontend/e2e/auth-access-control.spec.ts
git commit -m "test(e2e): cover auth access control"
```

## Task 10：全量回归、文档和人工验收

**文件：**
- Modify: `docs/v1.0.3/README.md`
- Modify: `docs/v1.0.3/specs/auth-access-control.md`
- Modify: `docs/DEVELOPMENT_ACCEPTANCE.md`
- Modify: `README.md`
- Modify: `INSTALL.md`

- [ ] **Step 1：更新文档**

- `docs/v1.0.3/README.md`：记录实现状态和测试入口。
- `docs/DEVELOPMENT_ACCEPTANCE.md`：补充鉴权功能必须跑真实浏览器 E2E。
- `INSTALL.md`：记录默认 admin 用户名、默认密码、环境变量兜底。
- `README.md`：只保留产品层面的说明和快速启动入口。

- [ ] **Step 2：运行后端定向测试**

Run:

```bash
uv run pytest tests/unit/test_auth_passwords.py tests/unit/test_auth_sessions.py tests/unit/test_feature_permissions.py tests/integration/test_auth_users_api.py tests/integration/test_feature_admins_api.py tests/integration/test_authz_features_api.py tests/integration/test_authz_wiki_api.py tests/integration/test_attachment_upload_gate.py tests/integration/test_audit_authz_api.py -v
```

Expected: PASS。

- [ ] **Step 3：运行后端广域回归**

Run:

```bash
uv run pytest tests/unit tests/integration -q
```

Expected: PASS。

- [ ] **Step 4：运行前端测试**

Run:

```bash
corepack pnpm --dir frontend test:run
corepack pnpm --dir frontend typecheck
```

Expected: PASS。

- [ ] **Step 5：运行真实浏览器 E2E**

Run:

```bash
corepack pnpm --dir frontend test:e2e -- auth-access-control.spec.ts route-refresh.spec.ts wiki-tail.spec.ts auth-session-switch.spec.ts --project=chromium
```

Expected: PASS。

- [ ] **Step 6：启动前后端做人工浏览器验收**

后端：

```bash
CODEASK_DATA_DIR=/tmp/codeask-v103-auth \
CODEASK_DATA_KEY=dev-auth-key-32-bytes-minimum-value \
uv run uvicorn codeask.app:create_app --factory --host 0.0.0.0 --port 8000
```

前端：

```bash
corepack pnpm --dir frontend dev --host 0.0.0.0
```

人工验收：

- 匿名会话可问答。
- 匿名可查看特性和 Wiki。
- 普通用户登录迁移匿名会话。
- admin 登录不迁移匿名会话。
- 非 admin 创建特性提示“请联系管理员添加”。
- admin 添加特性管理员。
- 特性管理员只能操作授权特性。
- 附件上传开关关闭后上传提示“该功能已被禁用”。
- 审计日志记录登录、拒绝、授权变更、附件拒绝。

- [ ] **Step 7：提交收尾文档**

Run:

```bash
git add docs/v1.0.3/README.md docs/v1.0.3/specs/auth-access-control.md docs/DEVELOPMENT_ACCEPTANCE.md README.md INSTALL.md
git commit -m "docs(v1.0.3): document auth acceptance status"
```

## 最终验收清单

- [ ] 匿名会话无需登录可用。
- [ ] 匿名可读特性和 Wiki。
- [ ] 匿名不能执行特性和 Wiki 写操作。
- [ ] 普通用户自动注册可用。
- [ ] 普通用户登录迁移匿名会话。
- [ ] admin 登录不迁移匿名会话。
- [ ] 用户名大小写敏感。
- [ ] 密码大小写敏感，trim 后至少 6 位。
- [ ] admin 可清空普通用户密码。
- [ ] 密码被清空的用户可下次登录重新设置密码。
- [ ] 添加特性管理员候选过滤 `admin`。
- [ ] 特性管理员不能添加或删除特性管理员。
- [ ] 全局配置 admin-only。
- [ ] 特性配置和 Wiki 写操作仅 admin 或特性管理员可用。
- [ ] 匿名和普通用户可基于自己的会话生成问题报告草稿。
- [ ] 问题报告管理仅 admin 或特性管理员可用。
- [ ] 访客 LLM 配置只保存在浏览器本地。
- [ ] 访客 LLM 配置可随请求用于单次模型调用，且不落库。
- [ ] 访客 LLM 配置可迁移到普通用户，不能迁移到 admin。
- [ ] 附件上传开关关闭时禁止所有新上传。
- [ ] 审计日志记录要求的鉴权和授权事件。
- [ ] Playwright 真实浏览器 E2E 通过。

## 自审结果

- 需求覆盖：设计文档中的身份、权限、用户管理、附件、LLM、报告、审计、E2E 要求均有对应任务。
- 占位扫描：计划文档不包含未解决占位标记。
- 类型一致：后端统一使用 `Actor`、`User`、`AuthSession`、`FeatureAdmin`；前端统一使用 `auth/me`、用户 API、特性管理员 API。
