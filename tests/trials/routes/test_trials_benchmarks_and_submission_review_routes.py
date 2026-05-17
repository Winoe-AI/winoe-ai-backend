from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.evaluations.repositories.evaluations_repositories_evaluations_core_model import (
    EVALUATION_RUN_STATUS_COMPLETED,
    EvaluationRun,
)
from app.shared.database.shared_database_models_model import WinoeReport
from app.trials.routes.trials_routes import (
    trials_routes_trials_v1_benchmarks_routes as benchmarks_routes,
)
from tests.shared.factories import (
    create_candidate_session,
    create_submission,
    create_talent_partner,
    create_trial,
)


def _add_completed_run(
    session, *, candidate_session, score: float, dimensions: list[dict]
):
    session.add(
        EvaluationRun(
            candidate_session_id=candidate_session.id,
            scenario_version_id=candidate_session.scenario_version_id,
            status=EVALUATION_RUN_STATUS_COMPLETED,
            started_at=datetime.now(UTC) - timedelta(hours=2),
            completed_at=datetime.now(UTC) - timedelta(hours=1),
            model_name="gpt-5-evaluator",
            model_version="2026-05-01",
            prompt_version="prompt.v4",
            rubric_version="rubric.v2",
            job_id=None,
            basis_fingerprint=None,
            overall_winoe_score=score,
            recommendation="hire",
            confidence=0.81,
            generated_at=datetime.now(UTC) - timedelta(hours=1),
            raw_report_json={"dimensions": dimensions},
            error_code=None,
            metadata_json={},
            day2_checkpoint_sha="day2-sha",
            day3_final_sha="day3-sha",
            cutoff_commit_sha="cutoff-sha",
            transcript_reference="transcript://benchmark-route",
        )
    )


def _add_winoe_report(session, *, candidate_session, generated_at: datetime):
    session.add(
        WinoeReport(
            candidate_session_id=candidate_session.id,
            generated_at=generated_at,
        )
    )


@pytest.mark.asyncio
async def test_get_benchmarks_route_happy_path(
    async_client, async_session, auth_header_factory
):
    talent_partner = await create_talent_partner(
        async_session, email="route-benchmarks@example.com"
    )
    trial, _ = await create_trial(async_session, created_by=talent_partner)
    candidate = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Route Candidate",
        invite_email="route@example.com",
        status="completed",
        completed_at=datetime.now(UTC) - timedelta(days=1),
    )
    _add_completed_run(
        async_session,
        candidate_session=candidate,
        score=84.0,
        dimensions=[{"name": "Architecture", "score": 8.4}],
    )
    _add_winoe_report(
        async_session,
        candidate_session=candidate,
        generated_at=datetime.now(UTC) - timedelta(hours=1),
    )
    await async_session.commit()

    response = await async_client.get(
        f"/api/v1/benchmarks?trial_id={trial.id}",
        headers=auth_header_factory(talent_partner),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cohort"]["n"] == 1
    assert body["candidates"][0]["id"] == str(candidate.id)
    assert body["candidates"][0]["report_id"] is not None
    assert body["candidates"][0]["dimensions"][0]["name"] == "Architecture"


@pytest.mark.asyncio
async def test_get_benchmarks_route_validation_and_filter_paths(
    async_client, async_session, auth_header_factory
):
    talent_partner = await create_talent_partner(
        async_session, email="route-benchmarks-validation@example.com"
    )
    trial, _ = await create_trial(async_session, created_by=talent_partner)
    await async_session.commit()

    missing_trial = await async_client.get(
        "/api/v1/benchmarks",
        headers=auth_header_factory(talent_partner),
    )
    assert missing_trial.status_code == 422, missing_trial.text
    assert missing_trial.json()["errorCode"] == "VALIDATION_ERROR"

    invalid_page = await async_client.get(
        f"/api/v1/benchmarks?trial_id={trial.id}&page=0",
        headers=auth_header_factory(talent_partner),
    )
    assert invalid_page.status_code == 422, invalid_page.text

    invalid_page_size = await async_client.get(
        f"/api/v1/benchmarks?trial_id={trial.id}&page_size=0",
        headers=auth_header_factory(talent_partner),
    )
    assert invalid_page_size.status_code == 422, invalid_page_size.text

    over_limit_page_size = await async_client.get(
        f"/api/v1/benchmarks?trial_id={trial.id}&page_size=101",
        headers=auth_header_factory(talent_partner),
    )
    assert over_limit_page_size.status_code == 422, over_limit_page_size.text

    invalid_filter = await async_client.get(
        f"/api/v1/benchmarks?trial_id={trial.id}&status=bogus&time_range=bogus",
        headers=auth_header_factory(talent_partner),
    )
    assert invalid_filter.status_code == 200, invalid_filter.text
    assert invalid_filter.json()["candidates"] == []


@pytest.mark.asyncio
async def test_get_benchmarks_compare_route_happy_path(
    async_client, async_session, auth_header_factory
):
    talent_partner = await create_talent_partner(
        async_session, email="route-benchmarks-compare@example.com"
    )
    trial, _ = await create_trial(async_session, created_by=talent_partner)
    candidate_a = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Compare Candidate A",
        invite_email="compare-a@example.com",
        status="completed",
        completed_at=datetime.now(UTC) - timedelta(days=1),
    )
    candidate_b = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Compare Candidate B",
        invite_email="compare-b@example.com",
        status="completed",
        completed_at=datetime.now(UTC) - timedelta(hours=12),
    )
    _add_completed_run(
        async_session,
        candidate_session=candidate_a,
        score=83.0,
        dimensions=[{"name": "Architecture", "score": 8.3}],
    )
    _add_winoe_report(
        async_session,
        candidate_session=candidate_a,
        generated_at=datetime.now(UTC) - timedelta(hours=1),
    )
    _add_completed_run(
        async_session,
        candidate_session=candidate_b,
        score=86.0,
        dimensions=[{"name": "Architecture", "score": 8.6}],
    )
    _add_winoe_report(
        async_session,
        candidate_session=candidate_b,
        generated_at=datetime.now(UTC) - timedelta(hours=1),
    )
    await async_session.commit()

    response = await async_client.get(
        f"/api/v1/benchmarks/compare?candidate_ids={candidate_a.id},{candidate_b.id}",
        headers=auth_header_factory(talent_partner),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["id"] for row in body["candidates"]] == [
        str(candidate_a.id),
        str(candidate_b.id),
    ]
    assert all(row["report_id"] is not None for row in body["candidates"])


