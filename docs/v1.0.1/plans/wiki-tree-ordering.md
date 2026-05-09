# Wiki Tree Ordering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reorder and move support to the native Wiki tree without changing unrelated Wiki behavior.

**Architecture:** Keep read/tree bootstrap logic in the existing tree service, add a dedicated backend ordering path for move/reindex, and split frontend drag/order state into focused hooks and tree helpers. Use one mutation path for both menu reorder and drag-and-drop.

**Tech Stack:** FastAPI, SQLAlchemy, React, TanStack Query, Vitest, pytest

---

### Task 1: Backend ordering contract

**Files:**
- Create: `src/codeask/wiki/tree/ordering.py`
- Modify: `src/codeask/api/wiki/schemas.py`
- Modify: `src/codeask/api/wiki/nodes.py`
- Modify: `src/codeask/wiki/tree/service.py`
- Test: `tests/integration/test_wiki_nodes_api.py`

- [ ] Add failing backend tests for same-parent reorder and folder move.
- [ ] Run only the new backend tests and confirm failure.
- [ ] Add `WikiNodeMove` schema and `POST /api/wiki/nodes/{node_id}/move`.
- [ ] Implement sibling reorder normalization in `tree/ordering.py`.
- [ ] Reuse existing subtree path refresh when parent changes.
- [ ] Re-run targeted backend tests until green.

### Task 2: Backend edge rules

**Files:**
- Modify: `src/codeask/wiki/tree/ordering.py`
- Modify: `src/codeask/wiki/tree/service.py`
- Test: `tests/integration/test_wiki_nodes_api.py`

- [ ] Add failing tests for invalid drop cases: self, descendant, system node, cross-space.
- [ ] Run the tests and confirm the expected failures.
- [ ] Implement validation guards and consistent conflict responses.
- [ ] Re-run backend node API tests until green.

### Task 3: Frontend tree ordering helpers

**Files:**
- Create: `frontend/src/lib/wiki/tree-ordering.ts`
- Create: `frontend/src/components/wiki/hooks/useWikiNodeOrdering.ts`
- Modify: `frontend/src/lib/wiki/api.ts`
- Modify: `frontend/src/types/wiki.ts`
- Test: `frontend/tests/wiki/tree-ordering.test.ts`

- [ ] Add failing pure-function tests for legal drop targets and target index calculation.
- [ ] Run the tree-ordering tests and confirm failure.
- [ ] Add move API client and hook wrapper.
- [ ] Implement pure tree-ordering helpers.
- [ ] Re-run the helper tests until green.

### Task 4: Tree menu reorder UI

**Files:**
- Modify: `frontend/src/components/wiki/WikiNodeMenu.tsx`
- Modify: `frontend/src/components/wiki/WikiTreeNode.tsx`
- Modify: `frontend/src/components/wiki/WikiWorkbench.tsx`
- Test: `frontend/tests/wiki/tree-node-menu.test.tsx`
- Test: `frontend/tests/wiki-node-workflow.test.tsx`

- [ ] Add failing tests for `上移` / `下移` visibility and action wiring.
- [ ] Run the targeted frontend tests and confirm failure.
- [ ] Wire menu actions through `useWikiNodeOrdering`.
- [ ] Refresh tree data and keep selection/expanded state stable after success.
- [ ] Re-run the targeted frontend tests until green.

### Task 5: Drag-and-drop interaction

**Files:**
- Create: `frontend/src/components/wiki/hooks/useWikiTreeDrag.ts`
- Create: `frontend/src/components/wiki/WikiTreeDropIndicator.tsx`
- Modify: `frontend/src/components/wiki/WikiTreePane.tsx`
- Modify: `frontend/src/components/wiki/WikiTreeNode.tsx`
- Modify: `frontend/src/styles/globals.css`
- Test: `frontend/tests/wiki-drag-workflow.test.tsx`

- [ ] Add failing drag workflow tests for reorder and move-into-folder behavior.
- [ ] Run the targeted drag tests and confirm failure.
- [ ] Implement drag state hook, drop indicator, and drop target highlighting.
- [ ] Block invalid targets before mutation dispatch.
- [ ] Re-run drag workflow tests until green.

### Task 6: Refactor and full verification

**Files:**
- Modify: `docs/v1.0.1/prd/llm-wiki.md`
- Modify: `docs/v1.0.1/design/llm-wiki-workbench.md`
- Modify: `docs/v1.0.1/plans/llm-wiki-workbench.md`
- Modify: `docs/v1.0.1/plans/llm-wiki-acceptance-checklist.md`
- Test: `frontend/tests/wiki*.test.ts*`
- Test: `tests/integration/test_wiki_nodes_api.py`

- [ ] Update official Wiki docs to record drag/move/order support and node restrictions.
- [ ] Run targeted backend wiki node tests.
- [ ] Run targeted frontend wiki tree/menu/drag tests.
- [ ] Run `corepack pnpm --dir frontend build`.
- [ ] Summarize any remaining gaps before commit.
