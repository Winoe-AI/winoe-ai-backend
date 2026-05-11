from __future__ import annotations

import pytest

from app.trials.repositories.trials_repositories_trials_trial_status_constants import (
    TRIAL_STATUS_COMPLETED,
)
from tests.trials.services.trials_lifecycle_service_utils import *


def test_require_trial_invitable_completed_raises_specific_error():
    sim = _trial(TRIAL_STATUS_COMPLETED)
    with pytest.raises(ApiError) as excinfo:
        trial_service.require_trial_invitable(sim)
    assert excinfo.value.status_code == 409
    assert excinfo.value.error_code == "TRIAL_COMPLETED"
