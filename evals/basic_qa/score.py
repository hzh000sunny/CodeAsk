"""Score basic model capability questions.

The suite measures whether normal, general-knowledge questions remain model-led
Q&A. It does not hard-block tools in production code: a small number of model
tool decisions is acceptable, but a high trigger rate indicates prompt/runtime
regression.
"""

from typing import Any

from evals.types import Case, Score, ScoreDimensions


def score(case: Case, agent_output: dict[str, Any]) -> Score:
    tool_triggered = bool(agent_output.get("tool_triggered", False))
    direct_answered = bool(agent_output.get("direct_answered", False))
    answer_text = str(agent_output.get("answer_text") or "").strip()
    triggered_tools = list(agent_output.get("triggered_tools") or [])
    not_expected = set(case.expected.get("tools_not_expected") or [])

    direct_score = 1.0 if direct_answered and answer_text else 0.0
    unexpected_tools = [tool for tool in triggered_tools if tool in not_expected]
    tool_score = 0.0 if tool_triggered or unexpected_tools else 1.0
    overall = direct_score * 0.65 + tool_score * 0.35

    notes: list[str] = []
    if tool_triggered:
        notes.append("model triggered tool use for a basic Q&A case")
    if unexpected_tools:
        notes.append(f"unexpected tools: {', '.join(unexpected_tools)}")

    return Score(
        case_id=case.id,
        dimensions=ScoreDimensions(
            overall=overall,
            breakdown={"direct_answer": direct_score, "no_unexpected_tools": tool_score},
            notes=notes,
        ),
        passed=direct_score == 1.0,
    )


def score_suite(cases: list[Case], outputs: dict[str, dict[str, Any]]) -> Score:
    max_rate = max(
        (float(case.expected.get("allowed_tool_trigger_rate", 0.0)) for case in cases),
        default=0.0,
    )
    per_case = [score(case, outputs.get(case.id, {})) for case in cases]
    triggered = [
        case.id
        for case in cases
        if outputs.get(case.id, {}).get("tool_triggered")
        or outputs.get(case.id, {}).get("triggered_tools")
    ]
    direct_failures = [
        item.case_id
        for item in per_case
        if item.dimensions.breakdown.get("direct_answer", 0.0) < 1.0
    ]
    trigger_rate = len(triggered) / max(len(cases), 1)
    passed = not direct_failures and trigger_rate <= max_rate
    notes = [
        f"tool_triggered_cases={len(triggered)}/{len(cases)}",
        f"allowed_tool_trigger_rate={max_rate:.2f}",
    ]
    if triggered:
        notes.append(f"triggered_case_ids={', '.join(triggered)}")
    if direct_failures:
        notes.append(f"direct_answer_failures={', '.join(direct_failures)}")
    return Score(
        case_id="basic_qa_suite",
        dimensions=ScoreDimensions(
            overall=1.0 if passed else 0.0,
            breakdown={
                "tool_trigger_rate": trigger_rate,
                "allowed_tool_trigger_rate": max_rate,
                "direct_answer_pass_rate": (len(cases) - len(direct_failures))
                / max(len(cases), 1),
            },
            notes=notes,
        ),
        passed=passed,
    )
