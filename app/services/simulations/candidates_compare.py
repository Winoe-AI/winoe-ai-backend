from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import User
from app.services.simulations.candidates_compare_access import (
    require_simulation_compare_access,
)
from app.services.simulations.candidates_compare_day_completion import (
    load_day_completion as _load_day_completion_impl,
)
from app.services.simulations.candidates_compare_formatting import (
    anonymized_candidate_label as _anonymized_candidate_label,
    display_name as _display_name,
    normalize_recommendation as _normalize_recommendation,
    normalize_score as _normalize_score,
)
from app.services.simulations.candidates_compare_models import (
    SimulationCompareAccessContext,
)
from app.services.simulations.candidates_compare_subqueries import (
    latest_run_subquery as _latest_run_subquery,
)
from app.services.simulations.candidates_compare_summary import (
    list_candidates_compare_summary as _list_candidates_compare_summary_impl,
)
from app.services.simulations.candidates_compare_time import (
    candidate_session_created_at as _candidate_session_created_at,
    default_day_completion as _default_day_completion,
    fit_profile_updated_at as _fit_profile_updated_at,
    max_datetime as _max_datetime,
    normalize_datetime as _normalize_datetime,
)
from app.services.simulations.candidates_compare_status import (
    derive_candidate_compare_status,
    derive_fit_profile_status,
)


async def _load_day_completion(
    db: AsyncSession,
    *,
    simulation_id: int,
    candidate_session_ids: list[int],
):
    return await _load_day_completion_impl(
        db,
        simulation_id=simulation_id,
        candidate_session_ids=candidate_session_ids,
    )


async def list_candidates_compare_summary(
    db: AsyncSession,
    *,
    simulation_id: int,
    user: User,
):
    return await _list_candidates_compare_summary_impl(
        db,
        simulation_id=simulation_id,
        user=user,
        require_access=require_simulation_compare_access,
        load_day_completion_for_sessions=_load_day_completion,
    )


__all__ = [
    "derive_candidate_compare_status",
    "derive_fit_profile_status",
    "list_candidates_compare_summary",
    "require_simulation_compare_access",
]
