# Maintainability Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split oversized frontend components and backend routers into focused modules without changing product behavior, API contracts, storage layout, or test expectations.

**Architecture:** This is a behavior-preserving refactor. Frontend page containers keep orchestration state while list panels, dialogs, forms, tabs, cache helpers, and pure model transforms move into nearby files. Backend routers keep the same public paths while route handlers and pure helpers move into domain-focused modules.

**Tech Stack:** React 19, TypeScript, TanStack Query, FastAPI, SQLAlchemy async, pytest, Vitest, uv, pnpm.

---

## Non-Negotiable Boundaries

- Do not change any API path, request schema, response schema, SSE event name, database schema, storage directory, or user-visible behavior.
- Do not redesign the UI; preserve existing class names, labels, dialogs, and test-visible text.
- Do not introduce new dependencies or global state frameworks.
- Preserve the current `main` branch behavior and keep the worktree clean of generated cache files.
- Run focused tests after each refactor slice and full verification before claiming completion.

## Target File Structure

### Frontend Session Module

```text
frontend/src/components/session/
├── SessionWorkspace.tsx
├── SessionListPanel.tsx
├── SessionListItem.tsx
├── SessionConversationPanel.tsx
├── SessionHeader.tsx
├── SessionComposer.tsx
├── SessionDialogs.tsx
├── SessionWorkspaceDialogs.tsx
├── session-cache.ts
├── session-clipboard.ts
├── session-feedback.ts
├── session-history.ts
├── useSessionNotices.ts
└── session-model.ts
```

Responsibilities:

- `SessionWorkspace.tsx`: page-level orchestration, selected session state, mutations, and three-column layout.
- `SessionListPanel.tsx`: session search, new-session button, bulk selection toolbar, and list rendering.
- `SessionListItem.tsx`: one session row and its portal menu.
- `SessionConversationPanel.tsx`: middle-column composition for header, action notice, message stream, and composer.
- `SessionHeader.tsx`: title, status badge, short session ID, and copy success popover.
- `SessionComposer.tsx`: textarea, upload trigger, force-code checkbox, report action, send action.
- `SessionDialogs.tsx`: delete, bulk delete, report readiness, report confirmation, and report success dialogs.
- `SessionWorkspaceDialogs.tsx`: page-level dialog composition and callbacks for session delete and report flows.
- `session-cache.ts`: query keys and TanStack cache upsert helpers.
- `session-clipboard.ts`: clipboard fallback and short session ID formatter.
- `session-feedback.ts`: feedback label helper.
- `session-history.ts`: persisted turns/traces to conversation messages, runtime insights, and stages.
- `useSessionNotices.ts`: session ID copy toast and transient action notices.

### Frontend Settings Module

```text
frontend/src/components/settings/
├── SettingsPage.tsx
├── UserSettings.tsx
├── GlobalSettings.tsx
├── SwitchControl.tsx
├── settings-types.ts
├── settings-utils.ts
├── llm/
│   ├── LlmConfigManager.tsx
│   ├── LlmConfigList.tsx
│   ├── LlmConfigForm.tsx
│   └── LlmConfigEditForm.tsx
└── repos/
    ├── RepoManager.tsx
    ├── RepoCreateForm.tsx
    └── RepoRow.tsx
```

Responsibilities:

- `SettingsPage.tsx`: settings shell, secondary navigation, admin/user branch.
- `UserSettings.tsx`: ordinary user subject/nickname and personal LLM block.
- `GlobalSettings.tsx`: global LLM, global repos, and global analysis policies composition.
- `llm/*`: all LLM create/edit/list behavior.
- `repos/*`: global repository create/edit/sync/delete behavior.
- `settings-utils.ts`: API error and protocol label pure helpers.

### Frontend Feature Module

```text
frontend/src/components/features/
├── FeatureWorkbench.tsx
├── FeatureListPanel.tsx
├── FeatureListItem.tsx
├── FeatureDialogs.tsx
├── FeatureTabs.tsx
├── FeatureSettings.tsx
├── KnowledgePanel.tsx
├── ReportsPanel.tsx
├── ReposPanel.tsx
└── feature-utils.ts
```

Responsibilities:

