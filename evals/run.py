"""CLI runner for offline eval suites.

Usage:
    uv run python -m evals.run --suite scope_detection
    uv run python -m evals.run --suite sufficiency --limit 5
    uv run python -m evals.run --suite answer_quality --emit-json /tmp/report.json
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any, Protocol

from evals.types import Case, Score, SuiteReport

_HERE = Path(__file__).resolve().parent
_SUITES = ("scope_detection", "sufficiency", "answer_quality")


class ScoreFn(Protocol):
    def __call__(self, case: Case, agent_output: dict[str, Any]) -> Score: ...


def _load_cases(suite: str, limit: int | None) -> list[Case]:
    path = _HERE / suite / "cases" / "seed_001.jsonl"
    cases: list[Case] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#"):
            continue
        cases.append(Case.model_validate_json(cleaned))
        if limit and len(cases) >= limit:
            break
    return cases


def _load_score(suite: str) -> ScoreFn:
    module = importlib.import_module(f"evals.{suite}.score")
    return module.score


def _stub_agent_run(case: Case, suite: str) -> dict[str, Any]:
    """Replay expected labels as deterministic agent output for smoke evals."""

    if suite == "scope_detection":
        return {
            "selected_feature_id": case.expected.get("correct_feature_id"),
            "ranked_feature_ids": case.expected.get("acceptable_feature_ids") or [],
            "confidence": "medium",
            "triggered_ask_user": case.expected.get("should_trigger_ask_user", False),
        }
    if suite == "sufficiency":
        return {
            "decision": case.expected.get("decision"),
            "rationale": " ".join(case.expected.get("rationale_keywords") or []),
            "recommend_code_investigation": case.expected.get(
                "should_recommend_code_investigation",
                False,
            ),
        }
    if suite == "answer_quality":
        return {
            "answer_text": "[stub answer]",
            "cited_evidence": case.expected.get("must_cite_evidence", False),
            "disclosed_uncertainty": case.expected.get("must_disclose_uncertainty") or [],
            "decision_phrasing": False,
            "code_evidence_bound_to_commit": case.expected.get(
                "must_bind_commit_for_code_evidence",
                False,
            ),
        }
    raise ValueError(f"unknown suite: {suite}")


def run_suite(suite: str, limit: int | None = None) -> SuiteReport:
    if suite not in _SUITES:
        raise ValueError(f"unknown suite: {suite}")
    cases = _load_cases(suite, limit)
    score_fn = _load_score(suite)
    per_case = [score_fn(case, _stub_agent_run(case, suite)) for case in cases]
    n_passed = sum(1 for score in per_case if score.passed)
    avg = sum(score.dimensions.overall for score in per_case) / max(len(per_case), 1)
    return SuiteReport(
        suite=suite,
        n_cases=len(per_case),
        n_passed=n_passed,
        avg_score=avg,
        per_case=per_case,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True, choices=_SUITES)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--emit-json", type=str, default=None)
    args = parser.parse_args()

    report = run_suite(args.suite, args.limit)
    out = report.model_dump(mode="json")
    text = json.dumps(out, indent=2, ensure_ascii=False)
    print(text)
    if args.emit_json:
        Path(args.emit_json).write_text(text, encoding="utf-8")
    return 0 if report.n_passed == report.n_cases else 1


if __name__ == "__main__":
    sys.exit(main())
