"""Score scope_detection runs."""

from typing import Any

from evals.types import Case, Score, ScoreDimensions


def score(case: Case, agent_output: dict[str, Any]) -> Score:
    """Score selected feature, top-3 candidates, and ask-user behavior."""

    acceptable = set(case.expected.get("acceptable_feature_ids") or [])
    selected = agent_output.get("selected_feature_id")
    ranked = agent_output.get("ranked_feature_ids") or []
    triggered = bool(agent_output.get("triggered_ask_user"))
    expected_trigger = bool(case.expected.get("should_trigger_ask_user"))

    top1 = 1.0 if selected in acceptable else 0.0
    top3 = 1.0 if any(feature_id in acceptable for feature_id in ranked[:3]) else 0.0
    ask_user_match = 1.0 if triggered == expected_trigger else 0.0

    notes: list[str] = []
    if expected_trigger and triggered:
        overall = (top3 + ask_user_match) / 2
        notes.append("ask_user case: scoring top3 and ask_user_match")
    else:
        overall = top1 * 0.5 + top3 * 0.3 + ask_user_match * 0.2

    return Score(
        case_id=case.id,
        dimensions=ScoreDimensions(
            overall=overall,
            breakdown={"top1": top1, "top3": top3, "ask_user_match": ask_user_match},
            notes=notes,
        ),
        passed=overall >= 0.7,
    )
