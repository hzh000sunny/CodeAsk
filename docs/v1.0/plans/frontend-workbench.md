# Frontend Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 起 `frontend/` 子项目并落地 CodeAsk 研发工作台所有页面 + 组件 + Vite proxy + 关键 e2e；前端 dev server 与 backend 联调，构建产物 `frontend/dist/` 留给 07 deployment 计划挂载。

**Architecture:** 独立 pnpm 子项目（与 backend 工具链隔离），React 19 SPA，TanStack Router 文件式路由，TanStack Query 管所有服务端状态，Zustand 仅承载跨页 UI 状态，shadcn/ui 复制式组件库以 Tailwind v4 渲染。SSE 通过 `microsoft/fetch-event-source` 接入 Agent 9 阶段事件流；自报身份通过 localStorage 生成 `client_id` + 可选 `nickname`，注入到所有请求的 `X-Subject-Id` header。

**Tech Stack:** React 19, TypeScript strict, Vite, pnpm, Tailwind CSS v4, shadcn/ui, lucide-react, TanStack Query v5, TanStack Router, Zustand, react-hook-form + zod, microsoft/fetch-event-source, react-markdown + remark-gfm, shiki, Recharts, Vitest + Testing Library, Playwright

**Source SDD docs**（路径相对本文件 `docs/v1.0/plans/frontend-workbench.md`）：
- `../design/overview.md`
- `../design/frontend-workbench.md`
- `../design/dependencies.md`
- `../design/wiki-search.md`
- `../design/evidence-report.md`
- `../design/agent-runtime.md`
- `../design/api-data-model.md`

**Depends on:** `docs/v1.0/plans/foundation.md`（subject_id 中间件契约 + `/api/healthz`）、`docs/v1.0/plans/wiki-knowledge.md`（`/api/features` / `/api/documents` / `/api/reports`）、`docs/v1.0/plans/code-index.md`（`/api/repos`）、`docs/v1.0/plans/agent-runtime.md`（`/api/sessions` + SSE 事件 + `/api/me/llm-configs` / `/api/admin/llm-configs`）

**Project root:** `/home/hzh/workspace/CodeAsk/`。本计划全部文件路径相对此根目录；前端文件均在 `frontend/` 下。

---

## 2026-05-01 Phase B 修订

以下修订优先级高于本计划较早 task 中的旧文案和代码片段：

- 全局壳层固定为 TopBar + Source List sidebar；左侧一级入口只有 `会话 / 特性 / 设置`。
- 会话列表只显示当前 subject 的会话，不提供"我的 / 全部"切换；列表顶部是搜索框 + 新建按钮，行操作放入三点菜单。
- 上传日志在无会话时自动创建默认会话；会话数据按 `sessions/<session_id>/` 隔离，右侧"会话数据"区域列出当前会话附件并支持重命名 / 编辑用途说明 / 删除。
- 会话附件以 `attachment_id` 作为稳定键；`display_name` 可变，`original_filename` 不变，`aliases` 保留历次名称，`description` 承载用户口语化用途说明。Agent prompt 必须注入这些映射，manifest 作为 DB 元数据快照同步更新。
- 普通用户无需登录即可使用；内置管理员登录只用于保护全局 LLM 配置、全局仓库写操作和后续系统级设置。
- LLM 配置 API 拆为个人 `/api/me/llm-configs` 与管理员 `/api/admin/llm-configs`；旧 `/api/llm-configs` 不再用于新 UI。
- 管理员设置页只显示全局配置，不显示个人用户配置。
- 仓库注册仍使用 `/api/repos`：读操作开放给特性关联仓库，创建 / 删除 / 刷新需要管理员。
- 特性页不手工创建问题报告，只展示会话生成的报告；仓库关联使用全局仓库池 checkbox。

详细契约见 `../specs/frontend-workbench-source-list-ia.md` 与 `../specs/frontend-workbench-admin-rbac.md`。

---

## 2026-05-02 Handoff 修订

以下 handoff 边界优先级高于本计划早期 task 和末尾旧验收清单：

- 当前实现是 Vite React SPA + TanStack Query；未采用 TanStack Router 文件路由、Zustand、shadcn 全量组件复制或 microsoft/fetch-event-source。
- 全局页面只有 `会话 / 特性 / 设置` 三个一级入口；没有独立 Wiki 页、Repos 页、Skills 页或 Dashboard 页。
- 特性页承载基础知识库上传入口、报告列表、仓库 checkbox 关联、特性 Skill；完整 LLM Wiki 目录上传 / 资源保存 / 预览 / 编辑 / re-index 后置为独立专项。
- Feedback 按钮持久化、frontend events、audit log 和 Maintainer Dashboard 数据面后置到 `metrics-eval`。
- 当前 frontend-workbench 验收以 `../specs/frontend-workbench-handoff.md` 为准。

---

## API 字段命名约定

后端 Pydantic schema 默认输出 **snake_case**（`subject_id` / `feature_id` / `created_at` / `verified_by`）。前端 TypeScript interface **直接保留 snake_case**，不做 camelCase 转换——避免维护一份双向映射的 noise，与 SSE event payload（同样 snake_case）保持一致。React 组件 props 用 camelCase 是常规 TS 风格，但**只有 props 是 camelCase；任何来自 API 的 model 字段都是 snake_case**。

## 强制约定（继承 foundation.md 的 TDD + 提交节奏）

- 每个 task 一个 commit
- 步骤里贴的代码必须**完整可拷贝**（含 TSX、Tailwind className、配置文件全文）；禁止 "implement similar to X" / "TODO" / "appropriate handling"
- 单文件组件 ≤ 200 行，超过就拆 sub-component
- 任何对 API 的 fetch 都通过 `frontend/src/lib/api.ts` 走，自动注入 `X-Subject-Id`
- 任何 SSE 都通过 `frontend/src/lib/sse.ts`，不直接用原生 EventSource
- TypeScript 严格模式；`tsc --noEmit` 与 `eslint` 必须零错误才能 commit
- shadcn/ui 组件**复制式**进 `frontend/src/components/ui/`（不作为 npm 包依赖）
- **frontend 不直连 LLM**——所有 LLM 调用走 backend 的个人 / 管理员 LLM 配置 API + Agent 路径
- 字体（JetBrains Mono / Fira Code）自托管在 `frontend/public/fonts/`，不引 Google Fonts CDN（依赖 `dependencies.md` §3.2）

## 不在本计划范围（明确推迟）

| 项 | 推迟到 | 原因 |
|---|---|---|
| Docker 多阶段镜像 / `frontend/dist/` 挂载到 backend `StaticFiles` | 07 deployment | 一期前端独立 dev server 已能联调 |
| pre-commit / GitHub Actions（前端 lint + test） | 07 deployment | 本计划只跑本地校验 |
| `/api/feedback` 后端实现与前端持久化接入 | 06 metrics-eval | 当前 handoff 不要求调用；待 metrics-eval 定义反馈 API 后接入 |
| feedback 按钮持久化 / frontend events / Dashboard 数据面 | 06 metrics-eval | 依赖 feedback、frontend_events、audit_log raw events |
| 完整 LLM Wiki 目录管理、资源引用、预览、编辑、re-index | 独立 LLM Wiki 专项 | 范围跨存储、索引、UI 与 Agent 检索上下文，不纳入当前收口 |
| TipTap in-app 文档编辑 | MVP+ | PRD 没要求 |
| 企业鉴权 / `AuthProvider` 替换 `<UserMenu />` slot | MVP+ | 一期仅内置管理员保护全局配置，普通用户仍匿名使用 |
| 强制昵称唯一 / 找人帮忙按钮 | 永久不做 | `frontend-workbench.md` §6.3 / §8.4 |

---

## File Structure

本计划交付以下文件（全部相对项目根 `/home/hzh/workspace/CodeAsk/`）：

```text
CodeAsk/
└── frontend/
    ├── package.json
    ├── pnpm-lock.yaml
    ├── pnpm-workspace.yaml             # 占位（未来拆 workspace 用，一期单包）
    ├── .gitignore
    ├── .npmrc
    ├── .nvmrc                          # node 22
    ├── index.html
    ├── vite.config.ts                  # Vite + plugin-react + TanStack Router plugin + proxy
    ├── tsconfig.json
    ├── tsconfig.node.json
    ├── tailwind.config.ts
    ├── postcss.config.js
    ├── components.json                 # shadcn/ui CLI 配置
    ├── eslint.config.js
    ├── .prettierrc.json
    ├── playwright.config.ts
    ├── vitest.config.ts
    ├── public/
    │   └── fonts/
    │       ├── JetBrainsMono-Regular.woff2
    │       └── JetBrainsMono-Bold.woff2
    ├── src/
    │   ├── main.tsx
    │   ├── App.tsx                     # RouterProvider + QueryClientProvider + ThemeProvider
    │   ├── styles/
    │   │   └── globals.css             # Tailwind 入口 + 字体 face + 主题 token
    │   ├── lib/
    │   │   ├── api.ts                  # fetch wrapper + X-Subject-Id 注入 + ApiError
    │   │   ├── sse.ts                  # microsoft/fetch-event-source POST+header 客户端
    │   │   ├── identity.ts             # localStorage client_id + nickname → subject_id
    │   │   ├── query-client.ts         # QueryClient 全局实例
    │   │   ├── format.ts               # 时间 / confidence 标签 / verdict 颜色
    │   │   ├── markdown.ts             # react-markdown + remark-gfm + shiki 配置
    │   │   └── utils.ts                # cn() 等 shadcn 默认 helper
    │   ├── stores/
    │   │   ├── identity-store.ts       # zustand 包 identity 让组件订阅
    │   │   └── session-stream-store.ts # 当前打开会话的 SSE 缓冲
    │   ├── hooks/
    │   │   ├── use-features.ts
    │   │   ├── use-documents.ts
    │   │   ├── use-reports.ts
    │   │   ├── use-repos.ts
    │   │   ├── use-skills.ts
    │   │   ├── use-llm-configs.ts
    │   │   ├── use-sessions.ts
    │   │   ├── use-session-stream.ts   # 包 SSE client
    │   │   ├── use-feedback.ts
    │   │   └── use-dashboard.ts
    │   ├── routes/                     # TanStack Router file-based
    │   │   ├── __root.tsx
    │   │   ├── index.tsx               # 重定向 /sessions
    │   │   ├── sessions.tsx            # /sessions layout
    │   │   ├── sessions.$id.tsx        # /sessions/:id
    │   │   ├── dashboard.tsx
    │   │   ├── wiki.tsx
    │   │   ├── wiki.documents.$id.tsx
    │   │   ├── wiki.reports.$id.tsx
    │   │   ├── repos.tsx
    │   │   ├── skills.tsx
    │   │   ├── settings.llm.tsx
    │   │   └── features.$id.tsx
    │   ├── components/
    │   │   ├── ui/                     # shadcn copies
    │   │   │   ├── button.tsx
    │   │   │   ├── card.tsx
    │   │   │   ├── dialog.tsx
    │   │   │   ├── input.tsx
    │   │   │   ├── textarea.tsx
    │   │   │   ├── select.tsx
    │   │   │   ├── tabs.tsx
    │   │   │   ├── badge.tsx
    │   │   │   ├── separator.tsx
    │   │   │   ├── scroll-area.tsx
    │   │   │   ├── tooltip.tsx
    │   │   │   ├── dropdown-menu.tsx
    │   │   │   ├── command.tsx
    │   │   │   ├── sheet.tsx
    │   │   │   ├── avatar.tsx
    │   │   │   ├── alert.tsx
    │   │   │   ├── checkbox.tsx
    │   │   │   ├── collapsible.tsx
    │   │   │   ├── radio-group.tsx
    │   │   │   ├── popover.tsx
    │   │   │   └── sonner.tsx
    │   │   ├── layout/
    │   │   │   ├── AppShell.tsx
    │   │   │   ├── Sidebar.tsx
    │   │   │   └── TopBar.tsx
    │   │   ├── identity/
    │   │   │   ├── UserMenu.tsx
    │   │   │   ├── NicknameDialog.tsx
    │   │   │   └── SelfReportBadge.tsx
    │   │   ├── session/
    │   │   │   ├── SessionList.tsx
    │   │   │   ├── SessionInputArea.tsx
    │   │   │   ├── SessionMessageList.tsx
    │   │   │   ├── InvestigationPanel.tsx
    │   │   │   ├── ScopeDetectionTransparency.tsx
    │   │   │   ├── SufficiencyJudgementTransparency.tsx
    │   │   │   ├── ToolCallStream.tsx
    │   │   │   ├── AnswerCard.tsx
    │   │   │   ├── EvidenceList.tsx
    │   │   │   ├── EvidenceItem.tsx
    │   │   │   ├── FeedbackButtons.tsx
    │   │   │   └── DeepenButton.tsx       # "再深查一下" 兜底按钮
    │   │   ├── dashboard/
    │   │   │   ├── MaintainerDashboard.tsx
    │   │   │   ├── PendingItemsList.tsx
    │   │   │   ├── FlywheelMetrics.tsx
    │   │   │   └── WatchedFeaturesPanel.tsx
    │   │   ├── wiki/
    │   │   │   ├── DocumentList.tsx
    │   │   │   ├── DocumentUpload.tsx
    │   │   │   ├── DocumentSearch.tsx
    │   │   │   ├── ReportList.tsx
    │   │   │   ├── ReportDetail.tsx
    │   │   │   └── ReportVerifyButton.tsx
    │   │   ├── repos/
    │   │   │   ├── RepoList.tsx
    │   │   │   ├── RepoRegisterDialog.tsx
    │   │   │   └── RepoStatusBadge.tsx
    │   │   ├── skills/
    │   │   │   ├── SkillList.tsx
    │   │   │   └── SkillEditor.tsx
    │   │   ├── settings/
    │   │   │   ├── LlmConfigList.tsx
    │   │   │   └── LlmConfigDialog.tsx
    │   │   └── features/
    │   │       ├── FeatureList.tsx
    │   │       ├── FeatureDetail.tsx
    │   │       └── FeatureRepoLinker.tsx
    │   └── types/
    │       ├── api.ts                  # snake_case API model interfaces
    │       └── sse.ts                  # SSE event union types
    ├── tests/                          # Vitest unit / component
    │   ├── setup.ts
    │   ├── identity.test.ts
    │   ├── api.test.ts
    │   ├── sse.test.ts
    │   ├── AnswerCard.test.tsx
    │   ├── FeedbackButtons.test.tsx
    │   ├── ScopeDetectionTransparency.test.tsx
    │   └── UserMenu.test.tsx
    └── e2e/
        ├── happy-path.spec.ts
        └── playwright-helpers.ts
```

---

## Task 1: pnpm 项目骨架（package.json + tsconfig + .gitignore + .npmrc）

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/.npmrc`
- Create: `frontend/.nvmrc`
- Create: `frontend/.gitignore`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/pnpm-workspace.yaml`

`frontend/` 是独立 pnpm 项目；与根目录 backend 工具链不共享。pnpm-workspace.yaml 占位为未来若拆 packages（如把 ui 抽包）做准备，一期是 single package。

- [ ] **Step 1: 创建 `frontend/.nvmrc`**

```text
22
```

- [ ] **Step 2: 创建 `frontend/.npmrc`**

```text
engine-strict=true
auto-install-peers=true
strict-peer-dependencies=false
```

- [ ] **Step 3: 创建 `frontend/.gitignore`**

```text
node_modules/
dist/
dist-ssr/
.vite/
.tsbuildinfo
*.log
.DS_Store
.env
.env.local
.env.*.local
coverage/
playwright-report/
test-results/
.eslintcache
```

- [ ] **Step 4: 创建 `frontend/pnpm-workspace.yaml`**

```yaml
packages:
  - "."
```

- [ ] **Step 5: 创建 `frontend/package.json`**

```json
{
  "name": "codeask-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "engines": {
    "node": ">=22",
    "pnpm": ">=9"
  },
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "lint": "eslint .",
    "format": "prettier --write .",
    "format:check": "prettier --check .",
    "typecheck": "tsc -b --noEmit",
    "test": "vitest run",
    "test:watch": "vitest",
    "e2e": "playwright test",
    "e2e:install": "playwright install --with-deps chromium"
  },
  "dependencies": {
    "@microsoft/fetch-event-source": "^2.0.1",
    "@radix-ui/react-avatar": "^1.1.2",
    "@radix-ui/react-checkbox": "^1.1.3",
    "@radix-ui/react-collapsible": "^1.1.2",
    "@radix-ui/react-dialog": "^1.1.4",
    "@radix-ui/react-dropdown-menu": "^2.1.4",
    "@radix-ui/react-popover": "^1.1.4",
    "@radix-ui/react-radio-group": "^1.2.2",
    "@radix-ui/react-scroll-area": "^1.2.2",
    "@radix-ui/react-select": "^2.1.4",
    "@radix-ui/react-separator": "^1.1.1",
    "@radix-ui/react-slot": "^1.1.1",
    "@radix-ui/react-tabs": "^1.1.2",
    "@radix-ui/react-tooltip": "^1.1.6",
    "@tanstack/react-query": "^5.62.0",
    "@tanstack/react-router": "^1.92.0",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "cmdk": "^1.0.4",
    "lucide-react": "^0.468.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-hook-form": "^7.54.0",
    "react-markdown": "^9.0.1",
    "recharts": "^2.15.0",
    "remark-gfm": "^4.0.0",
    "shiki": "^1.24.0",
    "sonner": "^1.7.1",
    "tailwind-merge": "^2.5.5",
    "tailwindcss-animate": "^1.0.7",
    "uuid": "^11.0.3",
    "zod": "^3.24.1",
    "zustand": "^5.0.2"
  },
  "devDependencies": {
    "@playwright/test": "^1.49.0",
    "@tailwindcss/postcss": "^4.0.0-beta.6",
    "@tanstack/router-plugin": "^1.92.0",
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.1.0",
    "@testing-library/user-event": "^14.5.2",
    "@types/node": "^22.10.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@types/uuid": "^10.0.0",
    "@vitejs/plugin-react": "^4.3.4",
    "autoprefixer": "^10.4.20",
    "eslint": "^9.16.0",
    "eslint-plugin-react-hooks": "^5.1.0",
    "eslint-plugin-react-refresh": "^0.4.16",
    "globals": "^15.13.0",
    "jsdom": "^25.0.1",
    "postcss": "^8.4.49",
    "prettier": "^3.4.2",
    "tailwindcss": "^4.0.0-beta.6",
    "typescript": "^5.7.2",
    "typescript-eslint": "^8.18.0",
    "vite": "^6.0.3",
    "vitest": "^2.1.8"
  }
}
```

