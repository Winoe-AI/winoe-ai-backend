from __future__ import annotations

import logging
from typing import Any

from app.core.db import async_session_maker
from app.jobs.handlers.scenario_generation_parse import _parse_positive_int
from app.jobs.handlers.scenario_generation_paths import (
    _apply_default_scenario_version,
    _apply_requested_scenario_version,
)
from app.jobs.handlers.scenario_generation_runtime import (
    handle_scenario_generation_impl,
)
from app.services.simulations.lifecycle import (
    apply_status_transition,
    normalize_simulation_status,
)
from app.services.simulations.scenario_generation import (
    SCENARIO_GENERATION_JOB_TYPE,
    apply_generated_task_updates,
    generate_scenario_payload,
)

logger = logging.getLogger(__name__)


async def handle_scenario_generation(payload_json: dict[str, Any]) -> dict[str, Any]:
    return await handle_scenario_generation_impl(payload_json, parse_positive_int=_parse_positive_int, async_session_maker=async_session_maker, normalize_simulation_status=normalize_simulation_status, generate_scenario_payload=generate_scenario_payload, apply_generated_task_updates=apply_generated_task_updates, apply_status_transition=apply_status_transition, apply_requested_scenario_version=_apply_requested_scenario_version, apply_default_scenario_version=_apply_default_scenario_version, logger=logger)


__all__ = ["SCENARIO_GENERATION_JOB_TYPE", "handle_scenario_generation"]
