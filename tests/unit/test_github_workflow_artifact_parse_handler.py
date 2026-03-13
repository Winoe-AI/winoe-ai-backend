from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.integrations.github.actions_runner import ActionsRunResult
from app.jobs.handlers import github_workflow_artifact_parse as parse_handler
from app.repositories.github_native.workspaces.models import Workspace
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
    create_submission,
)


@pytest.mark.asyncio
async def test_handle_github_workflow_artifact_parse_skips_invalid_payload():
    result = await parse_handler.handle_github_workflow_artifact_parse(
        {"submissionId": None}
    )

    assert result["status"] == "skipped_invalid_payload"


@pytest.mark.asyncio
async def test_handle_github_workflow_artifact_parse_persists_results(
    async_session,
    monkeypatch,
):
    recruiter = await create_recruiter(async_session, email="parse-handler@tenon.dev")
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
        code_repo_path="acme/parse-handler-repo",
        workflow_run_id="321",
    )
    workspace = Workspace(
        candidate_session_id=candidate_session.id,
        task_id=tasks[1].id,
        template_repo_full_name="acme/template-repo",
        repo_full_name="acme/parse-handler-repo",
        created_at=datetime.now(UTC),
    )
    async_session.add(workspace)
    await async_session.commit()

    session_maker = async_sessionmaker(
        bind=async_session.bind,
        expire_on_commit=False,
        autoflush=False,
    )
    monkeypatch.setattr(parse_handler, "async_session_maker", session_maker)

    class StubRunner:
        async def fetch_run_result(self, *, repo_full_name: str, run_id: int):
            assert repo_full_name == "acme/parse-handler-repo"
            assert run_id == 321
            return ActionsRunResult(
                status="passed",
                run_id=321,
                conclusion="success",
                passed=12,
                failed=0,
                total=12,
                stdout="ok",
                stderr=None,
                head_sha="abc321",
                html_url="https://example.test/runs/321",
                raw={"summary": {"passed": 12, "failed": 0}},
            )

    class StubGithubClient:
        async def aclose(self):
            return None

    monkeypatch.setattr(
        parse_handler,
        "_build_actions_runner",
        lambda: (StubRunner(), StubGithubClient()),
    )

    result = await parse_handler.handle_github_workflow_artifact_parse(
        {
            "submissionId": submission.id,
            "candidateSessionId": candidate_session.id,
            "taskId": tasks[1].id,
            "repoFullName": "acme/parse-handler-repo",
            "workflowRunId": 321,
            "workflowRunAttempt": 2,
            "workflowCompletedAt": "2026-03-13T14:00:00Z",
        }
    )

    assert result["status"] == "parsed_and_persisted"

    await async_session.refresh(submission)
    await async_session.refresh(workspace)
    assert submission.workflow_run_id == "321"
    assert submission.workflow_run_attempt == 2
    assert submission.workflow_run_status == "completed"
    assert submission.workflow_run_conclusion == "success"
    assert submission.tests_passed == 12
    assert submission.tests_failed == 0
    assert submission.commit_sha == "abc321"
    assert submission.test_output is not None
    parsed_output = json.loads(submission.test_output)
    assert parsed_output["runId"] == 321
    assert parsed_output["passed"] == 12
    assert parsed_output["failed"] == 0

    assert workspace.last_workflow_run_id == "321"
    assert workspace.last_workflow_conclusion == "success"
    assert workspace.latest_commit_sha == "abc321"
    assert workspace.last_test_summary_json is not None


def test_parse_handler_helpers_cover_edge_cases():
    assert parse_handler._parse_positive_int(True) is None
    assert parse_handler._parse_positive_int(0) is None
    assert parse_handler._parse_positive_int("0") is None
    assert parse_handler._parse_positive_int("-1") is None
    assert parse_handler._parse_positive_int("11") == 11

    assert parse_handler._parse_iso_datetime(None) is None
    assert parse_handler._parse_iso_datetime("  ") is None
    assert parse_handler._parse_iso_datetime("not-a-date") is None
    assert parse_handler._parse_iso_datetime("2026-03-13T14:00:00") == datetime(
        2026,
        3,
        13,
        14,
        0,
        tzinfo=UTC,
    )

    assert parse_handler._normalized_text(123) is None
    assert parse_handler._normalized_text("  hello  ") == "hello"


