from pydantic import BaseModel

from codeask.agent.chat_runtime.tool_contracts import (
    ToolErrorType,
    ToolResult,
    ToolSpec,
)


class SearchInput(BaseModel):
    query: str


def test_tool_spec_defaults_are_fail_closed() -> None:
    spec = ToolSpec(
        name="search_wiki",
        description="搜索 Wiki",
        input_model=SearchInput,
    )

    assert spec.read_only is False
    assert spec.concurrency_safe is False
    assert spec.requires_confirmation is True
    assert spec.requires_user_interaction is False


def test_tool_result_error_is_model_actionable() -> None:
    result = ToolResult.error(
        tool="read_code_file",
        error_type=ToolErrorType.NEEDS_CLARIFICATION,
        message="无法确定仓库",
        suggested_user_question="你希望我查看哪个仓库？",
    )

    assert result.ok is False
    assert result.error_type == ToolErrorType.NEEDS_CLARIFICATION
    assert result.suggested_user_question == "你希望我查看哪个仓库？"
