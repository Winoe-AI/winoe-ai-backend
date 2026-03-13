from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.domains import Job
from app.integrations.github.webhooks.handlers import workflow_run
from app.repositories.github_native.workspaces.models import Workspace
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
    create_submission,
)


def _workflow_payload(
    *,
    run_id: int,
    repo_full_name: str,
    head_sha: str | None = "sha-head",
    run_attempt: int | None = 1,
    conclusion: object = "success",
    completed_at: str | None = "2026-03-13T12:00:00Z",
) -> dict[str, object]:
    workflow_run_payload: dict[str, object] = {"id": run_id}
    if run_attempt is not None:
        workflow_run_payload["run_attempt"] = run_attempt
    if head_sha is not None:
        workflow_run_payload["head_sha"] = head_sha
    if completed_at is not None:
        workflow_run_payload["completed_at"] = completed_at
    workflow_run_payload["conclusion"] = conclusion

    return {
        "action": "completed",
        "repository": {"full_name": repo_full_name},
        "workflow_run": workflow_run_payload,
    }


def test_parse_workflow_run_completed_event_rejects_invalid_payload_shapes():
    assert workflow_run.parse_workflow_run_completed_event({}) is None
    assert (
        workflow_run.parse_workflow_run_completed_event(
            {
                "repository": {"full_name": "acme/repo"},
                "workflow_run": {"id": "not-an-int"},
            }
        )
        is None
    )
    assert (
        workflow_run.parse_workflow_run_completed_event(
            {
                "repository": {"full_name": "   "},
                "workflow_run": {"id": 1},
            }
        )
        is None
    )


def test_parse_workflow_run_completed_event_normalizes_fields():
    event = workflow_run.parse_workflow_run_completed_event(
        _workflow_payload(
            run_id=123,
            repo_full_name="acme/repo",
            head_sha="abc123",
            run_attempt=None,
            conclusion=777,
            completed_at="2026-03-13T14:30:00",
        )
    )

    assert event is not None
    assert event.workflow_run_id == 123
    assert event.run_attempt is None
    assert event.repo_full_name == "acme/repo"
    assert event.head_sha == "abc123"
    assert event.conclusion is None
    assert event.completed_at == datetime(2026, 3, 13, 14, 30, tzinfo=UTC)


def test_workflow_run_parse_helpers_cover_invalid_inputs():
    assert workflow_run._normalized_lower(123) is None

    assert workflow_run._coerce_positive_int(object()) is None
    assert workflow_run._coerce_positive_int("not-int") is None
    assert workflow_run._coerce_positive_int("0") is None
    assert workflow_run._coerce_positive_int("-4") is None
    assert workflow_run._coerce_positive_int("42") == 42

    assert workflow_run._parse_github_datetime(None) is None
    assert workflow_run._parse_github_datetime("   ") is None
    assert workflow_run._parse_github_datetime("not-a-date") is None
    assert workflow_run._parse_github_datetime("2026-03-13T14:30:00") == datetime(
        2026,
        3,
        13,
        14,
        30,
        tzinfo=UTC,
    )


