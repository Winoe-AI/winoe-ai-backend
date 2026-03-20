from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.api.routers.simulations_routes import lifecycle as lifecycle_route
from app.api.routers.tasks import helpers as task_helpers
from app.api.routers.tasks import draft as draft_route
from app.repositories.github_native.workspaces import repository as workspace_repo
from app.repositories.jobs import repository as jobs_repo
from app.repositories.recordings import repository as recordings_repo
from app.repositories.recordings.models import RECORDING_ASSET_STATUS_UPLOADED
from app.repositories.simulations import repository_owned
from app.repositories.simulations.simulation import SIMULATION_STATUS_TERMINATED
from app.repositories.transcripts import repository as transcripts_repo
from app.services.candidate_sessions import progress as cs_progress
from app.services.notifications import invite_content
from app.services.submissions import submission_progress
from app.services.submissions.use_cases import codespace_init as codespace_init_use_case
from app.services.submissions.use_cases import (
    codespace_validations,
    submit_workspace as submit_workspace_use_case,
)
from app.services.submissions.use_cases.codespace_init import (
    _validate_codespace_request_with_legacy_fallback,
)
from app.services.submissions.use_cases.submit_workspace import (
    fetch_workspace_and_branch,
)
from app.schemas.task_drafts import TaskDraftUpsertRequest
from tests.factories import (
    create_candidate_session,
    create_company,
    create_recruiter,
    create_simulation,
)


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


class _RowsResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_codespace_validation_falls_back_to_task_lookup(monkeypatch):
    candidate_session = SimpleNamespace(id=7, simulation_id=9)
    task = SimpleNamespace(id=11, simulation_id=9, type="code")
    called = {"belongs": False}

    async def _snapshot(*_args, **_kwargs):
        return ([], set(), None, 0, 0, False)

    monkeypatch.setattr(codespace_validations.cs_service, "progress_snapshot", _snapshot)
    monkeypatch.setattr(
        codespace_validations.submission_service,
        "load_task_or_404",
        _async_return(task),
    )
    monkeypatch.setattr(
        codespace_validations.submission_service,
        "ensure_task_belongs",
        lambda *_args, **_kwargs: called.__setitem__("belongs", True),
    )
    monkeypatch.setattr(
        codespace_validations.cs_service,
        "require_active_window",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        codespace_validations.submission_service,
        "ensure_in_order",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        codespace_validations.submission_service,
        "validate_run_allowed",
        lambda *_args, **_kwargs: None,
    )

    resolved = await codespace_validations.validate_codespace_request(
        object(), candidate_session, task.id
    )
    assert resolved is task
    assert called["belongs"] is True


@pytest.mark.asyncio
async def test_codespace_init_legacy_fallback_path(monkeypatch):
    candidate_session = SimpleNamespace(id=1, simulation_id=2)
    task = SimpleNamespace(id=5, simulation_id=2, type="code")

    async def _raise_missing_tasks(*_args, **_kwargs):
        raise HTTPException(status_code=500, detail="Simulation has no tasks")

    monkeypatch.setattr(
        codespace_init_use_case,
        "validate_codespace_request",
        _raise_missing_tasks,
    )
    monkeypatch.setattr(
        codespace_init_use_case.submission_service,
        "load_task_or_404",
        _async_return(task),
    )
    monkeypatch.setattr(
        codespace_init_use_case.submission_service,
        "ensure_task_belongs",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        codespace_init_use_case.cs_service,
        "require_active_window",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        codespace_init_use_case.cs_service,
        "progress_snapshot",
        _async_return(([], set(), task, 0, 1, False)),
    )
    monkeypatch.setattr(
        codespace_init_use_case.submission_service,
        "ensure_in_order",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        codespace_init_use_case.submission_service,
        "validate_run_allowed",
        lambda *_args, **_kwargs: None,
    )

    resolved = await _validate_codespace_request_with_legacy_fallback(
        object(), candidate_session, task.id
    )
    assert resolved is task