- [ ] **Step 6: 创建 `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2023", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "verbatimModuleSyntax": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    },
    "types": ["vite/client", "vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "tests"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 7: 创建 `frontend/tsconfig.node.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "noEmit": true
  },
  "include": ["vite.config.ts", "vitest.config.ts", "playwright.config.ts", "eslint.config.js"]
}
```

- [ ] **Step 8: 创建 `frontend/index.html`**

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>CodeAsk</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 9: 创建 `frontend/src/main.tsx`（最小占位，下一步迭代）**

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

const rootEl = document.getElementById("root");
if (!rootEl) {
  throw new Error("#root container missing in index.html");
}
createRoot(rootEl).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

- [ ] **Step 10: 创建 `frontend/src/App.tsx`（占位，Task 6 之后接 Router）**

```tsx
export default function App(): JSX.Element {
  return (
    <main style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <h1>CodeAsk frontend bootstrap</h1>
      <p>If you can read this, vite + react are wired up.</p>
    </main>
  );
}
```

- [ ] **Step 11: 安装 + smoke check**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm install
```
Expected: 依赖装好，生成 `pnpm-lock.yaml`。这一步不跑 vite（vite.config.ts 还没建）。

- [ ] **Step 12: 提交**

```bash
cd /home/hzh/workspace/CodeAsk
git add frontend/.gitignore frontend/.npmrc frontend/.nvmrc frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml frontend/tsconfig.json frontend/tsconfig.node.json frontend/index.html frontend/src/main.tsx frontend/src/App.tsx
git commit -m "chore(frontend): pnpm + tsconfig + vite skeleton (no build yet)"
```

---

## Task 2: Vite + Tailwind v4 + PostCSS + 字体自托管

**Files:**
- Create: `frontend/vite.config.ts`
- Create: `frontend/postcss.config.js`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/src/styles/globals.css`
- Create: `frontend/public/fonts/JetBrainsMono-Regular.woff2` (placeholder fetch)
- Create: `frontend/public/fonts/JetBrainsMono-Bold.woff2` (placeholder fetch)
- Modify: `frontend/src/main.tsx`（import globals.css）

Vite proxy 把 `/api/*` 反代到 `http://127.0.0.1:8000`（backend 监听端口，foundation.md Task 12 的承诺），让前端 dev server 与 backend 联调时不需要 CORS 调整。Tailwind v4 用新的 `@import "tailwindcss"` 风格（不再写 `@tailwind base; @tailwind components;`）。

- [ ] **Step 1: 创建 `frontend/vite.config.ts`**

```ts
import path from "node:path";
import { fileURLToPath } from "node:url";

import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [
    TanStackRouterVite({
      routesDirectory: "./src/routes",
      generatedRouteTree: "./src/routeTree.gen.ts",
      autoCodeSplitting: true,
    }),
    react(),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    target: "es2022",
  },
});
```

- [ ] **Step 2: 创建 `frontend/postcss.config.js`**

```js
export default {
  plugins: {
    "@tailwindcss/postcss": {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 3: 创建 `frontend/tailwind.config.ts`**

```ts
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "Fira Code", "ui-monospace", "monospace"],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        confidence: {
          high: "hsl(142 71% 45%)",
          medium: "hsl(38 92% 50%)",
          low: "hsl(0 84% 60%)",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [],
};

export default config;
```

- [ ] **Step 4: 创建 `frontend/src/styles/globals.css`**

```css
@import "tailwindcss";

@font-face {
  font-family: "JetBrains Mono";
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url("/fonts/JetBrainsMono-Regular.woff2") format("woff2");
}

@font-face {
  font-family: "JetBrains Mono";
  font-style: normal;
  font-weight: 700;
  font-display: swap;
  src: url("/fonts/JetBrainsMono-Bold.woff2") format("woff2");
}

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
    --card: 0 0% 100%;
    --card-foreground: 222.2 84% 4.9%;
    --primary: 222.2 47.4% 11.2%;
    --primary-foreground: 210 40% 98%;
    --secondary: 210 40% 96.1%;
    --secondary-foreground: 222.2 47.4% 11.2%;
    --muted: 210 40% 96.1%;
    --muted-foreground: 215.4 16.3% 46.9%;
    --accent: 210 40% 96.1%;
    --accent-foreground: 222.2 47.4% 11.2%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 210 40% 98%;
    --border: 214.3 31.8% 91.4%;
    --input: 214.3 31.8% 91.4%;
    --ring: 222.2 84% 4.9%;
    --radius: 0.5rem;
  }

  .dark {
    --background: 222.2 84% 4.9%;
    --foreground: 210 40% 98%;
    --card: 222.2 84% 4.9%;
    --card-foreground: 210 40% 98%;
    --primary: 210 40% 98%;
    --primary-foreground: 222.2 47.4% 11.2%;
    --secondary: 217.2 32.6% 17.5%;
    --secondary-foreground: 210 40% 98%;
    --muted: 217.2 32.6% 17.5%;
    --muted-foreground: 215 20.2% 65.1%;
    --accent: 217.2 32.6% 17.5%;
    --accent-foreground: 210 40% 98%;
    --destructive: 0 62.8% 30.6%;
    --destructive-foreground: 210 40% 98%;
    --border: 217.2 32.6% 17.5%;
    --input: 217.2 32.6% 17.5%;
    --ring: 212.7 26.8% 83.9%;
  }

  * {
    border-color: hsl(var(--border));
  }

  html,
  body,
  #root {
    height: 100%;
  }

  body {
    background-color: hsl(var(--background));
    color: hsl(var(--foreground));
    font-feature-settings:
      "rlig" 1,
      "calt" 1;
  }
}
```

- [ ] **Step 5: 把 `globals.css` 接进 `frontend/src/main.tsx`**

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./styles/globals.css";

const rootEl = document.getElementById("root");
if (!rootEl) {
  throw new Error("#root container missing in index.html");
}
createRoot(rootEl).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

- [ ] **Step 6: 字体文件占位**

`frontend/public/fonts/` 下放置 JetBrains Mono `Regular` 和 `Bold` 的 woff2。一期可以从 [JetBrains Mono GitHub release](https://github.com/JetBrains/JetBrainsMono/releases) 下载 ttf 后用 `woff2_compress` 转换；如果手头没有，**先放 0 字节占位文件**（CI 不会因此 fail，浏览器 fallback 系统字体），并在 README.md 写"实施时替换为真 woff2"。本步不拉外网。

```bash
cd /home/hzh/workspace/CodeAsk/frontend
mkdir -p public/fonts
# 占位（实施者后续应替换）
touch public/fonts/JetBrainsMono-Regular.woff2 public/fonts/JetBrainsMono-Bold.woff2
```

- [ ] **Step 7: 验证 dev server 起得来**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm dev &
DEV_PID=$!
sleep 4
curl -fs http://127.0.0.1:5173/ | head -c 200
kill $DEV_PID
```
Expected: 看到 `<!doctype html>` 开头的输出。

- [ ] **Step 8: 提交**

```bash
cd /home/hzh/workspace/CodeAsk
git add frontend/vite.config.ts frontend/postcss.config.js frontend/tailwind.config.ts frontend/src/styles/globals.css frontend/src/main.tsx frontend/public/fonts/
git commit -m "feat(frontend): vite + tailwind v4 + self-hosted font skeleton"
```

---

## Task 3: ESLint + Prettier + Vitest + Playwright 配置

**Files:**
- Create: `frontend/eslint.config.js`
- Create: `frontend/.prettierrc.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/tests/setup.ts`
- Create: `frontend/playwright.config.ts`

校验三件套配置就位，后续 task 写测试时 `pnpm test` / `pnpm e2e` 直接能跑。Playwright 一期只跑 chromium。

- [ ] **Step 1: 创建 `frontend/eslint.config.js`**

```js
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "src/routeTree.gen.ts", "playwright-report", "test-results"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommendedTypeChecked],
    files: ["src/**/*.{ts,tsx}", "tests/**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: {
        project: ["./tsconfig.json", "./tsconfig.node.json"],
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      "@typescript-eslint/consistent-type-imports": "error",
    },
  },
  {
    files: ["e2e/**/*.{ts,tsx}", "*.config.{ts,js}"],
    languageOptions: { globals: globals.node },
    rules: {
      "@typescript-eslint/no-unsafe-assignment": "off",
    },
  },
);
```

- [ ] **Step 2: 创建 `frontend/.prettierrc.json`**

```json
{
  "semi": true,
  "singleQuote": false,
  "trailingComma": "all",
  "printWidth": 100,
  "tabWidth": 2,
  "arrowParens": "always",
  "endOfLine": "lf"
}
```

- [ ] **Step 3: 创建 `frontend/vitest.config.ts`**

```ts
import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./tests/setup.ts",
    include: ["tests/**/*.test.{ts,tsx}"],
    css: false,
  },
});
```

- [ ] **Step 4: 创建 `frontend/tests/setup.ts`**

```ts
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});
```

- [ ] **Step 5: 创建 `frontend/playwright.config.ts`**

```ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",
  timeout: 60_000,
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "pnpm dev",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
```

- [ ] **Step 6: 跑 lint + typecheck（应当通过）**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm typecheck
pnpm lint
```
Expected: 零错误（当前还没真正的代码）。

- [ ] **Step 7: 提交**

```bash
cd /home/hzh/workspace/CodeAsk
git add frontend/eslint.config.js frontend/.prettierrc.json frontend/vitest.config.ts frontend/tests/setup.ts frontend/playwright.config.ts
git commit -m "chore(frontend): eslint + prettier + vitest + playwright config"
```

---

## Task 4: 自报身份 — identity 工具 + Zustand store + 单测

**Files:**
- Create: `frontend/src/lib/identity.ts`
- Create: `frontend/src/stores/identity-store.ts`
- Create: `frontend/tests/identity.test.ts`

落地 `frontend-workbench.md` §8："首次访问生成 UUID `client_id` 写 localStorage，可选 `nickname`，subject_id = `nickname@client_id` 或 `device@<short>`"。subject_id 限制在 `^[A-Za-z0-9._\-@]{1,128}$`（与 foundation.md `_SUBJECT_PATTERN` 完全一致），昵称里出现非法字符时 sanitize（替换为 `_`）。

- [ ] **Step 1: 写测试 `frontend/tests/identity.test.ts`**

```ts
import { beforeEach, describe, expect, it } from "vitest";

import {
  buildSubjectId,
  clearIdentity,
  getOrCreateClientId,
  getNickname,
  getSubjectId,
  sanitizeNickname,
  setNickname,
} from "@/lib/identity";

describe("identity", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("generates a uuid client_id on first access and persists it", () => {
    const first = getOrCreateClientId();
    const second = getOrCreateClientId();
    expect(first).toMatch(/^[0-9a-f-]{36}$/i);
    expect(second).toBe(first);
  });

  it("returns null nickname when not set", () => {
    expect(getNickname()).toBeNull();
  });

  it("sanitizes invalid nickname characters", () => {
    expect(sanitizeNickname("alice space!")).toBe("alice_space_");
    expect(sanitizeNickname("张三")).toBe("___");
    expect(sanitizeNickname("ok-name.1")).toBe("ok-name.1");
  });

  it("buildSubjectId uses nickname@client_id when nickname present", () => {
    expect(buildSubjectId("alice", "abcdef12-3456-7890-abcd-ef1234567890")).toBe(
      "alice@abcdef12-3456-7890-abcd-ef1234567890",
    );
  });

  it("buildSubjectId falls back to device@<short> when nickname is null", () => {
    const sid = buildSubjectId(null, "abcdef12-3456-7890-abcd-ef1234567890");
    expect(sid).toBe("device@abcdef12");
  });

  it("getSubjectId reflects setNickname immediately", () => {
    expect(getSubjectId()).toMatch(/^device@[0-9a-f]{8}$/);
    setNickname("bob");
    expect(getSubjectId()).toMatch(/^bob@[0-9a-f-]{36}$/);
  });

  it("clearIdentity wipes both client_id and nickname", () => {
    setNickname("carol");
    const idBefore = getOrCreateClientId();
    clearIdentity();
    const idAfter = getOrCreateClientId();
    expect(idAfter).not.toBe(idBefore);
    expect(getNickname()).toBeNull();
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm test tests/identity.test.ts
```
Expected: 找不到 `@/lib/identity`。

- [ ] **Step 3: 实现 `frontend/src/lib/identity.ts`**

```ts
import { v4 as uuidv4 } from "uuid";

const CLIENT_ID_KEY = "codeask:client_id";
const NICKNAME_KEY = "codeask:nickname";
const NICKNAME_INVALID = /[^A-Za-z0-9._\-]/g;
const NICKNAME_MAX = 32;

export function getOrCreateClientId(): string {
  const existing = window.localStorage.getItem(CLIENT_ID_KEY);
  if (existing && existing.length > 0) {
    return existing;
  }
  const fresh = uuidv4();
  window.localStorage.setItem(CLIENT_ID_KEY, fresh);
  return fresh;
}

export function getNickname(): string | null {
  const raw = window.localStorage.getItem(NICKNAME_KEY);
  return raw && raw.length > 0 ? raw : null;
}

export function sanitizeNickname(raw: string): string {
  return raw.replace(NICKNAME_INVALID, "_").slice(0, NICKNAME_MAX);
}

export function setNickname(raw: string): void {
  const cleaned = sanitizeNickname(raw);
  if (cleaned.length === 0) {
    window.localStorage.removeItem(NICKNAME_KEY);
    return;
  }
  window.localStorage.setItem(NICKNAME_KEY, cleaned);
}

export function clearIdentity(): void {
  window.localStorage.removeItem(CLIENT_ID_KEY);
  window.localStorage.removeItem(NICKNAME_KEY);
}

export function buildSubjectId(nickname: string | null, clientId: string): string {
  if (nickname && nickname.length > 0) {
    return `${nickname}@${clientId}`;
  }
  const short = clientId.replace(/-/g, "").slice(0, 8);
  return `device@${short}`;
}

export function getSubjectId(): string {
  return buildSubjectId(getNickname(), getOrCreateClientId());
}
```

- [ ] **Step 4: 实现 `frontend/src/stores/identity-store.ts`（Zustand 包一层供组件订阅 nickname 变化）**

```ts
import { create } from "zustand";

import {
  buildSubjectId,
  clearIdentity as wipe,
  getNickname,
  getOrCreateClientId,
  sanitizeNickname,
  setNickname as persist,
} from "@/lib/identity";

interface IdentityState {
  clientId: string;
  nickname: string | null;
  subjectId: string;
  setNickname: (raw: string) => void;
  clearIdentity: () => void;
}

export const useIdentityStore = create<IdentityState>((set, get) => {
  const clientId = getOrCreateClientId();
  const nickname = getNickname();
  return {
    clientId,
    nickname,
    subjectId: buildSubjectId(nickname, clientId),
    setNickname: (raw: string) => {
      const cleaned = sanitizeNickname(raw);
      const next = cleaned.length > 0 ? cleaned : null;
      persist(raw);
      set({ nickname: next, subjectId: buildSubjectId(next, get().clientId) });
    },
    clearIdentity: () => {
      wipe();
      const fresh = getOrCreateClientId();
      set({
        clientId: fresh,
        nickname: null,
        subjectId: buildSubjectId(null, fresh),
      });
    },
  };
});
```

- [ ] **Step 5: 跑测试确认通过**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm test tests/identity.test.ts
```
Expected: 7 个测试全部 PASS。

- [ ] **Step 6: 提交**

```bash
cd /home/hzh/workspace/CodeAsk
git add frontend/src/lib/identity.ts frontend/src/stores/identity-store.ts frontend/tests/identity.test.ts
git commit -m "feat(frontend): identity helper + zustand store + tests"
```

---

## Task 5: API client + ApiError + 自动注入 X-Subject-Id

**Files:**
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/types/api.ts`
- Create: `frontend/tests/api.test.ts`

`api.ts` 是所有 fetch 的唯一入口。每次请求自动从 `getSubjectId()` 拿身份注入 header；非 2xx 抛 `ApiError`（含 status + body）；GET / POST / PUT / DELETE / PATCH 是薄方法。**字段命名保持 snake_case 与后端 Pydantic 对齐**。

- [ ] **Step 1: 写测试 `frontend/tests/api.test.ts`**

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch } from "@/lib/api";
import { setNickname } from "@/lib/identity";

describe("apiFetch", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("injects X-Subject-Id derived from identity", async () => {
    setNickname("alice");
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    await apiFetch("/api/healthz");
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(headers.get("X-Subject-Id")).toMatch(/^alice@/);
  });

  it("parses JSON body on success", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ id: 1, name: "x" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const data = await apiFetch<{ id: number; name: string }>("/api/x");
    expect(data).toEqual({ id: 1, name: "x" });
  });

  it("throws ApiError on non-2xx", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "nope" }), {
        status: 404,
        headers: { "content-type": "application/json" },
      }),
    );
    await expect(apiFetch("/api/missing")).rejects.toBeInstanceOf(ApiError);
  });

  it("serializes JSON body on POST and sets content-type", async () => {
    fetchMock.mockResolvedValue(
      new Response("null", {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    await apiFetch("/api/x", { method: "POST", json: { feature_id: "f1" } });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("content-type")).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ feature_id: "f1" }));
  });

  it("returns null on 204", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    const result = await apiFetch<null>("/api/x", { method: "DELETE" });
    expect(result).toBeNull();
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm test tests/api.test.ts
```
Expected: import 失败。

- [ ] **Step 3: 创建 `frontend/src/types/api.ts`**

```ts
export type Iso8601 = string;

export interface Feature {
  id: string;
  name: string;
  description: string | null;
  owner_subject_id: string | null;
  created_at: Iso8601;
  updated_at: Iso8601;
}

export interface Repo {
  id: string;
  name: string;
  remote_url: string;
  default_branch: string;
  status: "registered" | "fetching" | "ready" | "error";
  last_synced_at: Iso8601 | null;
  error_message: string | null;
}

export interface Document {
  id: string;
  feature_id: string;
  kind: "doc" | "spec" | "runbook";
  title: string;
  path: string;
  tags: string[];
  summary: string | null;
  created_at: Iso8601;
  updated_at: Iso8601;
}

export type ReportStatus = "draft" | "verified" | "stale" | "superseded" | "rejected";

export interface ReportMetadata {
  feature_ids: string[];
  repo_commits: { repo_id: string; commit_sha: string }[];
  error_signatures: string[];
  trace_signals: string[];
  verified: boolean;
  verified_by: string | null;
  verified_at: Iso8601 | null;
  status: ReportStatus;
}

export interface Report {
  id: string;
  title: string;
  body_markdown: string;
  metadata: ReportMetadata;
  created_at: Iso8601;
  updated_at: Iso8601;
}

export interface Skill {
  id: string;
  name: string;
  scope: "global" | "feature";
  feature_id: string | null;
  body_markdown: string;
  updated_at: Iso8601;
}

export interface LlmConfig {
  id: string;
  name: string;
  protocol: "openai" | "openai_compatible" | "anthropic";
  model: string;
  base_url: string | null;
  is_default: boolean;
  created_at: Iso8601;
}

export type FeedbackVerdict = "solved" | "partial" | "wrong";

export interface SessionSummary {
  id: string;
  title: string;
  owner_subject_id: string;
  feature_id: string | null;
  feature_name: string | null;
  last_feedback: FeedbackVerdict | null;
  created_at: Iso8601;
  updated_at: Iso8601;
}

export interface SessionMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system";
  content_markdown: string;
  created_at: Iso8601;
}