@pytest.mark.asyncio
async def test_exact_workflow_run_id_match_takes_precedence_over_fallback(
    async_session,
):
    recruiter = await create_recruiter(
        async_session, email="webhook-priority@tenon.dev"
    )
    simulation, tasks = await create_simulation(async_session, created_by=recruiter)

    primary_session = await create_candidate_session(
        async_session,
        simulation=simulation,
        invite_email="webhook-priority-primary@tenon.dev",
        with_default_schedule=True,
    )
    fallback_session = await create_candidate_session(
        async_session,
        simulation=simulation,
        invite_email="webhook-priority-fallback@tenon.dev",
        with_default_schedule=True,
    )

    repo_full_name = "acme/preference-repo"
    run_id = 444101
    head_sha = "head-sha-precedence"

    direct_match = await create_submission(
        async_session,
        candidate_session=primary_session,
        task=tasks[1],
        code_repo_path=repo_full_name,
        workflow_run_id=str(run_id),
        workflow_run_status="queued",
        commit_sha="old-sha",
        last_run_at=datetime(2026, 3, 13, 8, 0, tzinfo=UTC),
    )
    fallback_candidate = await create_submission(
        async_session,
        candidate_session=fallback_session,
        task=tasks[1],
        code_repo_path=repo_full_name,
        commit_sha=head_sha,
        workflow_run_status="queued",
        last_run_at=datetime(2026, 3, 13, 8, 5, tzinfo=UTC),
    )

    workspace = Workspace(
        candidate_session_id=primary_session.id,
        task_id=tasks[1].id,
        template_repo_full_name="acme/template",
        repo_full_name=repo_full_name,
        latest_commit_sha="old-workspace-sha",
        created_at=datetime.now(UTC),
    )
    async_session.add(workspace)
    await async_session.commit()

    result = await workflow_run.process_workflow_run_completed_event(
        async_session,
        payload=_workflow_payload(
            run_id=run_id,
            repo_full_name=repo_full_name,
            head_sha=head_sha,
            run_attempt=2,
        ),
        delivery_id="delivery-priority",
    )

    assert result.outcome == "updated_status"
    assert result.reason_code == "matched_by_workflow_run_id"
    assert result.submission_id == direct_match.id
    assert result.workflow_run_id == run_id
    assert result.enqueued_artifact_parse is True

    await async_session.refresh(direct_match)
    await async_session.refresh(fallback_candidate)
    await async_session.refresh(workspace)

    assert direct_match.workflow_run_id == str(run_id)
    assert direct_match.workflow_run_status == "completed"
    assert direct_match.workflow_run_attempt == 2
    assert direct_match.workflow_run_conclusion == "success"
    assert direct_match.commit_sha == head_sha
    assert workspace.last_workflow_run_id == str(run_id)
    assert workspace.last_workflow_conclusion == "success"
    assert workspace.latest_commit_sha == head_sha

    assert fallback_candidate.workflow_run_id is None
    assert fallback_candidate.workflow_run_status == "queued"
    assert fallback_candidate.commit_sha == head_sha

    jobs = (
        await async_session.execute(
            select(Job).where(
                Job.job_type == workflow_run.GITHUB_WORKFLOW_ARTIFACT_PARSE_JOB_TYPE
            )
        )
    ).scalars()
    assert len(list(jobs)) == 1


@pytest.mark.asyncio
async def test_ambiguous_fallback_candidates_return_unmatched_without_mutation(
    async_session,
):
    recruiter = await create_recruiter(async_session, email="webhook-ambig@tenon.dev")
    simulation, tasks = await create_simulation(async_session, created_by=recruiter)
    first_session = await create_candidate_session(
        async_session,
        simulation=simulation,
        invite_email="webhook-ambig-first@tenon.dev",
        with_default_schedule=True,
    )
    second_session = await create_candidate_session(
        async_session,
        simulation=simulation,
        invite_email="webhook-ambig-second@tenon.dev",
        with_default_schedule=True,
    )

    repo_full_name = "acme/ambiguous-repo"
    head_sha = "ambiguous-sha"

    first = await create_submission(
        async_session,
        candidate_session=first_session,
        task=tasks[1],
        code_repo_path=repo_full_name,
        commit_sha=head_sha,
        workflow_run_status="queued",
        last_run_at=datetime(2026, 3, 13, 8, 0, tzinfo=UTC),
    )
    second = await create_submission(
        async_session,
        candidate_session=second_session,
        task=tasks[1],
        code_repo_path=repo_full_name,
        commit_sha=head_sha,
        workflow_run_status="in_progress",
        last_run_at=datetime(2026, 3, 13, 8, 1, tzinfo=UTC),
    )
    await async_session.commit()

    result = await workflow_run.process_workflow_run_completed_event(
        async_session,
        payload=_workflow_payload(
            run_id=707001,
            repo_full_name=repo_full_name,
            head_sha=head_sha,
        ),
        delivery_id="delivery-ambiguous-fallback",
    )

    assert result.outcome == "unmatched"
    assert result.reason_code == "mapping_ambiguous_repo_head_sha"
    assert result.submission_id is None
    assert result.enqueued_artifact_parse is False

    await async_session.refresh(first)
    await async_session.refresh(second)
    assert first.workflow_run_id is None
    assert second.workflow_run_id is None
    assert first.workflow_run_status == "queued"
    assert second.workflow_run_status == "in_progress"

    jobs = (
        await async_session.execute(
            select(Job).where(
                Job.job_type == workflow_run.GITHUB_WORKFLOW_ARTIFACT_PARSE_JOB_TYPE
            )
        )
    ).scalars()
    assert list(jobs) == []