@pytest.mark.asyncio
async def test_get_benchmarks_compare_route_validation_and_error_paths(
    async_client, async_session, auth_header_factory
):
    talent_partner = await create_talent_partner(
        async_session, email="route-benchmarks-compare-validation@example.com"
    )
    trial, _ = await create_trial(async_session, created_by=talent_partner)
    candidate_a = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Compare Candidate A",
        invite_email="compare-a@example.com",
        status="completed",
        completed_at=datetime.now(UTC) - timedelta(days=1),
    )
    candidate_b = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Compare Candidate B",
        invite_email="compare-b@example.com",
        status="completed",
        completed_at=datetime.now(UTC) - timedelta(hours=12),
    )
    candidate_c = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Compare Candidate C",
        invite_email="compare-c@example.com",
        status="completed",
        completed_at=datetime.now(UTC) - timedelta(hours=6),
    )
    await async_session.commit()

    missing_candidate_ids = await async_client.get(
        "/api/v1/benchmarks/compare",
        headers=auth_header_factory(talent_partner),
    )
    assert missing_candidate_ids.status_code == 422, missing_candidate_ids.text
    assert missing_candidate_ids.json()["errorCode"] == "VALIDATION_ERROR"

    one_candidate = await async_client.get(
        f"/api/v1/benchmarks/compare?candidate_ids={candidate_a.id}",
        headers=auth_header_factory(talent_partner),
    )
    assert one_candidate.status_code == 400, one_candidate.text
    assert one_candidate.json()["detail"] == "Compare requires 2 or 3 candidates."

    four_candidates = await async_client.get(
        (
            "/api/v1/benchmarks/compare?candidate_ids="
            f"{candidate_a.id},{candidate_b.id},{candidate_c.id},{candidate_a.id + 1000}"
        ),
        headers=auth_header_factory(talent_partner),
    )
    assert four_candidates.status_code == 400, four_candidates.text
    assert four_candidates.json()["detail"] == "Compare requires 2 or 3 candidates."

    duplicate_candidates = await async_client.get(
        f"/api/v1/benchmarks/compare?candidate_ids={candidate_a.id},{candidate_a.id}",
        headers=auth_header_factory(talent_partner),
    )
    assert duplicate_candidates.status_code == 400, duplicate_candidates.text
    assert (
        duplicate_candidates.json()["detail"]
        == "Compare requires unique candidate IDs."
    )

    malformed_ids = await async_client.get(
        "/api/v1/benchmarks/compare?candidate_ids=abc,123",
        headers=auth_header_factory(talent_partner),
    )
    assert malformed_ids.status_code == 400, malformed_ids.text
    assert malformed_ids.json()["detail"] == "Compare requires numeric candidate IDs."


