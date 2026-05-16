"""Application module for trials schemas trials scenario update schema workflows."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.shared.types.shared_types_types_model import TrialStatus
from app.trials.schemas.trials_schemas_trials_scenario_summary_schema import (
    ScenarioStateSummary,
)


class ScenarioVersionPatchResponse(BaseModel):
    """Response for scenario version patch requests."""

    scenarioVersionId: int
    status: str


class ScenarioActiveUpdateRequest(BaseModel):
    """Minimal payload to mutate the active scenario version."""

    storylineMd: str | None = None
    taskPromptsJson: dict | list | None = None
    rubricJson: dict | list | None = None
    focusNotes: str | None = None
    status: str | None = None


class ScenarioActiveUpdateResponse(BaseModel):
    """Response for active scenario version mutation."""

    trialId: int
    scenario: ScenarioStateSummary


class TrialActivateResponse(BaseModel):
    """Response payload for trial activation."""

    trialId: int
    status: TrialStatus
    activatedAt: datetime | None = None


class TrialTerminateCleanupSummary(BaseModel):
    """Cleanup work split into synchronous DB steps vs async GitHub teardown."""

    jobsCancelled: int = 0
    invitesRevoked: int = 0
    failures: list[str] = Field(default_factory=list)
    asyncRepoCodespaceCleanupEnqueued: bool = True
    asyncRepoCodespaceCleanupJobIds: list[str] = Field(default_factory=list)


class TrialTerminateResponse(BaseModel):
    """Response payload for trial termination."""

    trialId: int
    status: TrialStatus
    terminatedAt: datetime | None = None
    cleanupJobIds: list[str] = Field(default_factory=list)
    cleanup: TrialTerminateCleanupSummary | None = None


__all__ = [
    "ScenarioActiveUpdateRequest",
    "ScenarioActiveUpdateResponse",
    "ScenarioVersionPatchResponse",
    "TrialActivateResponse",
    "TrialTerminateCleanupSummary",
    "TrialTerminateResponse",
]
