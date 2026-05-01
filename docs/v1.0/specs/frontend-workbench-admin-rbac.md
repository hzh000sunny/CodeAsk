# Frontend Workbench Admin/RBAC Correction Spec

> Date: 2026-05-01
>
> This spec amends the original v1.0 frontend workbench plan. It supersedes older text that said global configuration is visible to every self-reported user.

## 1. Goal

The next frontend-workbench stage uses a phased correction strategy:

1. Keep anonymous, zero-friction access for normal users.
2. Add a built-in administrator login for global configuration.
3. Prevent normal users from reading global LLM provider details.
4. Move global repository registration into settings.
5. Turn session and feature pages into management surfaces instead of one-off forms.

## 2. Identity And Roles

CodeAsk now has two identity modes:

| Mode | Role | How It Is Identified | Access |
|---|---|---|---|
| Anonymous self-report | `member` | Browser-generated `X-Subject-Id` | Own sessions, own user settings, own LLM configs |
| Built-in admin | `admin` | Admin login cookie | Own admin sessions plus global settings, global LLM configs, and repo management; no personal/user settings section in UI |

Anonymous access remains enabled by default. A normal user can open the URL and use CodeAsk without logging in.

Admin login is intentionally small for v1.0:

- `POST /api/auth/admin/login` accepts a username and password.
- The default bootstrap account is username `admin`, password `admin`.
- The username comes from `CODEASK_ADMIN_USERNAME` when set.
- The password comes from `CODEASK_ADMIN_PASSWORD` when set.
- If `CODEASK_ADMIN_PASSWORD` is unset, local development accepts `admin`.
- Successful login writes an HttpOnly cookie.
- `POST /api/auth/logout` clears the cookie.
- `GET /api/auth/me` returns the effective role and display label.

This is not the final enterprise auth provider. It is a bridge that protects global configuration until the AuthProvider abstraction is implemented.

## 3. Global App Shell

The workbench shell is:

```text
TopBar
  Left: logo mark + CodeAsk
  Right: current user avatar/name + menu

Sidebar
  会话
  特性
  设置

Main
  current page
```

The older sidebar caption "研发知识工作台" is removed.

The account menu contains:

- Before admin login: only `登录`, which opens a neutral login page.
- After admin login: `个人信息`, `设置`, and `退出`.

Unsupported entries show "暂不支持" instead of silently doing nothing.

Primary and secondary sidebars must both support collapse and expand. The
primary sidebar collapses to icons, while session / feature / settings secondary
sidebars collapse to a narrow rail with a restore button. Collapse controls sit
on the middle-right boundary between the sidebar and the adjacent content, not
in the sidebar header; hover uses a subtle arrow/floating motion to indicate the
collapse or expand direction.

The login page itself must not expose administrator wording before credentials
are accepted. It uses the generic heading `登录`, generic failed-login feedback,
and password visibility toggle affordance.

## 4. LLM Configuration Scope

LLM configs are no longer a single global-only list.

Each config has:

| Field | Meaning |
|---|---|
| `scope` | `user` or `global` |
| `owner_subject_id` | required for user configs, null for global configs |
| `enabled` | whether this config can be selected by the runtime |
| `protocol` | message protocol adapter. Current workbench dropdown exposes `openai` and `anthropic` only |
| `max_tokens` | backend default is `200 * 1024`; hidden from the workbench configuration UI |
| `temperature` | backend default is `0.2`; hidden from the workbench configuration UI |
| `is_default` | legacy compatibility field only; the new workbench does not expose a "set default" operation |
| `rpm_limit` | retained for future scheduling, hidden from the current UI and ignored by current runtime selection |
| `quota_remaining` | retained for future scheduling, hidden from the current UI and ignored by current runtime selection |

Runtime selection:

1. If the request has an explicit `config_id`, it must belong to the current user or to an enabled global config visible to the runtime.
2. Otherwise, choose an enabled user config for the current subject.
3. If the user has no enabled config, choose an enabled global config.
4. If several configs are enabled, current v1.0 workbench behavior is deterministic by creation order; there is no default toggle in the UI.
5. Current v1.0 does not maintain quota/RPM state. Provider rate-limit, quota, or protocol failures are returned as call errors instead of being hidden behind a load-balancing decision.

Visibility:

- Members can list/create/update/delete only `/api/me/llm-configs`.
- Admins can list/create/update/delete `/api/admin/llm-configs`.
- `/api/llm-configs` is deprecated for UI usage and should not expose global provider details to members.

Workbench UI requirements:

- The add action is a primary action button, not a low-contrast secondary button.
- Each LLM config row exposes enabled state as a compact switch control.
- Each LLM config row exposes edit and delete actions.
- Editing happens inline on the same settings page and supports name, protocol, base URL, API key rotation, and model name.
- The edit form must not expose `max_tokens`, `temperature`, `is_default`, `rpm_limit`, or `quota_remaining`.

## 5. Global Repository Management

Global repository registration belongs in admin settings.

