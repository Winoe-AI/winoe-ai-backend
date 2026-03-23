from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domains.common.types import TaskType

from app.schemas.simulations_ai_models import SimulationAIConfig


class SimulationUpdate(BaseModel):
    """Payload for updating mutable simulation configuration."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    ai: SimulationAIConfig | None = None


class TaskOut(BaseModel):
    """Response model for a created task."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    day_index: int
    type: TaskType
    title: str = Field(..., min_length=1, max_length=200)


__all__ = ["SimulationUpdate", "TaskOut"]
