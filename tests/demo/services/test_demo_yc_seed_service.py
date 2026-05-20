from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.candidates.candidate_sessions.repositories.candidates_candidate_sessions_repositories_candidates_candidate_sessions_day_audit_model import (
    CandidateDayAudit,
)
from app.evaluations.repositories.evaluations_repositories_evaluations_core_model import (
    EvaluationDayScore,
    EvaluationReviewerReport,
    EvaluationRun,
)
from app.evaluations.repositories.evaluations_repositories_evaluations_create_run_with_scores_repository import (
    create_run_with_day_scores,
)
from app.evaluations.services.evaluations_services_evaluations_winoe_report_api_service import (
    fetch_winoe_report,
)
from app.integrations.github import FakeGithubClient
from app.media.repositories.recordings.media_repositories_recordings_media_recordings_core_model import (
    RecordingAsset,
)
from app.media.repositories.transcripts.media_repositories_transcripts_media_transcripts_core_model import (
    Transcript,
)
from app.shared.database.shared_database_models_model import (
    CandidateSession,
    Company,
    ScenarioVersion,
    Submission,
    Task,
    Trial,
    User,
    WinoeReport,
)
from app.submissions.repositories.github_native.workspaces.submissions_repositories_github_native_workspaces_submissions_github_native_workspaces_core_model import (
    Workspace,
    WorkspaceGroup,
)
from app.submissions.repositories.submissions_repositories_submissions_winoe_report_citation_model import (
    WinoeReportCitation,
)
from app.submissions.repositories.submissions_repositories_submissions_winoe_report_repository import (
    upsert_marker,
)
from scripts import seed_demo as seed_demo_script
from tests.shared.factories import (
    create_candidate_session,
    create_talent_partner,
    create_trial,
)


class _SharedSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False


class _SharedSessionMaker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return _SharedSessionContext(self._session)


def _session_maker(async_session):
    return _SharedSessionMaker(async_session)


def _seed_args(
    *,
    reset_db: bool = False,
    talent_partner_email: str = "demo@winoe.ai",
    talent_partner_name: str = "Demo Partner",
    company_name: str = "Acme",
    github_provider: str = "fake",
    allow_production_write: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        reset_db=reset_db,
        talent_partner_email=talent_partner_email,
        talent_partner_name=talent_partner_name,
        company_name=company_name,
        github_provider=github_provider,
        allow_production_write=allow_production_write,
    )


def _assert_no_retired_terms(text: str) -> None:
    denylist = [
        "te" "non",
        "si" "muhire",
        "re" "cruiter",
        "simu" "lation",
        "fit " "profile",
        "fit_" "profile",
        "fit " "score",
        "fit_" "score",
        "tem" + "plate",
        "tem" + "plate" + "_catalog",
        "pre" + "commit",
        "spe" + "cializor",
        "codespace " + "specification",
        "codespace" + "_spec",
        "starter " + "code",
        "pre-populated " + "codebase",
    ]
    lowered = text.lower()
    for term in denylist:
        assert term not in lowered


async def _assert_evidence_links(
    *,
    reviewer_reports: list[dict[str, object]],
) -> None:
    for reviewer_report in reviewer_reports:
        evidence_citations = reviewer_report.get("evidenceCitations") or []
        assert evidence_citations
        for citation in evidence_citations:
            assert isinstance(citation, dict)
            kind = citation.get("kind")
            ref = citation.get("ref")
            dimension_key = citation.get("dimensionKey")
            dimension_label = citation.get("dimensionLabel")
            assert isinstance(kind, str) and kind
            assert isinstance(ref, str) and ref
            assert isinstance(dimension_key, str) and dimension_key
            assert isinstance(dimension_label, str) and dimension_label
            if kind in {"commit", "diff", "commit_range"}:
                sha_prefix = ref.split(":", 1)[0]
                assert len(sha_prefix) == 40
                continue
            if kind in {"rubric", "submission"}:
                assert re.search(r":L\d+(?:-L?\d+)?$", ref)
                continue
            if kind == "tests":
                assert ref == "day2-tests.txt:L1-L4"
                continue
            if kind == "transcript":
                assert ref.endswith("02:14-02:48")
                continue
            raise AssertionError(f"unexpected evidence citation kind: {kind}")