export type Confidence = "high" | "medium" | "low";

export interface AnswerStructured {
  claim: string;
  confidence: Confidence;
  recommended_actions: string[];
  uncertainties: string[];
  evidence_ids: string[];
}

export type EvidenceKind = "log" | "code" | "wiki_doc" | "report" | "user_answer" | "system";

export interface EvidenceItem {
  id: string;
  type: EvidenceKind;
  summary: string;
  relevance: "supports" | "contradicts" | "context" | "uncertain";
  confidence: Confidence;
  source: Record<string, unknown>;
  captured_at: Iso8601;
}

export interface DashboardMetrics {
  range_days: 7 | 30;
  deflection_rate: number;
  deflection_delta_pp: number;
  wrong_feedback_rate: number;
  reports_verified_count: number;
  reports_hits_count: number;
  documents_changed_count: number;
}

export interface DashboardPendingItem {
  kind: "draft_report" | "partial_session" | "wrong_session";
  ref_id: string;
  title: string;
  created_at: Iso8601;
}
```

- [ ] **Step 4: 实现 `frontend/src/lib/api.ts`**

```ts
import { getSubjectId } from "@/lib/identity";

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export interface ApiFetchOptions extends Omit<RequestInit, "body"> {
  json?: unknown;
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const headers = new Headers(options.headers ?? {});
  headers.set("X-Subject-Id", getSubjectId());

  let body: BodyInit | null | undefined = undefined;
  if (options.json !== undefined) {
    headers.set("content-type", "application/json");
    body = JSON.stringify(options.json);
  } else if (options.body !== undefined && options.body !== null) {
    body = options.body as BodyInit;
  }

  const response = await fetch(path, {
    ...options,
    headers,
    body,
  });

  if (response.status === 204) {
    return null as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  const payload: unknown = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : `HTTP ${response.status}`;
    throw new ApiError(response.status, message, payload);
  }

  return payload as T;
}
```

- [ ] **Step 5: 跑测试确认通过**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm test tests/api.test.ts
```
Expected: 5 个测试 PASS。

- [ ] **Step 6: 提交**

```bash
cd /home/hzh/workspace/CodeAsk
git add frontend/src/lib/api.ts frontend/src/types/api.ts frontend/tests/api.test.ts
git commit -m "feat(frontend): apiFetch wrapper + ApiError + snake_case API types"
```

---

## Task 6: SSE client + event 类型 + 单测

**Files:**
- Create: `frontend/src/types/sse.ts`
- Create: `frontend/src/lib/sse.ts`
- Create: `frontend/tests/sse.test.ts`

`sse.ts` 包 `microsoft/fetch-event-source`，支持 POST + 自定义 header（原生 EventSource 做不到）。事件 union 类型严格映射 `agent-runtime.md` §11：`stage` / `tool_call` / `tool_result` / `evidence` / `ask_user` / `sufficiency_judgement` / `done` / `error`。前端额外消费 backend 同源命名的 `text_delta`（增量答案 token，命名沿用 OpenAI delta 习惯）和 `scope_detection`（A2 透明事件，承接 `frontend-workbench.md` §4.2）—— 这两个虽然在 agent-runtime.md §11 没显式列举，但 §4 + §6 的"UI 透明"承诺要求暴露。

- [ ] **Step 1: 创建 `frontend/src/types/sse.ts`**

```ts
import type { AnswerStructured, Confidence, EvidenceItem } from "@/types/api";

export interface StageEvent {
  type: "stage";
  name:
    | "input_analysis"
    | "scope_detection"
    | "knowledge_retrieval"
    | "sufficiency_judgement"
    | "code_investigation"
    | "version_confirmation"
    | "evidence_synthesis"
    | "answer_finalization"
    | "report_drafting";
  status: "running" | "done" | "skipped";
  message: string | null;
}

export interface ScopeDetectionEvent {
  type: "scope_detection";
  selected_feature_id: string | null;
  selected_feature_name: string | null;
  confidence: Confidence;
  candidates: { feature_id: string; feature_name: string; score: number }[];
  reason: string;
}

export interface SufficiencyJudgementEvent {
  type: "sufficiency_judgement";
  verdict: "sufficient" | "insufficient";
  reason: string;
  next: "evidence_synthesis" | "code_investigation";
}

export interface ToolCallStartEvent {
  type: "tool_call_start";
  call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
}

export interface ToolCallDoneEvent {
  type: "tool_call_done";
  call_id: string;
  ok: boolean;
  error_code: string | null;
  result_summary: string;
}

export interface EvidenceEvent {
  type: "evidence";
  evidence: EvidenceItem;
}

export interface AskUserEvent {
  type: "ask_user";
  question: string;
  expected: "feature_choice" | "version" | "free_text";
  options: { value: string; label: string }[];
}

export interface TextDeltaEvent {
  type: "text_delta";
  delta: string;
}

export interface DoneEvent {
  type: "done";
  answer: AnswerStructured | null;
  message_id: string;
}

export interface ErrorEvent {
  type: "error";
  error_code: string;
  message: string;
  recoverable: boolean;
}

export type AgentSseEvent =
  | StageEvent
  | ScopeDetectionEvent
  | SufficiencyJudgementEvent
  | ToolCallStartEvent
  | ToolCallDoneEvent
  | EvidenceEvent
  | AskUserEvent
  | TextDeltaEvent
  | DoneEvent
  | ErrorEvent;
```

- [ ] **Step 2: 写测试 `frontend/tests/sse.test.ts`**

```ts
import { describe, expect, it, vi } from "vitest";

import { parseSseEvent } from "@/lib/sse";

describe("parseSseEvent", () => {
  it("parses stage event", () => {
    const evt = parseSseEvent("stage", '{"name":"knowledge_retrieval","status":"running","message":null}');
    expect(evt).toEqual({
      type: "stage",
      name: "knowledge_retrieval",
      status: "running",
      message: null,
    });
  });

  it("parses sufficiency_judgement event", () => {
    const evt = parseSseEvent(
      "sufficiency_judgement",
      '{"verdict":"insufficient","reason":"docs missing","next":"code_investigation"}',
    );
    expect(evt?.type).toBe("sufficiency_judgement");
    if (evt?.type === "sufficiency_judgement") {
      expect(evt.verdict).toBe("insufficient");
      expect(evt.next).toBe("code_investigation");
    }
  });

  it("returns null for unknown event names", () => {
    const noisy = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(parseSseEvent("totally_unknown", "{}")).toBeNull();
    noisy.mockRestore();
  });

  it("returns null and logs on malformed JSON", () => {
    const noisy = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(parseSseEvent("stage", "not-json")).toBeNull();
    noisy.mockRestore();
  });
});
```

- [ ] **Step 3: 跑测试确认失败**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm test tests/sse.test.ts
```

- [ ] **Step 4: 实现 `frontend/src/lib/sse.ts`**

```ts
import { fetchEventSource } from "@microsoft/fetch-event-source";

import { getSubjectId } from "@/lib/identity";
import type { AgentSseEvent } from "@/types/sse";

const KNOWN_EVENT_NAMES = new Set<AgentSseEvent["type"]>([
  "stage",
  "scope_detection",
  "sufficiency_judgement",
  "tool_call_start",
  "tool_call_done",
  "evidence",
  "ask_user",
  "text_delta",
  "done",
  "error",
]);

export function parseSseEvent(name: string, data: string): AgentSseEvent | null {
  if (!KNOWN_EVENT_NAMES.has(name as AgentSseEvent["type"])) {
    console.warn("[sse] unknown event name", name);
    return null;
  }
  let payload: unknown;
  try {
    payload = JSON.parse(data);
  } catch (err) {
    console.warn("[sse] malformed JSON for event", name, err);
    return null;
  }
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  return { type: name, ...(payload as object) } as AgentSseEvent;
}

export interface StreamOptions {
  url: string;
  body: unknown;
  signal: AbortSignal;
  onEvent: (evt: AgentSseEvent) => void;
  onError?: (err: unknown) => void;
}

export async function streamAgent(opts: StreamOptions): Promise<void> {
  await fetchEventSource(opts.url, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "X-Subject-Id": getSubjectId(),
      accept: "text/event-stream",
    },
    body: JSON.stringify(opts.body),
    signal: opts.signal,
    openWhenHidden: true,
    onmessage(msg) {
      const evt = parseSseEvent(msg.event || "stage", msg.data);
      if (evt) opts.onEvent(evt);
    },
    onerror(err) {
      opts.onError?.(err);
      throw err;
    },
  });
}
```

- [ ] **Step 5: 跑测试确认通过**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm test tests/sse.test.ts
```
Expected: 4 个 PASS。

- [ ] **Step 6: 提交**

```bash
cd /home/hzh/workspace/CodeAsk
git add frontend/src/lib/sse.ts frontend/src/types/sse.ts frontend/tests/sse.test.ts
git commit -m "feat(frontend): SSE client + AgentSseEvent union types + parser tests"
```

---

## Task 7: TanStack Router + QueryClient + AppShell 接入

**Files:**
- Create: `frontend/src/lib/query-client.ts`
- Create: `frontend/src/lib/utils.ts`
- Create: `frontend/src/routes/__root.tsx`
- Create: `frontend/src/routes/index.tsx`
- Create: `frontend/src/routes/sessions.tsx`
- Create: `frontend/src/routes/sessions.$id.tsx`
- Create: `frontend/src/routes/dashboard.tsx`
- Create: `frontend/src/routes/wiki.tsx`
- Create: `frontend/src/routes/wiki.documents.$id.tsx`
- Create: `frontend/src/routes/wiki.reports.$id.tsx`
- Create: `frontend/src/routes/repos.tsx`
- Create: `frontend/src/routes/skills.tsx`
- Create: `frontend/src/routes/settings.llm.tsx`
- Create: `frontend/src/routes/features.$id.tsx`
- Create: `frontend/src/components/layout/AppShell.tsx`
- Create: `frontend/src/components/layout/Sidebar.tsx`
- Create: `frontend/src/components/layout/TopBar.tsx`
- Modify: `frontend/src/App.tsx`

每个路由文件都先放壳子（"X 页面，待 Task N 实现"），后续 task 逐步把页面填上。`AppShell` 是顶栏 + 左侧导航 + 中央 `<Outlet />` 的三段布局。

- [ ] **Step 1: 创建 `frontend/src/lib/utils.ts`（shadcn 默认 helper）**

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 2: 创建 `frontend/src/lib/query-client.ts`**

```ts
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
    mutations: {
      retry: 0,
    },
  },
});
```

- [ ] **Step 3: 创建 `frontend/src/components/layout/Sidebar.tsx`**

```tsx
import { Link } from "@tanstack/react-router";
import {
  BookOpen,
  GaugeCircle,
  GitBranch,
  Layers,
  MessagesSquare,
  Settings,
  Sparkles,
} from "lucide-react";

import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/sessions", label: "会话", icon: MessagesSquare },
  { to: "/dashboard", label: "Dashboard", icon: GaugeCircle },
  { to: "/wiki", label: "Wiki", icon: BookOpen },
  { to: "/repos", label: "仓库", icon: GitBranch },
  { to: "/skills", label: "Skill", icon: Sparkles },
  { to: "/settings/llm", label: "LLM", icon: Settings },
] as const;

export function Sidebar(): JSX.Element {
  return (
    <nav className="flex w-52 shrink-0 flex-col gap-1 border-r bg-muted/40 p-3">
      <div className="mb-3 flex items-center gap-2 px-2 text-sm font-semibold">
        <Layers className="h-4 w-4" /> CodeAsk
      </div>
      {NAV_ITEMS.map((item) => (
        <Link
          key={item.to}
          to={item.to}
          className={cn(
            "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
            "hover:bg-accent hover:text-accent-foreground",
          )}
          activeProps={{ className: "bg-accent text-accent-foreground font-medium" }}
        >
          <item.icon className="h-4 w-4" />
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
```

- [ ] **Step 4: 创建 `frontend/src/components/layout/TopBar.tsx`（占位 UserMenu，下一 Task 替换）**

```tsx
import { useIdentityStore } from "@/stores/identity-store";

export function TopBar(): JSX.Element {
  const subjectId = useIdentityStore((s) => s.subjectId);
  return (
    <header className="flex h-12 items-center justify-between border-b px-4">
      <div className="text-sm text-muted-foreground">研发问答工作台</div>
      <div className="text-xs">
        <span className="font-mono">{subjectId}</span>
        <span className="ml-2 rounded border px-1 text-[10px] text-muted-foreground">自报</span>
      </div>
    </header>
  );
}
```

- [ ] **Step 5: 创建 `frontend/src/components/layout/AppShell.tsx`**

```tsx
import { Outlet } from "@tanstack/react-router";

import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";

export function AppShell(): JSX.Element {
  return (
    <div className="flex h-full">
      <Sidebar />
      <div className="flex h-full flex-1 flex-col">
        <TopBar />
        <main className="flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: 创建 `frontend/src/routes/__root.tsx`**

```tsx
import { createRootRoute } from "@tanstack/react-router";

import { AppShell } from "@/components/layout/AppShell";

export const Route = createRootRoute({
  component: AppShell,
});
```

- [ ] **Step 7: 创建 `frontend/src/routes/index.tsx`**

```tsx
import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  beforeLoad: () => {
    throw redirect({ to: "/sessions" });
  },
});
```

- [ ] **Step 8: 创建占位路由 — 一一对应**

`frontend/src/routes/sessions.tsx`：

```tsx
import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/sessions")({
  component: () => (
    <div className="h-full">
      <Outlet />
    </div>
  ),
});
```

`frontend/src/routes/sessions.$id.tsx`：

```tsx
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/sessions/$id")({
  component: SessionPage,
});

function SessionPage(): JSX.Element {
  const { id } = Route.useParams();
  return <div className="p-6 text-sm text-muted-foreground">Session {id} — 待 Task 9 实现</div>;
}
```

`frontend/src/routes/dashboard.tsx`：

```tsx
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/dashboard")({
  component: () => (
    <div className="p-6 text-sm text-muted-foreground">Dashboard — 待 Task 13 实现</div>
  ),
});
```

`frontend/src/routes/wiki.tsx`：

```tsx
import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/wiki")({
  component: () => (
    <div className="h-full">
      <Outlet />
    </div>
  ),
});
```

`frontend/src/routes/wiki.documents.$id.tsx`：

```tsx
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/wiki/documents/$id")({
  component: () => <div className="p-6 text-sm text-muted-foreground">Document detail — 待 Task 14 实现</div>,
});
```

`frontend/src/routes/wiki.reports.$id.tsx`：

```tsx
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/wiki/reports/$id")({
  component: () => <div className="p-6 text-sm text-muted-foreground">Report detail — 待 Task 15 实现</div>,
});
```

`frontend/src/routes/repos.tsx`：

```tsx
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/repos")({
  component: () => <div className="p-6 text-sm text-muted-foreground">Repos — 待 Task 16 实现</div>,
});
```

`frontend/src/routes/skills.tsx`：

```tsx
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/skills")({
  component: () => <div className="p-6 text-sm text-muted-foreground">Skills — 待 Task 17 实现</div>,
});
```

`frontend/src/routes/settings.llm.tsx`：

```tsx
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/settings/llm")({
  component: () => <div className="p-6 text-sm text-muted-foreground">LLM 配置 — 待 Task 18 实现</div>,
});
```

`frontend/src/routes/features.$id.tsx`：

```tsx
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/features/$id")({
  component: () => <div className="p-6 text-sm text-muted-foreground">Feature detail — 待 Task 19 实现</div>,
});
```

- [ ] **Step 9: 重写 `frontend/src/App.tsx`**

```tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createRouter } from "@tanstack/react-router";

import { queryClient } from "@/lib/query-client";

import { routeTree } from "./routeTree.gen";

const router = createRouter({ routeTree, defaultPreload: "intent" });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

export default function App(): JSX.Element {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
```

- [ ] **Step 10: 跑 dev 验证 router 起得来**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm dev &
DEV_PID=$!
sleep 4
curl -fs http://127.0.0.1:5173/ | head -c 500
kill $DEV_PID
```
Expected: 输出包含 `<div id="root">`。

- [ ] **Step 11: typecheck + lint 通过**

```bash
pnpm typecheck && pnpm lint
```

- [ ] **Step 12: 提交**

```bash
cd /home/hzh/workspace/CodeAsk
git add frontend/src/lib/query-client.ts frontend/src/lib/utils.ts frontend/src/routes/ frontend/src/components/layout/ frontend/src/App.tsx frontend/src/routeTree.gen.ts
git commit -m "feat(frontend): TanStack Router shell + QueryClient + AppShell layout"
```

---

## Task 8: shadcn/ui base 组件批量安装 + components.json

**Files:**
- Create: `frontend/components.json`
- Create: `frontend/src/components/ui/button.tsx`
- Create: `frontend/src/components/ui/card.tsx`
- Create: `frontend/src/components/ui/dialog.tsx`
- Create: `frontend/src/components/ui/input.tsx`
- Create: `frontend/src/components/ui/textarea.tsx`
- Create: `frontend/src/components/ui/select.tsx`
- Create: `frontend/src/components/ui/tabs.tsx`
- Create: `frontend/src/components/ui/badge.tsx`
- Create: `frontend/src/components/ui/separator.tsx`
- Create: `frontend/src/components/ui/scroll-area.tsx`
- Create: `frontend/src/components/ui/tooltip.tsx`
- Create: `frontend/src/components/ui/dropdown-menu.tsx`
- Create: `frontend/src/components/ui/command.tsx`
- Create: `frontend/src/components/ui/sheet.tsx`
- Create: `frontend/src/components/ui/avatar.tsx`
- Create: `frontend/src/components/ui/alert.tsx`
- Create: `frontend/src/components/ui/checkbox.tsx`
- Create: `frontend/src/components/ui/collapsible.tsx`
- Create: `frontend/src/components/ui/radio-group.tsx`
- Create: `frontend/src/components/ui/popover.tsx`
- Create: `frontend/src/components/ui/sonner.tsx`

shadcn/ui 是**复制式**：用官方 CLI 把组件代码生成到 `frontend/src/components/ui/`，之后这些代码归本仓所有，可改可删。本步骤一次性把后续 task 用得到的全部 base 组件下载齐。组件代码量大，**不在本 plan 里贴每个 .tsx 全文**——通过 CLI 生成等价于"约定好用 shadcn 的官方 latest 版本"，只需 commit 生成结果。CLI 不连外网时也可手抄 shadcn registry（每个组件 < 100 行）。

- [ ] **Step 1: 创建 `frontend/components.json`**

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.ts",
    "css": "src/styles/globals.css",
    "baseColor": "slate",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  },
  "iconLibrary": "lucide"
}
```

- [ ] **Step 2: 用 shadcn CLI 批量生成组件**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm dlx shadcn@latest add \
  button card dialog input textarea select tabs badge separator \
  scroll-area tooltip dropdown-menu command sheet avatar alert \
  checkbox collapsible radio-group popover sonner \
  --yes --overwrite
```
Expected: `frontend/src/components/ui/*.tsx` 全部生成，且 `globals.css` 不被 CLI 重写覆盖（如被覆盖，从 git 还原 globals.css 后只 keep `ui/*` 的新文件）。

