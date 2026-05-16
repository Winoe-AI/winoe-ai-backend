"""Unit coverage for approve_trial_for_inviting (Task 5 lifecycle)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.shared.utils.shared_utils_errors_utils import ApiError
from app.trials.repositories.scenario_versions.trials_repositories_scenario_versions_trials_scenario_versions_model import (
    SCENARIO_VERSION_STATUS_LOCKED,
    SCENARIO_VERSION_STATUS_READY,
)
from app.trials.repositories.trials_repositories_trials_trial_model import (
    TRIAL_STATUS_ACTIVE_INVITING,
    TRIAL_STATUS_READY_FOR_REVIEW,
)
from app.trials.services import (
    trials_services_trials_lifecycle_approve_service as approve_mod,
)


def _scenario(
    *,
    status: str = SCENARIO_VERSION_STATUS_READY,
    brief: str = "Brief here.",
    rubric: dict | list | None = None,
):
    s = MagicMock()
    s.status = status
    s.project_brief_md = brief
    s.rubric_json = rubric if rubric is not None else {"dim": 1}
    return s


@pytest.mark.asyncio
async def test_approve_trial_active_inviting_idempotent():
    db = AsyncMock()
    trial = MagicMock()
    trial.status = TRIAL_STATUS_ACTIVE_INVITING
    trial.id = 42

    with patch.object(
        approve_mod,
        "require_owner_for_lifecycle",
        new_callable=AsyncMock,
        return_value=trial,
    ):
        out = await approve_mod.approve_trial_for_inviting(
            db, trial_id=42, actor_user_id=7
        )
    assert out is trial
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(trial)


@pytest.mark.asyncio
async def test_approve_trial_rejects_generating():
    db = AsyncMock()
    trial = MagicMock()
    trial.status = "generating"

    with patch.object(
        approve_mod,
        "require_owner_for_lifecycle",
        new_callable=AsyncMock,
        return_value=trial,
    ), pytest.raises(ApiError) as exc:
        await approve_mod.approve_trial_for_inviting(db, trial_id=1, actor_user_id=7)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_approve_trial_rejects_wrong_status():
    db = AsyncMock()
    trial = MagicMock()
    trial.status = "draft"

    with patch.object(
        approve_mod,
        "require_owner_for_lifecycle",
        new_callable=AsyncMock,
        return_value=trial,
    ), pytest.raises(ApiError) as exc:
        await approve_mod.approve_trial_for_inviting(db, trial_id=1, actor_user_id=7)
    assert exc.value.status_code == 409
    assert "not ready" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_approve_trial_rejects_pending_scenario():
    db = AsyncMock()
    trial = MagicMock()
    trial.status = TRIAL_STATUS_READY_FOR_REVIEW
    trial.pending_scenario_version_id = 99

    with patch.object(
        approve_mod,
        "require_owner_for_lifecycle",
        new_callable=AsyncMock,
        return_value=trial,
    ), pytest.raises(ApiError) as exc:
        await approve_mod.approve_trial_for_inviting(db, trial_id=1, actor_user_id=7)
    assert exc.value.error_code == "SCENARIO_APPROVAL_PENDING"


@pytest.mark.asyncio
async def test_approve_trial_rejects_missing_scenario():
    db = AsyncMock()
    trial = MagicMock()
    trial.status = TRIAL_STATUS_READY_FOR_REVIEW
    trial.pending_scenario_version_id = None

    with patch.object(
        approve_mod,
        "require_owner_for_lifecycle",
        new_callable=AsyncMock,
        return_value=trial,
    ), patch.object(
        approve_mod,
        "get_active_scenario_version",
        new_callable=AsyncMock,
        return_value=None,
    ), pytest.raises(ApiError) as exc:
        await approve_mod.approve_trial_for_inviting(db, trial_id=1, actor_user_id=7)
    assert exc.value.error_code == "SCENARIO_MISSING"


@pytest.mark.asyncio
async def test_approve_trial_rejects_missing_brief():
    db = AsyncMock()
    trial = MagicMock()
    trial.status = TRIAL_STATUS_READY_FOR_REVIEW
    trial.pending_scenario_version_id = None
    scenario = _scenario(brief="   ")

    with patch.object(
        approve_mod,
        "require_owner_for_lifecycle",
        new_callable=AsyncMock,
        return_value=trial,
    ), patch.object(
        approve_mod,
        "get_active_scenario_version",
        new_callable=AsyncMock,
        return_value=scenario,
    ), pytest.raises(ApiError) as exc:
        await approve_mod.approve_trial_for_inviting(db, trial_id=1, actor_user_id=7)
    assert exc.value.error_code == "TRIAL_BRIEF_MISSING"


@pytest.mark.asyncio
async def test_approve_trial_rejects_empty_rubric_dict():
    db = AsyncMock()
    trial = MagicMock()
    trial.status = TRIAL_STATUS_READY_FOR_REVIEW
    trial.pending_scenario_version_id = None
    scenario = _scenario(rubric={})

    with patch.object(
        approve_mod,
        "require_owner_for_lifecycle",
        new_callable=AsyncMock,
        return_value=trial,
    ), patch.object(
        approve_mod,
        "get_active_scenario_version",
        new_callable=AsyncMock,
        return_value=scenario,
    ), pytest.raises(ApiError) as exc:
        await approve_mod.approve_trial_for_inviting(db, trial_id=1, actor_user_id=7)
    assert exc.value.error_code == "TRIAL_RUBRIC_MISSING"


@pytest.mark.asyncio
async def test_approve_trial_rubric_accepts_nonempty_list():
    db = AsyncMock()
    trial = MagicMock()
    trial.status = TRIAL_STATUS_READY_FOR_REVIEW
    trial.pending_scenario_version_id = None
    scenario = _scenario(rubric=[{"k": "v"}])

    activated = MagicMock()
    activated.status = TRIAL_STATUS_ACTIVE_INVITING

    with patch.object(
        approve_mod,
        "require_owner_for_lifecycle",
        new_callable=AsyncMock,
        return_value=trial,
    ), patch.object(
        approve_mod,
        "get_active_scenario_version",
        new_callable=AsyncMock,
        return_value=scenario,
    ), patch.object(
        approve_mod,
        "lock_active_scenario_for_invites",
        new_callable=AsyncMock,
    ) as lock_fn, patch.object(
        approve_mod,
        "activate_trial",
        new_callable=AsyncMock,
        return_value=activated,
    ) as act_fn:
        out = await approve_mod.approve_trial_for_inviting(
            db, trial_id=1, actor_user_id=7
        )

    lock_fn.assert_awaited_once()
    db.commit.assert_awaited_once()
    act_fn.assert_awaited_once_with(db, trial_id=1, actor_user_id=7, now=None)
    assert out is activated


@pytest.mark.asyncio
async def test_approve_trial_when_scenario_already_locked_skips_lock():
    db = AsyncMock()
    trial = MagicMock()
    trial.status = TRIAL_STATUS_READY_FOR_REVIEW
    trial.pending_scenario_version_id = None
    scenario = _scenario(status=SCENARIO_VERSION_STATUS_LOCKED)

    activated = MagicMock()

    with patch.object(
        approve_mod,
        "require_owner_for_lifecycle",
        new_callable=AsyncMock,
        return_value=trial,
    ), patch.object(
        approve_mod,
        "get_active_scenario_version",
        new_callable=AsyncMock,
        return_value=scenario,
    ), patch.object(
        approve_mod,
        "lock_active_scenario_for_invites",
        new_callable=AsyncMock,
    ) as lock_fn, patch.object(
        approve_mod,
        "activate_trial",
        new_callable=AsyncMock,
        return_value=activated,
    ):
        out = await approve_mod.approve_trial_for_inviting(
            db, trial_id=3, actor_user_id=9
        )

    lock_fn.assert_not_called()
    assert out is activated


@pytest.mark.asyncio
async def test_approve_trial_rejects_scenario_not_ready_or_locked():
    db = AsyncMock()
    trial = MagicMock()
    trial.status = TRIAL_STATUS_READY_FOR_REVIEW
    trial.pending_scenario_version_id = None
    scenario = _scenario(status="generating")

    with patch.object(
        approve_mod,
        "require_owner_for_lifecycle",
        new_callable=AsyncMock,
        return_value=trial,
    ), patch.object(
        approve_mod,
        "get_active_scenario_version",
        new_callable=AsyncMock,
        return_value=scenario,
    ), pytest.raises(ApiError) as exc:
        await approve_mod.approve_trial_for_inviting(db, trial_id=1, actor_user_id=7)
    assert exc.value.error_code == "SCENARIO_NOT_READY"