@pytest.mark.asyncio
async def test_codespace_init_legacy_fallback_reraises_unrelated_http_error(monkeypatch):
    async def _raise_not_found(*_args, **_kwargs):
        raise HTTPException(status_code=404, detail="Task not found")

    monkeypatch.setattr(
        codespace_init_use_case,
        "validate_codespace_request",
        _raise_not_found,
    )

    with pytest.raises(HTTPException) as excinfo:
        await _validate_codespace_request_with_legacy_fallback(
            object(),
            SimpleNamespace(id=1, simulation_id=2),
            99,
        )
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_submission_progress_reraises_unrelated_type_error(monkeypatch):
    async def _raise_type_error(*_args, **_kwargs):
        raise TypeError("boom")

    monkeypatch.setattr(
        submission_progress.cs_service,
        "progress_snapshot",
        _raise_type_error,
    )

    with pytest.raises(TypeError):
        await submission_progress.progress_after_submission(
            object(),
            SimpleNamespace(status="in_progress", completed_at=None),
            now=datetime.now(UTC),
            tasks=[],
        )


@pytest.mark.asyncio
async def test_submit_workspace_uses_grouped_lookup_when_available(monkeypatch):
    workspace = SimpleNamespace(default_branch="main")

    class _WorkspaceRepo:
        async def get_by_session_and_task(self, *_args, **_kwargs):
            return None

        async def get_by_session_and_workspace_key(self, *_args, **_kwargs):
            return workspace

    monkeypatch.setattr(
        submit_workspace_use_case.submission_service,
        "workspace_repo",
        _WorkspaceRepo(),
    )
    monkeypatch.setattr(
        submit_workspace_use_case.submission_service,
        "validate_branch",
        lambda branch: branch,
    )

    found, branch = await fetch_workspace_and_branch(
        object(),
        candidate_session_id=1,
        task_id=2,
        payload=SimpleNamespace(branch=None),
        task_day_index=2,
        task_type="code",
    )
    assert found is workspace
    assert branch == "main"


@pytest.mark.asyncio
async def test_candidate_progress_missing_task_guards(monkeypatch):
    monkeypatch.setattr(cs_progress.cs_repo, "tasks_for_simulation", _async_return([]))
    with pytest.raises(HTTPException) as excinfo:
        await cs_progress.load_tasks(object(), 123)
    assert excinfo.value.status_code == 500

    class _NoRowsDB:
        async def execute(self, *_args, **_kwargs):
            return _RowsResult(rows=[])

    with pytest.raises(HTTPException) as excinfo2:
        await cs_progress.load_tasks_with_completion_state(
            _NoRowsDB(),
            simulation_id=123,
            candidate_session_id=456,
        )
    assert excinfo2.value.status_code == 500


@pytest.mark.asyncio
async def test_candidate_progress_load_tasks_returns_tasks(monkeypatch):
    task = SimpleNamespace(id=101, day_index=1, type="code")
    monkeypatch.setattr(cs_progress.cs_repo, "tasks_for_simulation", _async_return([task]))

    tasks = await cs_progress.load_tasks(object(), 1)
    assert tasks == [task]


@pytest.mark.asyncio
async def test_workspace_repo_grouped_lookup_by_key_and_precommit_sha_updates(monkeypatch):
    grouped_workspace = SimpleNamespace(id="ws-grouped")

    async def _group_lookup(*_args, **_kwargs):
        return grouped_workspace

    monkeypatch.setattr(workspace_repo, "get_by_session_and_workspace_key", _group_lookup)

    resolution = workspace_repo.WorkspaceResolution(
        workspace_key="day-2-code",
        uses_grouped_workspace=True,
        workspace_group=None,
        workspace_group_checked=False,
    )
    found = await workspace_repo.get_by_session_and_task(
        object(),
        candidate_session_id=1,
        task_id=2,
        workspace_resolution=resolution,
    )
    assert found is grouped_workspace

    class _DB:
        def __init__(self):
            self.commits = 0
            self.flushes = 0
            self.refreshes = 0

        async def commit(self):
            self.commits += 1

        async def flush(self):
            self.flushes += 1

        async def refresh(self, _workspace):
            self.refreshes += 1

    db = _DB()
    workspace = SimpleNamespace(precommit_sha=None, precommit_details_json='{"no_bundle":true}')
    updated = await workspace_repo.set_precommit_sha(
        db,
        workspace=workspace,
        precommit_sha="sha-1",
        commit=True,
        refresh=True,
    )
    assert updated.precommit_sha == "sha-1"
    assert updated.precommit_details_json is None
    assert db.commits == 1
    assert db.refreshes == 1

    updated = await workspace_repo.set_precommit_sha(
        db,
        workspace=workspace,
        precommit_sha="sha-2",
        commit=False,
        refresh=False,
    )
    assert updated.precommit_sha == "sha-2"
    assert db.flushes == 1


