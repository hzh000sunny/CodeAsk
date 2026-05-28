from codeask.agent.native_backend.chat_runtime.runtime import ChatRuntime
from codeask.agent.native_backend.orchestrator import AgentOrchestrator
from codeask.agent.native_backend.stages import StageContext
from codeask.agent.native_backend.tools import ToolRegistry


def test_native_backend_key_modules_importable() -> None:
    assert ChatRuntime is not None
    assert StageContext is not None
    assert ToolRegistry is not None


def test_native_orchestrator_can_be_instantiated_with_fake_dependencies() -> None:
    orchestrator = AgentOrchestrator(
        gateway=object(),  # type: ignore[arg-type]
        tool_registry=ToolRegistry(),
        trace_logger=object(),  # type: ignore[arg-type]
        session_factory=object(),  # type: ignore[arg-type]
    )

    assert isinstance(orchestrator, AgentOrchestrator)
