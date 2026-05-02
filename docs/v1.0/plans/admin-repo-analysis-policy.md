# Admin Repo And Analysis Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete global repository management and replace the ambiguous "Skill" wording with analysis policy configuration that is injected into Agent Runtime prompts.

**Architecture:** Repository management remains in the global repo pool (`/api/repos`) with admin-only mutation APIs. Analysis policies reuse the existing `skills` table for the MVP but rename the product concept to "analysis policy" and extend it with `enabled`, `stage`, and `priority` so runtime prompt assembly can inject scoped policies deterministically.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite migrations, React, TanStack Query, Vitest, pytest, uv, pnpm.

---

## Completion Status

Status: completed on 2026-05-03.

Current implementation notes:

- Repository update API and UI are implemented.
- `同步` / `重试同步` semantics replace the misleading `刷新` wording.
- Backend schedules hourly refresh for all non-`cloning` repositories.
- `skills` rows now carry `stage`, `enabled`, and `priority`; Alembic head is `0017`.
- Runtime prompt assembly injects enabled global and feature analysis policies by stage and priority.
- Global settings and feature detail pages both expose analysis policy management.
- Follow-up full Skill Package semantics are outside this plan.

### Task 1: Repository Edit And Sync Semantics

**Files:**
- Modify: `src/codeask/api/schemas/code_index.py`
- Modify: `src/codeask/api/code_index.py`
- Modify: `src/codeask/code_index/cloner.py`
- Test: `tests/integration/test_repos_api.py`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/components/settings/SettingsPage.tsx`
- Test: `frontend/tests/settings-page.test.tsx`

- [x] Add `RepoUpdateIn` and `PATCH /api/repos/{repo_id}`.
- [x] Allow editing repository name and source location.
- [x] If only the name changes, keep clone state unchanged.
- [x] If `url` or `local_path` changes, reset the repo to `registered`, clear sync errors, and enqueue the cache sync job.
- [x] Change refresh behavior into sync/retry semantics: ready repos fetch existing bare cache in place, failed/registered repos retry clone or fetch, and an hourly job refreshes the full repo pool.
- [x] Rename the frontend action away from misleading "刷新".
- [x] Add frontend row editing with visible success/error messages.

### Task 2: Analysis Policy Data Model And APIs

**Files:**
- Modify: `src/codeask/db/models/skill.py`
- Modify: `src/codeask/migrations.py`
- Modify: `src/codeask/api/schemas/skill.py`
- Modify: `src/codeask/api/skills.py`
- Test: `tests/integration/test_skills_api.py`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/lib/api.ts`

- [x] Extend skill rows with `enabled`, `stage`, and `priority`.
- [x] Keep API path `/api/skills` for compatibility, but expose fields as analysis policy data.
- [x] Require admin for global policy mutations.
- [x] Support list/create/update/delete with scope, stage, enabled, and priority.
- [x] Keep feature policies attached to a specific feature.

### Task 3: Runtime Policy Injection

**Files:**
- Modify: `src/codeask/agent/prompts.py`
- Modify: `src/codeask/agent/orchestrator.py`
- Test: `tests/unit/test_prompts.py` or existing prompt tests

- [x] Query enabled global policies and feature policies while building prompt context.
- [x] Inject policies into a structured `L2_ANALYSIS_POLICIES` section.
- [x] Filter policies by current stage at prompt assembly time: `all` applies to every stage; exact stage applies only there.
- [x] Sort policies by priority and creation order where available.

### Task 4: Frontend Analysis Policy UI

**Files:**
- Modify: `frontend/src/components/settings/SettingsPage.tsx`
- Modify: `frontend/src/components/features/FeatureWorkbench.tsx`
- Modify: `frontend/src/styles/globals.css`
- Test: `frontend/tests/settings-page.test.tsx`
- Test: `frontend/tests/feature-workbench.test.tsx`

- [x] Add "全局分析策略" to global settings.
- [x] Rename the feature-level prompt configuration surface to "特性分析策略".
- [x] Use switch controls for enabled state.
- [x] Provide create/edit/delete actions.
- [x] Use stage selector and priority input.
- [x] Keep UI compact and consistent with current settings cards.

### Task 5: Documentation And Verification

**Files:**
- Modify: `docs/v1.0/design/agent-runtime.md`
- Modify: `docs/v1.0/design/frontend-workbench.md`
- Modify: `docs/v1.0/design/api-data-model.md`

- [x] Document repository edit/sync semantics.
- [x] Document analysis policy vs future skill package distinction.
- [x] Document runtime injection order.
- [x] Run backend unit/integration checks.
- [x] Run frontend typecheck and test suite.
