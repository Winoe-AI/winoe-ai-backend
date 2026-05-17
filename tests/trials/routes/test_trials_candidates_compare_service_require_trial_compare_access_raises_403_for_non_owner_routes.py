from __future__ import annotations

import pytest

from tests.trials.services.trials_candidates_compare_service_utils import *


@pytest.mark.asyncio
async def test_require_trial_compare_access_allows_same_company_non_owner():
    trial = SimpleNamespace(id=77, company_id=5, created_by=101)
    db = _FakeDB([_ScalarResult(trial)])
    user = SimpleNamespace(id=100, company_id=5)

    context = await require_trial_compare_access(db, trial_id=77, user=user)

    assert context.trial_id == 77
