from codeask.sessions.trace_redaction import redact_trace_payload_for_frontend


def test_redacts_agent_session_paths_without_mutating_payload() -> None:
    workspace_file = (
        "/home/hzh/.codeask/agent_sessions/opencode/sess_abc123/workspace/repos/app/src/main.ts"
    )
    payload = {
        "tool_name": "read",
        "arguments_summary": {
            "filePath": workspace_file,
            "other": "/home/hzh/.ssh/id_rsa",
        },
        "summary": f"read {workspace_file}",
        "items": [
            {"path": "/home/hzh/.codeask/agent_sessions/opencode/sess_abc123/workspace/AGENTS.md"}
        ],
    }

    redacted = redact_trace_payload_for_frontend(payload, session_id="sess_abc123")

    assert redacted["arguments_summary"] == {
        "filePath": "workspace/repos/app/src/main.ts",
        "other": "[外部绝对路径已隐藏]",
    }
    assert redacted["summary"] == "read workspace/repos/app/src/main.ts"
    assert redacted["items"] == [{"path": "workspace/AGENTS.md"}]
    assert payload["arguments_summary"]["filePath"].startswith("/home/hzh/")


def test_hides_other_session_paths() -> None:
    payload = {
        "summary": "/home/hzh/.codeask/agent_sessions/opencode/sess_other/workspace/AGENTS.md"
    }

    redacted = redact_trace_payload_for_frontend(payload, session_id="sess_current")

    assert redacted["summary"] == "[外部绝对路径已隐藏]"


def test_redacts_agent_session_paths_under_sessions_parent() -> None:
    payload = {
        "tool_name": "read",
        "arguments_summary": {
            "filePath": (
                "/home/hzh/.codeask/agent_sessions/opencode/sessions/"
                "sess_current/workspace/repos/app/src/main.ts"
            )
        },
        "summary": (
            "Read /home/hzh/.codeask/agent_sessions/opencode/sessions/"
            "sess_current/workspace/repos/app/src/main.ts"
        ),
        "message": (
            "Opened /home/hzh/.codeask/agent_sessions/opencode/sessions/"
            "sess_current/workspace/repos/app/src/main.ts"
        ),
        "path": (
            "/home/hzh/.codeask/agent_sessions/opencode/sessions/"
            "sess_current/workspace/repos/app/src/main.ts"
        ),
    }

    redacted = redact_trace_payload_for_frontend(payload, session_id="sess_current")

    assert redacted["arguments_summary"]["filePath"] == "workspace/repos/app/src/main.ts"
    assert redacted["summary"] == "Read workspace/repos/app/src/main.ts"
    assert redacted["message"] == "Opened workspace/repos/app/src/main.ts"
    assert redacted["path"] == "workspace/repos/app/src/main.ts"


def test_redacts_opencode_result_paths_without_leading_slash() -> None:
    payload = {
        "tool_name": "read",
        "summary": (
            "home/hzh/.codeask/agent_sessions/opencode/sessions/"
            "sess_current/workspace/repos/app/src/main.ts"
        ),
        "message": (
            "Opened home/hzh/.codeask/agent_sessions/opencode/sessions/"
            "sess_current/workspace/repos/app/src/main.ts"
        ),
    }

    redacted = redact_trace_payload_for_frontend(payload, session_id="sess_current")

    assert redacted["summary"] == "workspace/repos/app/src/main.ts"
    assert redacted["message"] == "Opened workspace/repos/app/src/main.ts"
