# Frontend Workbench Handoff

> Date: 2026-05-03
>
> This handoff records the implemented frontend-workbench surface after the Phase B/C corrections. It supersedes older frontend-workbench plan snippets that still describe a dashboard-first layout, mine/all session toggle, global LLM visibility for anonymous users, manual report creation from feature pages, full LLM Wiki management as current-stage deliverables, or router/shadcn/fetch-event-source choices that were not adopted by the current implementation.

## 1. Current Goal

The current frontend-workbench stage is a usable R&D knowledge workbench with three primary entries:

| Entry | Current role |
|---|---|
| 会话 | Ask questions, stream Agent progress, manage per-session attachments, generate reports |
| 特性 | Manage feature list, feature settings, knowledge uploads, generated reports, repo links, feature analysis policies |
| 设置 | Member personal settings and personal LLM configs; admin global LLM configs, repo management, and global analysis policies |

This stage is now in stabilization and handoff. New large product surfaces should not be added to frontend-workbench until this handoff is accepted.

## 2. Implemented Shell And Navigation

- Top bar shows logo + `CodeAsk`.
- The old "研发知识工作台" top-bar descriptor is removed.
- Top-right account menu is role-aware:
  - anonymous/member: login only
  - admin: personal info, settings, logout
- Login page is neutral before authentication and includes password visibility toggle.
- Primary sidebar has exactly three top-level entries: `会话 / 特性 / 设置`.
- Primary sidebar and secondary sidebars support collapse/expand from the middle-right edge of the panel.
- The app is currently a Vite React SPA in `frontend/`; routes are state-driven inside `AppShell`, not TanStack Router file routes.

## 3. Identity And Permissions

Current identity behavior:

1. Anonymous users can open the URL directly.
2. The browser generates a local subject id and sends it as `X-Subject-Id`.
3. Admin login writes an HttpOnly cookie.
4. `GET /api/auth/me` is the source of role truth.

Admin bootstrap defaults:

| Field | Default |
|---|---|
| username | `admin` |
| password | `admin` |

Environment overrides:

- `CODEASK_ADMIN_USERNAME`
- `CODEASK_ADMIN_PASSWORD`
- `CODEASK_ADMIN_SESSION_TTL_HOURS`

Permission boundaries implemented in the workbench:

| Resource | Member | Admin |
|---|---|---|
| Own sessions | yes | yes |
| User settings | yes | no personal settings section |
| Personal LLM configs | yes | no |
| Global LLM configs | no | yes |
| Repo list read | yes | yes |
| Repo create/edit/delete/sync | no | yes |
| Global analysis policies | no | yes |

## 4. Sessions

Implemented:

- Session list scoped to current subject.
- No "我的 / 全部" toggle.
- Search + new session at the top of the session list.
- Row actions are under a three-dot menu:
  - edit name
  - share placeholder
  - pin/unpin
  - bulk operation mode
  - delete
- Delete requires confirmation.
- Bulk mode shows checkboxes and supports bulk delete.
- Empty state keeps composer usable.
- Sending without an existing session creates a default session first.
- Current session header shows a compact `sess_xxxx` pill.
- Clicking the session id pill copies the full session id and shows a short local success popover.

Session attachments:

- Upload is available even before an explicit session exists; upload creates a default session if needed.
- Attachments are scoped by session.
- Switching sessions reloads the selected session's attachment list.
- The attachment panel supports:
  - upload
  - rename display name
  - edit description
  - delete
- Attachment storage uses `attachment_id` as the stable physical key.
- `original_filename` remains immutable.
- `aliases` and `reference_names` preserve user-facing name history for Agent prompt mapping.
- `manifest.json` mirrors DB metadata for operational inspection.
- Deleting a session removes the associated session storage directory.

Report generation:

- The action sits in the composer action row, next to force-code-investigation and send.
- It checks whether there is enough basic conversation before generating.
- It opens a confirmation dialog.
- A report must bind to a feature; if inference is unclear, the user chooses one.
- Success returns a link into the bound feature's `问题报告` tab.

## 5. Features

Implemented:

- Feature list has search + add at the top.
- Feature creation does not ask for slug.
- Feature rows show feature name and slug.
- Feature rows expose a visible delete icon.
- Delete opens confirmation before calling `DELETE /api/features/{feature_id}`.
- Successful delete removes the row and invalidates the feature query.
- Feature detail tabs:
  - 设置
  - 知识库
  - 问题报告
  - 关联仓库
  - 特性分析策略

Feature reports:

- The feature page does not manually create problem reports.
- Reports generated from sessions appear in the feature's `问题报告` tab.

Feature repo links:

- Feature pages read the global repo pool through `GET /api/repos`.
- Repo association is checkbox-based.
- Feature pages do not register repositories.

Feature analysis policies:

- Feature scoped analysis policies can be created, edited, enabled/disabled, and deleted.
- Policies include stage, priority, enabled state, and prompt template.
- Runtime prompt injection reads enabled global and feature policies, filters by stage, and sorts by priority.

## 6. Settings

Member settings:

- User settings show subject id and nickname.
- Personal LLM config management is available to members.

Admin settings:

- Admin settings does not show the personal user settings page.
- Admin settings contains global LLM config management.
- Admin settings contains global repo management.
- Admin settings contains global analysis policy management.

LLM config UI:

- Create, edit, enable/disable, and delete are implemented.
- Enable/disable uses switch controls.
- Add uses a primary CTA.
- Protocol dropdown exposes:
  - OpenAI
  - Anthropic