- `FeatureWorkbench.tsx`: page-level selected feature state and layout.
- `FeatureListPanel.tsx`: feature search/create/list UI.
- `FeatureTabs.tsx`: tab selection to detail panel mapping.
- `KnowledgePanel.tsx`, `ReportsPanel.tsx`, `ReposPanel.tsx`: one tab surface per file.

### Frontend API Client Module

```text
frontend/src/lib/api.ts
frontend/src/lib/api-client.ts
frontend/src/lib/api-auth.ts
frontend/src/lib/api-sessions.ts
frontend/src/lib/api-audit.ts
frontend/src/lib/api-wiki.ts
frontend/src/lib/api-repos.ts
frontend/src/lib/api-skills.ts
frontend/src/lib/api-llm-configs.ts
```

Responsibilities:

- `api.ts`: preserve the existing public import path as a barrel export.
- `api-client.ts`: shared `ApiError`, `apiRequest`, JSON body handling, and subject header injection.
- `api-auth.ts`, `api-sessions.ts`, `api-audit.ts`, `api-wiki.ts`, `api-repos.ts`, `api-skills.ts`, `api-llm-configs.ts`: domain-specific API functions with the same names and payload shapes as before.

### Backend Sessions Module

```text
src/codeask/api/sessions.py
src/codeask/sessions/
├── __init__.py
├── attachments.py
├── messages.py
├── reports.py
└── traces.py
```

Responsibilities:

- `api/sessions.py`: keep the existing router and endpoint functions, but delegate storage, trace, and report helpers to `codeask.sessions`.
- `sessions/attachments.py`: attachment display names, descriptions, alias history, manifest writing, session storage dir collection, and storage dir cleanup.
- `sessions/messages.py`: user turn persistence, repo binding preparation, SSE response streaming, and assistant turn persistence.
- `sessions/reports.py`: completed-question-answer guard and generated report body.
- `sessions/traces.py`: trace visibility, trace payload normalization, and trace sorting priority.

### Backend Wiki Module

```text
src/codeask/api/wiki.py
src/codeask/wiki/api_support.py
```

Responsibilities:

- `api/wiki.py`: keep the existing router and endpoint functions.
- `wiki/api_support.py`: feature slug generation, repo response mapping, upload kind detection, wiki storage path, tag parsing, and markdown reference extraction.

This first pass intentionally does not split `api/wiki.py` into multiple routers. It lowers risk by moving pure support functions first; route-level splitting can follow after tests prove behavior stays stable.

### Backend Agent Tool Module

```text
src/codeask/agent/tools.py
src/codeask/agent/tool_models.py
src/codeask/agent/tool_schemas.py
src/codeask/agent/tool_delegates.py
```

Responsibilities:

- `tools.py`: preserve the public `ToolRegistry` import path and bootstrap flow.
- `tool_models.py`: shared tool result, context, exceptions, function type, and registered tool dataclass.
- `tool_schemas.py`: JSON schemas for runtime tools.
- `tool_delegates.py`: delegated tool registration, backend method dispatch, and result coercion.

## Task 1: Session Pure Helpers And Small Components

**Files:**

- Create: `frontend/src/components/session/session-cache.ts`
- Create: `frontend/src/components/session/session-clipboard.ts`
- Create: `frontend/src/components/session/session-feedback.ts`
- Create: `frontend/src/components/session/session-history.ts`
- Create: `frontend/src/components/session/SessionDialogs.tsx`
- Create: `frontend/src/components/session/SessionListItem.tsx`
- Create: `frontend/src/components/session/SessionConversationPanel.tsx`
- Create: `frontend/src/components/session/SessionHeader.tsx`
- Create: `frontend/src/components/session/SessionComposer.tsx`
- Create: `frontend/src/components/session/SessionWorkspaceDialogs.tsx`
- Create: `frontend/src/components/session/useSessionNotices.ts`
- Modify: `frontend/src/components/session/SessionWorkspace.tsx`
- Test: `frontend/tests/session-workspace.test.tsx`

Steps:

