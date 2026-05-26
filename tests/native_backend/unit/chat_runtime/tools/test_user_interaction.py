import pytest

from codeask.agent.native_backend.chat_runtime.tool_contracts import ToolContext
from codeask.agent.native_backend.chat_runtime.tools.user_interaction import (
    AskUserRequired,
    register_user_interaction_tools,
)


@pytest.mark.asyncio
async def test_ask_user_raises_pause_signal() -> None:
    registry = _registry_with_user_interaction()
    registered = registry.get("ask_user")
    assert registered is not None
    args = registered.spec.input_model.model_validate(
        {
            "question": "使用哪个分支？",
            "options": [{"label": "默认分支", "value": "default"}],
            "allow_free_text": True,
        }
    )

    with pytest.raises(AskUserRequired) as exc:
        await registered.handler(args, ToolContext(session_id="sess_1", turn_id="turn_1"))

    assert exc.value.question == "使用哪个分支？"


def _registry_with_user_interaction():
    from codeask.agent.native_backend.chat_runtime.tool_registry import ToolRegistry

    registry = ToolRegistry()
    register_user_interaction_tools(registry)
    return registry
