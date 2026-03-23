from __future__ import annotations

from app.repositories.scenario_versions.models import (
    SCENARIO_VERSION_STATUS_READY,
)
from app.repositories.simulations.simulation import (
    SIMULATION_STATUS_ACTIVE_INVITING,
    SIMULATION_STATUS_READY_FOR_REVIEW,
)

SCENARIO_PATCH_ERROR_CODE = "SCENARIO_PATCH_INVALID"
SCENARIO_NOT_EDITABLE_ERROR_CODE = "SCENARIO_NOT_EDITABLE"
ALLOWED_EDITABLE_SIMULATION_STATUSES = frozenset(
    {SIMULATION_STATUS_READY_FOR_REVIEW, SIMULATION_STATUS_ACTIVE_INVITING}
)
ALLOWED_EDITABLE_SCENARIO_STATUSES = frozenset({SCENARIO_VERSION_STATUS_READY})
SCENARIO_PATCH_FIELD_ORDER = (
    "storyline_md",
    "task_prompts_json",
    "rubric_json",
    "focus_notes",
)
SCENARIO_PATCH_DEEP_COPY_FIELDS = frozenset({"task_prompts_json", "rubric_json"})

