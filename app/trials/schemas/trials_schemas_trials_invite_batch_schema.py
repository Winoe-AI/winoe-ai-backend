"""Batch invite schemas for Talent Partner trials."""

from __future__ import annotations

from typing import Literal

from pydantic import EmailStr, Field

from app.shared.types.shared_types_base_model import APIModel


class TrialInviteCandidateRow(APIModel):
    """One invite row in a batch request."""

    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr


class TrialInviteCandidatesRequest(APIModel):
    """Invite multiple candidates to the same Trial."""

    candidates: list[TrialInviteCandidateRow] = Field(
        ...,
        min_length=1,
        max_length=50,
    )


class TrialInviteCandidateResultItem(APIModel):
    """Per-candidate invite outcome (success or captured failure)."""

    candidateSessionId: int | None = None
    name: str
    email: EmailStr
    inviteUrl: str = ""
    status: Literal["sent", "resent", "failed"]
    errorCode: str | None = None
    errorMessage: str | None = None
    workspaceProvisioningStatus: str | None = None
    workspaceProvisioningNotice: str | None = None


class TrialInviteCandidatesResponse(APIModel):
    """Response after batch inviting."""

    invites: list[TrialInviteCandidateResultItem]


__all__ = [
    "TrialInviteCandidateResultItem",
    "TrialInviteCandidateRow",
    "TrialInviteCandidatesRequest",
    "TrialInviteCandidatesResponse",
]
