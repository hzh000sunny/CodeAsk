import json
from pathlib import Path

import pytest

from codeask.agent.native_backend.chat_runtime.prompt import build_system_prompt
from evals.basic_qa.score import score_suite
from evals.types import Case

CASES_PATH = Path("evals/basic_qa/cases/seed_001.jsonl")


def _load_cases() -> list[Case]:
    return [
        Case.model_validate_json(line)
        for line in CASES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_basic_qa_question_bank_contains_expected_coverage() -> None:
    cases = _load_cases()

    assert len(cases) == 32
    assert {case.input["category"] for case in cases} == {
        "编程基础",
        "Linux / Shell",
        "算法与数据结构",
        "计算机网络",
        "数据库",
        "操作系统",
        "AI / 机器学习",
        "系统设计 / 产品",
        "逻辑推理",
        "Agent 自我认知",
        "上下文依赖",
    }
    assert all(
        case.expected["preferred_behavior"] in {"direct_answer", "use_conversation_context"}
        for case in cases
    )
    assert all(case.expected["allowed_tool_trigger_rate"] == pytest.approx(0.1) for case in cases)


def test_basic_qa_suite_allows_small_model_tool_decision_drift() -> None:
    cases = _load_cases()
    outputs = {
        case.id: {"direct_answered": True, "answer_text": "ok", "tool_triggered": False}
        for case in cases
    }
    for case in cases[:3]:
        outputs[case.id]["tool_triggered"] = True
        outputs[case.id]["triggered_tools"] = ["search_code"]

    suite_score = score_suite(cases, outputs)

    assert suite_score.passed is True
    assert suite_score.dimensions.breakdown["tool_trigger_rate"] == pytest.approx(3 / 32)


def test_basic_qa_suite_fails_when_tool_decision_drift_is_too_high() -> None:
    cases = _load_cases()
    outputs = {
        case.id: {"direct_answered": True, "answer_text": "ok", "tool_triggered": False}
        for case in cases
    }
    for case in cases[:4]:
        outputs[case.id]["tool_triggered"] = True
        outputs[case.id]["triggered_tools"] = ["search_code"]

    suite_score = score_suite(cases, outputs)

    assert suite_score.passed is False
    assert suite_score.dimensions.breakdown["tool_trigger_rate"] > 0.1


def test_basic_qa_prompt_guides_model_without_keyword_blocking() -> None:
    prompt = build_system_prompt()

    assert "通用编程" in prompt
    assert "优先直接回答" in prompt
    assert "除非用户明确要求" in prompt
    assert "关键字" not in prompt
    assert "拦截" not in prompt
    assert json.dumps({"prompt": prompt}, ensure_ascii=False)