@pytest.mark.asyncio
async def test_unique_fallback_candidate_is_matched_and_updated(async_session):
    recruiter = await create_recruiter(
        async_session, email="webhook-fallback@tenon.dev"
    )
    simulation, tasks = await create_simulation(async_session, created_by=recruiter)
    candidate_session = await create_candidate_session(
        async_session,
        simulation=simulation,
        invite_email="webhook-fallback-candidate@tenon.dev",
        with_default_schedule=True,
    )

    original_last_run_at = datetime(2026, 3, 13, 8, 10, tzinfo=UTC)
    submission = await create_submission(
        async_session,
        candidate_session=candidate_session,
        task=tasks[1],
        code_repo_path="acme/fallback-match",
        commit_sha="fallback-sha",
        workflow_run_status="queued",
        last_run_at=original_last_run_at,
    )
    await async_session.commit()

    result = await workflow_run.process_workflow_run_completed_event(
        async_session,
        payload=_workflow_payload(
            run_id=60601,
            repo_full_name="acme/fallback-match",
            head_sha="fallback-sha",
            completed_at=None,
        ),
        delivery_id="delivery-fallback-matched",
    )

    assert result.outcome == "updated_status"
    assert result.reason_code == "matched_by_repo_head_sha"
    assert result.submission_id == submission.id

    await async_session.refresh(submission)
    assert submission.workflow_run_id == "60601"
    assert submission.workflow_run_status == "completed"
    assert submission.last_run_at is not None
    observed_last_run_at = submission.last_run_at
    if observed_last_run_at.tzinfo is None:
        observed_last_run_at = observed_last_run_at.replace(tzinfo=UTC)
    assert observed_last_run_at == original_last_run_at


@pytest.mark.asyncio
async def test_terminal_fallback_candidate_is_not_selected(async_session):
    recruiter = await create_recruiter(
        async_session, email="webhook-terminal@tenon.dev"
    )
    simulation, tasks = await create_simulation(async_session, created_by=recruiter)
    candidate_session = await create_candidate_session(
        async_session,
        simulation=simulation,
        with_default_schedule=True,
    )

    await create_submission(
        async_session,
        candidate_session=candidate_session,
        task=tasks[1],
        code_repo_path="acme/terminal-repo",
        commit_sha="terminal-sha",
        workflow_run_status="completed",
        workflow_run_conclusion="success",
        workflow_run_completed_at=datetime(2026, 3, 13, 7, 30, tzinfo=UTC),
        last_run_at=datetime(2026, 3, 13, 7, 30, tzinfo=UTC),
    )
    await async_session.commit()

    result = await workflow_run.process_workflow_run_completed_event(
        async_session,
        payload=_workflow_payload(
            run_id=808001,
            repo_full_name="acme/terminal-repo",
            head_sha="terminal-sha",
        ),
        delivery_id="delivery-terminal-excluded",
    )

    assert result.outcome == "unmatched"
    assert result.reason_code == "mapping_unmatched"
    assert result.enqueued_artifact_parse is False


@pytest.mark.asyncio
async def test_direct_match_sets_last_run_at_when_completed_at_missing(async_session):
    recruiter = await create_recruiter(
        async_session, email="webhook-last-run@tenon.dev"
    )
    simulation, tasks = await create_simulation(async_session, created_by=recruiter)
    candidate_session = await create_candidate_session(
        async_session,
        simulation=simulation,
        invite_email="webhook-last-run-candidate@tenon.dev",
        with_default_schedule=True,
    )
    submission = await create_submission(
        async_session,
        candidate_session=candidate_session,
        task=tasks[1],
        code_repo_path="acme/last-run-fallback",
        workflow_run_id="515151",
        workflow_run_status="queued",
        last_run_at=None,
    )
    await async_session.commit()

    result = await workflow_run.process_workflow_run_completed_event(
        async_session,
        payload=_workflow_payload(
            run_id=515151,
            repo_full_name="acme/last-run-fallback",
            head_sha=None,
            completed_at=None,
        ),
        delivery_id="delivery-last-run-autoset",
    )

    assert result.outcome == "updated_status"
    await async_session.refresh(submission)
    assert submission.workflow_run_status == "completed"
    assert submission.workflow_run_completed_at is None
    assert submission.last_run_at is not None


@pytest.mark.asyncio
async def test_ambiguous_direct_workflow_run_id_match_returns_unmatched(async_session):
    recruiter = await create_recruiter(async_session, email="webhook-direct@tenon.dev")
    simulation, tasks = await create_simulation(async_session, created_by=recruiter)
    first_session = await create_candidate_session(
        async_session,
        simulation=simulation,
        invite_email="webhook-direct-first@tenon.dev",
        with_default_schedule=True,
    )
    second_session = await create_candidate_session(
        async_session,
        simulation=simulation,
        invite_email="webhook-direct-second@tenon.dev",
        with_default_schedule=True,
    )

    for candidate_session in (first_session, second_session):
        await create_submission(
            async_session,
            candidate_session=candidate_session,
            task=tasks[1],
            code_repo_path="acme/direct-ambiguous",
            workflow_run_id="9991",
            last_run_at=datetime(2026, 3, 13, 9, 0, tzinfo=UTC),
        )
    await async_session.commit()

    result = await workflow_run.process_workflow_run_completed_event(
        async_session,
        payload=_workflow_payload(
            run_id=9991,
            repo_full_name="acme/direct-ambiguous",
            head_sha="unused",
        ),
        delivery_id="delivery-direct-ambiguous",
    )

    assert result.outcome == "unmatched"
    assert result.reason_code == "mapping_ambiguous_workflow_run_id"
    assert result.submission_id is None


