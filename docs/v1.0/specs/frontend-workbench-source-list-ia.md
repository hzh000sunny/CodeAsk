# Frontend Workbench Source List IA

Status: accepted for the initial `frontend-workbench` implementation slice.

## Global App Shell

- The left global sidebar uses a Source List pattern: light, list-like navigation with subtle active state.
- The global sidebar can collapse to an icon rail and expand back without changing the current page.
- The global collapse affordance is a middle-right boundary control with subtle hover motion, not a header button.
- The only first-level entries are:
  - 会话
  - 特性
  - 设置
- Wiki, analysis policy, repo management, user settings, and global configuration must not appear as separate first-level navigation entries.
- All primary pages use the same AppShell and the same global sidebar.

## 会话

- The page keeps the conversation workspace focused on sessions only.
- The session list starts with a search input and a plus button for creating a session.
- The session list is a secondary sidebar and can collapse to a narrow rail.
- Its collapse affordance stays on the middle-right boundary between the list and conversation panel.
- The list does not label itself as "我的会话" or "全部会话"; sessions are already scoped by the current subject.
- The workspace keeps three page columns when there is room:
  - session list
  - conversation/messages
  - investigation progress
- Upload log belongs in the conversation composer area, not in settings or wiki pages.
- Upload log remains available even when the user has no existing session; the UI creates a default session before uploading.
- Uploaded logs and files are session-scoped data. The right-side investigation panel includes a `会话数据` region that lists only the selected session's attachments.
- Session data rows expose enough metadata to distinguish repeated filenames, and support rename/delete actions.

## 特性

- The feature list starts with a search input and a plus button for creating a feature.
- Selecting a feature opens the detail area on the same page.
- Feature detail uses same-page options/tabs:
  - 设置
  - 知识库
  - 问题报告
  - 关联仓库
  - 特性分析策略
- Upload Wiki belongs in the feature detail knowledge tab.
- Feature analysis policies, reports, and repo linkage are scoped to the selected feature.
- The feature list is a secondary sidebar and can collapse to a narrow rail.
- Its collapse affordance stays on the middle-right boundary between the feature list and detail panel.

## 设置

- Settings contains user settings and global configuration.
- User settings are personal and should remain visible to the current subject.
- Global configuration is an admin-owned area and is hidden from non-admin users in the current implementation.
- The settings index is a secondary sidebar and can collapse to a narrow rail.
- Its collapse affordance stays on the middle-right boundary between the settings index and settings content.
