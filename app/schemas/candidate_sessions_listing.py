from __future__ import annotations

from datetime import datetime

from pydantic import EmailStr

from app.domains.common.base import APIModel
from app.domains.common.types import CandidateSessionStatus


class CandidateSessionListItem(APIModel):
    """Schema for listing candidate sessions."""

    candidateSessionId: int
    inviteEmail: EmailStr
    candidateName: str
    status: CandidateSessionStatus
    startedAt: datetime | None
    completedAt: datetime | None
    hasFitProfile: bool
    inviteEmailStatus: str | None = None
    inviteEmailSentAt: datetime | None = None
    inviteEmailError: str | None = None
