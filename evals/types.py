"""Shared eval data types."""

from typing import Any

from pydantic import BaseModel, Field


class Case(BaseModel):
    """One test case, common across eval suites."""

    id: str
    input: dict[str, Any]
    expected: dict[str, Any]
    annotator: str
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None


class ScoreDimensions(BaseModel):
    """Per-case score dimensions."""

    overall: float = Field(..., ge=0.0, le=1.0)
    breakdown: dict[str, float] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class Score(BaseModel):
    """Score for one case."""

    case_id: str
    dimensions: ScoreDimensions
    passed: bool


class SuiteReport(BaseModel):
    """Aggregated score report for one suite."""

    suite: str
    n_cases: int
    n_passed: int
    avg_score: float
    per_case: list[Score]