@pytest.mark.asyncio
async def test_seed_demo_cli_creates_complete_dataset_and_is_idempotent(
    async_session, monkeypatch, capsys
):
    monkeypatch.setattr(seed_demo_script, "_run_migrations", lambda _root: None)
    monkeypatch.setattr(
        seed_demo_script,
        "async_session_maker",
        _session_maker(async_session),
    )
    monkeypatch.setattr(
        seed_demo_script, "_build_github_client", lambda _mode: FakeGithubClient()
    )

    args = _seed_args()
    await seed_demo_script._main_async(args)
    async_session.expire_all()
    await seed_demo_script._main_async(args)

    output = capsys.readouterr().out
    assert "demo-scoped refresh only" in output
    assert "using GitHub provider=fake" in output

    company_count = await async_session.scalar(
        select(func.count()).select_from(Company)
    )
    user_count = await async_session.scalar(select(func.count()).select_from(User))
    trial_count = await async_session.scalar(select(func.count()).select_from(Trial))
    candidate_session_count = await async_session.scalar(
        select(func.count()).select_from(CandidateSession)
    )
    submission_count = await async_session.scalar(
        select(func.count()).select_from(Submission)
    )
    report_count = await async_session.scalar(
        select(func.count()).select_from(WinoeReport)
    )
    citation_count = await async_session.scalar(
        select(func.count()).select_from(WinoeReportCitation)
    )
    run_count = await async_session.scalar(
        select(func.count()).select_from(EvaluationRun)
    )
    day_score_count = await async_session.scalar(
        select(func.count()).select_from(EvaluationDayScore)
    )
    reviewer_count = await async_session.scalar(
        select(func.count()).select_from(EvaluationReviewerReport)
    )
    workspace_count = await async_session.scalar(
        select(func.count()).select_from(Workspace)
    )
    workspace_group_count = await async_session.scalar(
        select(func.count()).select_from(WorkspaceGroup)
    )
    recording_count = await async_session.scalar(
        select(func.count()).select_from(RecordingAsset)
    )
    transcript_count = await async_session.scalar(
        select(func.count()).select_from(Transcript)
    )
    audit_count = await async_session.scalar(
        select(func.count()).select_from(CandidateDayAudit)
    )
    scenario_version_count = await async_session.scalar(
        select(func.count()).select_from(ScenarioVersion)
    )
    task_count = await async_session.scalar(select(func.count()).select_from(Task))

    assert company_count == 1
    assert user_count == 1
    assert trial_count == 3
    assert candidate_session_count == 4
    assert submission_count == 5
    assert report_count == 1
    assert run_count == 1
    assert day_score_count == 5
    assert reviewer_count == 5
    assert workspace_count == 1
    assert workspace_group_count == 1
    assert recording_count == 1
    assert transcript_count == 1
    assert audit_count == 2
    assert citation_count and citation_count > 0
    assert scenario_version_count == 3
    assert task_count == 15

    talent_partner = await async_session.scalar(
        select(User).where(User.email == "demo@winoe.ai")
    )
    assert talent_partner is not None

    trial = await async_session.scalar(
        select(Trial).where(Trial.title == "Senior Frontend Engineer Trial")
    )
    assert trial is not None
    assert trial.scenario_template == ""
    assert trial.status == "completed"
    assert "from-scratch product surface" in trial.focus
    assert trial.company_context == {
        "companyName": "Acme",
        "preferredLanguageFramework": "TypeScript + React",
        "demoMode": "yc-demo",
    }
    assert isinstance(trial.company_rubric_json, dict)
    assert set(trial.company_rubric_json).issuperset(
        {
            "designDocReviewer",
            "codeImplementationReviewer",
            "demoPresentationReviewer",
            "reflectionEssayReviewer",
            "winoeReport",
        }
    )
    assert all(
        isinstance(trial.company_rubric_json[key], dict)
        for key in (
            "designDocReviewer",
            "codeImplementationReviewer",
            "demoPresentationReviewer",
            "reflectionEssayReviewer",
            "winoeReport",
        )
    )

    brief_text = await async_session.scalar(
        select(ScenarioVersion.project_brief_md).where(
            ScenarioVersion.trial_id == trial.id
        )
    )
    assert brief_text is not None
    assert "Project Brief" in brief_text
    assert "from-scratch work Trial" in brief_text
    _assert_no_retired_terms(str(brief_text))

    candidate_sessions = (
        (
            await async_session.execute(
                select(CandidateSession).order_by(CandidateSession.id)
            )
        )
        .scalars()
        .all()
    )
    assert [row.candidate_name for row in candidate_sessions] == [
        "Marcus Okonjo",
        "Priya Patel",
        "Sarah Chen",
        "Nina Alvarez",
    ]
    assert [row.status for row in candidate_sessions] == [
        "not_started",
        "not_started",
        "completed",
        "not_started",
    ]
    assert [row.completed_at is not None for row in candidate_sessions] == [
        False,
        False,
        True,
        False,
    ]
    assert [len(row.day_windows_json or []) for row in candidate_sessions] == [
        0,
        0,
        5,
        0,
    ]
    awaiting_trial = await async_session.scalar(
        select(Trial).where(Trial.id == candidate_sessions[3].trial_id)
    )
    assert awaiting_trial is not None
    assert awaiting_trial.status == "active_inviting"
    assert candidate_sessions[3].status == "not_started"
    assert candidate_sessions[3].completed_at is None
    assert [day["status"] for day in candidate_sessions[2].day_windows_json or []] == [
        "submitted",
        "submitted",
        "submitted",
        "submitted",
        "submitted",
    ]

    submission_rows = (
        await async_session.execute(
            select(Submission, Task.day_index)
            .join(Task, Submission.task_id == Task.id)
            .order_by(Submission.candidate_session_id, Task.day_index)
        )
    ).all()
    assert len(submission_rows) == 5
    expected_artifacts = {
        1: "design_document",
        2: "implementation_kickoff",
        3: "implementation_wrap_up",
        4: "handoff_transcript",
        5: "reflection_essay",
    }
    per_candidate_day_indexes: dict[int, list[int]] = {}
    for submission, day_index in submission_rows:
        per_candidate_day_indexes.setdefault(
            submission.candidate_session_id, []
        ).append(day_index)
        assert submission.content_json["artifactType"] == expected_artifacts[day_index]
        if day_index == 4:
            assert submission.recording_id is not None
            assert (
                submission.content_json["transcriptRecordingId"]
                == submission.recording_id
            )
    assert all(days == [1, 2, 3, 4, 5] for days in per_candidate_day_indexes.values())

    recording_rows = (
        (
            await async_session.execute(
                select(RecordingAsset).order_by(RecordingAsset.candidate_session_id)
            )
        )
        .scalars()
        .all()
    )
    transcript_rows = (
        (
            await async_session.execute(
                select(Transcript).order_by(Transcript.recording_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(recording_rows) == 1
    assert len(transcript_rows) == 1

    reports = (
        (await async_session.execute(select(WinoeReport).order_by(WinoeReport.id)))
        .scalars()
        .all()
    )
    assert len(reports) == 1

    first_report = await fetch_winoe_report(
        async_session,
        candidate_session_id=candidate_sessions[2].id,
        user=talent_partner,
    )

    assert first_report["status"] == "ready"
    report = first_report["report"]
    assert isinstance(report["overallWinoeScore"], float)
    assert len(report["dayScores"]) == 5
    assert len(report["reviewerReports"]) == 5
    assert len(report["dimensions"]) == 8
    assert len(report["citations"]) == 16
    assert report["verdictOneLiner"]
    assert report["narrativeAssessment"]
    assert report["cohortContext"]
    assert [dimension["name"] for dimension in report["dimensions"]] == [
        "Architecture & Design",
        "Problem Understanding",
        "Implementation Quality",
        "Code Quality",
        "Testing Discipline",
        "Development Process",
        "Communication",
        "Reflection & Ownership",
    ]
    assert {citation["dimension"] for citation in report["citations"]} == {
        "Architecture & Design",
        "Problem Understanding",
        "Implementation Quality",
        "Code Quality",
        "Testing Discipline",
        "Development Process",
        "Communication",
        "Reflection & Ownership",
    }
    assert any(
        isinstance(citation, dict) and citation.get("dimensionKey")
        for day_score in report["dayScores"]
        for citation in day_score["evidence"]
    )
    assert {
        citation.get("dimensionKey")
        for day_score in report["dayScores"]
        for citation in day_score["evidence"]
        if isinstance(citation, dict) and citation.get("dimensionKey")
    }.issuperset(
        {
            "architectural_coherence",
            "scope_control",
            "implementation_discipline",
            "testing_discipline",
            "code_quality",
            "dependency_hygiene",
            "communication_handoff_demo",
            "evidence_trail_traceability",
            "reflection_self_awareness",
            "growth_orientation",
        }
    )
    for reviewer_report in report["reviewerReports"]:
        assert reviewer_report["dimensionalScores"]
        assert len(reviewer_report["dimensionalScores"]) >= 8
        assert reviewer_report["strengths"]
        assert reviewer_report["concerns"]
    await _assert_evidence_links(
        reviewer_reports=report["reviewerReports"],
    )

    submission_texts = (
        (await async_session.execute(select(Submission.content_text))).scalars().all()
    )
    for submission_text in submission_texts:
        if submission_text:
            _assert_no_retired_terms(str(submission_text))

    checklist_text = (
        Path(__file__).resolve().parents[3] / "YC_DEMO_CHECKLIST.md"
    ).read_text(encoding="utf-8")
    _assert_no_retired_terms(checklist_text)


@pytest.mark.asyncio
async def test_seed_demo_cli_accepts_custom_talent_partner_email_and_lists_trials(
    async_client, async_session, monkeypatch
):
    custom_email = "winoetalentpartner@gmail.com"
    monkeypatch.setattr(seed_demo_script, "_run_migrations", lambda _root: None)
    monkeypatch.setattr(
        seed_demo_script,
        "async_session_maker",
        _session_maker(async_session),
    )
    monkeypatch.setattr(
        seed_demo_script, "_build_github_client", lambda _mode: FakeGithubClient()
    )

    await seed_demo_script._main_async(
        _seed_args(
            talent_partner_email=custom_email,
            talent_partner_name="TalentPartner",
            company_name="Acme",
        )
    )

    talent_partner = await async_session.scalar(
        select(User).where(User.email == custom_email)
    )
    assert talent_partner is not None
    assert talent_partner.name == "TalentPartner"

    allowed_statuses = {"not_started", "in_progress", "completed", "expired"}
    active_trial = await async_session.scalar(
        select(Trial).where(Trial.title == "Senior Backend Engineer Trial")
    )
    awaiting_trial = await async_session.scalar(
        select(Trial).where(Trial.title == "Staff Engineer Trial")
    )
    assert active_trial is not None
    assert awaiting_trial is not None

    active_res = await async_client.get(
        f"/api/trials/{active_trial.id}/candidates",
        headers={"x-dev-user-email": custom_email},
    )
    awaiting_res = await async_client.get(
        f"/api/trials/{awaiting_trial.id}/candidates",
        headers={"x-dev-user-email": custom_email},
    )
    assert active_res.status_code == 200
    assert awaiting_res.status_code == 200

    active_rows = active_res.json()
    awaiting_rows = awaiting_res.json()
    assert active_rows
    assert awaiting_rows
    assert {row["status"] for row in active_rows} == {"not_started"}
    assert {row["status"] for row in awaiting_rows} == {"not_started"}
    assert all(row["status"] in allowed_statuses for row in active_rows)
    assert all(row["status"] in allowed_statuses for row in awaiting_rows)


@pytest.mark.asyncio
async def test_demo_rerun_preserves_non_demo_rows(async_session, monkeypatch):
    monkeypatch.setattr(seed_demo_script, "_run_migrations", lambda _root: None)
    monkeypatch.setattr(
        seed_demo_script,
        "async_session_maker",
        _session_maker(async_session),
    )
    monkeypatch.setattr(
        seed_demo_script, "_build_github_client", lambda _mode: FakeGithubClient()
    )

    await seed_demo_script._main_async(_seed_args())

    other_partner = await create_talent_partner(
        async_session,
        email="operator@acme.example",
        company_name="Acme Research",
        name="Acme Operator",
    )
    other_trial, _other_tasks = await create_trial(
        async_session,
        created_by=other_partner,
        title="Non Demo Trial",
        role="Backend Engineer",
        focus="Outside the demo scope",
        company_context={"demoMode": "not-demo"},
    )
    now = datetime.now(UTC)
    other_candidate_session = await create_candidate_session(
        async_session,
        trial=other_trial,
        candidate_name="Other Candidate",
        invite_email="other@example.com",
        candidate_email="other@example.com",
        status="completed",
        completed_at=now,
        started_at=now,
    )
    await create_run_with_day_scores(
        async_session,
        candidate_session_id=other_candidate_session.id,
        scenario_version_id=other_candidate_session.scenario_version_id,
        model_name="gpt-5.2",
        model_version="gpt-5.2",
        prompt_version="demo",
        rubric_version="demo",
        day2_checkpoint_sha="a" * 40,
        day3_final_sha="b" * 40,
        cutoff_commit_sha="b" * 40,
        transcript_reference="transcript:other",
        day_scores=[
            {
                "day_index": 1,
                "score": 0.5,
                "rubric_results_json": {"signal": 0.5},
                "evidence_pointers_json": [],
            }
        ],
        overall_winoe_score=0.5,
        recommendation="positive_signal",
        confidence=0.5,
        generated_at=now,
        raw_report_json={"overallWinoeScore": 0.5, "dimensions": [], "citations": []},
        status="completed",
        started_at=now,
        completed_at=now,
        commit=False,
    )
    await upsert_marker(
        async_session,
        candidate_session_id=other_candidate_session.id,
        generated_at=now,
        commit=False,
    )
    await async_session.commit()

    await seed_demo_script._main_async(_seed_args())

    other_company_count = await async_session.scalar(
        select(func.count()).select_from(Company).where(Company.name == "Acme Research")
    )
    other_user_count = await async_session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.email == "operator@acme.example")
    )
    demo_company_count = await async_session.scalar(
        select(func.count()).select_from(Company).where(Company.name == "Acme")
    )
    demo_user_count = await async_session.scalar(
        select(func.count()).select_from(User).where(User.email == "demo@winoe.ai")
    )

    assert other_company_count == 1
    assert other_user_count == 1
    assert demo_company_count == 1
    assert demo_user_count == 1


@pytest.mark.asyncio
async def test_seed_demo_reset_path_prints_full_reset_and_calls_reset_database(
    async_session, monkeypatch, capsys
):
    monkeypatch.setattr(
        seed_demo_script,
        "async_session_maker",
        _session_maker(async_session),
    )
    monkeypatch.setattr(
        seed_demo_script, "_build_github_client", lambda _mode: FakeGithubClient()
    )

    called = []

    async def _fake_drop(_engine):
        called.append("drop")

    async def _fake_reset(_engine):
        called.append("reset")

    def _fake_migrations(_root):
        called.append("migrations")

    monkeypatch.setattr(seed_demo_script, "_drop_existing_schema", _fake_drop)
    monkeypatch.setattr(seed_demo_script, "_run_migrations", _fake_migrations)
    monkeypatch.setattr(seed_demo_script, "_reset_database", _fake_reset)

    await seed_demo_script._main_async(_seed_args(reset_db=True))

    output = capsys.readouterr().out
    assert "full database reset requested" in output
    assert "using GitHub provider=fake" in output
    assert called == ["drop", "migrations", "reset"]


def test_fake_provider_mode_uses_fake_client_without_real_credentials(monkeypatch):
    class _RealClientShouldNotBeConstructed:
        def __init__(self, *args, **kwargs):
            raise AssertionError("real GitHub client should not be constructed")

    monkeypatch.setattr(
        seed_demo_script, "GithubClient", _RealClientShouldNotBeConstructed
    )
    client = seed_demo_script._build_github_client("fake")
    assert isinstance(client, FakeGithubClient)


def test_real_provider_mode_requires_github_config(monkeypatch):
    monkeypatch.setattr(seed_demo_script.settings.github, "GITHUB_ORG", "")
    monkeypatch.setattr(seed_demo_script.settings.github, "GITHUB_TOKEN", "")

    with pytest.raises(RuntimeError, match="WINOE_GITHUB_ORG and WINOE_GITHUB_TOKEN"):
        seed_demo_script._build_github_client("real")


def test_demo_seed_reset_is_blocked_in_production_like_env(monkeypatch):
    monkeypatch.setenv("WINOE_ENV", "production")
    with pytest.raises(RuntimeError, match="production-like environment"):
        seed_demo_script._ensure_safe_environment(
            reset_requested=True, allow_production_write=False
        )


@pytest.mark.asyncio
async def test_real_provider_validation_happens_before_reset(monkeypatch):
    monkeypatch.setattr(seed_demo_script, "_run_migrations", lambda _root: None)

    called = {"reset": False}

    async def _fake_reset(_engine):
        called["reset"] = True

    def _raise_missing_creds(_mode):
        raise RuntimeError(
            "Real GitHub provider mode requires WINOE_GITHUB_ORG and WINOE_GITHUB_TOKEN."
        )

    monkeypatch.setattr(seed_demo_script, "_reset_database", _fake_reset)
    monkeypatch.setattr(seed_demo_script, "_build_github_client", _raise_missing_creds)

    with pytest.raises(RuntimeError, match="WINOE_GITHUB_ORG and WINOE_GITHUB_TOKEN"):
        await seed_demo_script._main_async(
            _seed_args(reset_db=True, github_provider="real")
        )

    assert called["reset"] is False


@pytest.mark.asyncio
async def test_real_provider_org_preflight_happens_before_reset(monkeypatch):
    monkeypatch.setattr(seed_demo_script, "_run_migrations", lambda _root: None)

    called = {"reset": False}

    async def _fake_reset(_engine):
        called["reset"] = True

    class _RealClientStub:
        async def get_authenticated_user_login(self):
            return "demo-user"

        async def _get_json(self, _path):
            raise RuntimeError("GitHub API error (404)")

    monkeypatch.setattr(seed_demo_script, "_reset_database", _fake_reset)
    monkeypatch.setattr(
        seed_demo_script, "_build_github_client", lambda _mode: _RealClientStub()
    )

    with pytest.raises(RuntimeError, match="GitHub API error"):
        await seed_demo_script._main_async(
            _seed_args(reset_db=True, github_provider="real")
        )

    assert called["reset"] is False


def test_checklist_contains_seed_command_and_current_winoe_language():
    checklist_text = (
        Path(__file__).resolve().parents[3] / "YC_DEMO_CHECKLIST.md"
    ).read_text(encoding="utf-8")
    assert "export WINOE_ENV=local" in checklist_text
    assert "export WINOE_DEMO_MODE=true" in checklist_text
    assert "./scripts/seed_demo.sh" in checklist_text
    assert "http://localhost:3000/login" in checklist_text
    assert "http://localhost:3000/talent-partner/trials" in checklist_text
    assert "Talent Partner" in checklist_text
    assert "Evidence Trail" in checklist_text
    assert "Winoe Report" in checklist_text
    assert "Winoe Score" in checklist_text
    _assert_no_retired_terms(checklist_text)


@pytest.mark.asyncio
async def test_clear_demo_scope_nulls_trial_fk_before_scenario_version_delete(
    monkeypatch,
):
    from app.demo.services.yc_demo_seed_service import _clear_demo_scope

    class _ScalarResult:
        def __init__(self, values):
            self._values = values

        def scalars(self):
            return self

        def all(self):
            return list(self._values)

    class _RecordingSession:
        def __init__(self):
            self.calls = []

        async def scalar(self, stmt):
            return None

        async def execute(self, stmt):
            stmt_text = str(stmt)
            self.calls.append(stmt_text)
            if "SELECT users.id" in stmt_text:
                return _ScalarResult([2])
            if "SELECT trials.id" in stmt_text:
                return _ScalarResult([SimpleNamespace(id=11, company_id=1)])
            if "SELECT candidate_sessions.id" in stmt_text:
                return _ScalarResult([21])
            if "SELECT scenario_versions.id" in stmt_text:
                return _ScalarResult([31])
            if "SELECT tasks.id" in stmt_text:
                return _ScalarResult([41])
            if "SELECT workspaces.id" in stmt_text:
                return _ScalarResult([])
            if "SELECT workspace_groups.id" in stmt_text:
                return _ScalarResult([])
            if "SELECT evaluation_runs.id" in stmt_text:
                return _ScalarResult([])
            if "SELECT recording_assets.id" in stmt_text:
                return _ScalarResult([])
            if "SELECT jobs.id" in stmt_text:
                return _ScalarResult([])
            return _ScalarResult([])

        async def commit(self):
            self.calls.append("COMMIT")

    session = _RecordingSession()
    config = SimpleNamespace(
        trial_title="Senior Frontend Engineer Trial",
        company_name="Acme",
        talent_partner_email="demo@winoe.ai",
    )
    await _clear_demo_scope(session, config)

    trial_update_index = next(
        i for i, call in enumerate(session.calls) if "UPDATE trials" in call
    )
    scenario_delete_index = next(
        i
        for i, call in enumerate(session.calls)
        if "DELETE FROM scenario_versions" in call
    )
    assert trial_update_index < scenario_delete_index