- [ ] **Step 3: typecheck + 起 dev 验证**

```bash
pnpm typecheck
pnpm dev &
DEV_PID=$!
sleep 4
curl -fs http://127.0.0.1:5173/ > /dev/null
kill $DEV_PID
```
Expected: typecheck 0 错；dev server 200 OK。

- [ ] **Step 4: 提交**

```bash
cd /home/hzh/workspace/CodeAsk
git add frontend/components.json frontend/src/components/ui/
# 如果 globals.css 被 CLI 改动且并入了我们 task 2 的内容，可一起 add；否则 git restore globals.css 再 add
git commit -m "feat(frontend): shadcn/ui base components (21 primitives)"
```

---

## Task 9: TanStack Query hooks 全集（features / documents / reports / repos / skills / llm / sessions / dashboard / feedback）

**Files:**
- Create: `frontend/src/hooks/use-features.ts`
- Create: `frontend/src/hooks/use-documents.ts`
- Create: `frontend/src/hooks/use-reports.ts`
- Create: `frontend/src/hooks/use-repos.ts`
- Create: `frontend/src/hooks/use-skills.ts`
- Create: `frontend/src/hooks/use-llm-configs.ts`
- Create: `frontend/src/hooks/use-sessions.ts`
- Create: `frontend/src/hooks/use-feedback.ts`
- Create: `frontend/src/hooks/use-dashboard.ts`

每个 hook 只做"调 apiFetch + 标 query key"。命名约定：`useXxx()` = list；`useXxx(id)` = single；`useCreateXxx() / useUpdateXxx() / useDeleteXxx()` = mutation；mutation 成功后 `invalidateQueries({ queryKey: [...] })`。

- [ ] **Step 1: 创建 `frontend/src/hooks/use-features.ts`**

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { Feature } from "@/types/api";

const KEY = ["features"] as const;

export function useFeatures() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => apiFetch<Feature[]>("/api/features"),
  });
}

export function useFeature(id: string | null) {
  return useQuery({
    queryKey: [...KEY, id],
    queryFn: () => apiFetch<Feature>(`/api/features/${id}`),
    enabled: id !== null,
  });
}

export interface CreateFeatureInput {
  name: string;
  description: string | null;
}

export function useCreateFeature() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateFeatureInput) =>
      apiFetch<Feature>("/api/features", { method: "POST", json: input }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useUpdateFeatureRepos() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, repo_ids }: { id: string; repo_ids: string[] }) =>
      apiFetch<Feature>(`/api/features/${id}/repos`, { method: "PUT", json: { repo_ids } }),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: KEY });
      qc.invalidateQueries({ queryKey: [...KEY, vars.id] });
    },
  });
}
```

- [ ] **Step 2: 创建 `frontend/src/hooks/use-documents.ts`**

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { Document } from "@/types/api";

const KEY = ["documents"] as const;

export interface DocumentSearchHit {
  document_id: string;
  chunk_id: string;
  title: string;
  heading_path: string;
  snippet: string;
  score: number;
}

export function useDocuments(featureId: string | null) {
  return useQuery({
    queryKey: [...KEY, { feature_id: featureId }],
    queryFn: () =>
      apiFetch<Document[]>(
        featureId ? `/api/documents?feature_id=${encodeURIComponent(featureId)}` : "/api/documents",
      ),
  });
}

export function useDocument(id: string | null) {
  return useQuery({
    queryKey: [...KEY, id],
    queryFn: () => apiFetch<Document>(`/api/documents/${id}`),
    enabled: id !== null,
  });
}

export function useDocumentSearch(query: string) {
  return useQuery({
    queryKey: [...KEY, "search", query],
    queryFn: () =>
      apiFetch<DocumentSearchHit[]>(`/api/documents/search?q=${encodeURIComponent(query)}`),
    enabled: query.trim().length > 0,
  });
}

export function useUploadDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (form: FormData) => {
      const res = await fetch("/api/documents", {
        method: "POST",
        body: form,
        headers: { "X-Subject-Id": (await import("@/lib/identity")).getSubjectId() },
      });
      if (!res.ok) throw new Error(`upload failed: ${res.status}`);
      return (await res.json()) as Document;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
```

- [ ] **Step 3: 创建 `frontend/src/hooks/use-reports.ts`**

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { Report } from "@/types/api";

const KEY = ["reports"] as const;

export function useReports() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => apiFetch<Report[]>("/api/reports"),
  });
}

export function useReport(id: string | null) {
  return useQuery({
    queryKey: [...KEY, id],
    queryFn: () => apiFetch<Report>(`/api/reports/${id}`),
    enabled: id !== null,
  });
}

export function useVerifyReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<Report>(`/api/reports/${id}/verify`, { method: "POST", json: {} }),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: KEY });
      qc.invalidateQueries({ queryKey: [...KEY, id] });
    },
  });
}

export function useUnverifyReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<Report>(`/api/reports/${id}/unverify`, { method: "POST", json: {} }),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: KEY });
      qc.invalidateQueries({ queryKey: [...KEY, id] });
    },
  });
}
```

- [ ] **Step 4: 创建 `frontend/src/hooks/use-repos.ts`**

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { Repo } from "@/types/api";

const KEY = ["repos"] as const;

export function useRepos() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => apiFetch<Repo[]>("/api/repos"),
    refetchInterval: (q) => {
      const data = q.state.data;
      if (!data) return false;
      return data.some((r) => r.status === "fetching") ? 3_000 : false;
    },
  });
}

export interface RegisterRepoInput {
  name: string;
  remote_url: string;
  default_branch: string;
}

export function useRegisterRepo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: RegisterRepoInput) =>
      apiFetch<Repo>("/api/repos", { method: "POST", json: input }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteRepo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch<null>(`/api/repos/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
```

- [ ] **Step 5: 创建 `frontend/src/hooks/use-skills.ts`**

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { Skill } from "@/types/api";

const KEY = ["skills"] as const;

export function useSkills() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => apiFetch<Skill[]>("/api/skills"),
  });
}

export interface UpsertSkillInput {
  id: string | null;
  name: string;
  scope: "global" | "feature";
  feature_id: string | null;
  body_markdown: string;
}

export function useUpsertSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: UpsertSkillInput) =>
      input.id === null
        ? apiFetch<Skill>("/api/skills", { method: "POST", json: input })
        : apiFetch<Skill>(`/api/skills/${input.id}`, { method: "PUT", json: input }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch<null>(`/api/skills/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
```

- [ ] **Step 6: 创建 `frontend/src/hooks/use-llm-configs.ts`**

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { LlmConfig } from "@/types/api";

const KEY = ["llm-configs"] as const;

export function useLlmConfigs() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => apiFetch<LlmConfig[]>("/api/me/llm-configs"),
  });
}

export interface UpsertLlmConfigInput {
  id: string | null;
  name: string;
  protocol: "openai" | "openai_compatible" | "anthropic";
  model: string;
  base_url: string | null;
  api_key: string | null; // encrypted backend-side via Fernet
  is_default: boolean;
}

export function useUpsertLlmConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: UpsertLlmConfigInput) =>
      input.id === null
        ? apiFetch<LlmConfig>("/api/me/llm-configs", { method: "POST", json: input })
        : apiFetch<LlmConfig>(`/api/me/llm-configs/${input.id}`, { method: "PATCH", json: input }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteLlmConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch<null>(`/api/me/llm-configs/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
```

- [ ] **Step 7: 创建 `frontend/src/hooks/use-sessions.ts`**

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { SessionMessage, SessionSummary } from "@/types/api";

const KEY = ["sessions"] as const;

export interface SessionListFilter {
  scope: "mine" | "all";
  feature_id: string | null;
}

export function useSessions(filter: SessionListFilter) {
  return useQuery({
    queryKey: [...KEY, filter],
    queryFn: () => {
      const params = new URLSearchParams({ scope: filter.scope });
      if (filter.feature_id) params.set("feature_id", filter.feature_id);
      return apiFetch<SessionSummary[]>(`/api/sessions?${params.toString()}`);
    },
  });
}

export function useSession(id: string | null) {
  return useQuery({
    queryKey: [...KEY, id],
    queryFn: () => apiFetch<SessionSummary>(`/api/sessions/${id}`),
    enabled: id !== null,
  });
}

export function useSessionMessages(id: string | null) {
  return useQuery({
    queryKey: [...KEY, id, "messages"],
    queryFn: () => apiFetch<SessionMessage[]>(`/api/sessions/${id}/messages`),
    enabled: id !== null,
  });
}

export function useCreateSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { title: string }) =>
      apiFetch<SessionSummary>("/api/sessions", { method: "POST", json: input }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
```

- [ ] **Step 8: 创建 `frontend/src/hooks/use-feedback.ts`**

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { FeedbackVerdict } from "@/types/api";

export interface FeedbackInput {
  session_id: string;
  message_id: string;
  verdict: FeedbackVerdict;
  note: string | null;
}

export function useSendFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: FeedbackInput) =>
      apiFetch<{ ok: true }>("/api/feedback", { method: "POST", json: input }),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      qc.invalidateQueries({ queryKey: ["sessions", vars.session_id] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}
```

- [ ] **Step 9: 创建 `frontend/src/hooks/use-dashboard.ts`**

```ts
import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { DashboardMetrics, DashboardPendingItem } from "@/types/api";

const KEY = ["dashboard"] as const;

export function useDashboardMetrics(rangeDays: 7 | 30) {
  return useQuery({
    queryKey: [...KEY, "metrics", rangeDays],
    queryFn: () => apiFetch<DashboardMetrics>(`/api/metrics?range_days=${rangeDays}`),
  });
}

export function useDashboardPending() {
  return useQuery({
    queryKey: [...KEY, "pending"],
    queryFn: () => apiFetch<DashboardPendingItem[]>("/api/metrics/pending"),
  });
}
```

- [ ] **Step 10: typecheck**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm typecheck
```
Expected: 0 错。

- [ ] **Step 11: 提交**

```bash
cd /home/hzh/workspace/CodeAsk
git add frontend/src/hooks/
git commit -m "feat(frontend): TanStack Query hooks for all REST endpoints"
```

---

## Task 10: UserMenu + NicknameDialog + SelfReportBadge + 单测

**Files:**
- Create: `frontend/src/components/identity/SelfReportBadge.tsx`
- Create: `frontend/src/components/identity/NicknameDialog.tsx`
- Create: `frontend/src/components/identity/UserMenu.tsx`
- Modify: `frontend/src/components/layout/TopBar.tsx`（接入 UserMenu）
- Create: `frontend/tests/UserMenu.test.tsx`

落地 `frontend-workbench.md` §8：subject_id 显示 + "自报"小标识 + 改昵称 + 清除身份。NicknameDialog 用 react-hook-form + zod 校验昵称长度与字符。

- [ ] **Step 1: 创建 `frontend/src/components/identity/SelfReportBadge.tsx`**

```tsx
import { Badge } from "@/components/ui/badge";

export function SelfReportBadge(): JSX.Element {
  return (
    <Badge variant="outline" className="text-[10px] font-normal text-muted-foreground">
      自报
    </Badge>
  );
}
```

- [ ] **Step 2: 创建 `frontend/src/components/identity/NicknameDialog.tsx`**

```tsx
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { sanitizeNickname } from "@/lib/identity";

const schema = z.object({
  nickname: z
    .string()
    .min(0)
    .max(32, "最多 32 个字符")
    .refine((v) => sanitizeNickname(v) === v, {
      message: "只允许字母、数字、点、下划线、短横线",
    }),
});

type FormValues = z.infer<typeof schema>;

interface Props {
  open: boolean;
  defaultNickname: string;
  onOpenChange: (open: boolean) => void;
  onSubmit: (nickname: string) => void;
}

export function NicknameDialog({ open, defaultNickname, onOpenChange, onSubmit }: Props): JSX.Element {
  const { register, handleSubmit, formState } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { nickname: defaultNickname },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>设置昵称</DialogTitle>
          <DialogDescription>
            团队里看到你的会话时显示这个名字。可以随时改 / 清空。这是软识别，不是鉴权。
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-3"
          onSubmit={handleSubmit((v) => {
            onSubmit(v.nickname);
            onOpenChange(false);
          })}
        >
          <Input placeholder="例如 alice" {...register("nickname")} autoFocus />
          {formState.errors.nickname ? (
            <p className="text-xs text-destructive">{formState.errors.nickname.message}</p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button type="submit">保存</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 3: 安装 `@hookform/resolvers`**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm add @hookform/resolvers
```

- [ ] **Step 4: 创建 `frontend/src/components/identity/UserMenu.tsx`**

```tsx
import { useState } from "react";
import { LogOut, Pencil, User } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { NicknameDialog } from "@/components/identity/NicknameDialog";
import { SelfReportBadge } from "@/components/identity/SelfReportBadge";
import { useIdentityStore } from "@/stores/identity-store";

export function UserMenu(): JSX.Element {
  const { subjectId, nickname, setNickname, clearIdentity } = useIdentityStore();
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm" className="gap-2">
            <User className="h-4 w-4" />
            <span className="font-mono text-xs">{subjectId}</span>
            <SelfReportBadge />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel className="text-xs text-muted-foreground">
            自报身份（不是鉴权）
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setDialogOpen(true)}>
            <Pencil className="mr-2 h-4 w-4" />
            {nickname ? "改昵称" : "设置昵称"}
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => clearIdentity()}>
            <LogOut className="mr-2 h-4 w-4" />
            清除身份
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <NicknameDialog
        open={dialogOpen}
        defaultNickname={nickname ?? ""}
        onOpenChange={setDialogOpen}
        onSubmit={setNickname}
      />
    </>
  );
}
```

- [ ] **Step 5: 修改 `frontend/src/components/layout/TopBar.tsx`**

```tsx
import { UserMenu } from "@/components/identity/UserMenu";

export function TopBar(): JSX.Element {
  return (
    <header className="flex h-12 items-center justify-between border-b px-4">
      <div className="text-sm text-muted-foreground">研发问答工作台</div>
      <UserMenu />
    </header>
  );
}
```

- [ ] **Step 6: 写测试 `frontend/tests/UserMenu.test.tsx`**

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { UserMenu } from "@/components/identity/UserMenu";

describe("UserMenu", () => {
  it("shows device@<short> subject_id when no nickname", async () => {
    render(<UserMenu />);
    expect(screen.getByText(/^device@[0-9a-f]{8}$/)).toBeInTheDocument();
    expect(screen.getByText("自报")).toBeInTheDocument();
  });

  it("opens dropdown and dialog to set nickname, then displays it", async () => {
    const user = userEvent.setup();
    render(<UserMenu />);

    await user.click(screen.getByRole("button", { name: /device@/ }));
    await user.click(screen.getByText(/设置昵称/));

    const input = await screen.findByPlaceholderText("例如 alice");
    await user.clear(input);
    await user.type(input, "alice");
    await user.click(screen.getByRole("button", { name: "保存" }));

    expect(await screen.findByText(/^alice@[0-9a-f-]{36}$/)).toBeInTheDocument();
  });

  it("clear identity rotates client_id", async () => {
    const user = userEvent.setup();
    render(<UserMenu />);
    const before = screen.getByText(/^device@[0-9a-f]{8}$/).textContent;

    await user.click(screen.getByRole("button", { name: /device@/ }));
    await user.click(screen.getByText(/清除身份/));

    const after = screen.getByText(/^device@[0-9a-f]{8}$/).textContent;
    expect(after).not.toBe(before);
  });
});
```

- [ ] **Step 7: 跑测试**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm test tests/UserMenu.test.tsx
```
Expected: 3 PASS。

- [ ] **Step 8: 提交**

```bash
cd /home/hzh/workspace/CodeAsk
git add frontend/src/components/identity/ frontend/src/components/layout/TopBar.tsx frontend/tests/UserMenu.test.tsx frontend/package.json frontend/pnpm-lock.yaml
git commit -m "feat(frontend): UserMenu + NicknameDialog + self-report badge"
```

---

## Task 11: SessionList（当前用户会话 + 搜索新建 + 行操作菜单）

**Files:**
- Create: `frontend/src/lib/format.ts`
- Create: `frontend/src/components/session/SessionList.tsx`
- Modify: `frontend/src/routes/sessions.tsx`（嵌入 SessionList + 默认重定向到第一个会话或 new）

落地 `frontend-workbench.md` §3.1：默认按当前 `subject_id` 过滤会话，不提供"我的 / 全部"切换；列表顶部只有搜索框和新建按钮；条目展示标题、关联特性、最近反馈状态，右侧三点菜单承载编辑名称、分享、置顶、批量操作、删除。

- [ ] **Step 1: 创建 `frontend/src/lib/format.ts`**

```ts
import type { Confidence, FeedbackVerdict } from "@/types/api";

export function formatRelativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const min = Math.floor(ms / 60_000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min} 分钟前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} 小时前`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day} 天前`;
  return new Date(iso).toLocaleDateString("zh-CN");
}

export function feedbackLabel(v: FeedbackVerdict | null): string {
  switch (v) {
    case "solved":
      return "已解决";
    case "partial":
      return "部分解决";
    case "wrong":
      return "答错";
    default:
      return "待反馈";
  }
}

export function feedbackColor(v: FeedbackVerdict | null): string {
  switch (v) {
    case "solved":
      return "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
    case "partial":
      return "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300";
    case "wrong":
      return "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300";
    default:
      return "border-muted text-muted-foreground";
  }
}

export function confidenceLabel(c: Confidence): string {
  return c === "high" ? "高" : c === "medium" ? "中" : "低";
}

export function confidenceColor(c: Confidence): string {
  return c === "high"
    ? "bg-confidence-high/10 text-confidence-high border-confidence-high/40"
    : c === "medium"
      ? "bg-confidence-medium/10 text-confidence-medium border-confidence-medium/40"
      : "bg-confidence-low/10 text-confidence-low border-confidence-low/40";
}
```

- [ ] **Step 2: 创建 `frontend/src/components/session/SessionList.tsx`**

