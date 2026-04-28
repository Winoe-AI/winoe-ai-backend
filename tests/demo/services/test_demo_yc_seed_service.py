from __future__ import annotations

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
from app.evaluations.services.evaluations_services_evaluations_winoe_report_api_service import (
    fetch_winoe_report,
)
from app.integrations.github import FakeGithubClient
from app.shared.database.shared_database_models_model import (
    CandidateSession,
    Company,
    RecordingAsset,
    ScenarioVersion,
    Submission,
    Task,
    Transcript,
    Trial,
    User,
    WinoeReport,
)
from app.submissions.repositories.github_native.workspaces.submissions_repositories_github_native_workspaces_submissions_github_native_workspaces_core_model import (
    Workspace,
    WorkspaceGroup,
)
from scripts import seed_demo as seed_demo_script


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
    talent_partner_email: str = "talent.partner.demo@winoe.ai",
    talent_partner_name: str = "Winoe Demo Talent Partner",
    company_name: str = "Winoe Demo Company",
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
    async_session,
    *,
    candidate_session_id: int,
    reviewer_reports: list[dict[str, object]],
) -> None:
    for reviewer_report in reviewer_reports:
        evidence_citations = reviewer_report.get("evidenceCitations") or []
        assert evidence_citations
        for citation in evidence_citations:
            assert isinstance(citation, dict)
            kind = citation.get("kind")
            ref = citation.get("ref")
            assert isinstance(kind, str) and kind
            assert isinstance(ref, str) and ref
            if kind == "commit":
                assert len(ref) == 40
                continue
            if kind == "diff":
                assert len(ref) == 40
                continue
            if kind == "submission":
                assert ref.startswith("submission:")
                submission_id = int(ref.split(":", 1)[1])
                row = await async_session.scalar(
                    select(Submission).where(
                        Submission.id == submission_id,
                        Submission.candidate_session_id == candidate_session_id,
                    )
                )
                assert row is not None
                continue
            if kind == "transcript":
                assert ref.startswith("transcript:")
                transcript_id = int(ref.split(":", 1)[1])
                row = await async_session.scalar(
                    select(Transcript)
                    .join(RecordingAsset, Transcript.recording_id == RecordingAsset.id)
                    .where(
                        Transcript.id == transcript_id,
                        RecordingAsset.candidate_session_id == candidate_session_id,
                    )
                )
                assert row is not None
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
    assert trial_count == 1
    assert candidate_session_count == 2
    assert submission_count == 10
    assert report_count == 2
    assert run_count == 2
    assert day_score_count == 10
    assert reviewer_count == 10
    assert workspace_count == 2
    assert workspace_group_count == 2
    assert recording_count == 2
    assert transcript_count == 2
    assert audit_count == 4
    assert scenario_version_count == 1
    assert task_count == 5

    talent_partner = await async_session.scalar(
        select(User).where(User.email == "talent.partner.demo@winoe.ai")
    )
    assert talent_partner is not None

    trial = await async_session.scalar(
        select(Trial).where(Trial.title == "YC Demo Backend Engineer Trial")
    )
    assert trial is not None
    assert trial.scenario_template == ""
    assert trial.status == "ready_for_review"
    assert "from-scratch backend API" in trial.focus

    brief_text = await async_session.scalar(select(ScenarioVersion.project_brief_md))
    assert brief_text is not None
    assert "Project Brief" in brief_text
    assert "from-scratch backend service" in brief_text
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
        "Avery Chen",
        "Jordan Patel",
    ]
    assert [row.status for row in candidate_sessions] == ["completed", "completed"]
    assert [row.completed_at is not None for row in candidate_sessions] == [True, True]
    assert [len(row.day_windows_json or []) for row in candidate_sessions] == [5, 5]
    for row in candidate_sessions:
        assert [day["status"] for day in row.day_windows_json or []] == [
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
    assert len(submission_rows) == 10
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
    assert len(recording_rows) == 2
    assert len(transcript_rows) == 2

    reports = (
        (await async_session.execute(select(WinoeReport).order_by(WinoeReport.id)))
        .scalars()
        .all()
    )
    assert len(reports) == 2

    first_report = await fetch_winoe_report(
        async_session,
        candidate_session_id=candidate_sessions[0].id,
        user=talent_partner,
    )
    second_report = await fetch_winoe_report(
        async_session,
        candidate_session_id=candidate_sessions[1].id,
        user=talent_partner,
    )

    assert first_report["status"] == "ready"
    assert second_report["status"] == "ready"
    assert (
        first_report["report"]["overallWinoeScore"]
        > second_report["report"]["overallWinoeScore"]
    )

    for candidate_session, payload in zip(
        candidate_sessions, (first_report, second_report), strict=True
    ):
        report = payload["report"]
        assert isinstance(report["overallWinoeScore"], float)
        assert len(report["dayScores"]) == 5
        assert len(report["reviewerReports"]) == 5
        for reviewer_report in report["reviewerReports"]:
            assert reviewer_report["dimensionalScores"]
            assert len(reviewer_report["dimensionalScores"]) >= 3
            assert reviewer_report["strengths"]
            assert reviewer_report["concerns"]
        await _assert_evidence_links(
            async_session,
            candidate_session_id=candidate_session.id,
            reviewer_reports=report["reviewerReports"],
        )

    assert (
        first_report["report"]["reviewerReports"][0]["strengths"]
        != second_report["report"]["reviewerReports"][0]["strengths"]
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

    other_company = Company(name="Acme Research")
    async_session.add(other_company)
    await async_session.flush()
    other_user = User(
        name="Acme Operator",
        email="operator@acme.example",
        role="talent_partner",
        company_id=other_company.id,
        password_hash="",
    )
    async_session.add(other_user)
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
        select(func.count())
        .select_from(Company)
        .where(Company.name == "Winoe Demo Company")
    )
    demo_user_count = await async_session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.email == "talent.partner.demo@winoe.ai")
    )

    assert other_company_count == 1
    assert other_user_count == 1
    assert demo_company_count == 1
    assert demo_user_count == 1


@pytest.mark.asyncio
async def test_seed_demo_reset_path_prints_full_reset_and_calls_reset_database(
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

    called = {"reset": False}

    async def _fake_reset(_engine):
        called["reset"] = True

    monkeypatch.setattr(seed_demo_script, "_reset_database", _fake_reset)

    await seed_demo_script._main_async(_seed_args(reset_db=True))

    output = capsys.readouterr().out
    assert "full database reset requested" in output
    assert "using GitHub provider=fake" in output
    assert called["reset"] is True


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
    assert (
        "poetry run python -m scripts.seed_demo --github-provider fake --reset-db"
        in checklist_text
    )
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

    class _FakeCompany:
        id = 1

    class _RecordingSession:
        def __init__(self):
            self.calls = []

        async def scalar(self, stmt):
            if "companies" in str(stmt):
                return _FakeCompany()
            return None

        async def execute(self, stmt):
            stmt_text = str(stmt)
            self.calls.append(stmt_text)
            if "SELECT users.id" in stmt_text:
                return _ScalarResult([2])
            if "SELECT trials.id" in stmt_text:
                return _ScalarResult([11])
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
        trial_title="YC Demo Backend Engineer Trial",
        company_name="Winoe Demo Company",
        talent_partner_email="talent.partner.demo@winoe.ai",
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