@pytest.mark.asyncio
async def test_get_candidate_submission_review_route_happy_path(
    async_client, async_session, auth_header_factory
):
    talent_partner = await create_talent_partner(
        async_session, email="route-submission@example.com"
    )
    trial, tasks = await create_trial(async_session, created_by=talent_partner)
    candidate = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Submission Candidate",
        invite_email="submission@example.com",
        status="completed",
        completed_at=datetime.now(UTC) - timedelta(hours=1),
    )
    await create_submission(
        async_session,
        candidate_session=candidate,
        task=tasks[0],
        content_text="Design doc body for route test",
        content_json={"summary": "Design doc body for route test"},
    )
    await create_submission(
        async_session,
        candidate_session=candidate,
        task=tasks[1],
        content_text="Implementation kickoff body for route test",
        content_json={
            "artifactType": "implementation_kickoff",
            "repositorySnapshot": {
                "fileTree": [
                    {
                        "path": "src",
                        "name": "src",
                        "type": "folder",
                        "children": [
                            {
                                "path": "src/api/trials.ts",
                                "name": "trials.ts",
                                "type": "file",
                                "language": "typescript",
                                "content": "export const trialApi = true;\n",
                                "changed": True,
                            }
                        ],
                    }
                ],
                "commits": [
                    {
                        "sha": "kickoff-sha",
                        "message": "Implementation kickoff",
                        "timestamp": "2026-05-11T11:00:00Z",
                        "filesChanged": 2,
                        "changedFiles": ["src/api/trials.ts"],
                    }
                ],
                "selectedFilePath": "src/api/trials.ts",
                "selectedFileContent": "export const trialApi = true;\n",
                "selectedFileLanguage": "typescript",
                "selectedFileName": "trials.ts",
            },
        },
        commit_sha="kickoff-sha",
        code_repo_path="octocat/demo-sim",
        diff_summary_json='{"filesChanged": 2}',
    )
    await create_submission(
        async_session,
        candidate_session=candidate,
        task=tasks[2],
        content_text="Implementation wrap-up body for route test",
        content_json={
            "artifactType": "implementation_wrap_up",
            "repositorySnapshot": {
                "fileTree": [
                    {
                        "path": "src",
                        "name": "src",
                        "type": "folder",
                        "children": [
                            {
                                "path": "src/services/reporting.py",
                                "name": "reporting.py",
                                "type": "file",
                                "language": "python",
                                "content": "def build_report_summary():\n    return True\n",
                                "changed": True,
                            }
                        ],
                    }
                ],
                "commits": [
                    {
                        "sha": "wrap-sha",
                        "message": "Implementation wrap-up",
                        "timestamp": "2026-05-12T11:00:00Z",
                        "filesChanged": 1,
                        "changedFiles": ["src/services/reporting.py"],
                    }
                ],
                "selectedFilePath": "src/services/reporting.py",
                "selectedFileContent": "def build_report_summary():\n    return True\n",
                "selectedFileLanguage": "python",
                "selectedFileName": "reporting.py",
            },
        },
        commit_sha="wrap-sha",
        code_repo_path="octocat/demo-sim",
        diff_summary_json='{"filesChanged": 1}',
    )
    await async_session.commit()

    response = await async_client.get(
        f"/api/trials/{trial.id}/candidates/{candidate.id}/submission",
        headers=auth_header_factory(talent_partner),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["trial"]["id"] == str(trial.id)
    assert body["candidate"]["id"] == str(candidate.id)
    assert body["days"]["day1"]["markdown"] == "Design doc body for route test"
    assert body["days"]["day2"]["fileTree"]
    assert body["days"]["day2"]["commits"][0]["sha"] == "kickoff-sha"
    assert body["days"]["day2"]["selectedFilePath"] == "src/api/trials.ts"
    assert body["days"]["day3"]["fileTree"]
    assert body["days"]["day3"]["commits"][0]["sha"] == "wrap-sha"
    assert body["days"]["day3"]["selectedFilePath"] == "src/services/reporting.py"


@pytest.mark.asyncio
async def test_benchmark_route_helpers_cover_route_wrappers(monkeypatch) -> None:
    monkeypatch.setattr(
        benchmarks_routes,
        "ensure_talent_partner",
        lambda _user: None,
    )

    async def _fake_list_benchmarks(*_args, **_kwargs):
        return {
            "cohort": {"n": 1, "sufficient": True},
            "pagination": {"page": 1, "page_size": 25, "total": 1, "total_pages": 1},
            "candidates": [],
        }

    async def _fake_compare_benchmarks(*_args, **_kwargs):
        return {"candidates": []}

    monkeypatch.setattr(
        benchmarks_routes,
        "list_benchmarks",
        _fake_list_benchmarks,
    )
    monkeypatch.setattr(
        benchmarks_routes,
        "compare_benchmarks",
        _fake_compare_benchmarks,
    )

    listed = await benchmarks_routes.list_benchmarks_route(
        trial_id=123,
        db=SimpleNamespace(),
        user=SimpleNamespace(id=7),
        status_filter=None,
        time_range=None,
        page=1,
        page_size=25,
    )
    assert listed.cohort.n == 1
    assert listed.pagination.page_size == 25

    compared = await benchmarks_routes.compare_benchmarks_route(
        candidate_ids="10,20",
        db=SimpleNamespace(),
        user=SimpleNamespace(id=7),
    )
    assert compared.candidates == []
