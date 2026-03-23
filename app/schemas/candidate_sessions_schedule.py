from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.domains.common.base import APIModel
from app.domains.common.types import CandidateSessionStatus
from app.schemas.candidate_sessions_windows import (
    CandidateSimulationSummary,
    CurrentDayWindow,
    DayWindow,
)


class CandidateSessionResolveResponse(APIModel):
    """Schema for resolving a candidate session."""

    candidateSessionId: int
    status: CandidateSessionStatus
    claimedAt: datetime | None
    startedAt: datetime | None
    completedAt: datetime | None
    candidateName: str
    simulation: CandidateSimulationSummary
    aiNoticeText: str
    aiNoticeVersion: str
    evalEnabledByDay: dict[str, bool]
    startAt: datetime | None = None
    windowStartAt: datetime | None = None
    windowEndAt: datetime | None = None
    scheduledStartAt: datetime | None = None
    candidateTimezone: str | None = None
    dayWindows: list[DayWindow] = Field(default_factory=list)
    scheduleLockedAt: datetime | None = None
    currentDayWindow: CurrentDayWindow | None = None


class CandidateSessionScheduleRequest(APIModel):
    """Request payload for scheduling a candidate session."""

    scheduledStartAt: datetime
    candidateTimezone: str = Field(..., min_length=1, max_length=255)


class CandidateSessionScheduleResponse(APIModel):
    """Response payload for scheduling a candidate session."""

    candidateSessionId: int
    scheduledStartAt: datetime
    candidateTimezone: str
    dayWindows: list[DayWindow]
    scheduleLockedAt: datetime
