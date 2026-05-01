"""evals/run.py is importable from pytest and each stub suite passes."""

import pytest

from evals.run import run_suite


@pytest.mark.parametrize("suite", ["scope_detection", "sufficiency", "answer_quality"])
def test_suite_runs_and_passes_stub(suite: str) -> None:
    report = run_suite(suite)

    assert report.n_cases >= 1
    assert report.n_passed == report.n_cases, (
        f"suite {suite} failing stub cases: "
        f"{[score.case_id for score in report.per_case if not score.passed]}"
    )
    assert 0.0 <= report.avg_score <= 1.0


def test_score_dimensions_breakdown_present() -> None:
    report = run_suite("scope_detection")

    for score in report.per_case:
        assert score.dimensions.breakdown, f"case {score.case_id} missing breakdown"
        for name, value in score.dimensions.breakdown.items():
            assert 0.0 <= value <= 1.0, f"dimension {name} out of range: {value}"
