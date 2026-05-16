"""Approve Trial for inviting: lock scenario when needed, then activate."""

from __future__ import annotations

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.shared_database_models_model import ScenarioVersion, Trial
from app.shared.utils.shared_utils_errors_utils import ApiError
from app.trials.repositories.scenario_versions.trials_repositories_scenario_versions_trials_scenario_versions_model import (
    SCENARIO_VERSION_STATUS_LOCKED,
    SCENARIO_VERSION_STATUS_READY,
)
from app.trials.repositories.trials_repositories_trials_trial_model import (
    TRIAL_STATUS_ACTIVE_INVITING,
    TRIAL_STATUS_GENERATING,
    TRIAL_STATUS_READY_FOR_REVIEW,
    TRIAL_STATUS_TERMINATED,
)
from app.trials.services.trials_services_trials_lifecycle_access_service import (
    require_owner_for_lifecycle,
)
from app.trials.services.trials_services_trials_lifecycle_service import activate_trial
from app.trials.services.trials_services_trials_lifecycle_status_service import (
    normalize_trial_status,
)
from app.trials.services.trials_services_trials_scenario_versions_create_service import (
    get_active_scenario_version,
)
from app.trials.services.trials_services_trials_scenario_versions_lock_service import (
    lock_active_scenario_for_invites,
)


def _rubric_present(scenario: ScenarioVersion) -> bool:
    data = scenario.rubric_json
    if isinstance(data, dict):
        return bool(data)
    if isinstance(data, list):
        return len(data) > 0
    return False


def _brief_present(*, scenario: ScenarioVersion) -> bool:
    text = getattr(scenario, "project_brief_md", None)
    return isinstance(text, str) and bool(text.strip())


async def approve_trial_for_inviting(
    db: AsyncSession,
    *,
    trial_id: int,
    actor_user_id: int,
) -> Trial:
    """Lock the active scenario (if needed) and transition Trial to active_inviting.

    Idempotent: if the Trial is already ``active_inviting``, returns success.
    """
    trial = await require_owner_for_lifecycle(
        db, trial_id=trial_id, actor_user_id=actor_user_id, for_update=True
    )
    current = normalize_trial_status(trial.status)
    if current == TRIAL_STATUS_ACTIVE_INVITING:
        await db.commit()
        await db.refresh(trial)
        return trial
    if current == TRIAL_STATUS_TERMINATED:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Trial has been terminated.",
            error_code="TRIAL_TERMINATED",
            retryable=False,
            details={"status": current},
        )
    if current == TRIAL_STATUS_GENERATING:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Trial is still generating.",
            error_code="TRIAL_GENERATING",
            retryable=False,
            details={"status": current},
        )
    if current != TRIAL_STATUS_READY_FOR_REVIEW:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Trial is not ready for review.",
            error_code="TRIAL_NOT_READY_FOR_REVIEW",
            retryable=False,
            details={"status": current},
        )
    pending = getattr(trial, "pending_scenario_version_id", None)
    if pending is not None:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scenario approval is pending before inviting.",
            error_code="SCENARIO_APPROVAL_PENDING",
            retryable=False,
            details={"pendingScenarioVersionId": pending},
        )
    scenario = await get_active_scenario_version(db, trial.id)
    if scenario is None:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active scenario version for this Trial.",
            error_code="SCENARIO_MISSING",
            retryable=False,
            details={},
        )
    if not _brief_present(scenario=scenario):
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project Brief is missing for this Trial.",
            error_code="TRIAL_BRIEF_MISSING",
            retryable=False,
            details={},
        )
    if not _rubric_present(scenario):
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Evaluation rubric is missing for this Trial.",
            error_code="TRIAL_RUBRIC_MISSING",
            retryable=False,
            details={},
        )
    if scenario.status == SCENARIO_VERSION_STATUS_READY:
        await lock_active_scenario_for_invites(
            db, trial_id=trial.id, trial=trial, now=None
        )
    elif scenario.status != SCENARIO_VERSION_STATUS_LOCKED:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scenario version is not ready to approve.",
            error_code="SCENARIO_NOT_READY",
            retryable=False,
            details={"status": scenario.status},
        )
    await db.commit()
    return await activate_trial(
        db, trial_id=trial_id, actor_user_id=actor_user_id, now=None
    )


__all__ = ["approve_trial_for_inviting"]