- [ ] Move query keys and cache upsert helpers out of `SessionWorkspace.tsx`.
- [ ] Move clipboard fallback, short session ID formatter, and feedback label out of `SessionWorkspace.tsx`.
- [ ] Move persisted history reconstruction out of `SessionWorkspace.tsx`.
- [ ] Move dialogs and session list row into focused components.
- [ ] Move header and composer into focused components.
- [ ] Move conversation-panel composition, page dialog composition, and transient notice timers into focused modules.
- [ ] Run `corepack pnpm --dir frontend test:run --maxWorkers=1 --minWorkers=1 tests/session-workspace.test.tsx`.
- [ ] Run `corepack pnpm --dir frontend typecheck`.

## Task 2: Settings Module Split

**Files:**

- Create: `frontend/src/components/settings/UserSettings.tsx`
- Create: `frontend/src/components/settings/GlobalSettings.tsx`
- Create: `frontend/src/components/settings/SwitchControl.tsx`
- Create: `frontend/src/components/settings/settings-types.ts`
- Create: `frontend/src/components/settings/settings-utils.ts`
- Create: `frontend/src/components/settings/llm/LlmConfigManager.tsx`
- Create: `frontend/src/components/settings/llm/LlmConfigList.tsx`
- Create: `frontend/src/components/settings/llm/LlmConfigForm.tsx`
- Create: `frontend/src/components/settings/llm/LlmConfigEditForm.tsx`
- Create: `frontend/src/components/settings/repos/RepoManager.tsx`
- Create: `frontend/src/components/settings/repos/RepoCreateForm.tsx`
- Create: `frontend/src/components/settings/repos/RepoRow.tsx`
- Modify: `frontend/src/components/settings/SettingsPage.tsx`
- Test: `frontend/tests/settings-page.test.tsx`

Steps:

- [ ] Move user/global settings panels out of `SettingsPage.tsx`.
- [ ] Move LLM manager and LLM forms into `settings/llm`.
- [ ] Move repository manager and forms into `settings/repos`.
- [ ] Keep all existing labels, class names, mutation behavior, and query keys unchanged.
- [ ] Run `corepack pnpm --dir frontend test:run --maxWorkers=1 --minWorkers=1 tests/settings-page.test.tsx`.
- [ ] Run `corepack pnpm --dir frontend typecheck`.

## Task 3: Feature Workbench Split

**Files:**

- Create: `frontend/src/components/features/FeatureListPanel.tsx`
- Create: `frontend/src/components/features/FeatureListItem.tsx`
- Create: `frontend/src/components/features/FeatureDialogs.tsx`
- Create: `frontend/src/components/features/FeatureTabs.tsx`
- Create: `frontend/src/components/features/FeatureSettings.tsx`
- Create: `frontend/src/components/features/KnowledgePanel.tsx`
- Create: `frontend/src/components/features/ReportsPanel.tsx`
- Create: `frontend/src/components/features/ReposPanel.tsx`
- Create: `frontend/src/components/features/feature-utils.ts`
- Modify: `frontend/src/components/features/FeatureWorkbench.tsx`
- Test: `frontend/tests/feature-workbench.test.tsx`

Steps:

- [ ] Move feature list and delete dialog into focused files.
- [ ] Move each tab body into its own component file.
- [ ] Keep the same tab IDs, query keys, upload behavior, report preview rendering, and repo checkbox semantics.
- [ ] Run `corepack pnpm --dir frontend test:run --maxWorkers=1 --minWorkers=1 tests/feature-workbench.test.tsx`.
- [ ] Run `corepack pnpm --dir frontend typecheck`.

## Task 4: Backend Session Helper Split

**Files:**

- Create: `src/codeask/sessions/__init__.py`
- Create: `src/codeask/sessions/attachments.py`
- Create: `src/codeask/sessions/messages.py`
- Create: `src/codeask/sessions/reports.py`
- Create: `src/codeask/sessions/traces.py`
- Modify: `src/codeask/api/sessions.py`
- Test: `tests/integration/test_sessions_api.py`

Steps:

- [ ] Move attachment manifest, display name, alias, description, and storage cleanup helpers to `codeask.sessions.attachments`.
- [ ] Move message persistence, repo binding, SSE streaming, and assistant turn persistence helpers to `codeask.sessions.messages`.
- [ ] Move report readiness and report body helpers to `codeask.sessions.reports`.
- [ ] Move trace visibility and priority helpers to `codeask.sessions.traces`.
- [ ] Keep endpoint function names, response models, and exception status codes unchanged.
- [ ] Run `uv run pytest tests/integration/test_sessions_api.py tests/unit/test_runtime_env.py -q`.

