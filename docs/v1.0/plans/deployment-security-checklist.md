# Deployment Security Checklist

> Companion to `docs/v1.0/plans/deployment.md`. Maps deployment-security.md §5–§7 to auto and manual checks.

## Auto (pytest)

| ID | Checklist line | Test |
|---|---|---|
| AUTO-1 | shell 调用使用参数数组，不使用 `shell=True` | `tests/security/test_grep_no_shell_true.py` |
| AUTO-2 | 默认监听 `127.0.0.1`（代码默认值） | `tests/security/test_grep_default_bind.py` |
| AUTO-3 | 默认监听 `127.0.0.1`（Settings 运行时默认） | `tests/integration/test_security_checklist.py::test_default_settings_bind_localhost` |
| AUTO-4 | LLM API Key 加密存储 | `tests/integration/test_security_checklist.py::test_encrypted_field_is_not_plaintext_in_db` |
| AUTO-5 | 路径读取做根目录校验 | `tests/integration/test_security_checklist.py::test_safe_join_rejects_traversal` |
| AUTO-6 | 上传文件做 MIME 和后缀检查 | `tests/integration/test_security_checklist.py::test_upload_mime_rejects_exe_disguised_as_pdf` |
| AUTO-7 | 匿名身份默认生成 | `tests/integration/test_security_checklist.py::test_anonymous_subject_id_assigned` |

Run:

```bash
uv run pytest tests/security tests/integration/test_security_checklist.py -v
```

## Manual

| ID | Step |
|---|---|
| MANUAL-1 | `./start.sh` 在干净环境里启动，`/api/healthz` 返回 `ok`。 |
| MANUAL-2 | `./start.sh` 缺少 `CODEASK_DATA_KEY` 时退出并打印明确错误。 |
| MANUAL-3 | `frontend/dist/index.html` 存在时，`/` 直接返回 SPA。 |
| MANUAL-4 | `frontend/dist/index.html` 不存在时，backend 仍然启动且 `/api/*` 可用。 |
| MANUAL-5 | `frontend/` 通过 `corepack pnpm dev` 运行时可正常代理 `/api/*`。 |
| MANUAL-6 | 手工检查结构化日志输出为 JSON。 |

## When a checklist line moves from manual to auto

1. 在 `tests/security/` 或 `tests/integration/test_security_checklist.py` 新增测试。
2. 更新上面的 AUTO/MANUAL 表。
3. 同一个 PR 里合入，避免口头约定漂移。