```tsx
import { Link } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { feedbackColor, feedbackLabel, formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useCreateSession, useSessions } from "@/hooks/use-sessions";
import type { SessionSummary } from "@/types/api";

type Scope = "mine" | "all";

interface Props {
  activeId: string | null;
  onCreated?: (id: string) => void;
}

export function SessionList({ activeId, onCreated }: Props): JSX.Element {
  const [scope, setScope] = useState<Scope>("mine");
  const sessions = useSessions({ scope, feature_id: null });
  const create = useCreateSession();

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r">
      <div className="flex items-center justify-between gap-2 border-b p-3">
        <Tabs value={scope} onValueChange={(v) => setScope(v as Scope)}>
          <TabsList>
            <TabsTrigger value="mine">我的</TabsTrigger>
            <TabsTrigger value="all">全部</TabsTrigger>
          </TabsList>
        </Tabs>
        <Button
          size="sm"
          variant="outline"
          disabled={create.isPending}
          onClick={async () => {
            const created = await create.mutateAsync({ title: "新会话" });
            onCreated?.(created.id);
          }}
        >
          <Plus className="mr-1 h-4 w-4" />
          新建
        </Button>
      </div>
      <ScrollArea className="flex-1">
        <ul className="flex flex-col">
          {sessions.data?.map((s) => (
            <SessionRow key={s.id} session={s} active={s.id === activeId} />
          ))}
          {sessions.data?.length === 0 ? (
            <li className="p-4 text-sm text-muted-foreground">暂无会话</li>
          ) : null}
        </ul>
      </ScrollArea>
    </aside>
  );
}

function SessionRow({ session, active }: { session: SessionSummary; active: boolean }): JSX.Element {
  return (
    <li>
      <Link
        to="/sessions/$id"
        params={{ id: session.id }}
        className={cn(
          "flex flex-col gap-1 border-b px-3 py-2 text-sm hover:bg-accent",
          active && "bg-accent",
        )}
      >
        <div className="line-clamp-1 font-medium">{session.title}</div>
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          <span className="font-mono">{session.owner_subject_id}</span>
          {session.feature_name ? <Badge variant="secondary">{session.feature_name}</Badge> : null}
          <Badge
            variant="outline"
            className={cn("text-[10px]", feedbackColor(session.last_feedback))}
          >
            {feedbackLabel(session.last_feedback)}
          </Badge>
          <span className="ml-auto">{formatRelativeTime(session.updated_at)}</span>
        </div>
      </Link>
    </li>
  );
}
```

- [ ] **Step 3: 更新 `frontend/src/routes/sessions.tsx` —— 三栏在 sessions.$id 里组合，sessions/ 列表占左**

```tsx
import { createFileRoute, Outlet } from "@tanstack/react-router";

import { SessionList } from "@/components/session/SessionList";

export const Route = createFileRoute("/sessions")({
  component: SessionsLayout,
});

function SessionsLayout(): JSX.Element {
  const params = Route.useParams() as { id?: string };
  return (
    <div className="flex h-full">
      <SessionList activeId={params.id ?? null} />
      <div className="flex-1 overflow-hidden">
        <Outlet />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: typecheck + lint**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm typecheck && pnpm lint
```

- [ ] **Step 5: 提交**

```bash
cd /home/hzh/workspace/CodeAsk
git add frontend/src/lib/format.ts frontend/src/components/session/SessionList.tsx frontend/src/routes/sessions.tsx
git commit -m "feat(frontend): SessionList with mine/all toggle + feedback badge"
```

---

## Task 12: 会话工作台中间栏 — SessionInputArea + SessionMessageList + use-session-stream

**Files:**
- Create: `frontend/src/lib/markdown.ts`
- Create: `frontend/src/stores/session-stream-store.ts`
- Create: `frontend/src/hooks/use-session-stream.ts`
- Create: `frontend/src/components/session/SessionInputArea.tsx`
- Create: `frontend/src/components/session/SessionMessageList.tsx`

落地 `frontend-workbench.md` §3.2：自然语言输入 + 附件上传；不要场景 / 类型选择。SSE 缓冲在 Zustand store 里（跨组件共享 — InvestigationPanel 也消费同一缓冲）。Markdown 渲染统一走 `frontend/src/lib/markdown.ts`，shiki 高亮代码。

- [ ] **Step 1: 创建 `frontend/src/lib/markdown.ts`**

```tsx
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { codeToHtml } from "shiki";

interface Props {
  content: string;
}

export function Markdown({ content }: Props): JSX.Element {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        code: ({ inline, className, children, ...rest }) => {
          if (inline) {
            return (
              <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]" {...rest}>
                {children}
              </code>
            );
          }
          const lang = /language-(\w+)/.exec(className ?? "")?.[1] ?? "text";
          return <ShikiBlock code={String(children).replace(/\n$/, "")} lang={lang} />;
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

function ShikiBlock({ code, lang }: { code: string; lang: string }): JSX.Element {
  const [html, setHtml] = useState<string>("");
  useEffect(() => {
    let cancelled = false;
    void codeToHtml(code, { lang, theme: "github-dark" })
      .then((rendered) => {
        if (!cancelled) setHtml(rendered);
      })
      .catch(() => {
        if (!cancelled) setHtml(`<pre><code>${escapeHtml(code)}</code></pre>`);
      });
    return () => {
      cancelled = true;
    };
  }, [code, lang]);
  return <div className="overflow-x-auto rounded-md text-sm" dangerouslySetInnerHTML={{ __html: html }} />;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
```

- [ ] **Step 2: 创建 `frontend/src/stores/session-stream-store.ts`**

```ts
import { create } from "zustand";

import type {
  AgentSseEvent,
  AskUserEvent,
  EvidenceEvent,
  ScopeDetectionEvent,
  StageEvent,
  SufficiencyJudgementEvent,
  ToolCallDoneEvent,
  ToolCallStartEvent,
} from "@/types/sse";
import type { AnswerStructured } from "@/types/api";

interface ToolCallRecord {
  call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  status: "running" | "done";
  ok: boolean | null;
  error_code: string | null;
  result_summary: string | null;
}

export interface StreamState {
  sessionId: string | null;
  isStreaming: boolean;
  stage: StageEvent | null;
  scope: ScopeDetectionEvent | null;
  sufficiency: SufficiencyJudgementEvent | null;
  toolCalls: ToolCallRecord[];
  evidence: EvidenceEvent["evidence"][];
  pendingQuestion: AskUserEvent | null;
  textBuffer: string;
  finalAnswer: AnswerStructured | null;
  finalMessageId: string | null;
  errorMessage: string | null;
  reset: (sessionId: string) => void;
  push: (evt: AgentSseEvent) => void;
  setStreaming: (isStreaming: boolean) => void;
}

export const useSessionStream = create<StreamState>((set) => ({
  sessionId: null,
  isStreaming: false,
  stage: null,
  scope: null,
  sufficiency: null,
  toolCalls: [],
  evidence: [],
  pendingQuestion: null,
  textBuffer: "",
  finalAnswer: null,
  finalMessageId: null,
  errorMessage: null,
  reset: (sessionId) =>
    set({
      sessionId,
      isStreaming: false,
      stage: null,
      scope: null,
      sufficiency: null,
      toolCalls: [],
      evidence: [],
      pendingQuestion: null,
      textBuffer: "",
      finalAnswer: null,
      finalMessageId: null,
      errorMessage: null,
    }),
  setStreaming: (isStreaming) => set({ isStreaming }),
  push: (evt) =>
    set((s) => {
      switch (evt.type) {
        case "stage":
          return { stage: evt };
        case "scope_detection":
          return { scope: evt };
        case "sufficiency_judgement":
          return { sufficiency: evt };
        case "tool_call_start": {
          const next: ToolCallRecord = {
            call_id: evt.call_id,
            tool_name: evt.tool_name,
            arguments: evt.arguments,
            status: "running",
            ok: null,
            error_code: null,
            result_summary: null,
          };
          return { toolCalls: [...s.toolCalls, next] };
        }
        case "tool_call_done": {
          const done = evt as ToolCallDoneEvent;
          const start = evt as ToolCallStartEvent;
          void start; // type-only reference
          return {
            toolCalls: s.toolCalls.map((t) =>
              t.call_id === done.call_id
                ? {
                    ...t,
                    status: "done",
                    ok: done.ok,
                    error_code: done.error_code,
                    result_summary: done.result_summary,
                  }
                : t,
            ),
          };
        }
        case "evidence":
          return { evidence: [...s.evidence, evt.evidence] };
        case "ask_user":
          return { pendingQuestion: evt };
        case "text_delta":
          return { textBuffer: s.textBuffer + evt.delta };
        case "done":
          return {
            isStreaming: false,
            finalAnswer: evt.answer,
            finalMessageId: evt.message_id,
          };
        case "error":
          return { isStreaming: false, errorMessage: evt.message };
        default:
          return {};
      }
    }),
}));
```

- [ ] **Step 3: 创建 `frontend/src/hooks/use-session-stream.ts`**

```ts
import { useCallback, useRef } from "react";

import { streamAgent } from "@/lib/sse";
import { useSessionStream } from "@/stores/session-stream-store";

export interface SendInput {
  prompt: string;
  attachment_ids: string[];
  feature_id_override: string | null;
}

export function useStreamSession(sessionId: string | null) {
  const abortRef = useRef<AbortController | null>(null);
  const reset = useSessionStream((s) => s.reset);
  const push = useSessionStream((s) => s.push);
  const setStreaming = useSessionStream((s) => s.setStreaming);

  const send = useCallback(
    async (input: SendInput) => {
      if (!sessionId) return;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      reset(sessionId);
      setStreaming(true);
      try {
        await streamAgent({
          url: `/api/sessions/${sessionId}/messages`,
          body: input,
          signal: controller.signal,
          onEvent: push,
          onError: (err) => console.error("[stream]", err),
        });
      } finally {
        setStreaming(false);
      }
    },
    [sessionId, reset, push, setStreaming],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setStreaming(false);
  }, [setStreaming]);

  return { send, cancel };
}
```

- [ ] **Step 4: 创建 `frontend/src/components/session/SessionInputArea.tsx`**

```tsx
import { Paperclip, Send, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useStreamSession } from "@/hooks/use-session-stream";

interface Props {
  sessionId: string;
}

export function SessionInputArea({ sessionId }: Props): JSX.Element {
  const [prompt, setPrompt] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const { send, cancel } = useStreamSession(sessionId);

  const onSubmit = async (): Promise<void> => {
    if (!prompt.trim()) return;
    // 一期附件直接随 prompt 走 — 后端在 04 plan 提供 /api/sessions/:id/attachments
    // 这里先把附件名拼进 prompt（实际实施时改为先 POST attachments 拿 id）
    const attachment_ids: string[] = [];
    await send({ prompt, attachment_ids, feature_id_override: null });
    setPrompt("");
    setFiles([]);
  };

  return (
    <div className="border-t bg-background p-3">
      {files.length > 0 ? (
        <div className="mb-2 flex flex-wrap gap-2">
          {files.map((f, i) => (
            <span
              key={i}
              className="flex items-center gap-1 rounded border bg-muted/40 px-2 py-1 text-xs"
            >
              <Paperclip className="h-3 w-3" />
              {f.name}
              <button type="button" onClick={() => setFiles(files.filter((_, j) => j !== i))}>
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      ) : null}
      <Textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="自然语言提问，可粘贴日志 / 附文件。无需选场景或类型。"
        className="min-h-[88px]"
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            void onSubmit();
          }
        }}
      />
      <div className="mt-2 flex items-center justify-between">
        <label className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
          <input
            type="file"
            multiple
            className="hidden"
            onChange={(e) => setFiles([...files, ...Array.from(e.target.files ?? [])])}
          />
          <Paperclip className="inline h-4 w-4" /> 添加附件
        </label>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={cancel}>
            取消
          </Button>
          <Button size="sm" onClick={() => void onSubmit()}>
            <Send className="mr-1 h-4 w-4" />
            发送 (⌘/Ctrl+Enter)
          </Button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: 创建 `frontend/src/components/session/SessionMessageList.tsx`**

```tsx
import { ScrollArea } from "@/components/ui/scroll-area";
import { Markdown } from "@/lib/markdown";
import { cn } from "@/lib/utils";
import { useSessionMessages } from "@/hooks/use-sessions";
import { useSessionStream } from "@/stores/session-stream-store";

interface Props {
  sessionId: string;
}

export function SessionMessageList({ sessionId }: Props): JSX.Element {
  const messages = useSessionMessages(sessionId);
  const liveText = useSessionStream((s) => (s.sessionId === sessionId ? s.textBuffer : ""));
  const isStreaming = useSessionStream((s) => s.isStreaming && s.sessionId === sessionId);

  return (
    <ScrollArea className="h-full">
      <div className="flex flex-col gap-4 p-6">
        {messages.data?.map((m) => (
          <div
            key={m.id}
            className={cn(
              "rounded-md border p-3",
              m.role === "user" ? "bg-secondary/40" : "bg-card",
            )}
          >
            <div className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">
              {m.role}
            </div>
            <Markdown content={m.content_markdown} />
          </div>
        ))}
        {isStreaming && liveText.length > 0 ? (
          <div className="rounded-md border bg-card p-3">
            <div className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">
              assistant (streaming)
            </div>
            <Markdown content={liveText} />
          </div>
        ) : null}
      </div>
    </ScrollArea>
  );
}
```

- [ ] **Step 6: typecheck**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm typecheck
```

- [ ] **Step 7: 提交**

```bash
cd /home/hzh/workspace/CodeAsk
git add frontend/src/lib/markdown.ts frontend/src/stores/session-stream-store.ts frontend/src/hooks/use-session-stream.ts frontend/src/components/session/SessionInputArea.tsx frontend/src/components/session/SessionMessageList.tsx
git commit -m "feat(frontend): session input + message list + SSE stream store"
```

---

## Task 13: 右栏调查面板 — A2 + A3 透明 + tool stream + DeepenButton

**Files:**
- Create: `frontend/src/components/session/ScopeDetectionTransparency.tsx`
- Create: `frontend/src/components/session/SufficiencyJudgementTransparency.tsx`
- Create: `frontend/src/components/session/ToolCallStream.tsx`
- Create: `frontend/src/components/session/DeepenButton.tsx`
- Create: `frontend/src/components/session/InvestigationPanel.tsx`
- Create: `frontend/tests/ScopeDetectionTransparency.test.tsx`

A2 透明（§4.2）：顶部展示 selected feature + confidence + 候选下拉，切换触发 onFeatureChange。A3 透明（§4.3）：sufficient/insufficient + reason，"再深查一下"按钮强制扩展（即使 sufficient）。

- [ ] **Step 1: 创建 `frontend/src/components/session/ScopeDetectionTransparency.tsx`**

```tsx
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { confidenceColor, confidenceLabel } from "@/lib/format";
import type { ScopeDetectionEvent } from "@/types/sse";

interface Props {
  event: ScopeDetectionEvent;
  onFeatureChange: (featureId: string) => void;
}

export function ScopeDetectionTransparency({ event, onFeatureChange }: Props): JSX.Element {
  return (
    <Card className="p-3">
      <div className="mb-2 text-xs font-semibold uppercase text-muted-foreground">A2 定界</div>
      <div className="flex items-center gap-2">
        <span className="text-sm">特性：</span>
        <Select
          value={event.selected_feature_id ?? ""}
          onValueChange={(v) => onFeatureChange(v)}
        >
          <SelectTrigger className="h-8 w-44 text-sm">
            <SelectValue placeholder="未定界" />
          </SelectTrigger>
          <SelectContent>
            {event.candidates.map((c) => (
              <SelectItem key={c.feature_id} value={c.feature_id}>
                {c.feature_name} ({c.score.toFixed(2)})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Badge className={confidenceColor(event.confidence)}>
          信心 {confidenceLabel(event.confidence)}
        </Badge>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{event.reason}</p>
    </Card>
  );
}
```

- [ ] **Step 2: 创建 `frontend/src/components/session/SufficiencyJudgementTransparency.tsx`**

```tsx
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import type { SufficiencyJudgementEvent } from "@/types/sse";

interface Props {
  event: SufficiencyJudgementEvent;
}

export function SufficiencyJudgementTransparency({ event }: Props): JSX.Element {
  const isSuff = event.verdict === "sufficient";
  return (
    <Card className="p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase text-muted-foreground">A3 充分性</span>
        <Badge variant={isSuff ? "secondary" : "destructive"}>
          {isSuff ? "够" : "不够"}
        </Badge>
      </div>
      <p className="text-xs text-muted-foreground">{event.reason}</p>
      <p className="mt-1 text-[11px] text-muted-foreground">
        下一步：{event.next === "code_investigation" ? "进入代码层" : "合成答案"}
      </p>
    </Card>
  );
}
```

- [ ] **Step 3: 创建 `frontend/src/components/session/ToolCallStream.tsx`**

```tsx
import { Check, CircleDashed, X } from "lucide-react";

import { Card } from "@/components/ui/card";
import { useSessionStream } from "@/stores/session-stream-store";

export function ToolCallStream(): JSX.Element {
  const calls = useSessionStream((s) => s.toolCalls);
  if (calls.length === 0) {
    return <Card className="p-3 text-xs text-muted-foreground">尚无工具调用</Card>;
  }
  return (
    <Card className="p-3">
      <div className="mb-2 text-xs font-semibold uppercase text-muted-foreground">工具调用流</div>
      <ul className="flex flex-col gap-1.5 text-xs">
        {calls.map((c) => (
          <li key={c.call_id} className="flex items-start gap-2">
            <span className="mt-0.5">
              {c.status === "running" ? (
                <CircleDashed className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
              ) : c.ok ? (
                <Check className="h-3.5 w-3.5 text-emerald-600" />
              ) : (
                <X className="h-3.5 w-3.5 text-red-600" />
              )}
            </span>
            <div className="flex-1">
              <span className="font-mono">{c.tool_name}</span>
              <span className="ml-1 text-muted-foreground">
                {summarizeArgs(c.arguments)}
              </span>
              {c.result_summary ? (
                <p className="mt-0.5 text-[11px] text-muted-foreground">{c.result_summary}</p>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function summarizeArgs(args: Record<string, unknown>): string {
  const parts = Object.entries(args)
    .slice(0, 3)
    .map(([k, v]) => `${k}=${typeof v === "string" ? JSON.stringify(v) : String(v)}`);
  return `(${parts.join(", ")})`;
}
```

- [ ] **Step 4: 创建 `frontend/src/components/session/DeepenButton.tsx`**

```tsx
import { ChevronsDown } from "lucide-react";

import { Button } from "@/components/ui/button";

interface Props {
  onClick: () => void;
  disabled?: boolean;
}

export function DeepenButton({ onClick, disabled }: Props): JSX.Element {
  return (
    <Button variant="outline" size="sm" onClick={onClick} disabled={disabled}>
      <ChevronsDown className="mr-1 h-4 w-4" />
      再深查一下
    </Button>
  );
}
```

- [ ] **Step 5: 创建 `frontend/src/components/session/InvestigationPanel.tsx`**

