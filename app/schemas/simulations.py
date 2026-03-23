from __future__ import annotations

from typing import Any

from app.domains.tasks.schemas_public import TaskPublic
from app.schemas.simulations_ai_builders import build_simulation_company_context
from app.schemas.simulations_ai_compat import build_simulation_ai_config_with_resolver
from app.schemas.simulations_ai_models import (
    SimulationAIConfig,
    SimulationCompanyContext,
    SimulationDayWindowOverride,
)
from app.schemas.simulations_ai_values import (
    normalize_eval_enabled_by_day,
    resolve_simulation_ai_fields,
)
from app.schemas.simulations_create import SimulationCreate
from app.schemas.simulations_exports import SIMULATIONS_SCHEMA_EXPORTS
from app.schemas.simulations_limits import (
    MAX_AI_NOTICE_TEXT_CHARS,
    MAX_AI_NOTICE_VERSION_CHARS,
    MAX_SCENARIO_NOTES_CHARS,
    MAX_SCENARIO_RUBRIC_BYTES,
    MAX_SCENARIO_STORYLINE_CHARS,
    MAX_SCENARIO_TASK_PROMPTS_BYTES,
    normalize_role_level,
)
from app.schemas.simulations_response_detail import (
    SimulationDetailResponse,
    SimulationDetailTask,
    SimulationLifecycleRequest,
)
from app.schemas.simulations_response_overview import (
    SimulationCreateResponse,
    SimulationListItem,
)
from app.schemas.simulations_scenario_patch import (
    ScenarioVersionPatchRequest,
    ScenarioVersionPatchTaskPrompt,
)
from app.schemas.simulations_scenario_summary import (
    ScenarioApproveResponse,
    ScenarioRegenerateResponse,
    ScenarioStateSummary,
    ScenarioVersionSummary,
    SimulationDetailScenario,
)
from app.schemas.simulations_scenario_update import (
    ScenarioActiveUpdateRequest,
    ScenarioActiveUpdateResponse,
    ScenarioVersionPatchResponse,
    SimulationActivateResponse,
    SimulationTerminateResponse,
)
from app.schemas.simulations_update import SimulationUpdate, TaskOut


def build_simulation_ai_config(
    *,
    notice_version: str | None,
    notice_text: str | None,
    eval_enabled_by_day: Any,
) -> SimulationAIConfig | None:
    return build_simulation_ai_config_with_resolver(
        notice_version=notice_version,
        notice_text=notice_text,
        eval_enabled_by_day=eval_enabled_by_day,
        resolver=resolve_simulation_ai_fields,
    )


__all__ = SIMULATIONS_SCHEMA_EXPORTS
