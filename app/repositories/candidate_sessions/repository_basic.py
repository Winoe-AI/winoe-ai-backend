from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domains import CandidateSession
from app.domains.simulations.simulation import Simulation
from app.repositories.simulations.simulation import SIMULATION_STATUS_TERMINATED


def _not_terminated_simulation_clause():
    return or_(
        Simulation.status.is_(None),
        Simulation.status != SIMULATION_STATUS_TERMINATED,
    )


async def get_by_id(db: AsyncSession, session_id: int) -> CandidateSession | None:
    res = await db.execute(
        select(CandidateSession)
        .join(Simulation, Simulation.id == CandidateSession.simulation_id)
        .where(
            CandidateSession.id == session_id,
            _not_terminated_simulation_clause(),
        )
        .options(selectinload(CandidateSession.simulation))
    )
    return res.scalar_one_or_none()


async def get_by_id_for_update(
    db: AsyncSession, session_id: int
) -> CandidateSession | None:
    res = await db.execute(
        select(CandidateSession)
        .join(Simulation, Simulation.id == CandidateSession.simulation_id)
        .where(
            CandidateSession.id == session_id,
            _not_terminated_simulation_clause(),
        )
        .options(selectinload(CandidateSession.simulation))
        .with_for_update()
    )
    return res.scalar_one_or_none()


__all__ = ["get_by_id", "get_by_id_for_update"]
