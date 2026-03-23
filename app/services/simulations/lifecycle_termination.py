from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains import Simulation
from app.repositories.simulations.simulation import SIMULATION_STATUS_TERMINATED
from app.services.simulations.cleanup_jobs import enqueue_simulation_cleanup_job
from app.services.simulations.lifecycle_access import require_owner_for_lifecycle
from app.services.simulations.lifecycle_transition_rules import apply_status_transition


@dataclass(slots=True)
class TerminateSimulationResult:
    simulation: Simulation
    cleanup_job_ids: list[str]


async def terminate_simulation_with_cleanup_impl(
    db: AsyncSession,
    *,
    simulation_id: int,
    actor_user_id: int,
    reason: str | None = None,
    now: datetime | None = None,
    require_owner: Callable[..., object] = require_owner_for_lifecycle,
    apply_transition: Callable[..., bool] = apply_status_transition,
    enqueue_cleanup_job: Callable[..., object] = enqueue_simulation_cleanup_job,
    normalize_status: Callable[..., str | None],
    logger: logging.Logger,
) -> TerminateSimulationResult:
    changed_at = now or datetime.now(UTC)
    normalized_reason = (reason or "").strip() or None
    simulation = await require_owner(
        db, simulation_id, actor_user_id, for_update=True
    )
    from_status = normalize_status(simulation.status)
    try:
        changed = apply_transition(
            simulation,
            target_status=SIMULATION_STATUS_TERMINATED,
            changed_at=changed_at,
        )
    except ApiError:
        logger.warning(
            "Rejected simulation termination simulationId=%s actorUserId=%s from=%s",
            simulation_id,
            actor_user_id,
            from_status,
        )
        raise
    if changed:
        simulation.terminated_by_recruiter_id = actor_user_id
        if normalized_reason is not None:
            simulation.terminated_reason = normalized_reason
    cleanup_job = await enqueue_cleanup_job(
        db,
        simulation=simulation,
        terminated_by_user_id=actor_user_id,
        reason=normalized_reason,
        commit=False,
    )
    await db.commit()
    await db.refresh(simulation)
    cleanup_job_ids = [str(cleanup_job.id)]
    logger.info(
        "Simulation terminated simulationId=%s actorUserId=%s from=%s to=%s cleanupJobIds=%s",
        simulation.id,
        actor_user_id,
        from_status,
        normalize_status(simulation.status),
        cleanup_job_ids,
    )
    return TerminateSimulationResult(simulation=simulation, cleanup_job_ids=cleanup_job_ids)


__all__ = ["TerminateSimulationResult", "terminate_simulation_with_cleanup_impl"]