@pytest.mark.asyncio
async def test_jobs_create_or_get_commit_integrity_reraises_when_not_recoverable(monkeypatch):
    async def _load_none(*_args, **_kwargs):
        return None

    class _DB:
        def add(self, _obj):
            return None

        async def commit(self):
            raise IntegrityError("insert", {}, RuntimeError("duplicate"))

        async def rollback(self):
            return None

        async def refresh(self, _obj):
            raise AssertionError("refresh should not run on failed commit")

    monkeypatch.setattr(jobs_repo, "_load_idempotent_job", _load_none)
    with pytest.raises(IntegrityError):
        await jobs_repo.create_or_get_idempotent(
            _DB(),
            job_type="branch_job",
            idempotency_key="branch-key-commit-error",
            payload_json={"a": 1},
            company_id=1,
            commit=True,
        )


@pytest.mark.asyncio
async def test_jobs_create_or_update_many_integrity_recovery_paths(monkeypatch):
    specs = [
        jobs_repo.IdempotentJobSpec(
            job_type="batch_type_a",
            idempotency_key="batch-key-a",
            payload_json={"a": 1},
        ),
        jobs_repo.IdempotentJobSpec(
            job_type="batch_type_b",
            idempotency_key="batch-key-b",
            payload_json={"b": 1},
        ),
        jobs_repo.IdempotentJobSpec(
            job_type="batch_type_c",
            idempotency_key="batch-key-c",
            payload_json={"c": 1},
        ),
    ]

    async def _load_for_keys(*_args, **_kwargs):
        return {}

    load_one_values = iter(
        [
            SimpleNamespace(id="existing-a"),  # First spec resolves immediately.
            None,  # Second spec enters nested insert path.
            SimpleNamespace(id="existing-b"),  # Second spec conflict recovery.
            None,  # Third spec enters nested insert path and succeeds.
        ]
    )

    async def _load_one(*_args, **_kwargs):
        return next(load_one_values)

    monkeypatch.setattr(jobs_repo, "_load_idempotent_jobs_for_keys", _load_for_keys)
    monkeypatch.setattr(jobs_repo, "_load_idempotent_job", _load_one)

    class _Nested:
        def __init__(self, db):
            self.db = db

        async def __aenter__(self):
            self.db.in_nested = True
            return self

        async def __aexit__(self, exc_type, exc, tb):
            self.db.in_nested = False
            return False

    class _DB:
        def __init__(self):
            self.in_nested = False
            self.nested_flush_calls = 0
            self.final_flush_calls = 0
            self.added = []

        async def execute(self, *_args, **_kwargs):
            raise IntegrityError("insert", {}, RuntimeError("race"))

        def begin_nested(self):
            return _Nested(self)

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            if self.in_nested:
                self.nested_flush_calls += 1
                if self.nested_flush_calls == 1:
                    raise IntegrityError("nested", {}, RuntimeError("race"))
            else:
                self.final_flush_calls += 1

    db = _DB()
    resolved = await jobs_repo.create_or_update_many_idempotent(
        db,
        company_id=1,
        jobs=specs,
        commit=False,
    )
    assert len(resolved) == 3
    assert db.nested_flush_calls == 2
    assert db.final_flush_calls == 1
    assert len(db.added) == 2


