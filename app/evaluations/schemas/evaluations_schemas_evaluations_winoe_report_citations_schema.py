"""Winoe Report citations response schema."""

from __future__ import annotations

from app.shared.types.shared_types_base_model import APIModel


class WinoeReportCitationOut(APIModel):
    """Represent one citation in a Winoe Report."""

    artifact_type: str
    artifact_ref: str
    excerpt: str
    view_url: str | None = None


class WinoeReportCitationsResponse(APIModel):
    """Represent the citations response for one Winoe Report dimension."""

    dimension: str | None = None
    citations: list[WinoeReportCitationOut]


__all__ = [
    "WinoeReportCitationOut",
    "WinoeReportCitationsResponse",
]
