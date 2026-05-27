from __future__ import annotations

import pytest

from app.evaluations.repositories.evaluations_repositories_trial_evaluation_state_model import (
    TrialEvaluationStateRecord,
)
from app.shared.database.shared_database_models_model import WinoeReport
from tests.candidates.services.candidates_session_service_utils import *


@pytest.mark.asyncio
async def test_invite_list_for_principal_includes_progress(async_session):
    talent_partner = await create_talent_partner(async_session, email="list@sim.com")
    sim, tasks = await create_trial(async_session, created_by=talent_partner)
    cs = await create_candidate_session(
        async_session,
        trial=sim,
        invite_email="jane@example.com",
        status="in_progress",
    )
    await create_submission(
        async_session,
        candidate_session=cs,
        task=tasks[0],
        content_text="day1",
    )
    await async_session.commit()

    principal = _principal(cs.invite_email)
    invites = await cs_service.invite_list_for_principal(async_session, principal)
    assert len(invites) == 1
    invite = invites[0]
    assert invite.candidateSessionId == cs.id
    assert invite.progress.completed == 1
    assert invite.progress.total == len(tasks)


@pytest.mark.asyncio
async def test_invite_list_for_principal_uses_finalized_evaluation_state(
    async_session,
):
    talent_partner = await create_talent_partner(
        async_session, email="report-list@sim.com"
    )
    sim, _ = await create_trial(async_session, created_by=talent_partner)
    cs = await create_candidate_session(
        async_session,
        trial=sim,
        invite_email="finalized-candidate@example.com",
        status="completed",
    )
    async_session.add(
        WinoeReport(candidate_session_id=cs.id, generated_at=datetime.now(UTC))
    )
    async_session.add(
        TrialEvaluationStateRecord(
            trial_id=sim.id,
            candidate_session_id=cs.id,
            state="report_finalized",
            evidence_trail_validation_status="passed",
            report_finalization_status="finalized",
        )
    )
    await async_session.commit()

    invites = await cs_service.invite_list_for_principal(
        async_session,
        _principal(cs.invite_email),
    )

    assert len(invites) == 1
    assert invites[0].hasReport is True
    assert invites[0].reportReady is True
    assert invites[0].reportStatus == "finalized"
    assert invites[0].reportSharedWithTalentPartner is True
