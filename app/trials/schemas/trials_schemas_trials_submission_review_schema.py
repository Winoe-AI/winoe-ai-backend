"""Application module for trials schemas trials submission review schema workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.shared.types.shared_types_base_model import APIModel
from app.submissions.schemas.submissions_schemas_submissions_talent_partner_base_schema import (
    TalentPartnerTranscriptOut,
)


class SubmissionReviewTrialOut(APIModel):
    """Represent the trial summary shown in submission review."""

    id: str
    title: str


class SubmissionReviewCandidateOut(APIModel):
    """Represent the candidate summary shown in submission review."""

    id: str
    name: str
    email: str
    avatarUrl: str | None = None
    completedAt: datetime | None = None
    status: str


class SubmissionReviewMarkdownDayOut(APIModel):
    """Represent a markdown day submission."""

    submittedAt: datetime | None = None
    wordCount: int | None = None
    markdown: str | None = None
    contentJson: dict[str, Any] | None = None


class SubmissionReviewCodeCommitOut(APIModel):
    """Represent a code commit entry."""

    sha: str
    message: str
    timestamp: datetime | None = None
    filesChanged: int | None = None
    changedFiles: list[str] = Field(default_factory=list)


class SubmissionReviewCodeFileOut(APIModel):
    """Represent a file tree node."""

    path: str
    name: str
    type: str
    language: str | None = None
    content: str | None = None
    changed: bool = False
    children: list[SubmissionReviewCodeFileOut] = Field(default_factory=list)


class SubmissionReviewCodeDayOut(APIModel):
    """Represent a code day submission."""

    submittedAt: datetime | None = None
    wordCount: int | None = None
    contentJson: dict[str, Any] | None = None
    fileTree: list[SubmissionReviewCodeFileOut] = Field(default_factory=list)
    commits: list[SubmissionReviewCodeCommitOut] = Field(default_factory=list)
    selectedFilePath: str | None = None
    selectedFileContent: str | None = None
    selectedFileLanguage: str | None = None
    selectedFileName: str | None = None


class SubmissionReviewHandoffMaterialOut(APIModel):
    """Represent a supplemental handoff material."""

    recordingId: str
    assetKind: str | None = None
    contentType: str
    bytes: int
    status: str
    createdAt: datetime
    downloadUrl: str | None = None


class SubmissionReviewDemoDayOut(APIModel):
    """Represent the handoff + demo day submission."""

    submittedAt: datetime | None = None
    durationSeconds: int | None = None
    videoUrl: str | None = None
    posterUrl: str | None = None
    transcript: TalentPartnerTranscriptOut | None = None
    supplementalMaterials: list[SubmissionReviewHandoffMaterialOut] = Field(
        default_factory=list
    )
    contentJson: dict[str, Any] | None = None


class SubmissionReviewDaysOut(APIModel):
    """Represent the five trial days."""

    day1: SubmissionReviewMarkdownDayOut | None = None
    day2: SubmissionReviewCodeDayOut | None = None
    day3: SubmissionReviewCodeDayOut | None = None
    day4: SubmissionReviewDemoDayOut | None = None
    day5: SubmissionReviewMarkdownDayOut | None = None


class SubmissionReviewPayloadOut(APIModel):
    """Represent the Talent Partner submission review payload."""

    trial: SubmissionReviewTrialOut
    candidate: SubmissionReviewCandidateOut
    days: SubmissionReviewDaysOut
    artifacts: list[dict[str, Any]] = Field(default_factory=list)


SubmissionReviewCodeFileOut.model_rebuild()


__all__ = [
    "SubmissionReviewCandidateOut",
    "SubmissionReviewCodeCommitOut",
    "SubmissionReviewCodeDayOut",
    "SubmissionReviewCodeFileOut",
    "SubmissionReviewDaysOut",
    "SubmissionReviewDemoDayOut",
    "SubmissionReviewHandoffMaterialOut",
    "SubmissionReviewMarkdownDayOut",
    "SubmissionReviewPayloadOut",
    "SubmissionReviewTrialOut",
]