@pytest.mark.asyncio
async def test_jobs_claim_next_runnable_exhausts_conflicts(monkeypatch):
    del monkeypatch  # unused, retained for consistent test signature style

    class _ClaimResult:
        def __init__(self, *, first_row=None, rowcount=0):
            self._first = first_row
            self.rowcount = rowcount

        def first(self):
            return self._first

    class _DB:
        def __init__(self):
            self.calls = 0
            self.rollbacks = 0
            self.commits = 0

        async def execute(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls % 2 == 1:
                return _ClaimResult(first_row=SimpleNamespace(id="job-1", attempt=0))
            return _ClaimResult(rowcount=0)

        async def rollback(self):
            self.rollbacks += 1

        async def commit(self):
            self.commits += 1

    db = _DB()
    claimed = await jobs_repo.claim_next_runnable(
        db,
        worker_id="worker-conflict",
        now=datetime.now(UTC),
        lease_seconds=30,
    )
    assert claimed is None
    assert db.rollbacks == 8
    assert db.commits == 0


@pytest.mark.asyncio
async def test_jobs_create_or_update_many_reraises_when_recovery_lookup_missing(monkeypatch):
    specs = [
        jobs_repo.IdempotentJobSpec(
            job_type="batch_type_recover",
            idempotency_key="batch-key-recover",
            payload_json={"x": 1},
        )
    ]

    async def _load_for_keys(*_args, **_kwargs):
        return {}

    async def _load_none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(jobs_repo, "_load_idempotent_jobs_for_keys", _load_for_keys)
    monkeypatch.setattr(jobs_repo, "_load_idempotent_job", _load_none)

    class _Nested:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _DB:
        async def execute(self, *_args, **_kwargs):
            raise IntegrityError("insert", {}, RuntimeError("race"))

        def begin_nested(self):
            return _Nested()

        def add(self, _obj):
            return None

        async def flush(self):
            raise IntegrityError("nested", {}, RuntimeError("race"))

    with pytest.raises(IntegrityError):
        await jobs_repo.create_or_update_many_idempotent(
            _DB(),
            company_id=1,
            jobs=specs,
            commit=False,
        )


@pytest.mark.asyncio
async def test_simulation_lifecycle_routes_cover_response_paths(monkeypatch):
    activated_at = datetime.now(UTC)
    terminated_at = datetime.now(UTC)
    simulation = SimpleNamespace(
        id=44,
        status="active",
        activated_at=activated_at,
        terminated_at=terminated_at,
    )
    terminated = SimpleNamespace(simulation=simulation, cleanup_job_ids=["job-1"])

    monkeypatch.setattr(
        lifecycle_route, "ensure_recruiter_or_none", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        lifecycle_route.sim_service,
        "activate_simulation",
        _async_return(simulation),
    )
    monkeypatch.setattr(
        lifecycle_route.sim_service,
        "terminate_simulation_with_cleanup",
        _async_return(terminated),
    )
    monkeypatch.setattr(
        lifecycle_route.sim_service,
        "normalize_simulation_status_or_raise",
        lambda _status: "active_inviting",
    )

    payload = SimpleNamespace(confirm=True, reason="cleanup")
    user = SimpleNamespace(id=7)
    activated = await lifecycle_route.activate_simulation(44, payload, object(), user)
    terminated_response = await lifecycle_route.terminate_simulation(
        44, payload, object(), user
    )
    assert activated.status == "active_inviting"
    assert activated.activatedAt == activated_at
    assert terminated_response.status == "active_inviting"
    assert terminated_response.terminatedAt == terminated_at
    assert terminated_response.cleanupJobIds == ["job-1"]


@pytest.mark.asyncio
async def test_invite_content_handles_naive_expiration_datetime():
    simulation = SimpleNamespace(title="Backend Pass", role="Engineer")
    subject, text, html = invite_content.invite_email_content(
        candidate_name="Casey",
        invite_url="https://example.com/invite/123",
        simulation=simulation,
        expires_at=datetime(2026, 3, 21, 12, 0, 0),  # intentionally naive
    )
    assert "Backend Pass" in subject
    assert "2026-03-21" in text
    assert "2026-03-21" in html


@pytest.mark.asyncio
async def test_tasks_concurrency_guard_skips_limiter_when_disabled(monkeypatch):
    class _Limiter:
        def concurrency_guard(self, *_args, **_kwargs):
            raise AssertionError("limiter should not be called when disabled")

    monkeypatch.setattr(task_helpers.rate_limit, "rate_limit_enabled", lambda: False)
    monkeypatch.setattr(task_helpers.rate_limit, "limiter", _Limiter())

    async with task_helpers._concurrency_guard("session:1", 1):
        pass


@pytest.mark.asyncio
async def test_repository_owned_for_update_and_include_terminated_filter(async_session):
    recruiter = await create_recruiter(async_session, email="owned-filter@test.com")
    simulation, _ = await create_simulation(async_session, created_by=recruiter)

    owned = await repository_owned.get_owned(
        async_session,
        simulation.id,
        recruiter.id,
        for_update=True,
    )
    assert owned is not None

    simulation.status = SIMULATION_STATUS_TERMINATED
    await async_session.commit()

    filtered_sim, filtered_tasks = await repository_owned.get_owned_with_tasks(
        async_session,
        simulation.id,
        recruiter.id,
        include_terminated=False,
    )
    assert filtered_sim is None
    assert filtered_tasks == []


@pytest.mark.asyncio
async def test_transcript_repository_commit_true_paths(async_session):
    recruiter = await create_recruiter(async_session, email="transcript-pass2@test.com")
    simulation, tasks = await create_simulation(async_session, created_by=recruiter)
    candidate_session = await create_candidate_session(
        async_session,
        simulation=simulation,
    )
    recording = await recordings_repo.create_recording_asset(
        async_session,
        candidate_session_id=candidate_session.id,
        task_id=tasks[0].id,
        storage_key="recordings/pass2.mp4",
        content_type="video/mp4",
        bytes_count=1024,
        status=RECORDING_ASSET_STATUS_UPLOADED,
        commit=True,
    )

    transcript, created = await transcripts_repo.get_or_create_transcript(
        async_session,
        recording_id=recording.id,
        status="pending",
        commit=True,
    )
    assert created is True
    assert transcript.id is not None

    deleted = await transcripts_repo.mark_deleted(
        async_session,
        transcript=transcript,
        commit=True,
    )
    assert deleted.deleted_at is not None

    removed_count = await transcripts_repo.hard_delete_by_recording_id(
        async_session,
        recording.id,
        commit=True,
    )
    assert removed_count == 1


@pytest.mark.asyncio
async def test_draft_route_progress_snapshot_missing_task_returns_404(monkeypatch):
    async def _snapshot(*_args, **_kwargs):
        return ([], set(), None, 0, 0, False)

    monkeypatch.setattr(draft_route.cs_service, "progress_snapshot", _snapshot)

    with pytest.raises(HTTPException) as excinfo:
        await draft_route.put_task_draft_route(
            task_id=9,
            payload=TaskDraftUpsertRequest(contentText="x", contentJson=None),
            candidate_session=SimpleNamespace(id=1, simulation_id=2),
            db=SimpleNamespace(),
        )
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_draft_route_commits_when_db_supports_commit(monkeypatch):
    task = SimpleNamespace(id=9, simulation_id=2)
    draft = SimpleNamespace(updated_at=datetime.now(UTC))
    committed = {"count": 0}

    async def _snapshot(*_args, **_kwargs):
        return ([task], set(), task, 0, 1, False)

    async def _upsert(*_args, **_kwargs):
        return draft

    class _DB:
        async def commit(self):
            committed["count"] += 1

    monkeypatch.setattr(draft_route.cs_service, "progress_snapshot", _snapshot)
    monkeypatch.setattr(
        draft_route.cs_service,
        "require_active_window",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        draft_route,
        "validate_draft_payload_size",
        lambda **_kwargs: (1, 1),
    )
    monkeypatch.setattr(draft_route.task_drafts_repo, "upsert_draft", _upsert)

    response = await draft_route.put_task_draft_route(
        task_id=task.id,
        payload=TaskDraftUpsertRequest(contentText="x", contentJson=None),
        candidate_session=SimpleNamespace(id=1, simulation_id=2),
        db=_DB(),
    )
    assert response.taskId == task.id
    assert committed["count"] == 1


@pytest.mark.asyncio
async def test_jobs_repository_branch_gaps(async_session, monkeypatch):
    company = await create_company(async_session, name="Jobs Branch Co")
    company_id = company.id
    original_load_idempotent_job = jobs_repo._load_idempotent_job
    existing = await jobs_repo.create_or_get_idempotent(
        async_session,
        job_type="branch_job",
        idempotency_key="branch-key",
        payload_json={"a": 1},
        company_id=company_id,
    )
    existing_id = existing.id

    candidate_principal = SimpleNamespace(
        permissions=["candidate:access"],
        claims={"email_verified": True},
        email=" ",
        sub="candidate-sub",
    )
    assert (
        await jobs_repo.get_by_id_for_principal(
            async_session, existing_id, candidate_principal
        )
        is None
    )

    no_access_principal = SimpleNamespace(
        permissions=["viewer"],
        claims={},
        email="viewer@example.com",
        sub="viewer-sub",
    )
    assert (
        await jobs_repo.get_by_id_for_principal(
            async_session, existing_id, no_access_principal
        )
        is None
    )

    spec = jobs_repo.IdempotentJobSpec(
        job_type="spec_type",
        idempotency_key="spec-key",
        payload_json={"v": 1},
    )
    job_from_spec = jobs_repo._job_from_spec(company_id=company_id, spec=spec)
    assert job_from_spec.job_type == "spec_type"
    assert job_from_spec.idempotency_key == "spec-key"

    assert (
        await jobs_repo._load_idempotent_jobs_for_keys(
            async_session,
            company_id=company_id,
            keys=[],
        )
        == {}
    )

    async def _load_none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(jobs_repo, "_load_idempotent_job", _load_none)
    with pytest.raises(IntegrityError):
        await jobs_repo.create_or_get_idempotent(
            async_session,
            job_type="branch_job",
            idempotency_key="branch-key",
            payload_json={"a": 2},
            company_id=company_id,
            commit=False,
        )

    calls = {"count": 0}

    async def _load_side_effect(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return None
        return SimpleNamespace(id=existing_id)

    monkeypatch.setattr(jobs_repo, "_load_idempotent_job", _load_side_effect)
    recovered = await jobs_repo.create_or_get_idempotent(
        async_session,
        job_type="branch_job",
        idempotency_key="branch-key",
        payload_json={"a": 3},
        company_id=company_id,
        commit=True,
    )
    assert recovered.id == existing_id
    monkeypatch.setattr(
        jobs_repo, "_load_idempotent_job", original_load_idempotent_job
    )

    updated = await jobs_repo.create_or_update_idempotent(
        async_session,
        job_type="branch_job",
        idempotency_key="branch-key",
        payload_json={"a": 4},
        company_id=company_id,
        commit=False,
    )
    assert updated.payload_json == {"a": 4}

    created = await jobs_repo.create_or_update_idempotent(
        async_session,
        job_type="branch_new",
        idempotency_key="branch-new-key",
        payload_json={"b": 1},
        company_id=company_id,
        commit=False,
    )
    assert created.job_type == "branch_new"
    assert created.idempotency_key == "branch-new-key"

    resolved = await jobs_repo.create_or_update_many_idempotent(
        async_session,
        company_id=company_id,
        jobs=[],
        commit=False,
    )
    assert resolved == []

    class _ClaimResult:
        def __init__(self, *, first_row=None, rowcount=0):
            self._first = first_row
            self.rowcount = rowcount

        def first(self):
            return self._first

    class _ClaimDB:
        def __init__(self):
            self.calls = 0
            self.rollback_count = 0

        async def execute(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return _ClaimResult(
                    first_row=SimpleNamespace(
                        id="job-1",
                        attempt=0,
                    )
                )
            return _ClaimResult(rowcount=0)

        async def commit(self):
            return None

        async def rollback(self):
            self.rollback_count += 1

    claim_db = _ClaimDB()
    claimed = await jobs_repo.claim_next_runnable(
        claim_db,
        worker_id="worker-1",
        now=datetime.now(UTC),
        lease_seconds=30,
    )
    assert claimed is None
    assert claim_db.rollback_count == 1