```tsx
import { ScrollArea } from "@/components/ui/scroll-area";
import { DeepenButton } from "@/components/session/DeepenButton";
import { ScopeDetectionTransparency } from "@/components/session/ScopeDetectionTransparency";
import { SufficiencyJudgementTransparency } from "@/components/session/SufficiencyJudgementTransparency";
import { ToolCallStream } from "@/components/session/ToolCallStream";
import { useStreamSession } from "@/hooks/use-session-stream";
import { useSessionStream } from "@/stores/session-stream-store";

interface Props {
  sessionId: string;
}

export function InvestigationPanel({ sessionId }: Props): JSX.Element {
  const stage = useSessionStream((s) => s.stage);
  const scope = useSessionStream((s) => s.scope);
  const sufficiency = useSessionStream((s) => s.sufficiency);
  const { send } = useStreamSession(sessionId);

  return (
    <aside className="flex h-full w-96 shrink-0 flex-col border-l">
      <div className="border-b p-3 text-xs font-semibold uppercase text-muted-foreground">
        调查进度
      </div>
      <ScrollArea className="flex-1">
        <div className="flex flex-col gap-3 p-3">
          {stage ? (
            <div className="rounded border bg-card p-3 text-xs">
              <div className="font-semibold">{stage.name}</div>
              <div className="text-muted-foreground">
                状态：{stage.status} {stage.message ? `· ${stage.message}` : ""}
              </div>
            </div>
          ) : null}
          {scope ? (
            <ScopeDetectionTransparency
              event={scope}
              onFeatureChange={(fid) =>
                void send({
                  prompt: "（用户改正特性，重新调查）",
                  attachment_ids: [],
                  feature_id_override: fid,
                })
              }
            />
          ) : null}
          {sufficiency ? <SufficiencyJudgementTransparency event={sufficiency} /> : null}
          <ToolCallStream />
          <div className="mt-2">
            <DeepenButton
              onClick={() =>
                void send({
                  prompt: "（用户要求再深查代码层）",
                  attachment_ids: [],
                  feature_id_override: null,
                })
              }
            />
          </div>
        </div>
      </ScrollArea>
    </aside>
  );
}
```

- [ ] **Step 6: 写测试 `frontend/tests/ScopeDetectionTransparency.test.tsx`**

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ScopeDetectionTransparency } from "@/components/session/ScopeDetectionTransparency";
import type { ScopeDetectionEvent } from "@/types/sse";

const sampleEvent: ScopeDetectionEvent = {
  type: "scope_detection",
  selected_feature_id: "feat_order",
  selected_feature_name: "订单",
  confidence: "high",
  reason: "日志中出现 OrderService 符号",
  candidates: [
    { feature_id: "feat_order", feature_name: "订单", score: 0.92 },
    { feature_id: "feat_payment", feature_name: "支付", score: 0.41 },
  ],
};

describe("ScopeDetectionTransparency", () => {
  it("renders selected feature, confidence, and reason", () => {
    render(<ScopeDetectionTransparency event={sampleEvent} onFeatureChange={() => {}} />);
    expect(screen.getByText("订单")).toBeInTheDocument();
    expect(screen.getByText(/信心 高/)).toBeInTheDocument();
    expect(screen.getByText(/OrderService/)).toBeInTheDocument();
  });

  it("calls onFeatureChange when user picks a different candidate", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ScopeDetectionTransparency event={sampleEvent} onFeatureChange={onChange} />);
    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByText(/支付/));
    expect(onChange).toHaveBeenCalledWith("feat_payment");
  });
});
```

- [ ] **Step 7: 跑测试**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm test tests/ScopeDetectionTransparency.test.tsx
```
Expected: 2 PASS。

- [ ] **Step 8: 提交**

```bash
cd /home/hzh/workspace/CodeAsk
git add frontend/src/components/session/ScopeDetectionTransparency.tsx frontend/src/components/session/SufficiencyJudgementTransparency.tsx frontend/src/components/session/ToolCallStream.tsx frontend/src/components/session/DeepenButton.tsx frontend/src/components/session/InvestigationPanel.tsx frontend/tests/ScopeDetectionTransparency.test.tsx
git commit -m "feat(frontend): InvestigationPanel with A2/A3 transparency + DeepenButton"
```

---

## Task 14: 答案展示 — AnswerCard + EvidenceList + EvidenceItem + FeedbackButtons + 单测

> 2026-05-02 handoff note：本 task 中关于 `FeedbackButtons` 写入 `/api/feedback` 的代码和测试是早期计划片段。当前 frontend-workbench handoff 不把反馈持久化作为验收项；反馈 API、frontend events 与 Dashboard 数据面由 `metrics-eval` 接续。

**Files:**
- Create: `frontend/src/components/session/EvidenceItem.tsx`
- Create: `frontend/src/components/session/EvidenceList.tsx`
- Create: `frontend/src/components/session/FeedbackButtons.tsx`
- Create: `frontend/src/components/session/AnswerCard.tsx`
- Create: `frontend/tests/AnswerCard.test.tsx`
- Create: `frontend/tests/FeedbackButtons.test.tsx`

落地 §5：结论醒目（大字号 + confidence badge）+ 建议操作（带"决策权在你"提示）+ 不确定点 + 证据折叠 + 反馈按钮。"决策权在你"是 PRD §6.1 不假装自信的 UI 落地。

- [ ] **Step 1: 创建 `frontend/src/components/session/EvidenceItem.tsx`**

```tsx
import { Badge } from "@/components/ui/badge";
import { confidenceLabel } from "@/lib/format";
import type { EvidenceItem as EvidenceModel } from "@/types/api";

interface Props {
  evidence: EvidenceModel;
}

export function EvidenceItem({ evidence }: Props): JSX.Element {
  return (
    <li className="rounded border p-2 text-xs">
      <div className="mb-1 flex items-center gap-1.5">
        <Badge variant="outline" className="text-[10px]">
          {evidence.type}
        </Badge>
        <Badge variant="outline" className="text-[10px]">
          {evidence.relevance}
        </Badge>
        <span className="text-muted-foreground">置信度 {confidenceLabel(evidence.confidence)}</span>
      </div>
      <p className="text-foreground">{evidence.summary}</p>
      <pre className="mt-1 overflow-x-auto rounded bg-muted/40 p-1.5 font-mono text-[10px]">
        {JSON.stringify(evidence.source, null, 2)}
      </pre>
      {isProvisionalCode(evidence) ? (
        <p className="mt-1 text-[10px] text-amber-600">⚠ 来自默认分支预查，未确认故障版本</p>
      ) : null}
    </li>
  );
}

function isProvisionalCode(e: EvidenceModel): boolean {
  if (e.type !== "code") return false;
  const sha = (e.source as { commit_sha?: string }).commit_sha;
  return !sha || sha === "HEAD" || sha.startsWith("default:");
}
```

- [ ] **Step 2: 创建 `frontend/src/components/session/EvidenceList.tsx`**

```tsx
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronDown } from "lucide-react";

import { EvidenceItem } from "@/components/session/EvidenceItem";
import type { EvidenceItem as EvidenceModel } from "@/types/api";

interface Props {
  evidence: EvidenceModel[];
}

export function EvidenceList({ evidence }: Props): JSX.Element | null {
  if (evidence.length === 0) return null;
  return (
    <Collapsible>
      <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ChevronDown className="h-3 w-3 transition-transform data-[state=open]:rotate-180" />
        证据 ({evidence.length})
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ul className="mt-2 flex flex-col gap-1.5">
          {evidence.map((e) => (
            <EvidenceItem key={e.id} evidence={e} />
          ))}
        </ul>
      </CollapsibleContent>
    </Collapsible>
  );
}
```

- [ ] **Step 3: 创建 `frontend/src/components/session/FeedbackButtons.tsx`**

```tsx
import { Check, CircleSlash, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useSendFeedback } from "@/hooks/use-feedback";
import type { FeedbackVerdict } from "@/types/api";

interface Props {
  sessionId: string;
  messageId: string;
}

export function FeedbackButtons({ sessionId, messageId }: Props): JSX.Element {
  const [active, setActive] = useState<FeedbackVerdict | null>(null);
  const [note, setNote] = useState("");
  const send = useSendFeedback();

  const submit = (verdict: FeedbackVerdict): void => {
    setActive(verdict);
    void send.mutate({ session_id: sessionId, message_id: messageId, verdict, note: note || null });
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-muted-foreground">这个回答：</span>
        <Button
          size="sm"
          variant={active === "solved" ? "default" : "outline"}
          onClick={() => submit("solved")}
          aria-label="已解决"
        >
          <Check className="mr-1 h-3.5 w-3.5" /> 已解决
        </Button>
        <Button
          size="sm"
          variant={active === "partial" ? "default" : "outline"}
          onClick={() => submit("partial")}
          aria-label="部分解决"
        >
          <CircleSlash className="mr-1 h-3.5 w-3.5" /> 部分解决
        </Button>
        <Button
          size="sm"
          variant={active === "wrong" ? "default" : "outline"}
          onClick={() => submit("wrong")}
          aria-label="没解决"
        >
          <X className="mr-1 h-3.5 w-3.5" /> 没解决
        </Button>
      </div>
      <Textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="可选备注：漏了什么 / 哪一步错了"
        className="min-h-[48px] text-xs"
      />
    </div>
  );
}
```

- [ ] **Step 4: 创建 `frontend/src/components/session/AnswerCard.tsx`**

```tsx
import { AlertTriangle, Lightbulb } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { EvidenceList } from "@/components/session/EvidenceList";
import { FeedbackButtons } from "@/components/session/FeedbackButtons";
import { confidenceColor, confidenceLabel } from "@/lib/format";
import type { AnswerStructured, EvidenceItem } from "@/types/api";

interface Props {
  sessionId: string;
  messageId: string;
  answer: AnswerStructured;
  evidence: EvidenceItem[];
}

export function AnswerCard({ sessionId, messageId, answer, evidence }: Props): JSX.Element {
  return (
    <Card className="p-5">
      <header className="mb-3 flex items-start justify-between gap-3">
        <h2 className="text-xl font-semibold leading-tight">{answer.claim}</h2>
        <Badge className={confidenceColor(answer.confidence)} aria-label={`置信度 ${answer.confidence}`}>
          置信度 {confidenceLabel(answer.confidence)}
        </Badge>
      </header>

      {answer.recommended_actions.length > 0 ? (
        <section className="mb-3">
          <div className="mb-1 flex items-center gap-1 text-sm font-medium">
            <Lightbulb className="h-4 w-4" />
            建议操作
          </div>
          <ul className="ml-5 list-disc text-sm">
            {answer.recommended_actions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-muted-foreground">※ 这是建议，决策权在你。</p>
        </section>
      ) : null}

      {answer.uncertainties.length > 0 ? (
        <section className="mb-3">
          <div className="mb-1 flex items-center gap-1 text-sm font-medium">
            <AlertTriangle className="h-4 w-4" />
            不确定点
          </div>
          <ul className="ml-5 list-disc text-sm">
            {answer.uncertainties.map((u, i) => (
              <li key={i}>{u}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <Separator className="my-3" />
      <FeedbackButtons sessionId={sessionId} messageId={messageId} />
      <Separator className="my-3" />
      <EvidenceList evidence={evidence} />
    </Card>
  );
}
```

- [ ] **Step 5: 写 `frontend/tests/AnswerCard.test.tsx`**

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnswerCard } from "@/components/session/AnswerCard";
import type { AnswerStructured, EvidenceItem } from "@/types/api";

function wrap(node: JSX.Element): JSX.Element {
  const qc = new QueryClient();
  return <QueryClientProvider client={qc}>{node}</QueryClientProvider>;
}

const answer: AnswerStructured = {
  claim: "调用 timeout 是 hardcode 1s",
  confidence: "medium",
  recommended_actions: ["把 timeout 临时调大到 3s", "联系上游团队"],
  uncertainties: ["未拿到上游服务日志"],
  evidence_ids: ["ev_1"],
};

const evidence: EvidenceItem[] = [
  {
    id: "ev_1",
    type: "code",
    summary: "client.call(timeout=1)",
    relevance: "supports",
    confidence: "high",
    source: { repo_id: "r1", path: "p.py", commit_sha: "abc", line_start: 10, line_end: 11 },
    captured_at: "2026-04-29T00:00:00Z",
  },
];

