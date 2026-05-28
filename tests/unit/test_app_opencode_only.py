from fastapi import FastAPI


def test_app_lifespan_does_not_expose_native_runtime_state(app: FastAPI) -> None:
    assert not hasattr(app.state, "tool_registry")
    assert not hasattr(app.state, "agent_orchestrator")
    assert not hasattr(app.state, "chat_runtime")
    assert hasattr(app.state, "trace_logger")
    assert hasattr(app.state, "worktree_manager")
    assert hasattr(app.state, "opencode_worktree_manager")
