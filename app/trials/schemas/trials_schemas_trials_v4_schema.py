"""Schemas for Talent Partner Trial creation API v4."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.trials.schemas.trials_schemas_trials_ai_models_schema import (
    TrialCompanyContext,
)
from app.trials.schemas.trials_schemas_trials_create_schema import TrialCreate
from app.trials.schemas.trials_schemas_trials_limits_schema import (
    _ALLOWED_ROLE_LEVELS,
    MAX_FOCUS_NOTES_CHARS,
    normalize_role_level,
)


class TrialCreateV4Request(BaseModel):
    """Talent Partner Trial creation (v4 from-scratch flow)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    role_title: str = Field(..., min_length=1, max_length=200)
    seniority: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )
    preferred_language_framework: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
    )
    focus_notes: str = Field(
        ...,
        min_length=1,
        max_length=MAX_FOCUS_NOTES_CHARS,
    )
    evaluation_focus_areas: list[str] | None = Field(default=None, max_length=24)

    @field_validator("seniority")
    @classmethod
    def _validate_seniority(cls, value: str) -> str:
        normalized = normalize_role_level(value)
        if normalized not in _ALLOWED_ROLE_LEVELS:
            allowed = ", ".join(sorted(_ALLOWED_ROLE_LEVELS))
            raise ValueError(f"seniority must be one of: {allowed}")
        return normalized

    def to_trial_create(self) -> TrialCreate:
        """Map v4 payload to the internal TrialCreate model."""
        role_title = self.role_title.strip()
        focus = self.focus_notes.strip()
        pref = (
            self.preferred_language_framework.strip()
            if self.preferred_language_framework
            else None
        )
        company_context: TrialCompanyContext | None = None
        if self.evaluation_focus_areas:
            company_context = TrialCompanyContext(
                evaluation_focus_areas=list(self.evaluation_focus_areas),
            )
        return TrialCreate(
            title=role_title,
            role=role_title,
            seniority=self.seniority,
            focus=focus,
            preferred_language_framework=pref,
            company_context=company_context,
        )


class TrialCreateV4Response(BaseModel):
    """Minimal response after Trial drafting is queued."""

    model_config = ConfigDict(extra="forbid")

    trial_id: str
    job_id: str
    status: Literal["generating"] = "generating"


__all__ = ["TrialCreateV4Request", "TrialCreateV4Response"]
