"""Public invite token summary (unauthenticated)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.shared.types.shared_types_base_model import APIModel


class CandidateInvitePublicSummary(APIModel):
    """Minimal invite metadata for the welcome screen."""

    state: Literal["ready"] = "ready"
    role: str
    company: str | None = None
    talentPartnerName: str | None = None


class CandidateSessionClaimRequest(APIModel):
    """Profile fields supplied when a candidate claims an invite."""

    fullName: str = Field(..., min_length=1, max_length=255)
    preferredDisplayName: str | None = Field(default=None, max_length=255)
    candidateTimezone: str = Field(..., min_length=1, max_length=255)


__all__ = ["CandidateInvitePublicSummary", "CandidateSessionClaimRequest"]