## Task 5: Backend Wiki Support Split

**Files:**

- Create: `src/codeask/wiki/api_support.py`
- Modify: `src/codeask/api/wiki.py`
- Test: wiki integration tests

Steps:

- [ ] Move slug generation, repo serialization, upload kind, storage path, tag parsing, and markdown reference extraction helpers to `codeask.wiki.api_support`.
- [ ] Keep endpoint function names, response models, and exception status codes unchanged.
- [ ] Run `uv run pytest tests/integration/test_wiki_documents_api.py tests/integration/test_wiki_reports_api.py tests/integration/test_wiki_search.py tests/integration/test_wiki_models.py -q`.

## Task 6: Frontend API Client Split

**Files:**

- Create: `frontend/src/lib/api-client.ts`
- Create: `frontend/src/lib/api-auth.ts`
- Create: `frontend/src/lib/api-sessions.ts`
- Create: `frontend/src/lib/api-audit.ts`
- Create: `frontend/src/lib/api-wiki.ts`
- Create: `frontend/src/lib/api-repos.ts`
- Create: `frontend/src/lib/api-skills.ts`
- Create: `frontend/src/lib/api-llm-configs.ts`
- Modify: `frontend/src/lib/api.ts`
- Test: `frontend/tests/api.test.ts`

Steps:

- [ ] Move shared request handling to `api-client.ts`.
- [ ] Move each API group into a domain-specific file.
- [ ] Keep `frontend/src/lib/api.ts` as the same public import path by re-exporting every domain module.
- [ ] Run `corepack pnpm --dir frontend test:run --maxWorkers=1 --minWorkers=1 tests/api.test.ts`.
- [ ] Run `corepack pnpm --dir frontend typecheck`.

## Task 7: Backend Agent Tool Split

**Files:**

- Create: `src/codeask/agent/tool_models.py`
- Create: `src/codeask/agent/tool_schemas.py`
- Create: `src/codeask/agent/tool_delegates.py`
- Modify: `src/codeask/agent/tools.py`
- Test: `tests/unit/test_tool_registry.py`

Steps:

- [ ] Move shared tool models and exceptions to `tool_models.py`.
- [ ] Move JSON schemas to `tool_schemas.py`.
- [ ] Move delegated tool registration and result coercion to `tool_delegates.py`.
- [ ] Keep `codeask.agent.tools` as the existing public import path for `ToolRegistry`, `ToolResult`, `ToolContext`, `AskUserSignal`, and `RepoNotReadyError`.
- [ ] Run `uv run pytest tests/unit/test_tool_registry.py tests/unit/test_stage_scope_detection.py tests/integration/test_orchestrator_ask_user.py tests/integration/test_orchestrator_sufficient.py tests/integration/test_orchestrator_insufficient.py -q`.

## Task 8: Final Verification

**Files:**

- All touched files.

Steps:

- [ ] Run `uv run pytest`.
- [ ] Run `corepack pnpm --dir frontend test:run --maxWorkers=1 --minWorkers=1`.
- [ ] Run `corepack pnpm --dir frontend typecheck`.
- [ ] Run `git diff --check`.
- [ ] Check line counts for frontend and backend hotspots with `find frontend/src src/codeask -type f \( -name '*.tsx' -o -name '*.ts' -o -name '*.py' \) -print0 | xargs -0 wc -l | sort -nr | head -35`.

## Success Criteria

- Existing test suites pass.
- `SessionWorkspace.tsx`, `SettingsPage.tsx`, `FeatureWorkbench.tsx`, `frontend/src/lib/api.ts`, `src/codeask/api/sessions.py`, `src/codeask/api/wiki.py`, `src/codeask/api/llm_configs.py`, and `src/codeask/agent/tools.py` are materially smaller and easier to inspect.
- New files have single-purpose responsibilities and no new behavior.
- Public API, UI text, storage layout, and runtime semantics remain unchanged.