@pytest.mark.asyncio
async def test_process_workflow_run_completed_event_unmatched_without_head_sha(
    async_session,
):
    result = await workflow_run.process_workflow_run_completed_event(
        async_session,
        payload=_workflow_payload(
            run_id=9910,
            repo_full_name="acme/no-head-sha",
            head_sha=None,
        ),
        delivery_id="delivery-no-head-sha",
    )

    assert result.outcome == "unmatched"
    assert result.reason_code == "mapping_unmatched"
    assert result.workflow_run_id == 9910


@pytest.mark.asyncio
async def test_process_workflow_run_completed_event_invalid_payload_is_ignored(
    async_session,
):
    result = await workflow_run.process_workflow_run_completed_event(
        async_session,
        payload={"action": "completed"},
        delivery_id="delivery-invalid",
    )

    assert result.outcome == "ignored"
    assert result.reason_code == "workflow_run_payload_invalid"


@pytest.mark.asyncio
async def test_process_workflow_run_completed_event_company_unresolved_returns_unmatched(
    async_session,
    monkeypatch,
):
    recruiter = await create_recruiter(
        async_session,
        email="webhook-no-company@tenon.dev",
    )
    simulation, tasks = await create_simulation(async_session, created_by=recruiter)
    candidate_session = await create_candidate_session(
        async_session,
        simulation=simulation,
        with_default_schedule=True,
    )
    submission = await create_submission(
        async_session,
        candidate_session=candidate_session,
        task=tasks[1],
        code_repo_path="acme/no-company",
        workflow_run_id="12345",
        last_run_at=datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
    )
    await async_session.commit()

    async def _return_none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(workflow_run, "_company_id_for_submission", _return_none)

    result = await workflow_run.process_workflow_run_completed_event(
        async_session,
        payload=_workflow_payload(
            run_id=12345,
            repo_full_name="acme/no-company",
        ),
        delivery_id="delivery-no-company",
    )

    assert result.outcome == "unmatched"
    assert result.reason_code == "submission_company_unresolved"
    assert result.submission_id == submission.id
    assert result.workflow_run_id == 12345


@pytest.mark.asyncio
async def test_duplicate_completed_delivery_returns_duplicate_noop_and_is_idempotent(
    async_session,
):
    recruiter = await create_recruiter(async_session, email="webhook-noop@tenon.dev")
    simulation, tasks = await create_simulation(async_session, created_by=recruiter)
    candidate_session = await create_candidate_session(
        async_session,
        simulation=simulation,
        with_default_schedule=True,
    )

    run_id = 66550
    head_sha = "noop-head-sha"
    completed_at = datetime(2026, 3, 13, 12, 0, tzinfo=UTC)
    submission = await create_submission(
        async_session,
        candidate_session=candidate_session,
        task=tasks[1],
        code_repo_path="acme/noop-repo",
        workflow_run_id=str(run_id),
        workflow_run_attempt=3,
        workflow_run_status="completed",
        workflow_run_conclusion="success",
        workflow_run_completed_at=completed_at,
        commit_sha=head_sha,
        last_run_at=completed_at,
    )
    await async_session.commit()

    payload = _workflow_payload(
        run_id=run_id,
        repo_full_name="acme/noop-repo",
        head_sha=head_sha,
        run_attempt=3,
        completed_at="2026-03-13T12:00:00Z",
    )

    first = await workflow_run.process_workflow_run_completed_event(
        async_session,
        payload=payload,
        delivery_id="delivery-noop-1",
    )
    second = await workflow_run.process_workflow_run_completed_event(
        async_session,
        payload=payload,
        delivery_id="delivery-noop-2",
    )

    assert first.outcome == "duplicate_noop"
    assert first.enqueued_artifact_parse is True
    assert second.outcome == "duplicate_noop"
    assert second.enqueued_artifact_parse is False
    assert first.submission_id == submission.id
    assert second.submission_id == submission.id

    jobs = (
        await async_session.execute(
            select(Job).where(
                Job.job_type == workflow_run.GITHUB_WORKFLOW_ARTIFACT_PARSE_JOB_TYPE
            )
        )
    ).scalars()
    assert len(list(jobs)) == 1
