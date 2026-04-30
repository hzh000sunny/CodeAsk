"""Agent state machine: enum and valid-transition table."""

from enum import StrEnum


class AgentState(StrEnum):
    Initialize = "initialize"
    InputAnalysis = "input_analysis"
    ScopeDetection = "scope_detection"
    KnowledgeRetrieval = "knowledge_retrieval"
    SufficiencyJudgement = "sufficiency_judgement"
    CodeInvestigation = "code_investigation"
    VersionConfirmation = "version_confirmation"
    EvidenceSynthesis = "evidence_synthesis"
    AnswerFinalization = "answer_finalization"
    ReportDrafting = "report_drafting"
    AskUser = "ask_user"
    Terminate = "terminate"


_TRANSITIONS: dict[AgentState, set[AgentState]] = {
    AgentState.Initialize: {AgentState.InputAnalysis},
    AgentState.InputAnalysis: {AgentState.ScopeDetection},
    AgentState.ScopeDetection: {AgentState.KnowledgeRetrieval, AgentState.AskUser},
    AgentState.KnowledgeRetrieval: {AgentState.SufficiencyJudgement},
    AgentState.SufficiencyJudgement: {
        AgentState.AnswerFinalization,
        AgentState.CodeInvestigation,
    },
    AgentState.CodeInvestigation: {
        AgentState.VersionConfirmation,
        AgentState.AnswerFinalization,
        AgentState.AskUser,
    },
    AgentState.VersionConfirmation: {
        AgentState.CodeInvestigation,
        AgentState.AskUser,
        AgentState.AnswerFinalization,
    },
    AgentState.AnswerFinalization: {AgentState.EvidenceSynthesis},
    AgentState.EvidenceSynthesis: {AgentState.ReportDrafting, AgentState.Terminate},
    AgentState.ReportDrafting: {AgentState.Terminate},
    AgentState.AskUser: {
        AgentState.ScopeDetection,
        AgentState.CodeInvestigation,
        AgentState.VersionConfirmation,
        AgentState.Terminate,
    },
    AgentState.Terminate: set(),
}


def is_valid_transition(src: AgentState, dst: AgentState) -> bool:
    return dst in _TRANSITIONS.get(src, set())


def allowed_next(state: AgentState) -> set[AgentState]:
    return _TRANSITIONS.get(state, set()).copy()
