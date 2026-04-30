"""Agent state enum values and transition table."""

from codeask.agent.state import AgentState, allowed_next, is_valid_transition


def test_agent_state_values_are_complete() -> None:
    assert list(AgentState) == [
        AgentState.Initialize,
        AgentState.InputAnalysis,
        AgentState.ScopeDetection,
        AgentState.KnowledgeRetrieval,
        AgentState.SufficiencyJudgement,
        AgentState.CodeInvestigation,
        AgentState.VersionConfirmation,
        AgentState.EvidenceSynthesis,
        AgentState.AnswerFinalization,
        AgentState.ReportDrafting,
        AgentState.AskUser,
        AgentState.Terminate,
    ]


def test_agent_state_stage_values_are_snake_case() -> None:
    assert [state.value for state in AgentState] == [
        "initialize",
        "input_analysis",
        "scope_detection",
        "knowledge_retrieval",
        "sufficiency_judgement",
        "code_investigation",
        "version_confirmation",
        "evidence_synthesis",
        "answer_finalization",
        "report_drafting",
        "ask_user",
        "terminate",
    ]


def test_valid_transitions() -> None:
    assert is_valid_transition(AgentState.Initialize, AgentState.InputAnalysis)
    assert is_valid_transition(AgentState.ScopeDetection, AgentState.KnowledgeRetrieval)
    assert is_valid_transition(AgentState.ScopeDetection, AgentState.AskUser)
    assert is_valid_transition(AgentState.SufficiencyJudgement, AgentState.AnswerFinalization)
    assert is_valid_transition(AgentState.SufficiencyJudgement, AgentState.CodeInvestigation)
    assert is_valid_transition(AgentState.AskUser, AgentState.VersionConfirmation)


def test_invalid_transitions() -> None:
    assert not is_valid_transition(AgentState.Initialize, AgentState.CodeInvestigation)
    assert not is_valid_transition(AgentState.KnowledgeRetrieval, AgentState.CodeInvestigation)
    assert not is_valid_transition(AgentState.Terminate, AgentState.Initialize)


def test_allowed_next_returns_copy() -> None:
    next_states = allowed_next(AgentState.Initialize)
    next_states.clear()
    assert allowed_next(AgentState.Initialize) == {AgentState.InputAnalysis}
