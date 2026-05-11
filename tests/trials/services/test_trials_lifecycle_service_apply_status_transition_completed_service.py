from __future__ import annotations

from datetime import UTC, datetime

from app.trials.repositories.trials_repositories_trials_trial_status_constants import (
    TRIAL_STATUS_ACTIVE_INVITING,
    TRIAL_STATUS_COMPLETED,
)
from tests.trials.services.trials_lifecycle_service_utils import *


def test_apply_status_transition_allows_active_inviting_to_completed():
    sim = _trial(TRIAL_STATUS_ACTIVE_INVITING)
    changed = trial_service.apply_status_transition(
        sim,
        target_status=TRIAL_STATUS_COMPLETED,
        changed_at=datetime.now(UTC),
    )
    assert changed is True
    assert sim.status == TRIAL_STATUS_COMPLETED
