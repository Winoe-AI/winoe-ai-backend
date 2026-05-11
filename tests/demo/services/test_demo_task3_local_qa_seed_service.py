from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.demo.services.task3_local_qa_seed_service import (
    TASK3_ACTIVE_TITLE,
    TASK3_AWAITING_TITLE,
    TASK3_COMPLETED_TITLE,
    seed_task3_local_qa,
)
from app.shared.database.shared_database_models_model import (
    CandidateSession,
    Company,
    Submission,
    Task,
    Trial,
    User,
)


def _seed_titles() -> tuple[str, str, str]:
    return (TASK3_ACTIVE_TITLE, TASK3_AWAITING_TITLE, TASK3_COMPLETED_TITLE)


@pytest.mark.asyncio
async def test_task3_seed_is_idempotent_and_recreates_expected_counts(async_session):
    email = "talent_partner1@local.test"
    await seed_task3_local_qa(async_session, talent_partner_email=email)
    await seed_task3_local_qa(async_session, talent_partner_email=email)

    user = await async_session.scalar(select(User).where(User.email == email))
    assert user is not None

    trials = (
        (
            await async_session.execute(
                select(Trial).where(
                    Trial.created_by == user.id,
                    Trial.title.in_(_seed_titles()),
                )
            )
        )
        .scalars()
        .all()
    )
    assert sorted(trial.title for trial in trials) == sorted(_seed_titles())

    counts = {}
    for title in _seed_titles():
        counts[title] = await async_session.scalar(
            select(func.count())
            .select_from(CandidateSession)
            .join(Trial, CandidateSession.trial_id == Trial.id)
            .where(Trial.created_by == user.id, Trial.title == title)
        )

    assert counts[TASK3_ACTIVE_TITLE] == 3
    assert counts[TASK3_AWAITING_TITLE] == 0
    assert counts[TASK3_COMPLETED_TITLE] == 2


@pytest.mark.asyncio
async def test_task3_seed_purge_deletes_submission_before_candidate_session(
    async_session,
):
    email = "talent_partner1@local.test"
    await seed_task3_local_qa(async_session, talent_partner_email=email)

    active_trial = await async_session.scalar(
        select(Trial).where(Trial.title == TASK3_ACTIVE_TITLE)
    )
    assert active_trial is not None

    candidate_session = await async_session.scalar(
        select(CandidateSession).where(CandidateSession.trial_id == active_trial.id)
    )
    assert candidate_session is not None

    task = await async_session.scalar(
        select(Task).where(Task.trial_id == active_trial.id)
    )
    assert task is not None

    extra_invite = "task3qa-regression-extra@local.test"
    extra_candidate = CandidateSession(
        trial_id=int(active_trial.id),
        scenario_version_id=int(candidate_session.scenario_version_id),
        candidate_name="Regression Extra Candidate",
        invite_email=extra_invite,
        candidate_email=extra_invite,
        candidate_auth0_email=extra_invite,
        token="task3qa-regression-extra-token",
        status="in_progress",
        invite_email_status="sent",
        candidate_timezone="America/New_York",
    )
    async_session.add(extra_candidate)
    await async_session.flush()

    old_candidate_session_id = int(extra_candidate.id)
    submission = Submission(
        candidate_session_id=old_candidate_session_id,
        task_id=int(task.id),
        submitted_at=datetime.now(UTC),
        content_text="seed regression payload",
        content_json={"artifactType": "manual"},
        code_repo_path=None,
    )
    async_session.add(submission)
    await async_session.commit()

    old_submission_id = int(submission.id)
    await seed_task3_local_qa(async_session, talent_partner_email=email)

    submission_after = await async_session.scalar(
        select(Submission).where(Submission.id == old_submission_id)
    )
    assert submission_after is None
    extra_invite_after = await async_session.scalar(
        select(CandidateSession).where(CandidateSession.invite_email == extra_invite)
    )
    assert extra_invite_after is None

    refreshed_active_count = await async_session.scalar(
        select(func.count())
        .select_from(CandidateSession)
        .join(Trial, CandidateSession.trial_id == Trial.id)
        .where(Trial.title == TASK3_ACTIVE_TITLE)
    )
    assert refreshed_active_count == 3


@pytest.mark.asyncio
async def test_task3_seed_does_not_purge_unrelated_trial(async_session):
    email = "talent_partner1@local.test"
    await seed_task3_local_qa(async_session, talent_partner_email=email)

    user = await async_session.scalar(select(User).where(User.email == email))
    assert user is not None
    company = await async_session.scalar(
        select(Company).where(Company.id == user.company_id)
    )
    assert company is not None

    unrelated_trial = Trial(
        company_id=int(company.id),
        title="Fresh Contract Live Trial",
        role="Backend Engineer",
        preferred_language_framework="Python, FastAPI",
        seniority="Senior",
        focus="Unrelated user trial",
        company_context={"team": "partnerships"},
        company_rubric_json=None,
        ai_prompt_overrides_json=None,
        ai_notice_version="v1",
        ai_notice_text="Default notice",
        scenario_template="",
        template_key="default",
        created_by=int(user.id),
        status="draft",
    )
    async_session.add(unrelated_trial)
    await async_session.commit()

    unrelated_id = int(unrelated_trial.id)
    await seed_task3_local_qa(async_session, talent_partner_email=email)

    still_exists = await async_session.scalar(
        select(Trial).where(Trial.id == unrelated_id)
    )
    assert still_exists is not None


@pytest.mark.asyncio
async def test_task3_seed_refuses_production_environment(async_session, monkeypatch):
    monkeypatch.setattr(
        "app.demo.services.task3_local_qa_seed_service.settings.is_production_environment",
        lambda: True,
    )
    with pytest.raises(RuntimeError, match="not allowed in production"):
        await seed_task3_local_qa(
            async_session, talent_partner_email="talent_partner1@local.test"
        )
