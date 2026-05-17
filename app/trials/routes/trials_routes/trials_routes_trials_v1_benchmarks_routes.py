"""Application module for v1 benchmark routes workflows."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.auth.shared_auth_current_user_utils import get_current_user
from app.shared.auth.shared_auth_roles_utils import ensure_talent_partner
from app.shared.database import get_session
from app.shared.database.shared_database_models_model import User
from app.trials.schemas.trials_schemas_trials_benchmarks_schema import (
    TrialBenchmarksCompareResponse,
    TrialBenchmarksResponse,
)
from app.trials.services.trials_services_trials_benchmarks_service import (
    compare_benchmarks,
    list_benchmarks,
)

router = APIRouter(prefix="/v1")
logger = logging.getLogger(__name__)


@router.get(
    "/benchmarks",
    response_model=TrialBenchmarksResponse,
    status_code=status.HTTP_200_OK,
    summary="List Benchmarks",
    responses={
        status.HTTP_403_FORBIDDEN: {"description": "Talent Partner access required."},
        status.HTTP_404_NOT_FOUND: {"description": "Trial not found."},
    },
)
async def list_benchmarks_route(
    trial_id: Annotated[int, Query(..., ge=1)],
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    time_range: Annotated[str | None, Query(alias="time_range")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> TrialBenchmarksResponse:
    """Return benchmark cohort stats and candidates."""
    ensure_talent_partner(user)
    started_at = perf_counter()
    payload = await list_benchmarks(
        db,
        trial_id=trial_id,
        user=user,
        status_filter=status_filter,
        time_range=time_range,
        page=page,
        page_size=page_size,
    )
    logger.info(
        "Benchmarks fetched trialId=%s talentPartnerId=%s rowCount=%s latencyMs=%s",
        trial_id,
        user.id,
        len(payload["candidates"]),
        int((perf_counter() - started_at) * 1000),
    )
    return TrialBenchmarksResponse.model_validate(payload)


@router.get(
    "/benchmarks/compare",
    response_model=TrialBenchmarksCompareResponse,
    status_code=status.HTTP_200_OK,
    summary="Compare Benchmarks",
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Invalid candidate count."},
        status.HTTP_403_FORBIDDEN: {"description": "Talent Partner access required."},
        status.HTTP_404_NOT_FOUND: {"description": "Candidate not found."},
    },
)
async def compare_benchmarks_route(
    candidate_ids: Annotated[str, Query(alias="candidate_ids")],
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> TrialBenchmarksCompareResponse:
    """Return side-by-side benchmark data for 2-3 candidates."""
    ensure_talent_partner(user)
    ids = [part.strip() for part in (candidate_ids or "").split(",") if part.strip()]
    try:
        parsed_ids = [int(value) for value in ids]
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Compare requires numeric candidate IDs.",
        ) from exc
    payload = await compare_benchmarks(
        db,
        candidate_ids=parsed_ids,
        user=user,
    )
    return TrialBenchmarksCompareResponse.model_validate(payload)


__all__ = ["compare_benchmarks_route", "list_benchmarks_route", "router"]
