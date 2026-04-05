"""Application module for tasks schemas tasks public schema workflows."""

from __future__ import annotations

from datetime import datetime

from app.shared.types.shared_types_base_model import APIModel


class TaskRecordedSubmissionPublic(APIModel):
    """Recorded submission reference for candidate task hydration."""

    submissionId: int
    submittedAt: datetime
    contentText: str | None = None
    contentJson: dict[str, object] | None = None


class TaskPublic(APIModel):
    """Public-facing task schema for candidates. Keeps only what the candidate needs to see."""

    id: int
    dayIndex: int
    title: str
    type: str
    description: str
    recordedSubmission: TaskRecordedSubmissionPublic | None = None
    cutoffCommitSha: str | None = None
    cutoffAt: datetime | None = None
