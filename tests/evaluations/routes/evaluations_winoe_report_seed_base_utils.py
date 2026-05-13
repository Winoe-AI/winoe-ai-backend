from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from tests.shared.factories import (
    create_candidate_session,
    create_submission,
    create_talent_partner,
    create_trial,
)


async def _seed_winoe_report_candidate_session(
    async_session: AsyncSession,
    *,
    ai_eval_enabled_by_day: dict[str, bool] | None = None,
):
    talent_partner = await create_talent_partner(
        async_session,
        email="winoe-report-owner@test.com",
    )
    trial, tasks = await create_trial(
        async_session,
        created_by=talent_partner,
        ai_eval_enabled_by_day=ai_eval_enabled_by_day,
    )
    candidate_session = await create_candidate_session(
        async_session,
        trial=trial,
        status="completed",
        candidate_name="Winoe Report Candidate",
        invite_email="winoe-report-candidate@example.com",
    )
    tasks_by_day = {task.day_index: task for task in tasks}
    return talent_partner, candidate_session, tasks_by_day


async def _seed_day1_day2_day3_submissions(
    async_session: AsyncSession,
    *,
    candidate_session,
    tasks_by_day,
) -> None:
    await create_submission(
        async_session,
        candidate_session=candidate_session,
        task=tasks_by_day[1],
        content_text=(
            "System design plan with tradeoffs, constraints, and rollout notes.\n"
            "Architecture sketch and service boundaries.\n"
            "Data flow and storage decisions.\n"
            "Operational constraints and rollout sequence.\n"
            "Observability considerations.\n"
            "Fallback and recovery plan.\n"
            "Open questions and assumptions.\n"
            "Final decision summary."
        ),
        content_json={"kind": "day1_design", "sections": {"overview": "plan"}},
    )
    day2_submission = await create_submission(
        async_session,
        candidate_session=candidate_session,
        task=tasks_by_day[2],
        content_text=(
            "Implementation detail line 1\n"
            "Implementation detail line 2\n"
            "Implementation detail line 3\n"
            "Implementation detail line 4\n"
            "Implementation detail line 5\n"
            "Implementation detail line 6\n"
            "Implementation detail line 7\n"
            "Implementation detail line 8"
        ),
        code_repo_path="acme/winoe-report-repo",
        commit_sha="abc1234",
        workflow_run_id="2002",
        diff_summary_json=json.dumps({"base": "base-day2", "head": "head-day2"}),
        tests_passed=5,
        tests_failed=1,
        test_output=json.dumps(
            {
                "passed": 5,
                "failed": 1,
                "total": 6,
                "summary": {
                    "evidenceArtifacts": {
                        "commitMetadata": {
                            "artifactId": 201,
                            "data": {
                                "payload": {
                                    "commits": [
                                        {
                                            "sha": "abc1234",
                                            "files_changed": ["src/a.ts"],
                                            "files_changed_count": 1,
                                            "timestamp": "2026-05-06T00:00:00Z",
                                        }
                                    ]
                                }
                            },
                        },
                        "fileCreationTimeline": {
                            "artifactId": 202,
                            "data": {
                                "payload": {
                                    "files": [
                                        {
                                            "timestamp": "2026-05-06T00:00:00Z",
                                            "commit_sha": "abc1234",
                                            "message": "Add implementation scaffold",
                                            "files": ["src/a.ts"],
                                        }
                                    ]
                                }
                            },
                        },
                    }
                },
            }
        ),
    )
    day2_submission.checkpoint_sha = "abc1234-checkpoint"
    day3_submission = await create_submission(
        async_session,
        candidate_session=candidate_session,
        task=tasks_by_day[3],
        content_text=(
            "Code quality line 1\n"
            "Code quality line 2\n"
            "Code quality line 3\n"
            "Code quality line 4\n"
            "Code quality line 5\n"
            "Code quality line 6\n"
            "Code quality line 7\n"
            "Code quality line 8"
        ),
        code_repo_path="acme/winoe-report-repo",
        commit_sha="def5678",
        workflow_run_id="3003",
        diff_summary_json=json.dumps({"base": "base-day3", "head": "head-day3"}),
        tests_passed=6,
        tests_failed=0,
        test_output=json.dumps(
            {
                "passed": 6,
                "failed": 0,
                "total": 6,
                "summary": {
                    "evidenceArtifacts": {
                        "commitMetadata": {
                            "artifactId": 301,
                            "data": {
                                "payload": {
                                    "commits": [
                                        {
                                            "sha": "def5678",
                                            "files_changed": ["src/b.ts"],
                                            "files_changed_count": 1,
                                            "timestamp": "2026-05-06T00:05:00Z",
                                        }
                                    ]
                                }
                            },
                        },
                        "fileCreationTimeline": {
                            "artifactId": 302,
                            "data": {
                                "payload": {
                                    "files": [
                                        {
                                            "timestamp": "2026-05-06T00:05:00Z",
                                            "commit_sha": "def5678",
                                            "message": "Add code quality evidence",
                                            "files": ["src/b.ts"],
                                        }
                                    ]
                                }
                            },
                        },
                    }
                },
            }
        ),
    )
    day3_submission.final_sha = "def5678-final"
