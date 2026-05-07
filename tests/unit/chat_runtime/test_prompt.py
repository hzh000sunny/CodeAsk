from codeask.agent.chat_runtime.prompt import build_system_prompt


def test_prompt_hides_legacy_stage_terms() -> None:
    prompt = build_system_prompt()

    assert "正常聊天优先" in prompt
    assert "ScopeDetection" not in prompt
    assert "SufficiencyJudgement" not in prompt
    assert "code_investigation" not in prompt