- The UI does not expose:
  - Max Tokens
  - Temperature
  - RPM
  - remaining quota
  - "set default"
- API create/update payloads do not send hidden runtime fields.
- Backend defaults:
  - `max_tokens = 200 * 1024`
  - `temperature = 0.2`
- RPM and quota are retained only as compatibility fields and are ignored by current runtime selection.
- Provider failures are returned as call errors instead of being hidden behind quota/RPM scheduling.

Repo management:

- Global repo management supports create, edit, sync/retry sync, and delete.
- Repo edit fields use the same single-column width as analysis policy forms.
- The action label is `同步` or `重试同步`; the old `刷新` wording is not used.
- The backend schedules an hourly refresh for all non-`cloning` repos.
- Local directories that are git worktrees and have `origin` are fetched and pulled before CodeAsk updates the bare cache.

Analysis policy UI:

- The product wording is analysis policy, not full Skill Package.
- Global settings and feature details both use the same policy manager.
- Policies support name, stage, priority, enabled switch, prompt template, edit, delete, and create.
- Runtime injection uses enabled global + feature policies filtered by stage and sorted by priority.

## 7. Current API Surface Consumed By Frontend

Auth:

- `GET /api/auth/me`
- `POST /api/auth/admin/login`
- `POST /api/auth/logout`

Sessions:

- `GET /api/sessions`
- `POST /api/sessions`
- `PATCH /api/sessions/{id}`
- `DELETE /api/sessions/{id}`
- `POST /api/sessions/bulk-delete`
- `GET /api/sessions/{id}/turns`
- `GET /api/sessions/{id}/traces`
- `POST /api/sessions/{id}/messages`
- `GET /api/sessions/{id}/attachments`
- `POST /api/sessions/{id}/attachments`
- `PATCH /api/sessions/{id}/attachments/{attachment_id}`
- `DELETE /api/sessions/{id}/attachments/{attachment_id}`
- `POST /api/sessions/{id}/reports`

Features / knowledge / reports:

- `GET /api/features`
- `POST /api/features`
- `PUT /api/features/{id}`
- `DELETE /api/features/{id}`
- `GET /api/documents?feature_id={id}`
- `POST /api/documents`
- `DELETE /api/documents/{id}`
- `GET /api/reports?feature_id={id}`

Repos:

- `GET /api/repos`
- `POST /api/repos`
- `PATCH /api/repos/{id}`
- `DELETE /api/repos/{id}`
- `POST /api/repos/{id}/refresh`
- `GET /api/features/{feature_id}/repos`
- `POST /api/features/{feature_id}/repos/{repo_id}`
- `DELETE /api/features/{feature_id}/repos/{repo_id}`

Analysis policies (`/api/skills` compatibility path):

- `GET /api/skills`
- `POST /api/skills`
- `PATCH /api/skills/{id}`
- `DELETE /api/skills/{id}`

LLM configs:

- `GET /api/me/llm-configs`
- `POST /api/me/llm-configs`
- `PATCH /api/me/llm-configs/{id}`
- `DELETE /api/me/llm-configs/{id}`
- `GET /api/admin/llm-configs`
- `POST /api/admin/llm-configs`
- `PATCH /api/admin/llm-configs/{id}`
- `DELETE /api/admin/llm-configs/{id}`

Metrics:

- `POST /api/feedback`
- `POST /api/events`
- `GET /api/audit-log`

## 8. Verification Commands

Frontend-workbench handoff should be verified with:

```bash
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
corepack pnpm --dir frontend test:run
corepack pnpm --dir frontend build
corepack pnpm --dir frontend test:e2e
git diff --check
```

Local dev servers:

```bash
CODEASK_HOST=0.0.0.0 CODEASK_PORT=8000 uv run codeask
corepack pnpm --dir frontend dev --host 0.0.0.0 --port 5173
```

## 9. Deferred Items

The following items are explicitly deferred and should not block frontend-workbench handoff:

| Deferred item | Next owner |
|---|---|
| Full LLM Wiki directory upload and management | Dedicated LLM Wiki plan |
| Wiki file tree, preview, edit, delete, and re-index workflow | Dedicated LLM Wiki plan |
| Relative image/resource preservation for uploaded wiki directories | Dedicated LLM Wiki plan |
| Markdown cross-reference parsing | Dedicated LLM Wiki plan |
| Full Skill Package semantics beyond prompt analysis policies | Agent/runtime follow-up |
| Maintainer Dashboard aggregation and UI backed by raw metrics data | frontend follow-up |
| Enterprise auth provider | post-v1.0 auth plan |
| Docker / compose / image packaging | post-v1.0 packaging plan |

## 10. Next Plan

After this handoff, completed follow-up plans include:

- `metrics-eval`: raw feedback, frontend events, audit log, eval harness, and CI workflow.
- `deployment`: backend static mount, local `start.sh`, CI, and security smoke.
- `admin-repo-analysis-policy`: repo edit/sync semantics, analysis policy fields, runtime injection, and UI management.

Remaining product follow-ups:

- Full LLM Wiki should remain a separate plan because it changes knowledge ingestion, storage, resource mapping, preview/edit UX, and Agent retrieval context.
- Maintainer Dashboard should be implemented from raw `feedback`, `frontend_events`, `audit_log`, and `agent_traces` data instead of mock-only UI.
- Docker packaging should stay separate from the v1.0 local single-process deployment contract.
