"""Score answer quality runs."""

from typing import Any

from evals.types import Case, Score, ScoreDimensions


def score(case: Case, agent_output: dict[str, Any]) -> Score:
    """Score evidence, uncertainty disclosure, decision tone, and commit binding."""

    expected = case.expected
    cited = bool(agent_output.get("cited_evidence", False))
    cite_score = 1.0 if cited or not expected.get("must_cite_evidence") else 0.0

    disclosed = agent_output.get("disclosed_uncertainty") or []
    expected_disclose: list[str] = expected.get("must_disclose_uncertainty") or []
    if expected_disclose:
        disclose_score = sum(item in disclosed for item in expected_disclose) / len(
            expected_disclose
        )
    else:
        disclose_score = 1.0

    decision_phrasing = bool(agent_output.get("decision_phrasing"))
    no_decision_score = (
        1.0 if not decision_phrasing or not expected.get("must_not_phrase_as_decision") else 0.0
    )

    bound = bool(agent_output.get("code_evidence_bound_to_commit", False))
    commit_score = 1.0 if bound or not expected.get("must_bind_commit_for_code_evidence") else 0.0

    overall = (cite_score + disclose_score + no_decision_score + commit_score) / 4
    return Score(
        case_id=case.id,
        dimensions=ScoreDimensions(
            overall=overall,
            breakdown={
                "cite": cite_score,
                "disclose": disclose_score,
                "no_decision_phrasing": no_decision_score,
                "commit_binding": commit_score,
            },
        ),
        passed=overall >= 0.75,
    )
