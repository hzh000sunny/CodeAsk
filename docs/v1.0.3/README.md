# CodeAsk v1.0.3

v1.0.3 聚焦登录、用户、特性管理员和权限控制。目标是在保留“未登录也能直接发起会话”的低门槛体验前提下，把特性配置、Wiki 管理、全局配置、用户管理等写操作收敛到明确的权限模型中。

## 文档索引

- [鉴权与访问控制设计草案](./specs/auth-access-control.md)
- [鉴权与访问控制实现计划](./plans/auth-access-control.md)

## 当前状态

- 阶段：后端鉴权、用户、特性管理员、资源权限和审计日志已完成；下一步进入前端登录、用户设置、访客 LLM 和权限 UI。
- 已提交后端阶段：
  - `bcb1670 fix(auth): renew sessions by remaining lifetime`
  - `61307fb feat(auth): add unified login and user APIs`
  - `e5d6abe feat(authz): add feature administrator permissions`
  - `002d56b feat(authz): enforce resource permissions`
  - 本次提交：`feat(audit): record auth and authorization events`
- 最新验证记录：
  - 后端权限与审计组合回归：`116 passed`。
  - ruff 检查、ruff format check、聚焦 pyright 检查均通过。
- 仍需在前端 Task 7/8 完成后，启动真实浏览器执行 v1.0.3 E2E 和人工验收。
