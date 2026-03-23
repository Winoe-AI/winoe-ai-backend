from __future__ import annotations

from datetime import datetime

from app.domains.common.base import APIModel
from app.domains.common.progress import ProgressSummary
from app.domains.common.types import CandidateSessionStatus
from app.domains.tasks.schemas_public import TaskPublic


class CurrentTaskWindow(APIModel):
    """Window metadata for the current task day."""

    windowStartAt: datetime | None = None
    windowEndAt: datetime | None = None
    nextOpenAt: datetime | None = None
    isOpen: bool
    now: datetime


class CurrentTaskResponse(APIModel):
    """Schema for the current task assigned to the candidate."""

    candidateSessionId: int
    status: CandidateSessionStatus
    currentDayIndex: int | None
    currentTask: TaskPublic | None
    completedTaskIds: list[int]
    progress: ProgressSummary
    isComplete: bool
    currentWindow: CurrentTaskWindow | None = None
