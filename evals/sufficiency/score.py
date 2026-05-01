"""Score sufficiency judgement runs."""

from typing import Any

from evals.types import Case, Score, ScoreDimensions


def score(case: Case, agent_output: dict[str, Any]) -> Score:
    """Score decision accuracy, fatal false-sufficient leaks, and rationale coverage."""

    expected_decision = case.expected.get("decision")
    expected_keywords: list[str] = case.expected.get("rationale_keywords") or []
    expected_recommend = bool(case.expected.get("should_recommend_code_investigation"))

    actual_decision = agent_output.get("decision")
    rationale = (agent_output.get("rationale") or "").lower()
    actual_recommend = bool(agent_output.get("recommend_code_investigation"))

    decision_match = 1.0 if actual_decision == expected_decision else 0.0
    false_sufficient = (
        1.0 if expected_decision == "insufficient" and actual_decision == "sufficient" else 0.0
    )
    recommend_match = 1.0 if actual_recommend == expected_recommend else 0.0
    if expected_keywords:
        hits = sum(1 for keyword in expected_keywords if keyword.lower() in rationale)
        rationale_coverage = hits / len(expected_keywords)
    else:
        rationale_coverage = 1.0

    overall = (
        decision_match * 0.5
        + (1.0 - false_sufficient) * 0.2
        + recommend_match * 0.15
        + rationale_coverage * 0.15
    )
    notes = []
    if false_sufficient:
        notes.append("FATAL: judged sufficient when expected insufficient")

    return Score(
        case_id=case.id,
        dimensions=ScoreDimensions(
            overall=overall,
            breakdown={
                "decision_match": decision_match,
                "false_sufficient": false_sufficient,
                "recommend_match": recommend_match,
                "rationale_coverage": rationale_coverage,
            },
            notes=notes,
        ),
        passed=overall >= 0.7 and false_sufficient == 0.0,
    )