describe("AnswerCard", () => {
  it("renders claim, confidence, actions, uncertainties, decision-power notice", () => {
    render(wrap(<AnswerCard sessionId="s1" messageId="m1" answer={answer} evidence={evidence} />));
    expect(screen.getByText(/timeout 是 hardcode/)).toBeInTheDocument();
    expect(screen.getByText(/置信度 中/)).toBeInTheDocument();
    expect(screen.getByText(/把 timeout 临时调大/)).toBeInTheDocument();
    expect(screen.getByText(/未拿到上游服务日志/)).toBeInTheDocument();
    expect(screen.getByText(/决策权在你/)).toBeInTheDocument();
  });

  it("evidence list is collapsed by default and shows count", () => {
    render(wrap(<AnswerCard sessionId="s1" messageId="m1" answer={answer} evidence={evidence} />));
    expect(screen.getByText(/证据 \(1\)/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: 写 `frontend/tests/FeedbackButtons.test.tsx`**

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FeedbackButtons } from "@/components/session/FeedbackButtons";

describe("FeedbackButtons", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("posts feedback with verdict=solved", async () => {
    const qc = new QueryClient();
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={qc}>
        <FeedbackButtons sessionId="s1" messageId="m1" />
      </QueryClientProvider>,
    );
    await user.click(screen.getByLabelText("已解决"));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/feedback");
    expect(init.method).toBe("POST");
    const body = JSON.parse(init.body as string);
    expect(body.verdict).toBe("solved");
    expect(body.session_id).toBe("s1");
    expect(body.message_id).toBe("m1");
  });
});
```

- [ ] **Step 7: 跑测试**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm test tests/AnswerCard.test.tsx tests/FeedbackButtons.test.tsx
```
Expected: 3 PASS。

- [ ] **Step 8: 提交**

```bash
cd /home/hzh/workspace/CodeAsk
git add frontend/src/components/session/EvidenceItem.tsx frontend/src/components/session/EvidenceList.tsx frontend/src/components/session/FeedbackButtons.tsx frontend/src/components/session/AnswerCard.tsx frontend/tests/AnswerCard.test.tsx frontend/tests/FeedbackButtons.test.tsx
git commit -m "feat(frontend): AnswerCard + EvidenceList + FeedbackButtons (with tests)"
```

---

## Task 15: 把会话工作台拼起来 — sessions/$id 接入三栏

**Files:**
- Modify: `frontend/src/routes/sessions.$id.tsx`

落地 §3：左 SessionList（已在 sessions.tsx layout）+ 中 message list + 输入区 + 答案 + 右 InvestigationPanel。

- [ ] **Step 1: 重写 `frontend/src/routes/sessions.$id.tsx`**

```tsx
import { createFileRoute } from "@tanstack/react-router";

import { AnswerCard } from "@/components/session/AnswerCard";
import { InvestigationPanel } from "@/components/session/InvestigationPanel";
import { SessionInputArea } from "@/components/session/SessionInputArea";
import { SessionMessageList } from "@/components/session/SessionMessageList";
import { useSessionStream } from "@/stores/session-stream-store";

export const Route = createFileRoute("/sessions/$id")({
  component: SessionPage,
});

function SessionPage(): JSX.Element {
  const { id } = Route.useParams();
  const finalAnswer = useSessionStream((s) => (s.sessionId === id ? s.finalAnswer : null));
  const finalMessageId = useSessionStream((s) => (s.sessionId === id ? s.finalMessageId : null));
  const evidence = useSessionStream((s) => (s.sessionId === id ? s.evidence : []));

  return (
    <div className="flex h-full">
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="flex-1 overflow-hidden">
          <SessionMessageList sessionId={id} />
        </div>
        {finalAnswer && finalMessageId ? (
          <div className="px-6 pb-3">
            <AnswerCard
              sessionId={id}
              messageId={finalMessageId}
              answer={finalAnswer}
              evidence={evidence}
            />
          </div>
        ) : null}
        <SessionInputArea sessionId={id} />
      </div>
      <InvestigationPanel sessionId={id} />
    </div>
  );
}
```

- [ ] **Step 2: typecheck + lint + dev smoke**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm typecheck && pnpm lint
pnpm dev &
DEV_PID=$!
sleep 4
curl -fs http://127.0.0.1:5173/sessions > /dev/null
kill $DEV_PID
```

- [ ] **Step 3: 提交**

```bash
cd /home/hzh/workspace/CodeAsk
git add frontend/src/routes/sessions.$id.tsx
git commit -m "feat(frontend): wire SessionPage three-column layout"
```

---

## Task 16: Maintainer Dashboard — PendingItemsList + FlywheelMetrics + WatchedFeaturesPanel

**Files:**
- Create: `frontend/src/components/dashboard/PendingItemsList.tsx`
- Create: `frontend/src/components/dashboard/FlywheelMetrics.tsx`
- Create: `frontend/src/components/dashboard/WatchedFeaturesPanel.tsx`
- Create: `frontend/src/components/dashboard/MaintainerDashboard.tsx`
- Modify: `frontend/src/routes/dashboard.tsx`

落地 `frontend-workbench.md` §9：待我处理（草稿 / 部分解决 / 答错）+ 飞轮信号（30 天 deflection / 错误率 / 验证报告 / 命中数 / 文档变更）+ 关注的特性。Recharts 渲染 sparkline。

- [ ] **Step 1: 创建 `frontend/src/components/dashboard/PendingItemsList.tsx`**

```tsx
import { Link } from "@tanstack/react-router";

import { Card } from "@/components/ui/card";
import { useDashboardPending } from "@/hooks/use-dashboard";
import { formatRelativeTime } from "@/lib/format";

const KIND_LABEL: Record<string, string> = {
  draft_report: "报告草稿",
  partial_session: "部分解决会话",
  wrong_session: "答错会话",
};

export function PendingItemsList(): JSX.Element {
  const q = useDashboardPending();
  return (
    <Card className="p-4">
      <h3 className="mb-3 text-sm font-semibold">待我处理</h3>
      {q.isPending ? (
        <p className="text-xs text-muted-foreground">加载中…</p>
      ) : q.data && q.data.length > 0 ? (
        <ul className="flex flex-col gap-1.5">
          {q.data.map((item) => (
            <li key={`${item.kind}:${item.ref_id}`} className="flex items-center gap-2 text-sm">
              <span className="rounded bg-muted px-1.5 py-0.5 text-[10px]">
                {KIND_LABEL[item.kind] ?? item.kind}
              </span>
              <Link
                to={item.kind === "draft_report" ? "/wiki/reports/$id" : "/sessions/$id"}
                params={{ id: item.ref_id }}
                className="line-clamp-1 hover:underline"
              >
                {item.title}
              </Link>
              <span className="ml-auto text-xs text-muted-foreground">
                {formatRelativeTime(item.created_at)}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">没有待处理项 ✓</p>
      )}
    </Card>
  );
}
```

- [ ] **Step 2: 创建 `frontend/src/components/dashboard/FlywheelMetrics.tsx`**

```tsx
import { Card } from "@/components/ui/card";
import { useDashboardMetrics } from "@/hooks/use-dashboard";

function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

function delta(pp: number): string {
  const sign = pp > 0 ? "↑" : pp < 0 ? "↓" : "·";
  return `${sign} ${Math.abs(pp).toFixed(1)}pp`;
}

export function FlywheelMetrics(): JSX.Element {
  const q = useDashboardMetrics(30);
  return (
    <Card className="p-4">
      <h3 className="mb-3 text-sm font-semibold">飞轮信号（最近 30 天）</h3>
      {q.data ? (
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <Metric label="deflection rate" value={pct(q.data.deflection_rate)} sub={delta(q.data.deflection_delta_pp)} />
          <Metric label="错误反馈率" value={pct(q.data.wrong_feedback_rate)} />
          <Metric label="新增已验证报告" value={String(q.data.reports_verified_count)} />
          <Metric label="已验证报告被命中" value={String(q.data.reports_hits_count)} />
          <Metric label="文档新增/更新" value={String(q.data.documents_changed_count)} />
        </dl>
      ) : (
        <p className="text-xs text-muted-foreground">加载中…</p>
      )}
    </Card>
  );
}

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }): JSX.Element {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-lg font-semibold tabular-nums">
        {value}
        {sub ? <span className="ml-2 text-xs font-normal text-muted-foreground">{sub}</span> : null}
      </dd>
    </div>
  );
}
```

- [ ] **Step 3: 创建 `frontend/src/components/dashboard/WatchedFeaturesPanel.tsx`**

```tsx
import { Card } from "@/components/ui/card";
import { useFeatures } from "@/hooks/use-features";

export function WatchedFeaturesPanel(): JSX.Element {
  const q = useFeatures();
  return (
    <Card className="p-4">
      <h3 className="mb-3 text-sm font-semibold">关注的特性</h3>
      {q.data && q.data.length > 0 ? (
        <ul className="flex flex-wrap gap-1.5">
          {q.data.map((f) => (
            <li
              key={f.id}
              className="rounded border bg-muted/30 px-2 py-1 text-xs hover:bg-muted"
            >
              {f.name}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">尚无特性，去 Wiki 创建一个。</p>
      )}
    </Card>
  );
}
```

- [ ] **Step 4: 创建 `frontend/src/components/dashboard/MaintainerDashboard.tsx`**

```tsx
import { FlywheelMetrics } from "@/components/dashboard/FlywheelMetrics";
import { PendingItemsList } from "@/components/dashboard/PendingItemsList";
import { WatchedFeaturesPanel } from "@/components/dashboard/WatchedFeaturesPanel";

export function MaintainerDashboard(): JSX.Element {
  return (
    <div className="grid h-full grid-cols-1 gap-4 overflow-auto p-6 lg:grid-cols-2">
      <PendingItemsList />
      <FlywheelMetrics />
      <div className="lg:col-span-2">
        <WatchedFeaturesPanel />
      </div>
    </div>
  );
}
```

- [ ] **Step 5: 重写 `frontend/src/routes/dashboard.tsx`**

```tsx
import { createFileRoute } from "@tanstack/react-router";

import { MaintainerDashboard } from "@/components/dashboard/MaintainerDashboard";

export const Route = createFileRoute("/dashboard")({
  component: MaintainerDashboard,
});
```

- [ ] **Step 6: typecheck**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm typecheck
```

- [ ] **Step 7: 提交**

```bash
cd /home/hzh/workspace/CodeAsk
git add frontend/src/components/dashboard/ frontend/src/routes/dashboard.tsx
git commit -m "feat(frontend): Maintainer dashboard (pending + metrics + watched features)"
```

---

## Task 17: Wiki — DocumentList / Upload / Search / ReportList / ReportDetail / ReportVerifyButton

**Files:**
- Create: `frontend/src/components/wiki/DocumentList.tsx`
- Create: `frontend/src/components/wiki/DocumentUpload.tsx`
- Create: `frontend/src/components/wiki/DocumentSearch.tsx`
- Create: `frontend/src/components/wiki/ReportList.tsx`
- Create: `frontend/src/components/wiki/ReportDetail.tsx`
- Create: `frontend/src/components/wiki/ReportVerifyButton.tsx`
- Modify: `frontend/src/routes/wiki.tsx`
- Modify: `frontend/src/routes/wiki.documents.$id.tsx`
- Modify: `frontend/src/routes/wiki.reports.$id.tsx`

落地 `evidence-report.md` §7.4：报告详情页显著展示 verified_by + verified_at + 撤销验证按钮。文档 list/upload/search 是 wiki 管理基础。

- [ ] **Step 1: 创建 `frontend/src/components/wiki/DocumentSearch.tsx`**

```tsx
import { Search } from "lucide-react";
import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { Input } from "@/components/ui/input";
import { useDocumentSearch } from "@/hooks/use-documents";

export function DocumentSearch(): JSX.Element {
  const [q, setQ] = useState("");
  const r = useDocumentSearch(q);
  return (
    <div>
      <div className="flex items-center gap-2">
        <Search className="h-4 w-4 text-muted-foreground" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜索文档" />
      </div>
      {r.data ? (
        <ul className="mt-3 flex flex-col gap-1">
          {r.data.map((h) => (
            <li key={h.chunk_id} className="rounded border p-2 text-sm">
              <Link
                to="/wiki/documents/$id"
                params={{ id: h.document_id }}
                className="font-medium hover:underline"
              >
                {h.title}
              </Link>
              <div className="text-xs text-muted-foreground">{h.heading_path}</div>
              <p className="mt-1 line-clamp-2 text-xs">{h.snippet}</p>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 2: 创建 `frontend/src/components/wiki/DocumentUpload.tsx`**

```tsx
import { Upload } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { useUploadDocument } from "@/hooks/use-documents";
import { useFeatures } from "@/hooks/use-features";

export function DocumentUpload(): JSX.Element {
  const features = useFeatures();
  const upload = useUploadDocument();
  const [featureId, setFeatureId] = useState<string>("");

  const onPick = (e: React.ChangeEvent<HTMLInputElement>): void => {
    const file = e.target.files?.[0];
    if (!file || !featureId) return;
    const form = new FormData();
    form.append("feature_id", featureId);
    form.append("file", file);
    upload.mutate(form);
  };

  return (
    <div className="flex items-center gap-2">
      <select
        className="rounded border bg-background px-2 py-1 text-sm"
        value={featureId}
        onChange={(e) => setFeatureId(e.target.value)}
      >
        <option value="">选择特性…</option>
        {features.data?.map((f) => (
          <option key={f.id} value={f.id}>
            {f.name}
          </option>
        ))}
      </select>
      <label>
        <input type="file" className="hidden" onChange={onPick} disabled={!featureId} />
        <Button asChild size="sm" variant="outline" disabled={!featureId}>
          <span>
            <Upload className="mr-1 h-4 w-4" />
            上传文档
          </span>
        </Button>
      </label>
      {upload.isPending ? <span className="text-xs">上传中…</span> : null}
    </div>
  );
}
```

- [ ] **Step 3: 创建 `frontend/src/components/wiki/DocumentList.tsx`**

```tsx
import { Link } from "@tanstack/react-router";

import { Card } from "@/components/ui/card";
import { useDocuments } from "@/hooks/use-documents";

export function DocumentList(): JSX.Element {
  const q = useDocuments(null);
  return (
    <Card className="p-3">
      <h3 className="mb-2 text-sm font-semibold">所有文档</h3>
      <ul className="flex flex-col">
        {q.data?.map((d) => (
          <li key={d.id}>
            <Link
              to="/wiki/documents/$id"
              params={{ id: d.id }}
              className="block rounded px-2 py-1.5 text-sm hover:bg-accent"
            >
              <div className="font-medium">{d.title}</div>
              <div className="text-xs text-muted-foreground">{d.path}</div>
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}
```

- [ ] **Step 4: 创建 `frontend/src/components/wiki/ReportList.tsx`**

```tsx
import { Link } from "@tanstack/react-router";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { useReports } from "@/hooks/use-reports";

export function ReportList(): JSX.Element {
  const q = useReports();
  return (
    <Card className="p-3">
      <h3 className="mb-2 text-sm font-semibold">报告</h3>
      <ul className="flex flex-col">
        {q.data?.map((r) => (
          <li key={r.id}>
            <Link
              to="/wiki/reports/$id"
              params={{ id: r.id }}
              className="flex items-center justify-between gap-2 rounded px-2 py-1.5 text-sm hover:bg-accent"
            >
              <span className="line-clamp-1">{r.title}</span>
              <Badge variant={r.metadata.verified ? "default" : "outline"}>
                {r.metadata.status}
              </Badge>
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}
```

- [ ] **Step 5: 创建 `frontend/src/components/wiki/ReportVerifyButton.tsx`**

```tsx
import { CheckCircle2, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useUnverifyReport, useVerifyReport } from "@/hooks/use-reports";
import type { Report } from "@/types/api";

interface Props {
  report: Report;
}

export function ReportVerifyButton({ report }: Props): JSX.Element {
  const verify = useVerifyReport();
  const unverify = useUnverifyReport();
  if (report.metadata.verified) {
    return (
      <Button
        variant="destructive"
        size="sm"
        disabled={unverify.isPending}
        onClick={() => unverify.mutate(report.id)}
      >
        <RotateCcw className="mr-1 h-4 w-4" />
        撤销验证
      </Button>
    );
  }
  return (
    <Button size="sm" disabled={verify.isPending} onClick={() => verify.mutate(report.id)}>
      <CheckCircle2 className="mr-1 h-4 w-4" />
      验证
    </Button>
  );
}
```

- [ ] **Step 6: 创建 `frontend/src/components/wiki/ReportDetail.tsx`**

```tsx
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { ReportVerifyButton } from "@/components/wiki/ReportVerifyButton";
import { Markdown } from "@/lib/markdown";
import { formatRelativeTime } from "@/lib/format";
import { SelfReportBadge } from "@/components/identity/SelfReportBadge";
import { useReport } from "@/hooks/use-reports";

interface Props {
  reportId: string;
}

export function ReportDetail({ reportId }: Props): JSX.Element {
  const q = useReport(reportId);
  if (!q.data) return <div className="p-6 text-sm text-muted-foreground">加载中…</div>;
  const r = q.data;
  return (
    <Card className="m-6 p-6">
      <header className="mb-3 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{r.title}</h1>
          <p className="mt-1 text-xs text-muted-foreground">
            状态：{r.metadata.status}
          </p>
          {r.metadata.verified ? (
            <p className="mt-0.5 text-xs">
              验证人：<span className="font-mono">{r.metadata.verified_by}</span>{" "}
              <SelfReportBadge /> · {r.metadata.verified_at ? formatRelativeTime(r.metadata.verified_at) : ""}
            </p>
          ) : null}
        </div>
        <ReportVerifyButton report={r} />
      </header>
      <Separator className="my-3" />
      <Markdown content={r.body_markdown} />
    </Card>
  );
}
```

- [ ] **Step 7: 重写 `frontend/src/routes/wiki.tsx` + sub-routes**

`frontend/src/routes/wiki.tsx`：

```tsx
import { createFileRoute, Outlet } from "@tanstack/react-router";

import { DocumentList } from "@/components/wiki/DocumentList";
import { DocumentSearch } from "@/components/wiki/DocumentSearch";
import { DocumentUpload } from "@/components/wiki/DocumentUpload";
import { ReportList } from "@/components/wiki/ReportList";

export const Route = createFileRoute("/wiki")({
  component: WikiLayout,
});

function WikiLayout(): JSX.Element {
  return (
    <div className="flex h-full">
      <aside className="flex w-80 shrink-0 flex-col gap-3 border-r p-4">
        <DocumentUpload />
        <DocumentSearch />
        <DocumentList />
        <ReportList />
      </aside>
      <div className="flex-1 overflow-auto">
        <Outlet />
      </div>
    </div>
  );
}
```

`frontend/src/routes/wiki.documents.$id.tsx`：

```tsx
import { createFileRoute } from "@tanstack/react-router";

import { Card } from "@/components/ui/card";
import { Markdown } from "@/lib/markdown";
import { useDocument } from "@/hooks/use-documents";

export const Route = createFileRoute("/wiki/documents/$id")({
  component: DocPage,
});

function DocPage(): JSX.Element {
  const { id } = Route.useParams();
  const q = useDocument(id);
  if (!q.data) return <div className="p-6 text-sm text-muted-foreground">加载中…</div>;
  return (
    <Card className="m-6 p-6">
      <h1 className="text-2xl font-semibold">{q.data.title}</h1>
      <p className="mt-1 text-xs text-muted-foreground">{q.data.path}</p>
      <div className="mt-4">
        <Markdown content={q.data.summary ?? "（暂无 summary）"} />
      </div>
    </Card>
  );
}
```

`frontend/src/routes/wiki.reports.$id.tsx`：

```tsx
import { createFileRoute } from "@tanstack/react-router";

import { ReportDetail } from "@/components/wiki/ReportDetail";

export const Route = createFileRoute("/wiki/reports/$id")({
  component: () => {
    const { id } = Route.useParams();
    return <ReportDetail reportId={id} />;
  },
});
```

- [ ] **Step 8: typecheck + 提交**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm typecheck
cd /home/hzh/workspace/CodeAsk
git add frontend/src/components/wiki/ frontend/src/routes/wiki.tsx frontend/src/routes/wiki.documents.$id.tsx frontend/src/routes/wiki.reports.$id.tsx
git commit -m "feat(frontend): wiki management (docs + reports + verify/unverify)"
```

---

## Task 18: Repos / Skills / LLM 配置 / Features 详情页

> 2026-05-02 handoff note：本 task 中旧的 LLM 配置代码片段已被当前实现覆盖。当前 UI 只展示 OpenAI / Anthropic 协议，支持添加、编辑、switch 启停和删除，不展示 `openai_compatible`、`is_default`、Max Tokens、Temperature、RPM 或剩余额度。

**Files:**
- Create: `frontend/src/components/repos/RepoStatusBadge.tsx`
- Create: `frontend/src/components/repos/RepoRegisterDialog.tsx`
- Create: `frontend/src/components/repos/RepoList.tsx`
- Create: `frontend/src/components/skills/SkillEditor.tsx`
- Create: `frontend/src/components/skills/SkillList.tsx`
- Create: `frontend/src/components/settings/LlmConfigDialog.tsx`
- Create: `frontend/src/components/settings/LlmConfigList.tsx`
- Create: `frontend/src/components/features/FeatureRepoLinker.tsx`
- Create: `frontend/src/components/features/FeatureList.tsx`
- Create: `frontend/src/components/features/FeatureDetail.tsx`
- Modify: `frontend/src/routes/repos.tsx` / `skills.tsx` / `settings.llm.tsx` / `features.$id.tsx`

把剩下的配置类页面一次性补齐。每个组件只暴露最小必要交互 — 列表 + 创建 dialog + 删除。

- [ ] **Step 1: 创建 `frontend/src/components/repos/RepoStatusBadge.tsx`**

```tsx
import { Badge } from "@/components/ui/badge";
import type { Repo } from "@/types/api";

const STATUS_LABEL: Record<Repo["status"], string> = {
  registered: "已登记",
  fetching: "拉取中",
  ready: "就绪",
  error: "失败",
};

export function RepoStatusBadge({ status }: { status: Repo["status"] }): JSX.Element {
  const variant =
    status === "ready" ? "default" : status === "error" ? "destructive" : "secondary";
  return <Badge variant={variant}>{STATUS_LABEL[status]}</Badge>;
}
```

- [ ] **Step 2: 创建 `frontend/src/components/repos/RepoRegisterDialog.tsx`**

```tsx
import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useRegisterRepo } from "@/hooks/use-repos";

const schema = z.object({
  name: z.string().min(1).max(64),
  remote_url: z.string().url(),
  default_branch: z.string().min(1).max(64),
});

type Values = z.infer<typeof schema>;

export function RepoRegisterDialog(): JSX.Element {
  const [open, setOpen] = useState(false);
  const register = useRegisterRepo();
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", remote_url: "", default_branch: "main" },
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">注册仓库</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>注册仓库</DialogTitle>
        </DialogHeader>
        <form
          className="flex flex-col gap-3"
          onSubmit={form.handleSubmit(async (v) => {
            await register.mutateAsync(v);
            setOpen(false);
          })}
        >
          <Input placeholder="仓库名" {...form.register("name")} />
          <Input placeholder="git URL" {...form.register("remote_url")} />
          <Input placeholder="默认分支 (main)" {...form.register("default_branch")} />
          <DialogFooter>
            <Button type="submit" disabled={register.isPending}>注册</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 3: 创建 `frontend/src/components/repos/RepoList.tsx`**

```tsx
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { RepoRegisterDialog } from "@/components/repos/RepoRegisterDialog";
import { RepoStatusBadge } from "@/components/repos/RepoStatusBadge";
import { useDeleteRepo, useRepos } from "@/hooks/use-repos";

export function RepoList(): JSX.Element {
  const q = useRepos();
  const del = useDeleteRepo();
  return (
    <div className="p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">代码仓库</h2>
        <RepoRegisterDialog />
      </div>
      <Card className="divide-y">
        {q.data?.map((r) => (
          <div key={r.id} className="flex items-center gap-3 p-3 text-sm">
            <span className="font-medium">{r.name}</span>
            <span className="font-mono text-xs text-muted-foreground">{r.remote_url}</span>
            <span className="text-xs text-muted-foreground">@{r.default_branch}</span>
            <RepoStatusBadge status={r.status} />
            {r.error_message ? (
              <span className="text-xs text-destructive">{r.error_message}</span>
            ) : null}
            <Button
              variant="ghost"
              size="sm"
              className="ml-auto"
              onClick={() => del.mutate(r.id)}
              aria-label="删除仓库"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        ))}
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: 创建 `frontend/src/components/skills/SkillEditor.tsx`**

```tsx
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useFeatures } from "@/hooks/use-features";
import { useUpsertSkill } from "@/hooks/use-skills";
import type { Skill } from "@/types/api";

interface Props {
  initial: Skill | null;
  onDone: () => void;
}

export function SkillEditor({ initial, onDone }: Props): JSX.Element {
  const features = useFeatures();
  const upsert = useUpsertSkill();
  const [name, setName] = useState("");
  const [scope, setScope] = useState<"global" | "feature">("global");
  const [featureId, setFeatureId] = useState<string>("");
  const [body, setBody] = useState("");

  useEffect(() => {
    setName(initial?.name ?? "");
    setScope(initial?.scope ?? "global");
    setFeatureId(initial?.feature_id ?? "");
    setBody(initial?.body_markdown ?? "");
  }, [initial]);

  return (
    <div className="flex h-full flex-col gap-2">
      <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Skill 名" />
      <div className="flex gap-2 text-sm">
        <label>
          <input
            type="radio"
            checked={scope === "global"}
            onChange={() => setScope("global")}
          />{" "}
          全局
        </label>
        <label>
          <input
            type="radio"
            checked={scope === "feature"}
            onChange={() => setScope("feature")}
          />{" "}
          特性
        </label>
        {scope === "feature" ? (
          <select
            className="rounded border bg-background px-2 py-1 text-sm"
            value={featureId}
            onChange={(e) => setFeatureId(e.target.value)}
          >
            <option value="">选择特性…</option>
            {features.data?.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        ) : null}
      </div>
      <Textarea
        className="flex-1 font-mono"
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="# Skill markdown 提示词"
      />
      <Button
        onClick={async () => {
          await upsert.mutateAsync({
            id: initial?.id ?? null,
            name,
            scope,
            feature_id: scope === "feature" ? featureId || null : null,
            body_markdown: body,
          });
          onDone();
        }}
      >
        保存
      </Button>
    </div>
  );
}
```

- [ ] **Step 5: 创建 `frontend/src/components/skills/SkillList.tsx`**

```tsx
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { SkillEditor } from "@/components/skills/SkillEditor";
import { useDeleteSkill, useSkills } from "@/hooks/use-skills";
import type { Skill } from "@/types/api";

export function SkillList(): JSX.Element {
  const q = useSkills();
  const del = useDeleteSkill();
  const [editing, setEditing] = useState<Skill | null>(null);
  const [creating, setCreating] = useState(false);

  return (
    <div className="grid h-full grid-cols-2 gap-4 p-6">
      <Card className="overflow-auto p-3">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Skills</h2>
          <Button
            size="sm"
            onClick={() => {
              setEditing(null);
              setCreating(true);
            }}
          >
            新建
          </Button>
        </div>
        <ul className="flex flex-col gap-1">
          {q.data?.map((s) => (
            <li
              key={s.id}
              className="flex items-center gap-2 rounded p-1.5 hover:bg-accent"
            >
              <button
                className="flex-1 text-left text-sm"
                onClick={() => {
                  setEditing(s);
                  setCreating(false);
                }}
              >
                {s.name}{" "}
                <span className="text-[10px] text-muted-foreground">[{s.scope}]</span>
              </button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => del.mutate(s.id)}
                aria-label="删除"
              >
                ×
              </Button>
            </li>
          ))}
        </ul>
      </Card>
      <Card className="p-3">
        {creating || editing ? (
          <SkillEditor
            initial={editing}
            onDone={() => {
              setCreating(false);
              setEditing(null);
            }}
          />
        ) : (
          <p className="text-sm text-muted-foreground">选择左侧 skill 编辑，或新建。</p>
        )}
      </Card>
    </div>
  );
}
```

- [ ] **Step 6: 创建 `frontend/src/components/settings/LlmConfigDialog.tsx`**

```tsx
import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useUpsertLlmConfig } from "@/hooks/use-llm-configs";

const schema = z.object({
  name: z.string().min(1),
  protocol: z.enum(["openai", "openai_compatible", "anthropic"]),
  model: z.string().min(1),
  base_url: z.string().optional(),
  api_key: z.string().min(1),
  is_default: z.boolean(),
});

type Values = z.infer<typeof schema>;

export function LlmConfigDialog(): JSX.Element {
  const [open, setOpen] = useState(false);
  const upsert = useUpsertLlmConfig();
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      protocol: "openai",
      model: "gpt-4o-mini",
      base_url: "",
      api_key: "",
      is_default: false,
    },
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">新增 LLM 配置</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>LLM 配置</DialogTitle>
        </DialogHeader>
        <form
          className="flex flex-col gap-2"
          onSubmit={form.handleSubmit(async (v) => {
            await upsert.mutateAsync({
              id: null,
              name: v.name,
              protocol: v.protocol,
              model: v.model,
              base_url: v.base_url ? v.base_url : null,
              api_key: v.api_key,
              is_default: v.is_default,
            });
            setOpen(false);
          })}
        >
          <Input placeholder="名称" {...form.register("name")} />
          <select
            className="rounded border bg-background px-2 py-1 text-sm"
            {...form.register("protocol")}
          >
            <option value="openai">OpenAI</option>
            <option value="openai_compatible">OpenAI compatible</option>
            <option value="anthropic">Anthropic</option>
          </select>
          <Input placeholder="model" {...form.register("model")} />
          <Input placeholder="base_url（可选）" {...form.register("base_url")} />
          <Input type="password" placeholder="API Key" {...form.register("api_key")} />
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" {...form.register("is_default")} /> 设为默认
          </label>
          <DialogFooter>
            <Button type="submit" disabled={upsert.isPending}>保存</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 7: 创建 `frontend/src/components/settings/LlmConfigList.tsx`**

```tsx
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { LlmConfigDialog } from "@/components/settings/LlmConfigDialog";
import { useDeleteLlmConfig, useLlmConfigs } from "@/hooks/use-llm-configs";

export function LlmConfigList(): JSX.Element {
  const q = useLlmConfigs();
  const del = useDeleteLlmConfig();
  return (
    <div className="p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">LLM 供应商</h2>
        <LlmConfigDialog />
      </div>
      <Card className="divide-y">
        {q.data?.map((c) => (
          <div key={c.id} className="flex items-center gap-3 p-3 text-sm">
            <span className="font-medium">{c.name}</span>
            <Badge variant="outline">{c.protocol}</Badge>
            <span className="font-mono text-xs">{c.model}</span>
            {c.base_url ? (
              <span className="text-xs text-muted-foreground">{c.base_url}</span>
            ) : null}
            {c.is_default ? <Badge>默认</Badge> : null}
            <Button
              variant="ghost"
              size="sm"
              className="ml-auto"
              onClick={() => del.mutate(c.id)}
            >
              删除
            </Button>
          </div>
        ))}
      </Card>
      <p className="mt-3 text-xs text-muted-foreground">
        API Key 在后端用 Fernet 加密存储（CODEASK_DATA_KEY）。
      </p>
    </div>
  );
}
```

- [ ] **Step 8: 创建 `frontend/src/components/features/FeatureRepoLinker.tsx`**

```tsx
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { useUpdateFeatureRepos } from "@/hooks/use-features";
import { useRepos } from "@/hooks/use-repos";

interface Props {
  featureId: string;
  initialRepoIds: string[];
}

export function FeatureRepoLinker({ featureId, initialRepoIds }: Props): JSX.Element {
  const repos = useRepos();
  const update = useUpdateFeatureRepos();
  const [picked, setPicked] = useState<Set<string>>(new Set(initialRepoIds));

  useEffect(() => {
    setPicked(new Set(initialRepoIds));
  }, [initialRepoIds]);

  const toggle = (id: string): void => {
    const next = new Set(picked);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setPicked(next);
  };

  return (
    <Card className="p-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold">关联仓库</h3>
        <Button
          size="sm"
          onClick={() => update.mutate({ id: featureId, repo_ids: Array.from(picked) })}
        >
          保存
        </Button>
      </div>
      <ul className="flex flex-col gap-1">
        {repos.data?.map((r) => (
          <li key={r.id} className="flex items-center gap-2 text-sm">
            <Checkbox checked={picked.has(r.id)} onCheckedChange={() => toggle(r.id)} />
            {r.name}
          </li>
        ))}
      </ul>
    </Card>
  );
}
```

- [ ] **Step 9: 创建 `frontend/src/components/features/FeatureList.tsx`**

```tsx
import { Link } from "@tanstack/react-router";

import { Card } from "@/components/ui/card";
import { useFeatures } from "@/hooks/use-features";

export function FeatureList(): JSX.Element {
  const q = useFeatures();
  return (
    <Card className="p-3">
      <h3 className="mb-2 text-sm font-semibold">特性</h3>
      <ul className="flex flex-col">
        {q.data?.map((f) => (
          <li key={f.id}>
            <Link
              to="/features/$id"
              params={{ id: f.id }}
              className="block rounded px-2 py-1.5 text-sm hover:bg-accent"
            >
              {f.name}
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}
```

- [ ] **Step 10: 创建 `frontend/src/components/features/FeatureDetail.tsx`**

```tsx
import { Card } from "@/components/ui/card";
import { FeatureRepoLinker } from "@/components/features/FeatureRepoLinker";
import { useFeature } from "@/hooks/use-features";

interface Props {
  featureId: string;
}

export function FeatureDetail({ featureId }: Props): JSX.Element {
  const q = useFeature(featureId);
  if (!q.data) return <div className="p-6 text-sm text-muted-foreground">加载中…</div>;
  return (
    <div className="grid grid-cols-2 gap-4 p-6">
      <Card className="p-4">
        <h2 className="text-lg font-semibold">{q.data.name}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{q.data.description ?? "（暂无描述）"}</p>
        <p className="mt-2 text-xs">
          owner: <span className="font-mono">{q.data.owner_subject_id ?? "—"}</span>
        </p>
      </Card>
      <FeatureRepoLinker featureId={featureId} initialRepoIds={[]} />
    </div>
  );
}
```

- [ ] **Step 11: 重写 4 个路由文件接入组件**

`frontend/src/routes/repos.tsx`：

```tsx
import { createFileRoute } from "@tanstack/react-router";

import { RepoList } from "@/components/repos/RepoList";

export const Route = createFileRoute("/repos")({ component: RepoList });
```

`frontend/src/routes/skills.tsx`：

```tsx
import { createFileRoute } from "@tanstack/react-router";

import { SkillList } from "@/components/skills/SkillList";

export const Route = createFileRoute("/skills")({ component: SkillList });
```

`frontend/src/routes/settings.llm.tsx`：

```tsx
import { createFileRoute } from "@tanstack/react-router";

import { LlmConfigList } from "@/components/settings/LlmConfigList";

export const Route = createFileRoute("/settings/llm")({ component: LlmConfigList });
```

`frontend/src/routes/features.$id.tsx`：

```tsx
import { createFileRoute } from "@tanstack/react-router";

import { FeatureDetail } from "@/components/features/FeatureDetail";

export const Route = createFileRoute("/features/$id")({
  component: () => {
    const { id } = Route.useParams();
    return <FeatureDetail featureId={id} />;
  },
});
```

- [ ] **Step 12: typecheck + lint**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm typecheck && pnpm lint
```

- [ ] **Step 13: 提交**

```bash
cd /home/hzh/workspace/CodeAsk
git add frontend/src/components/repos/ frontend/src/components/skills/ frontend/src/components/settings/ frontend/src/components/features/ frontend/src/routes/repos.tsx frontend/src/routes/skills.tsx frontend/src/routes/settings.llm.tsx frontend/src/routes/features.$id.tsx
git commit -m "feat(frontend): repos + skills + LLM config + feature detail pages"
```

---

## Task 19: e2e happy path（Playwright + 后端 mock）+ 全量回归

**Files:**
- Create: `frontend/e2e/playwright-helpers.ts`
- Create: `frontend/e2e/happy-path.spec.ts`

Playwright 用 page.route() 拦截 `/api/*` 与 `/api/sessions/:id/messages` 的 SSE，验证：
1. 主页重定向到 /sessions
2. UserMenu 显示 device@ subject_id
3. 会话列表渲染
4. 进入一个会话 → 输入提问 → 看到 stage / scope_detection / sufficiency_judgement / done 事件流处理 → AnswerCard 出现 → 点"已解决" → POST /api/feedback 被 mock 接到

> 2026-05-02 handoff note：当前 e2e 以 `frontend/e2e/happy-path.spec.ts` 的实现为准，不要求覆盖 `/api/feedback`。反馈持久化与 Dashboard 信号在 `metrics-eval` 阶段补齐。

- [ ] **Step 1: 创建 `frontend/e2e/playwright-helpers.ts`**

```ts
import type { Page, Route } from "@playwright/test";

export interface ApiMockState {
  sessions: { id: string; title: string }[];
  feedbackHits: { verdict: string }[];
}

export function attachMocks(page: Page, state: ApiMockState): void {
  page.route("**/api/sessions?**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        state.sessions.map((s) => ({
          id: s.id,
          title: s.title,
          owner_subject_id: "device@deadbeef",
          feature_id: null,
          feature_name: null,
          last_feedback: null,
          created_at: "2026-04-29T00:00:00Z",
          updated_at: "2026-04-29T00:00:00Z",
        })),
      ),
    }),
  );

  page.route("**/api/sessions/sess_1", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "sess_1",
        title: "demo",
        owner_subject_id: "device@deadbeef",
        feature_id: null,
        feature_name: null,
        last_feedback: null,
        created_at: "2026-04-29T00:00:00Z",
        updated_at: "2026-04-29T00:00:00Z",
      }),
    }),
  );

  page.route("**/api/sessions/sess_1/messages", (route: Route) => {
    if (route.request().method() === "GET") {
      void route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
      return;
    }
    const body =
      [
        'event: stage',
        'data: {"name":"knowledge_retrieval","status":"running","message":null}',
        '',
        'event: sufficiency_judgement',
        'data: {"verdict":"sufficient","reason":"docs covered it","next":"evidence_synthesis"}',
        '',
        'event: done',
        'data: {"answer":{"claim":"timeout 是 hardcode 1s","confidence":"medium","recommended_actions":["调到 3s"],"uncertainties":["缺上游日志"],"evidence_ids":[]},"message_id":"msg_1"}',
        '',
        '',
      ].join("\n");
    void route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body,
    });
  });

  page.route("**/api/feedback", async (route) => {
    const data = route.request().postDataJSON() as { verdict: string };
    state.feedbackHits.push({ verdict: data.verdict });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true }),
    });
  });

  // permissive default for other endpoints
  page.route("**/api/**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
}
```

- [ ] **Step 2: 创建 `frontend/e2e/happy-path.spec.ts`**

```ts
import { expect, test } from "@playwright/test";

import { attachMocks, type ApiMockState } from "./playwright-helpers";

test("happy path: ask question, see SSE, click solved", async ({ page }) => {
  const state: ApiMockState = {
    sessions: [{ id: "sess_1", title: "demo" }],
    feedbackHits: [],
  };
  await attachMocks(page, state);

  await page.goto("/");
  await expect(page).toHaveURL(/\/sessions/);
  await expect(page.getByText(/^device@[0-9a-f]{8}$/)).toBeVisible();

  await page.getByText("demo").click();
  await expect(page).toHaveURL(/\/sessions\/sess_1/);

  const textarea = page.getByPlaceholder(/自然语言提问/);
  await textarea.fill("订单偶发失败");
  await page.getByRole("button", { name: /发送/ }).click();

  await expect(page.getByText(/timeout 是 hardcode 1s/)).toBeVisible({ timeout: 5_000 });
  await expect(page.getByText(/置信度 中/)).toBeVisible();
  await expect(page.getByText(/决策权在你/)).toBeVisible();

  await page.getByLabel("已解决").click();
  await expect.poll(() => state.feedbackHits.length).toBeGreaterThan(0);
  expect(state.feedbackHits[0]?.verdict).toBe("solved");
});
```

- [ ] **Step 3: 安装 Playwright 浏览器**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm e2e:install
```

- [ ] **Step 4: 跑 e2e**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm e2e
```
Expected: 1 PASS。

- [ ] **Step 5: 全量回归**

```bash
cd /home/hzh/workspace/CodeAsk/frontend
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```
Expected：format / lint / typecheck / vitest / vite build 全部通过。`frontend/dist/` 生成。

- [ ] **Step 6: 提交**

```bash
cd /home/hzh/workspace/CodeAsk
git add frontend/e2e/
git commit -m "test(frontend): e2e happy path + full regression"
```

- [ ] **Step 7: 打 tag**

```bash
git tag -a frontend-workbench-v0.1.0 -m "Frontend workbench milestone"
```

---

## 验收标志（计划完整通过后应满足）

- [ ] `corepack pnpm --dir frontend dev --host 0.0.0.0 --port 5173` 在 5173 起前端，`/api/*` 走 vite proxy 反代到 backend 8000
- [ ] 浏览器访问 `/` 默认进入会话工作台
- [ ] 顶栏 UserMenu 区分未登录普通用户和管理员；未登录只显示登录入口，管理员登录后显示全局配置能力
- [ ] 一级入口只有 `会话 / 特性 / 设置`；一级与二级侧边栏均可收起 / 展开
- [ ] 会话列表只显示当前 subject 会话，不提供"我的 / 全部"切换；条目右侧三点菜单包含编辑名称、分享占位、置顶、批量操作、删除
- [ ] 会话页支持默认会话发送、SSE 阶段展示、强制代码调查、会话级附件上传 / 重命名 / 说明 / 删除、session id 短标签复制、报告生成确认和特性绑定
- [ ] 特性页支持搜索、新建、删除确认；详情 tab 包含设置、知识库、问题报告、关联仓库、特性 Skill
- [ ] 特性页不创建问题报告；只展示会话生成 / 归档到该特性的报告
- [ ] 设置页普通用户只看到用户配置和个人 LLM 配置；管理员只看到全局 LLM 配置和仓库管理
- [ ] LLM 配置支持 OpenAI / Anthropic 协议、添加、编辑、switch 启停、删除；不展示 Max Tokens / Temperature / RPM / 剩余额度 / 默认配置切换
- [ ] `corepack pnpm --dir frontend test:run` 通过
- [ ] `corepack pnpm --dir frontend build` 通过
- [ ] `corepack pnpm --dir frontend test:e2e` 通过

以下不阻塞当前 frontend-workbench handoff：Maintainer Dashboard、feedback 持久化、完整 LLM Wiki 管理、企业级 AuthProvider、单端口静态挂载。

---

## Self-review 检查表（写完计划后实施前对照）

| 项 | 状态 |
|---|---|
| frontend-workbench.md §3-§9 全部页面 / 组件 / 交互均映射到 task | ✓ Tasks 11-18 |
| `dependencies.md` §3 锁定栈逐项落到 package.json | ✓ Task 1 |
| TipTap 不引入 | ✓ 不在 package.json |
| TanStack Router 选定（二选一时优先 Router 不是 React Router） | ✓ Task 7 |
| Vite proxy `/api/*` → 127.0.0.1:8000 | ✓ Task 2 |
| 自报身份 client_id + nickname → subject_id 注入 X-Subject-Id | ✓ Task 4 / Task 5 |
| SSE 用 microsoft/fetch-event-source（POST + header） | ✓ Task 6 |
| 答案"决策权在你"提示 | ✓ Task 14 |
| "再深查一下"按钮在 sufficient 也可点 | ✓ Task 13 |
| 撤销验证按钮显著展示 verified_by + verified_at | ✓ Task 17 |
| 反馈按钮三档 + 备注 + 写 /api/feedback | Deferred：由 `metrics-eval` 定义并接入 |
| 不做找人帮忙按钮 | ✓ 明确推迟表 |
| 不做强制鉴权 | ✓ 明确推迟表 |
| API 字段 snake_case 一致 | ✓ §"API 字段命名约定" + Task 5 types/api.ts |
| TS strict + ESLint + Prettier 跑通 | ✓ Task 3 / Task 19 step 5 |
| 无 placeholder（"类似" / "appropriate" / "TODO"） | ✓ 全文 grep 通过 |