Endpoints use the existing repository resource path. Read access is open because
feature pages need the global repository pool for checkbox linking, while
mutating operations require the admin role:

- `GET /api/repos` — readable by members and admins.
- `POST /api/repos` — admin only.
- `DELETE /api/repos/{repo_id}` — admin only.
- `POST /api/repos/{repo_id}/refresh` — admin only.

`/api/admin/repos` is not part of the current v1.0 implementation. It can be
added later as an alias if the API surface needs a stricter admin namespace.

Feature pages do not register repositories. They only link or unlink existing global repositories:

- `GET /api/features/{feature_id}/repos`
- `POST /api/features/{feature_id}/repos/{repo_id}`
- `DELETE /api/features/{feature_id}/repos/{repo_id}`

The feature UI presents global repos as checkbox rows.

Feature list actions:

- The feature list uses search + add at the top.
- Each feature row shows the name and slug, plus a visible delete icon action.
- Delete opens a confirmation dialog before calling `DELETE /api/features/{feature_id}`.
- After successful deletion, the row is removed from the current list and the feature query is invalidated.
- Feature deletion is a list-management action; it should not be hidden inside the feature detail tabs.

## 6. Sessions

Session list rows use a three-dot menu instead of a visible delete-only icon.

Minimum row menu:

- 编辑名称
- 分享
- 置顶
- 批量操作
- 删除

Current behavior:

- 编辑名称 calls `PATCH /api/sessions/{session_id}`.
- 置顶 calls `PATCH /api/sessions/{session_id}` with `pinned`.
- 删除 calls `DELETE /api/sessions/{session_id}` after confirmation.
- 分享 shows "暂不支持".
- 批量操作 enters selection mode.

Bulk mode:

- A checkbox appears before every session row.
- Users can select multiple rows.
- Bulk delete calls `POST /api/sessions/bulk-delete`.

Default session:

- If no session exists, the composer remains usable.
- Sending a message automatically creates a default session and immediately posts the message to it.

Report generation:

- The composer action row exposes "生成报告" to the left of the send button and
  to the right of "强制代码调查".
- The first backend contract is `POST /api/sessions/{session_id}/reports`.
- Clicking "生成报告" first opens a confirmation flow, or a blocking message if
  the session has not completed at least one user question and agent answer.
- A report must bind to a feature. If the runtime cannot infer a feature with
  enough confidence, the confirmation dialog requires the user to choose one.
- The endpoint creates a draft report from the session context and rejects
  sessions without a completed question/answer.
- After generation, the UI shows a success dialog with a link into the bound
  feature's "问题报告" tab and selects the generated report.
- Feature-side reports list those reports; it does not create reports directly.

Session attachments:

- Uploading a log before any session exists creates a default session first.
- Attachments are listed from `/api/sessions/{session_id}/attachments` and scoped to the selected session.
- Repeated filenames are allowed; the physical path uses `attachment_id`, while the UI shows editable `display_name`, original filename, size, and short ID.
- Rename and delete use `PATCH` / `DELETE /api/sessions/{session_id}/attachments/{attachment_id}`.

Personal LLM config endpoints:

- `/api/me/llm-configs` is for ordinary `member` subjects only.
- Built-in admin users manage global model accounts through `/api/admin/llm-configs`.
- Admin requests to `/api/me/llm-configs` return 403 so the admin role does not create or display personal/user configuration.

## 7. Features

Feature creation only asks for:

- name
- description

Slug is generated by the backend. The frontend may display it as metadata, but it is not user input in the create flow.

Knowledge management current boundary:

- The current frontend-workbench keeps a feature knowledge tab and basic document upload/list/delete access.
- Full LLM Wiki management is explicitly deferred to a dedicated plan, including directory upload, relative resource preservation, preview, content editing, metadata editing, and re-index workflow.
- Directory upload should remain a separate future endpoint because it creates a group of related documents/resources.

Reports:

- Feature report tab lists reports created from sessions.
- Manual report creation from the feature page is removed.

Skills:

- Feature skill tab supports create, list, edit, delete.
- A skill can be enabled/selected for the feature.
- Runtime skill selection is explicit in the session payload or derived from the feature default.

## 8. Phase B Implementation Boundary

This stage implements:

- TopBar and account menu.
- Built-in admin login and logout.
- Role-aware settings visibility.
- Admin settings page shows only global configuration; admins do not get a personal/user settings section in the current UI.
- User/global LLM config API separation.
- Global repository management in admin settings.
- Session three-dot menu, rename, pin, bulk delete, delete confirmation.
- Default session auto-create on send.
- Session report draft endpoint and UI entry.
- Feature creation without slug input.
- Feature report tab as read-only report list.
- Feature repo tab as checkbox linker over global repo pool.

This stage documents but does not fully implement:

- Directory wiki upload with image/resource storage.
- Rich wiki preview/edit/re-index workflow.
- Real quota/RPM LLM load balancing.
- Enterprise SSO/OIDC/LDAP providers.
