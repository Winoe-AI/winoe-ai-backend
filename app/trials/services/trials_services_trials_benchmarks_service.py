"""Application module for trials services trials benchmarks service workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import mean, median
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluations.repositories.evaluations_repositories_evaluations_core_model import (
    EVALUATION_RUN_STATUS_COMPLETED,
    EvaluationRun,
)
from app.evaluations.services.evaluations_services_evaluations_winoe_report_access_service import (
    has_company_access,
)
from app.shared.database.shared_database_models_model import (
    CandidateSession,
    Submission,
    Task,
    Trial,
    User,
    WinoeReport,
)
from app.trials.services.trials_services_trials_candidates_compare_access_service import (
    require_trial_compare_access,
)


@dataclass(slots=True)
class _BenchmarkRow:
    candidate_session_id: int
    candidate_name: str | None
    candidate_email: str | None
    candidate_status: str | None
    candidate_started_at: Any
    candidate_completed_at: Any
    trial_id: int
    trial_title: str
    submission_submitted_at: Any
    report_id: int | None
    winoe_score: float | None
    raw_report_json: dict[str, Any] | None
    latest_run_status: str | None


def _dimension_score(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if number < 0:
        return None
    if number <= 1:
        number *= 10
    if number > 10:
        return 10.0
    return round(number, 2)


def _normalize_score(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if number < 0:
        return None
    return round(number * 100 if number <= 1 else number, 2)


def _parse_dimensions(raw_report_json: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(raw_report_json, dict):
        return []
    raw_dimensions = raw_report_json.get("dimensions")
    if not isinstance(raw_dimensions, list):
        return []
    dimensions: list[dict[str, Any]] = []
    for item in raw_dimensions:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("label")
        score = _dimension_score(item.get("score"))
        if not isinstance(name, str) or score is None:
            continue
        dimensions.append({"name": name, "score": score})
    return dimensions


def _parse_compare_dimensions(
    raw_report_json: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    dimensions = _parse_dimensions(raw_report_json)
    return dimensions


def _cohort_stats(scores: list[float], total: int) -> dict[str, Any]:
    if not scores:
        return {
            "n": total,
            "median": None,
            "mean": None,
            "range": None,
            "sufficient": total >= 3,
        }
    low = min(scores)
    high = max(scores)
    return {
        "n": total,
        "median": round(float(median(scores)), 2),
        "mean": round(float(mean(scores)), 2),
        "range": [round(low, 2), round(high, 2)],
        "sufficient": total >= 3,
    }


async def _load_trial_rows(
    db: AsyncSession,
    *,
    trial_id: int,
) -> tuple[list[_BenchmarkRow], str]:
    trial = await db.scalar(select(Trial.title).where(Trial.id == trial_id))
    if trial is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Trial not found"
        )

    latest_submission_subq = (
        select(
            Submission.candidate_session_id.label("candidate_session_id"),  # type: ignore[name-defined]
            func.max(Submission.submitted_at).label("submitted_at"),  # type: ignore[name-defined]
        )
        .join(Task, Task.id == Submission.task_id)  # type: ignore[name-defined]
        .where(Task.trial_id == trial_id)  # type: ignore[name-defined]
        .group_by(Submission.candidate_session_id)  # type: ignore[name-defined]
        .subquery()
    )
    latest_run_subq = (
        select(
            EvaluationRun.candidate_session_id.label("candidate_session_id"),
            func.max(EvaluationRun.id).label("run_id"),
        )
        .group_by(EvaluationRun.candidate_session_id)
        .subquery()
    )
    latest_report_subq = (
        select(
            WinoeReport.candidate_session_id.label("candidate_session_id"),
            func.max(WinoeReport.id).label("report_id"),
        )
        .group_by(WinoeReport.candidate_session_id)
        .subquery()
    )
    stmt = (
        select(
            CandidateSession.id,
            CandidateSession.candidate_name,
            CandidateSession.invite_email,
            CandidateSession.status,
            CandidateSession.started_at,
            CandidateSession.completed_at,
            Trial.id.label("trial_id"),
            Trial.title.label("trial_title"),
            latest_submission_subq.c.submitted_at,
            latest_report_subq.c.report_id,
            EvaluationRun.overall_winoe_score,
            EvaluationRun.raw_report_json,
            EvaluationRun.status.label("latest_run_status"),
        )
        .join(Trial, Trial.id == CandidateSession.trial_id)
        .outerjoin(
            latest_submission_subq,
            latest_submission_subq.c.candidate_session_id == CandidateSession.id,
        )
        .outerjoin(
            latest_run_subq,
            latest_run_subq.c.candidate_session_id == CandidateSession.id,
        )
        .outerjoin(
            latest_report_subq,
            latest_report_subq.c.candidate_session_id == CandidateSession.id,
        )
        .outerjoin(EvaluationRun, EvaluationRun.id == latest_run_subq.c.run_id)
        .where(CandidateSession.trial_id == trial_id)
        .order_by(CandidateSession.id.asc())
    )
    rows = [
        _BenchmarkRow(
            candidate_session_id=int(row.id),
            candidate_name=getattr(row, "candidate_name", None),
            candidate_email=getattr(row, "invite_email", None),
            candidate_status=getattr(row, "status", None),
            candidate_started_at=getattr(row, "started_at", None),
            candidate_completed_at=getattr(row, "completed_at", None),
            trial_id=int(row.trial_id),
            trial_title=str(row.trial_title),
            submission_submitted_at=getattr(row, "submitted_at", None),
            report_id=int(row.report_id)
            if getattr(row, "report_id", None) is not None
            and getattr(row, "latest_run_status", None)
            == EVALUATION_RUN_STATUS_COMPLETED
            else None,
            winoe_score=_normalize_score(getattr(row, "overall_winoe_score", None)),
            raw_report_json=getattr(row, "raw_report_json", None)
            if isinstance(getattr(row, "raw_report_json", None), dict)
            else None,
            latest_run_status=getattr(row, "latest_run_status", None),
        )
        for row in (await db.execute(stmt)).all()
    ]
    return rows, str(trial)


def _candidate_status(row: _BenchmarkRow) -> str:
    if row.latest_run_status in {"pending", "running"}:
        return "report_pending"
    if (
        row.latest_run_status == EVALUATION_RUN_STATUS_COMPLETED
        and row.report_id is not None
    ):
        return "evaluated"
    if row.candidate_status == "completed" or row.candidate_completed_at is not None:
        return "completed"
    return "in_progress"


def _build_candidate_row(row: _BenchmarkRow) -> dict[str, Any]:
    dimensions = _parse_dimensions(row.raw_report_json)
    return {
        "id": str(row.candidate_session_id),
        "name": row.candidate_name
        or row.candidate_email
        or f"Candidate {row.candidate_session_id}",
        "email": row.candidate_email or "",
        "trial_id": str(row.trial_id),
        "trial_title": row.trial_title,
        "report_id": str(row.report_id) if row.report_id is not None else None,
        "winoe_score": row.winoe_score,
        "dimensions": dimensions,
        "status": _candidate_status(row),
        "submitted_at": row.submission_submitted_at
        or row.candidate_completed_at
        or row.candidate_started_at,
    }


async def list_benchmarks(
    db: AsyncSession,
    *,
    trial_id: int,
    user: User,
    status_filter: str | None = None,
    time_range: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    """Return benchmark cohort stats for a single owned Trial."""
    await require_trial_compare_access(db, trial_id=trial_id, user=user)
    rows, _trial_title = await _load_trial_rows(db, trial_id=trial_id)
    filtered = [
        row
        for row in rows
        if _matches_status(row, status_filter) and _matches_time_range(row, time_range)
    ]
    scores = [row.winoe_score for row in filtered if row.winoe_score is not None]
    total = len(filtered)
    total_pages = max(1, (total + page_size - 1) // page_size)
    safe_page = max(1, min(page, total_pages))
    start = (safe_page - 1) * page_size
    stop = start + page_size
    page_rows = filtered[start:stop]
    return {
        "cohort": _cohort_stats(scores, total),
        "pagination": {
            "page": safe_page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        },
        "candidates": [_build_candidate_row(row) for row in page_rows],
    }


async def compare_benchmarks(
    db: AsyncSession,
    *,
    candidate_ids: list[int],
    user: User,
) -> dict[str, Any]:
    """Return a same-Trial compare payload for 2-3 candidates."""
    if len(candidate_ids) < 2 or len(candidate_ids) > 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Compare requires 2 or 3 candidates.",
        )
    if len(set(candidate_ids)) != len(candidate_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Compare requires unique candidate IDs.",
        )
    requested_rows = (
        await db.execute(
            select(
                CandidateSession.id,
                CandidateSession.trial_id,
                Trial.company_id,
            )
            .join(Trial, Trial.id == CandidateSession.trial_id)
            .where(CandidateSession.id.in_(candidate_ids))
        )
    ).all()
    if not requested_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more candidate IDs were not found.",
        )
    if len(requested_rows) != len(candidate_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more candidate IDs were not found.",
        )
    if any(
        not has_company_access(
            trial_company_id=company_id,
            expected_company_id=getattr(user, "company_id", None),
        )
        for _candidate_id, _trial_id, company_id in requested_rows
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Candidate access forbidden",
        )

    trial_ids = {
        int(trial_id) for _candidate_id, trial_id, _company_id in requested_rows
    }
    if len(trial_ids) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Candidates must belong to the same Trial.",
        )
    trial_id = next(iter(trial_ids))
    await require_trial_compare_access(db, trial_id=trial_id, user=user)
    rows, _trial_title = await _load_trial_rows(db, trial_id=trial_id)
    row_by_id = {row.candidate_session_id: row for row in rows}
    if any(candidate_id not in row_by_id for candidate_id in candidate_ids):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Candidate access forbidden",
        )
    selected_rows = [row_by_id[candidate_id] for candidate_id in candidate_ids]
    return {
        "candidates": [
            {
                **_build_candidate_row(row),
                "score_ring": row.winoe_score,
                "radar_dimensions": _parse_compare_dimensions(row.raw_report_json),
            }
            for row in selected_rows
        ]
    }


def _matches_status(row: _BenchmarkRow, status_filter: str | None) -> bool:
    if not status_filter or status_filter == "all":
        return True
    return _candidate_status(row) == status_filter


def _matches_time_range(row: _BenchmarkRow, time_range: str | None) -> bool:
    if not time_range or time_range == "all":
        return True
    value = (
        row.submission_submitted_at
        or row.candidate_completed_at
        or row.candidate_started_at
    )
    if value is None:
        return False
    try:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
            now = datetime.now(UTC)
        else:
            now = datetime.now(value.tzinfo)
    except Exception:
        now = datetime.now(UTC)
    delta_days = (now - value).days
    if time_range == "30d":
        return delta_days <= 30
    if time_range == "90d":
        return delta_days <= 90
    return True


__all__ = ["compare_benchmarks", "list_benchmarks"]
