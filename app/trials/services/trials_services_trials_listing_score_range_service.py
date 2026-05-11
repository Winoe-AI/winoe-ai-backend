"""Aggregate Winoe score ranges for Talent Partner trial listings."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.candidate_sessions.repositories.candidates_candidate_sessions_repositories_candidates_candidate_sessions_candidate_session_model import (
    CandidateSession,
)
from app.evaluations.repositories.evaluations_repositories_evaluations_core_model import (
    EVALUATION_RUN_STATUS_COMPLETED,
    EvaluationRun,
)


def _format_range(min_score: float, max_score: float) -> str:
    if abs(min_score - max_score) < 1e-9:
        return f"{min_score:.2f}"
    lo, hi = (
        (min_score, max_score) if min_score <= max_score else (max_score, min_score)
    )
    return f"{lo:.2f} - {hi:.2f}"


async def score_range_by_trial_ids(
    db: AsyncSession, trial_ids: list[int]
) -> dict[int, str]:
    """Return min-max overall Winoe scores per trial from completed evaluation runs."""
    if not trial_ids:
        return {}
    stmt = (
        select(
            CandidateSession.trial_id,
            func.min(EvaluationRun.overall_winoe_score),
            func.max(EvaluationRun.overall_winoe_score),
        )
        .join(
            EvaluationRun,
            EvaluationRun.candidate_session_id == CandidateSession.id,
        )
        .where(
            CandidateSession.trial_id.in_(trial_ids),
            EvaluationRun.status == EVALUATION_RUN_STATUS_COMPLETED,
            EvaluationRun.overall_winoe_score.isnot(None),
        )
        .group_by(CandidateSession.trial_id)
    )
    rows = (await db.execute(stmt)).all()
    out: dict[int, str] = {}
    for trial_id, mn, mx in rows:
        if mn is None or mx is None:
            continue
        out[int(trial_id)] = _format_range(float(mn), float(mx))
    return out


__all__ = ["score_range_by_trial_ids"]
