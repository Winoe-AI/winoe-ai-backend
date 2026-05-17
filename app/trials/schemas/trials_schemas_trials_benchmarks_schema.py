"""Application module for trials schemas trials benchmarks schema workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.shared.types.shared_types_base_model import APIModel


class TrialBenchmarksCohortOut(APIModel):
    """Represent cohort-level benchmark stats."""

    n: int
    median: float | None = None
    mean: float | None = None
    range: tuple[float, float] | None = None
    sufficient: bool


class TrialBenchmarksPaginationOut(APIModel):
    """Represent benchmark pagination."""

    page: int
    page_size: int
    total: int
    total_pages: int


class TrialBenchmarkDimensionOut(APIModel):
    """Represent one dimension score for benchmarks."""

    name: str
    score: float


class TrialBenchmarkCandidateOut(APIModel):
    """Represent one benchmark candidate row."""

    id: str
    name: str
    email: str
    trial_id: str
    trial_title: str
    report_id: str | None = None
    winoe_score: float | None = None
    dimensions: list[TrialBenchmarkDimensionOut] = Field(default_factory=list)
    status: Literal[
        "completed",
        "in_progress",
        "report_pending",
        "evaluated",
    ]
    submitted_at: datetime | None = None


class TrialBenchmarksResponse(APIModel):
    """Represent benchmark listing response."""

    cohort: TrialBenchmarksCohortOut
    pagination: TrialBenchmarksPaginationOut
    candidates: list[TrialBenchmarkCandidateOut] = Field(default_factory=list)


class TrialBenchmarkCompareCandidateOut(APIModel):
    """Represent candidate compare row for benchmarks."""

    id: str
    name: str
    email: str
    trial_id: str
    trial_title: str
    report_id: str | None = None
    winoe_score: float | None = None
    dimensions: list[TrialBenchmarkDimensionOut] = Field(default_factory=list)
    status: Literal[
        "completed",
        "in_progress",
        "report_pending",
        "evaluated",
    ]
    submitted_at: datetime | None = None
    score_ring: float | None = None
    radar_dimensions: list[TrialBenchmarkDimensionOut] = Field(default_factory=list)


class TrialBenchmarksCompareResponse(APIModel):
    """Represent side-by-side benchmark compare response."""

    candidates: list[TrialBenchmarkCompareCandidateOut] = Field(default_factory=list)


__all__ = [
    "TrialBenchmarkCandidateOut",
    "TrialBenchmarkCompareCandidateOut",
    "TrialBenchmarkDimensionOut",
    "TrialBenchmarksCohortOut",
    "TrialBenchmarksCompareResponse",
    "TrialBenchmarksPaginationOut",
    "TrialBenchmarksResponse",
]