@pytest.mark.asyncio
async def test_handle_github_workflow_artifact_parse_submission_not_found(
    async_session,
    monkeypatch,
):
    session_maker = async_sessionmaker(
        bind=async_session.bind,
        expire_on_commit=False,
        autoflush=False,
    )
    monkeypatch.setattr(parse_handler, "async_session_maker", session_maker)

    result = await parse_handler.handle_github_workflow_artifact_parse(
        {
            "submissionId": 999999,
            "repoFullName": "acme/parse-handler-repo",
            "workflowRunId": 321,
        }
    )

    assert result["status"] == "submission_not_found"


@pytest.mark.asyncio
async def test_handle_github_workflow_artifact_parse_skips_mismatch_paths(
    async_session,
    monkeypatch,
):
    recruiter = await create_recruiter(
        async_session,
        email="parse-handler-mismatch@tenon.dev",
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
        code_repo_path="acme/parse-handler-repo",
        workflow_run_id="321",
    )
    await async_session.commit()

    session_maker = async_sessionmaker(
        bind=async_session.bind,
        expire_on_commit=False,
        autoflush=False,
    )
    monkeypatch.setattr(parse_handler, "async_session_maker", session_maker)

    candidate_mismatch = await parse_handler.handle_github_workflow_artifact_parse(
        {
            "submissionId": submission.id,
            "candidateSessionId": candidate_session.id + 999,
            "taskId": tasks[1].id,
            "repoFullName": "acme/parse-handler-repo",
            "workflowRunId": 321,
        }
    )
    assert candidate_mismatch["status"] == "skipped_candidate_session_mismatch"

    task_mismatch = await parse_handler.handle_github_workflow_artifact_parse(
        {
            "submissionId": submission.id,
            "candidateSessionId": candidate_session.id,
            "taskId": tasks[1].id + 999,
            "repoFullName": "acme/parse-handler-repo",
            "workflowRunId": 321,
        }
    )
    assert task_mismatch["status"] == "skipped_task_mismatch"

    run_mismatch = await parse_handler.handle_github_workflow_artifact_parse(
        {
            "submissionId": submission.id,
            "candidateSessionId": candidate_session.id,
            "taskId": tasks[1].id,
            "repoFullName": "acme/parse-handler-repo",
            "workflowRunId": 999,
        }
    )
    assert run_mismatch["status"] == "skipped_workflow_run_mismatch"


@pytest.mark.asyncio
async def test_handle_github_workflow_artifact_parse_sets_last_run_when_timestamp_missing(
    async_session,
    monkeypatch,
):
    recruiter = await create_recruiter(
        async_session,
        email="parse-handler-last-run@tenon.dev",
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
        code_repo_path="acme/parse-handler-repo",
        workflow_run_id=None,
        last_run_at=None,
    )
    await async_session.commit()

    session_maker = async_sessionmaker(
        bind=async_session.bind,
        expire_on_commit=False,
        autoflush=False,
    )
    monkeypatch.setattr(parse_handler, "async_session_maker", session_maker)

    class StubRunner:
        async def fetch_run_result(self, *, repo_full_name: str, run_id: int):
            assert repo_full_name == "acme/parse-handler-repo"
            assert run_id == 322
            return ActionsRunResult(
                status="passed",
                run_id=322,
                conclusion=None,
                passed=3,
                failed=0,
                total=3,
                stdout="ok",
                stderr=None,
                head_sha="",
                html_url="https://example.test/runs/322",
                raw={"summary": {"passed": 3, "failed": 0}},
            )

    class StubGithubClient:
        async def aclose(self):
            return None

    monkeypatch.setattr(
        parse_handler,
        "_build_actions_runner",
        lambda: (StubRunner(), StubGithubClient()),
    )

    result = await parse_handler.handle_github_workflow_artifact_parse(
        {
            "submissionId": submission.id,
            "candidateSessionId": candidate_session.id,
            "taskId": tasks[1].id,
            "repoFullName": "acme/parse-handler-repo",
            "workflowRunId": 322,
        }
    )

    assert result["status"] == "parsed_and_persisted"
    await async_session.refresh(submission)
    assert submission.workflow_run_status == "completed"
    assert submission.workflow_run_conclusion is None
    assert submission.workflow_run_completed_at is None
    assert submission.last_run_at is not None


@pytest.mark.asyncio
async def test_build_actions_runner_returns_configured_runner_and_client():
    runner, github_client = parse_handler._build_actions_runner()
    try:
        assert (
            runner.workflow_file
            == parse_handler.settings.github.GITHUB_ACTIONS_WORKFLOW_FILE
        )
        assert runner.poll_interval_seconds == 2.0
        assert runner.max_poll_seconds == 90.0
    finally:
        await github_client.aclose()
