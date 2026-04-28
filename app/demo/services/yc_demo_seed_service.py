"""YC demo seed helpers for creating a deterministic golden-path dataset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.candidates.candidate_sessions.repositories.candidates_candidate_sessions_repositories_candidates_candidate_sessions_day_audit_model import (
    CandidateDayAudit,
)
from app.evaluations.repositories.evaluations_repositories_evaluations_core_model import (
    EVALUATION_RECOMMENDATION_LEAN_HIRE,
    EVALUATION_RECOMMENDATION_STRONG_HIRE,
    EVALUATION_RUN_STATUS_COMPLETED,
    EvaluationDayScore,
    EvaluationReviewerReport,
    EvaluationRun,
)
from app.evaluations.repositories.evaluations_repositories_evaluations_create_run_repository import (
    create_run,
)
from app.evaluations.repositories.evaluations_repositories_evaluations_day_scores_repository import (
    add_day_scores,
)
from app.integrations.github import FakeGithubClient, GithubClient
from app.shared.database.shared_database_models_model import (
    CandidateSession,
    Company,
    RecordingAsset,
    Submission,
    Task,
    Transcript,
    Trial,
    User,
)
from app.shared.jobs.repositories.shared_jobs_repositories_models_repository import (
    Job,
)
from app.submissions.repositories.github_native.workspaces.submissions_repositories_github_native_workspaces_submissions_github_native_workspaces_core_model import (
    Workspace,
    WorkspaceGroup,
)
from app.submissions.repositories.submissions_repositories_submissions_winoe_report_repository import (
    upsert_marker,
)
from app.submissions.services.submissions_services_submissions_workspace_bootstrap_service import (
    bootstrap_empty_candidate_repo,
)
from app.trials.constants.trials_constants_trials_defaults_constants import (
    DEFAULT_TEMPLATE_KEY,
)
from app.trials.repositories.scenario_versions.trials_repositories_scenario_versions_trials_scenario_versions_model import (
    ScenarioVersion as TrialScenarioVersion,
)
from app.trials.repositories.trials_repositories_trials_trial_status_constants import (
    TRIAL_STATUS_GENERATING,
    TRIAL_STATUS_READY_FOR_REVIEW,
)
from app.trials.services.trials_services_trials_scenario_versions_create_service import (
    create_initial_scenario_version,
)
from app.trials.services.trials_services_trials_task_seed_service import (
    seed_default_tasks,
)


@dataclass(slots=True)
class DemoSeedConfig:
    """Configuration for the YC demo seed."""

    talent_partner_email: str = "talent.partner.demo@winoe.ai"
    talent_partner_name: str = "Winoe Demo Talent Partner"
    company_name: str = "Winoe Demo Company"
    trial_title: str = "YC Demo Backend Engineer Trial"
    trial_role: str = "Backend Engineer"
    trial_seniority: str = "Senior"
    trial_focus: str = (
        "Design and ship a from-scratch backend API for a B2B operations workflow."
    )
    trial_tech_stack: str = "Python, FastAPI, PostgreSQL"
    git_owner: str = "winoe-ai-demo"
    repo_prefix: str = "yc-demo-candidate-"
    codespace_workspace_key: str = "coding"
    timezone: str = "America/New_York"
    reset_db: bool = False


@dataclass(slots=True)
class DemoCandidateProfile:
    """Deterministic profile for one demo candidate."""

    label: str
    name: str
    email: str
    repo_suffix: str
    overall_score: float
    confidence: float
    recommendation: str
    internal_recommendation: str
    strength_points: list[str]
    concern_points: list[str]
    summary_line: str
    day_scores: dict[int, float]
    test_summary: dict[str, tuple[int, int]]


@dataclass(slots=True)
class DemoSeedSummary:
    """High-level summary of the seeded demo dataset."""

    company_id: int
    trial_id: int
    candidate_session_ids: list[int]
    repo_full_names: list[str]


def _apply_legacy_trial_fields(trial: Trial) -> None:
    """Keep the seeded trial compatible with existing stored columns."""
    trial.scenario_template = ""
    trial.template_key = DEFAULT_TEMPLATE_KEY


def _stable_hex(*parts: object, length: int = 40) -> str:
    seed = "\u241f".join("" if part is None else str(part) for part in parts)
    return sha256(seed.encode("utf-8")).hexdigest()[:length]


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _demo_trial_brief_markdown(config: DemoSeedConfig) -> str:
    return (
        "# Project Brief\n\n"
        "## Business Context\n\n"
        f"{config.company_name} needs a lightweight internal API for coordinating "
        "candidate evidence, review notes, and hiring decision prep.\n\n"
        "## Product Goal\n\n"
        "Build a from-scratch backend service that can track an intake workflow, "
        "surface evidence-backed progress, and support Talent Partner review.\n\n"
        "## Technical Constraints\n\n"
        "- Start from an empty repository.\n"
        "- Commit a devcontainer so the project is reproducible.\n"
        "- Use clear validation, idempotent writes, and readable API boundaries.\n"
        "- Keep the architecture simple enough to finish in five days.\n\n"
        "## Expected Deliverables\n\n"
        "- A stable API with create, read, and status endpoints.\n"
        "- Tests that prove the core workflow.\n"
        "- Documentation that explains the design and tradeoffs.\n\n"
        "## Risks\n\n"
        "- Overengineering the storage model.\n"
        "- Missing edge-case handling around duplicate requests.\n"
        "- Treating the demo as a toy instead of a real hiring workflow.\n"
    )


def _demo_scenario_storyline() -> str:
    return (
        "A Talent Partner needs a reliable evidence trail for a five-day "
        "from-scratch build and wants to compare two candidates with a clear "
        "Winoe Report."
    )


def _demo_task_prompts(tasks: list[Task]) -> list[dict[str, Any]]:
    return [
        {
            "dayIndex": task.day_index,
            "type": task.type,
            "title": task.title,
            "description": task.description,
        }
        for task in sorted(tasks, key=lambda item: item.day_index)
    ]


def _demo_candidate_profiles() -> list[DemoCandidateProfile]:
    return [
        DemoCandidateProfile(
            label="candidate-a",
            name="Avery Chen",
            email="avery.chen.demo@winoe.ai",
            repo_suffix="avery-chen",
            overall_score=0.91,
            confidence=0.88,
            recommendation="strong_signal",
            internal_recommendation=EVALUATION_RECOMMENDATION_STRONG_HIRE,
            strength_points=[
                "Clear architecture notes with strong API boundaries",
                "Consistent testing discipline across the build",
                "Good documentation and handoff clarity",
            ],
            concern_points=[
                "Would benefit from one more load-focused test",
                "Day 3 could call out a couple more rollback risks",
            ],
            summary_line=(
                "Avery shows strong from-scratch judgment, with only minor gaps "
                "around deeper operational hardening."
            ),
            day_scores={1: 0.93, 2: 0.92, 3: 0.91, 4: 0.89, 5: 0.90},
            test_summary={1: (14, 0), 2: (18, 0), 3: (20, 0)},
        ),
        DemoCandidateProfile(
            label="candidate-b",
            name="Jordan Patel",
            email="jordan.patel.demo@winoe.ai",
            repo_suffix="jordan-patel",
            overall_score=0.74,
            confidence=0.76,
            recommendation="mixed_signal",
            internal_recommendation=EVALUATION_RECOMMENDATION_LEAN_HIRE,
            strength_points=[
                "Delivered a functional backend and a credible review path",
                "Handoff communication is clear and professional",
                "Reflection is honest about tradeoffs and next steps",
            ],
            concern_points=[
                "Tests are narrower than the strongest submission",
                "Implementation notes could be more systematic",
                "Documentation is useful but less complete",
            ],
            summary_line=(
                "Jordan is credible and productive, but the evidence is thinner "
                "and the overall story is less disciplined."
            ),
            day_scores={1: 0.76, 2: 0.73, 3: 0.72, 4: 0.74, 5: 0.75},
            test_summary={1: (10, 0), 2: (11, 1), 3: (12, 1)},
        ),
    ]


def _candidate_repo_name(
    config: DemoSeedConfig, candidate: DemoCandidateProfile
) -> str:
    return f"{config.repo_prefix}{candidate.repo_suffix}"


def _candidate_token(config: DemoSeedConfig, candidate: DemoCandidateProfile) -> str:
    return _stable_hex(
        config.company_name, candidate.email, "candidate-token", length=32
    )


def _candidate_commit_sha(
    config: DemoSeedConfig, candidate: DemoCandidateProfile, *, day: int
) -> str:
    return _stable_hex(config.company_name, candidate.email, "commit", day, length=40)


def _candidate_recording_key(
    config: DemoSeedConfig, candidate: DemoCandidateProfile
) -> str:
    return f"demo/{config.company_name.lower().replace(' ', '-')}/{candidate.label}/day4-handoff.mp4"


def _candidate_design_doc(candidate: DemoCandidateProfile) -> str:
    return (
        "# Day 1 Design Document\n\n"
        "## Architecture\n\n"
        "Use a small FastAPI service with one core domain module, a service layer, "
        "and a repository boundary around persistence.\n\n"
        "## Stack\n\n"
        "Python, FastAPI, PostgreSQL, and a thin integration layer for artifact "
        "capture.\n\n"
        "## Tradeoffs\n\n"
        "Prefer clear boundaries over extra abstraction. Keep writes idempotent "
        "so reruns do not drift the demo state.\n\n"
        "## Testing Plan\n\n"
        "Cover the API shape, duplicate-request behavior, and the most important "
        "repository transitions.\n\n"
        "## Implementation Plan\n\n"
        "1. Create the API and persistence structure.\n"
        "2. Add the core workflow and validation.\n"
        "3. Add tests, docs, and a concise handoff.\n\n"
        "## Risks\n\n"
        f"- {candidate.concern_points[0]}\n"
        f"- {candidate.concern_points[1]}\n"
    )


def _candidate_kickoff_doc(candidate: DemoCandidateProfile) -> str:
    return (
        "# Day 2 Implementation Kickoff\n\n"
        "## Progress\n\n"
        f"{candidate.summary_line}\n\n"
        "## Repository Shape\n\n"
        "- Devcontainer committed.\n"
        "- README explains the project brief.\n"
        "- Core API skeleton and persistence paths are in place.\n\n"
        "## Early Validation\n\n"
        "The first tests focus on the public routes, duplicate protection, and "
        "the basic evidence trail.\n"
    )


def _candidate_wrapup_doc(candidate: DemoCandidateProfile) -> str:
    return (
        "# Day 3 Implementation Wrap-Up\n\n"
        "## Finalization\n\n"
        f"{candidate.summary_line}\n\n"
        "## Evidence\n\n"
        "- Commit progression is visible in the repo history.\n"
        "- The tests cover the main from-scratch flow.\n"
        "- The README and API notes explain how to run the system.\n\n"
        "## Final Notes\n\n"
        "The remaining gaps are small, explicit, and easy to review in the demo.\n"
    )


def _candidate_handoff_doc(candidate: DemoCandidateProfile) -> str:
    strengths = "\n".join(f"- {item}" for item in candidate.strength_points)
    concerns = "\n".join(f"- {item}" for item in candidate.concern_points)
    return (
        "# Day 4 Handoff + Demo\n\n"
        "I walked through the architecture, the evidence trail, the main tradeoffs, "
        "and the next steps for hardening the build.\n\n"
        "## Strengths\n\n"
        f"{strengths}\n\n"
        "## Areas to Watch\n\n"
        f"{concerns}\n\n"
        "## Next Steps\n\n"
        "Tighten the last operational edge cases and continue to keep the evidence "
        "trail crisp for review.\n"
    )


def _candidate_reflection_doc(candidate: DemoCandidateProfile) -> str:
    return (
        "# Day 5 Reflection\n\n"
        "## What Went Well\n\n"
        f"{candidate.strength_points[0]}\n\n"
        "## What Was Hard\n\n"
        f"{candidate.concern_points[0]}\n\n"
        "## What I Would Change\n\n"
        "I would budget more time for a deeper edge-case pass and one more "
        "round of API polish.\n\n"
        "## How I Used Tools\n\n"
        "I used automation to accelerate the repetitive parts, then reviewed the "
        "outputs manually to keep the evidence trail honest.\n\n"
        "## What I Learned\n\n"
        "A small, readable system is easier to defend when the evidence is "
        "collected day by day.\n"
    )


def _candidate_submissions(
    config: DemoSeedConfig,
    candidate: DemoCandidateProfile,
    *,
    repo_full_name: str,
    bootstrap_commit_sha: str,
    day2_commit_sha: str,
    day3_commit_sha: str,
    recording_key: str,
) -> dict[int, dict[str, Any]]:
    return {
        1: {
            "content_text": _candidate_design_doc(candidate),
            "content_json": {
                "artifactType": "design_document",
                "candidate": candidate.name,
                "company": config.company_name,
                "summary": candidate.summary_line,
            },
            "code_repo_path": None,
            "commit_sha": None,
            "test_output": None,
            "tests_passed": None,
            "tests_failed": None,
            "diff_summary_json": None,
        },
        2: {
            "content_text": _candidate_kickoff_doc(candidate),
            "content_json": {
                "artifactType": "implementation_kickoff",
                "repoFullName": repo_full_name,
                "bootstrapCommitSha": bootstrap_commit_sha,
                "summary": candidate.summary_line,
            },
            "code_repo_path": repo_full_name,
            "commit_sha": day2_commit_sha,
            "test_output": (
                f"pytest: {candidate.test_summary[1][0]} passed, "
                f"{candidate.test_summary[1][1]} failed"
            ),
            "tests_passed": candidate.test_summary[1][0],
            "tests_failed": candidate.test_summary[1][1],
            "diff_summary_json": (
                f"Added API skeleton, validation, and the first service layer for {candidate.name}."
            ),
        },
        3: {
            "content_text": _candidate_wrapup_doc(candidate),
            "content_json": {
                "artifactType": "implementation_wrap_up",
                "repoFullName": repo_full_name,
                "finalCommitSha": day3_commit_sha,
                "summary": candidate.summary_line,
            },
            "code_repo_path": repo_full_name,
            "commit_sha": day3_commit_sha,
            "test_output": (
                f"pytest: {candidate.test_summary[2][0]} passed, "
                f"{candidate.test_summary[2][1]} failed"
            ),
            "tests_passed": candidate.test_summary[2][0],
            "tests_failed": candidate.test_summary[2][1],
            "diff_summary_json": (
                f"Finished the API, tightened docs, and polished the final evidence trail for {candidate.name}."
            ),
        },
        4: {
            "content_text": _candidate_handoff_doc(candidate),
            "content_json": {
                "artifactType": "handoff_transcript",
                "recordingKey": recording_key,
                "summary": candidate.summary_line,
            },
            "code_repo_path": None,
            "commit_sha": None,
            "test_output": None,
            "tests_passed": None,
            "tests_failed": None,
            "diff_summary_json": None,
        },
        5: {
            "content_text": _candidate_reflection_doc(candidate),
            "content_json": {
                "artifactType": "reflection_essay",
                "summary": candidate.summary_line,
            },
            "code_repo_path": repo_full_name,
            "commit_sha": day3_commit_sha,
            "test_output": None,
            "tests_passed": None,
            "tests_failed": None,
            "diff_summary_json": None,
        },
    }


def _evidence_pointers(
    *,
    repo_full_name: str,
    bootstrap_commit_sha: str,
    day2_commit_sha: str,
    day3_commit_sha: str,
    submission_ids_by_day: dict[int, int],
    transcript_id: int,
) -> dict[int, list[dict[str, Any]]]:
    def repo_commit_url(sha: str) -> str:
        return f"https://github.com/{repo_full_name}/commit/{sha}"

    return {
        1: [
            {
                "kind": "submission",
                "ref": f"submission:{submission_ids_by_day[1]}",
                "excerpt": "Architecture plan, tradeoffs, and testing strategy.",
                "dayIndex": 1,
            },
            {
                "kind": "commit",
                "ref": bootstrap_commit_sha,
                "url": repo_commit_url(bootstrap_commit_sha),
                "excerpt": "Bootstrap commit created the empty repository, devcontainer, and README.",
                "dayIndex": 1,
            },
        ],
        2: [
            {
                "kind": "commit",
                "ref": day2_commit_sha,
                "url": repo_commit_url(day2_commit_sha),
                "excerpt": "Initial implementation kickoff commit.",
                "dayIndex": 2,
            },
            {
                "kind": "submission",
                "ref": f"submission:{submission_ids_by_day[2]}",
                "excerpt": "Kickoff tests established the core workflow shape.",
                "dayIndex": 2,
            },
        ],
        3: [
            {
                "kind": "diff",
                "ref": day3_commit_sha,
                "url": repo_commit_url(day3_commit_sha),
                "excerpt": "Wrap-up commit completed the core workflow and docs.",
                "dayIndex": 3,
            },
            {
                "kind": "submission",
                "ref": f"submission:{submission_ids_by_day[3]}",
                "excerpt": "Wrap-up test results show the final pass/fail balance.",
                "dayIndex": 3,
            },
        ],
        4: [
            {
                "kind": "transcript",
                "ref": f"transcript:{transcript_id}",
                "excerpt": "Demo transcript with architecture, tradeoffs, and next steps.",
                "dayIndex": 4,
                "startMs": 0,
                "endMs": 120000,
            },
            {
                "kind": "submission",
                "ref": f"submission:{submission_ids_by_day[4]}",
                "excerpt": "Handoff transcript and demo summary.",
                "dayIndex": 4,
            },
        ],
        5: [
            {
                "kind": "submission",
                "ref": f"submission:{submission_ids_by_day[5]}",
                "excerpt": "Reflection essay covering what went well, what was hard, and what changed.",
                "dayIndex": 5,
            },
            {
                "kind": "submission",
                "ref": f"submission:{submission_ids_by_day[5]}",
                "excerpt": "Reflection quality, self-awareness, and next-step realism.",
                "dayIndex": 5,
            },
        ],
    }


def _dimensional_scores(
    candidate: DemoCandidateProfile, *, day_index: int
) -> dict[str, float]:
    if candidate.label == "candidate-a":
        base = {
            1: {"architecture": 0.95, "planning": 0.93, "communication": 0.94},
            2: {"implementation": 0.93, "testing": 0.92, "discipline": 0.91},
            3: {"implementation": 0.92, "testing": 0.93, "docs": 0.90},
            4: {"communication": 0.91, "judgment": 0.88, "delivery": 0.89},
            5: {"reflection": 0.90, "self-awareness": 0.89, "tooling": 0.88},
        }
    else:
        base = {
            1: {"architecture": 0.78, "planning": 0.76, "communication": 0.77},
            2: {"implementation": 0.75, "testing": 0.72, "discipline": 0.73},
            3: {"implementation": 0.74, "testing": 0.71, "docs": 0.72},
            4: {"communication": 0.76, "judgment": 0.72, "delivery": 0.73},
            5: {"reflection": 0.75, "self-awareness": 0.74, "tooling": 0.73},
        }
    return base[day_index]


def _assessment_text(candidate: DemoCandidateProfile, *, day_index: int) -> str:
    if candidate.label == "candidate-a":
        assessments = {
            1: "Clear, practical design with sensible boundaries and low-risk tradeoffs.",
            2: "Strong kickoff momentum and disciplined setup for a from-scratch build.",
            3: "Well-finished implementation with good hygiene and useful documentation.",
            4: "Confident demo delivery with honest caveats and a coherent narrative.",
            5: "Reflective and specific about tradeoffs, growth areas, and next steps.",
        }
    else:
        assessments = {
            1: "Solid design, though the plan is lighter on operational detail.",
            2: "Functional implementation kickoff with a narrower testing story.",
            3: "Useful wrap-up, but the documentation and structure are less complete.",
            4: "Clear handoff, with less depth on tradeoffs and failure modes.",
            5: "Honest reflection that identifies real gaps without fully resolving them.",
        }
    return assessments[day_index]


def _strengths(candidate: DemoCandidateProfile, *, day_index: int) -> list[str]:
    if candidate.label == "candidate-a":
        strengths = {
            1: [
                "The architecture is easy to follow",
                "Tradeoffs are described plainly",
            ],
            2: [
                "The build starts in a disciplined way",
                "Tests come in early",
            ],
            3: [
                "The repository is polished and readable",
                "Documentation tracks the implementation",
            ],
            4: [
                "The handoff is calm and structured",
                "The demo maps back to evidence cleanly",
            ],
            5: [
                "The reflection is candid and specific",
                "The candidate shows strong self-review",
            ],
        }
    else:
        strengths = {
            1: [
                "The design is practical and feasible",
                "The candidate explains the main path clearly",
            ],
            2: [
                "The implementation is functional",
                "The kickoff path is easy to follow",
            ],
            3: [
                "The wrap-up documents the outcome",
                "The repo is reasonably organized",
            ],
            4: [
                "The handoff is professional and clear",
                "The demo covers the core build",
            ],
            5: [
                "The reflection is honest",
                "The candidate can name the gaps plainly",
            ],
        }
    return strengths[day_index]


def _concerns(candidate: DemoCandidateProfile, *, day_index: int) -> list[str]:
    if candidate.label == "candidate-a":
        concerns = {
            1: [
                "Operational hardening is not fully explored",
                "A deeper rollout plan would help",
            ],
            2: [
                "Load testing is still missing",
                "The kickoff could mention failure recovery more directly",
            ],
            3: [
                "There is room for one more edge-case pass",
                "Rollback notes could be stronger",
            ],
            4: [
                "The demo could show one more negative path",
                "No major concerns beyond polish",
            ],
            5: [
                "The reflection could include one more concrete follow-up",
                "No major concerns beyond scope",
            ],
        }
    else:
        concerns = {
            1: [
                "Operational detail is thinner than ideal",
                "A few edge cases remain implicit",
            ],
            2: [
                "The testing story is narrower than the best submissions",
                "The kickoff could be more systematic",
            ],
            3: [
                "Documentation is useful but not as complete",
                "More explicit tradeoff discussion would help",
            ],
            4: [
                "The demo misses a couple of deeper tradeoffs",
                "The handoff is credible but not as layered",
            ],
            5: [
                "The reflection is honest but light on specifics",
                "The next-step plan could be more concrete",
            ],
        }
    return concerns[day_index]


def _build_report_rows(
    *,
    candidate: DemoCandidateProfile,
    repo_full_name: str,
    bootstrap_commit_sha: str,
    day2_commit_sha: str,
    day3_commit_sha: str,
    submission_ids_by_day: dict[int, int],
    transcript_id: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence = _evidence_pointers(
        repo_full_name=repo_full_name,
        bootstrap_commit_sha=bootstrap_commit_sha,
        day2_commit_sha=day2_commit_sha,
        day3_commit_sha=day3_commit_sha,
        submission_ids_by_day=submission_ids_by_day,
        transcript_id=transcript_id,
    )
    day_rows: list[dict[str, Any]] = []
    reviewer_rows: list[dict[str, Any]] = []
    for day_index in range(1, 6):
        day_score = candidate.day_scores[day_index]
        day_rows.append(
            {
                "day_index": day_index,
                "score": day_score,
                "rubric_results_json": {
                    "architecture": _dimensional_scores(
                        candidate, day_index=day_index
                    ).get(
                        "architecture",
                        day_score,
                    ),
                    "planning": _dimensional_scores(candidate, day_index=day_index).get(
                        "planning",
                        day_score,
                    ),
                    "implementation": _dimensional_scores(
                        candidate, day_index=day_index
                    ).get("implementation", day_score),
                    "testing": _dimensional_scores(candidate, day_index=day_index).get(
                        "testing",
                        day_score,
                    ),
                    "communication": _dimensional_scores(
                        candidate, day_index=day_index
                    ).get("communication", day_score),
                },
                "evidence_pointers_json": evidence[day_index],
            }
        )
        reviewer_rows.append(
            {
                "reviewer_agent_key": (
                    "designDocReviewer"
                    if day_index == 1
                    else "codeImplementationReviewer"
                    if day_index in {2, 3}
                    else "demoPresentationReviewer"
                    if day_index == 4
                    else "reflectionEssayReviewer"
                ),
                "day_index": day_index,
                "submission_kind": (
                    "design_document"
                    if day_index == 1
                    else "implementation"
                    if day_index in {2, 3}
                    else "handoff"
                    if day_index == 4
                    else "reflection"
                ),
                "score": day_score,
                "dimensional_scores_json": _dimensional_scores(
                    candidate, day_index=day_index
                ),
                "evidence_citations_json": evidence[day_index],
                "assessment_text": _assessment_text(candidate, day_index=day_index),
                "strengths_json": _strengths(candidate, day_index=day_index),
                "risks_json": _concerns(candidate, day_index=day_index),
            }
        )
    return day_rows, reviewer_rows


async def _clear_demo_scope(db: AsyncSession, config: DemoSeedConfig) -> None:
    """Remove any existing demo-scoped rows before reseeding."""
    candidate_emails = [candidate.email for candidate in _demo_candidate_profiles()]
    company = await db.scalar(
        select(Company).where(Company.name == config.company_name)
    )
    company_id = company.id if company is not None else None
    user_filters = [User.email == config.talent_partner_email]
    if candidate_emails:
        user_filters.append(User.email.in_(candidate_emails))
    if company_id is not None:
        user_filters.append(User.company_id == company_id)
    user_ids = (
        (await db.execute(select(User.id).where(or_(*user_filters)))).scalars().all()
    )

    trial_filters = [Trial.title == config.trial_title]
    if company_id is not None:
        trial_filters.append(Trial.company_id == company_id)
    trial_ids = (
        (await db.execute(select(Trial.id).where(or_(*trial_filters)))).scalars().all()
    )

    candidate_session_filters = [CandidateSession.invite_email.in_(candidate_emails)]
    if trial_ids:
        candidate_session_filters.append(CandidateSession.trial_id.in_(trial_ids))
    candidate_session_ids = (
        (
            await db.execute(
                select(CandidateSession.id).where(or_(*candidate_session_filters))
            )
        )
        .scalars()
        .all()
    )

    scenario_version_ids: list[int] = []
    task_ids: list[int] = []
    workspace_ids: list[int] = []
    workspace_group_ids: list[int] = []
    evaluation_run_ids: list[int] = []
    recording_ids: list[int] = []
    if trial_ids:
        scenario_version_ids = (
            (
                await db.execute(
                    select(TrialScenarioVersion.id).where(
                        TrialScenarioVersion.trial_id.in_(trial_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        task_ids = (
            (await db.execute(select(Task.id).where(Task.trial_id.in_(trial_ids))))
            .scalars()
            .all()
        )
    if candidate_session_ids:
        workspace_ids = (
            (
                await db.execute(
                    select(Workspace.id).where(
                        Workspace.candidate_session_id.in_(candidate_session_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        workspace_group_ids = (
            (
                await db.execute(
                    select(WorkspaceGroup.id).where(
                        WorkspaceGroup.candidate_session_id.in_(candidate_session_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        evaluation_run_ids = (
            (
                await db.execute(
                    select(EvaluationRun.id).where(
                        EvaluationRun.candidate_session_id.in_(candidate_session_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        recording_ids = (
            (
                await db.execute(
                    select(RecordingAsset.id).where(
                        RecordingAsset.candidate_session_id.in_(candidate_session_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
    job_ids: list[str] = []
    if candidate_session_ids or company_id is not None:
        job_filters = []
        if candidate_session_ids:
            job_filters.append(Job.candidate_session_id.in_(candidate_session_ids))
        if company_id is not None:
            job_filters.append(Job.company_id == company_id)
        job_ids = (
            (await db.execute(select(Job.id).where(or_(*job_filters)))).scalars().all()
        )

    if evaluation_run_ids:
        await db.execute(
            delete(EvaluationReviewerReport).where(
                EvaluationReviewerReport.run_id.in_(evaluation_run_ids)
            )
        )
        await db.execute(
            delete(EvaluationDayScore).where(
                EvaluationDayScore.run_id.in_(evaluation_run_ids)
            )
        )
        await db.execute(
            delete(EvaluationRun).where(EvaluationRun.id.in_(evaluation_run_ids))
        )

    if candidate_session_ids:
        if job_ids:
            await db.execute(delete(Job).where(Job.id.in_(job_ids)))
        await db.execute(
            delete(Submission).where(
                Submission.candidate_session_id.in_(candidate_session_ids)
            )
        )
        await db.execute(
            delete(CandidateDayAudit).where(
                CandidateDayAudit.candidate_session_id.in_(candidate_session_ids)
            )
        )
        await db.execute(
            delete(Transcript).where(Transcript.recording_id.in_(recording_ids))
        )
        await db.execute(
            delete(RecordingAsset).where(RecordingAsset.id.in_(recording_ids))
        )
        await db.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
        await db.execute(
            delete(WorkspaceGroup).where(WorkspaceGroup.id.in_(workspace_group_ids))
        )
        await db.execute(
            delete(CandidateSession).where(
                CandidateSession.id.in_(candidate_session_ids)
            )
        )
    elif job_ids:
        await db.execute(delete(Job).where(Job.id.in_(job_ids)))

    if trial_ids:
        await db.execute(
            update(Trial)
            .where(Trial.id.in_(trial_ids))
            .values(
                active_scenario_version_id=None,
                pending_scenario_version_id=None,
                status=TRIAL_STATUS_GENERATING,
            )
        )

    if task_ids:
        await db.execute(delete(Task).where(Task.id.in_(task_ids)))

    if scenario_version_ids:
        await db.execute(
            delete(TrialScenarioVersion).where(
                TrialScenarioVersion.id.in_(scenario_version_ids)
            )
        )

    if trial_ids:
        await db.execute(delete(Trial).where(Trial.id.in_(trial_ids)))

    if user_ids:
        await db.execute(delete(User).where(User.id.in_(user_ids)))
    if company is not None:
        await db.execute(delete(Company).where(Company.id == company.id))

    await db.commit()


async def _reset_database(engine: AsyncEngine) -> None:
    """Delete every application row for an explicit full reset."""
    from app.shared.database.shared_database_models_model import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if conn.dialect.name == "sqlite":
            await conn.exec_driver_sql("PRAGMA foreign_keys = OFF")
            try:
                for table in reversed(Base.metadata.sorted_tables):
                    await conn.execute(table.delete())
            finally:
                await conn.exec_driver_sql("PRAGMA foreign_keys = ON")
            return
        table_names = [
            table.name
            for table in Base.metadata.sorted_tables
            if table.name != "alembic_version"
        ]
        if table_names:
            quoted = ", ".join(f'"{name}"' for name in table_names)
            await conn.exec_driver_sql(
                f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"
            )


async def seed_yc_demo_dataset(
    db: AsyncSession,
    *,
    config: DemoSeedConfig,
    github_client: GithubClient | FakeGithubClient,
) -> DemoSeedSummary:
    """Create or replace the demo dataset in the current database."""
    await _clear_demo_scope(db, config)

    company = Company(name=config.company_name)
    db.add(company)
    await db.flush()

    talent_partner = User(
        name=config.talent_partner_name,
        email=config.talent_partner_email,
        role="talent_partner",
        company_id=company.id,
        password_hash="",
    )
    db.add(talent_partner)
    await db.flush()

    trial = Trial(
        company_id=company.id,
        title=config.trial_title,
        role=config.trial_role,
        tech_stack=config.trial_tech_stack,
        seniority=config.trial_seniority,
        focus=config.trial_focus,
        company_context={
            "companyName": config.company_name,
            "preferredLanguageFramework": config.trial_tech_stack,
            "demoMode": "yc-demo",
        },
        company_rubric_json={
            "dimensions": [
                "architecture",
                "testing",
                "documentation",
                "communication",
                "judgment",
            ]
        },
        ai_prompt_overrides_json=None,
        ai_notice_version="yc-demo-v1",
        ai_notice_text="Winoe demo notice for the YC rehearsal dataset.",
        ai_eval_enabled_by_day={
            "1": True,
            "2": True,
            "3": True,
            "4": True,
            "5": True,
        },
        day_window_overrides_enabled=True,
        day_window_overrides_json={"5": {"startLocal": "09:00", "endLocal": "21:00"}},
        created_by=talent_partner.id,
        status=TRIAL_STATUS_GENERATING,
        generating_at=_now(),
    )
    db.add(trial)
    _apply_legacy_trial_fields(trial)
    await db.flush()

    tasks = await seed_default_tasks(db, trial.id, trial.template_key)
    scenario_version = await create_initial_scenario_version(
        db, trial=trial, tasks=tasks
    )
    scenario_version.storyline_md = _demo_scenario_storyline()
    scenario_version.task_prompts_json = _demo_task_prompts(tasks)
    scenario_version.rubric_json = {
        "dimensions": [
            {"key": "architecture", "weight": 0.25},
            {"key": "implementation", "weight": 0.35},
            {"key": "testing", "weight": 0.20},
            {"key": "documentation", "weight": 0.10},
            {"key": "judgment", "weight": 0.10},
        ]
    }
    scenario_version.project_brief_md = _demo_trial_brief_markdown(config)
    scenario_version.focus_notes = config.trial_focus
    scenario_version.tech_stack = config.trial_tech_stack
    scenario_version.seniority = config.trial_seniority
    scenario_version.locked_at = _now()
    trial.status = TRIAL_STATUS_READY_FOR_REVIEW
    trial.ready_for_review_at = _now()
    trial.activated_at = _now()
    await db.flush()

    candidate_sessions: list[CandidateSession] = []
    repo_full_names: list[str] = []
    for candidate in _demo_candidate_profiles():
        candidate_session = CandidateSession(
            trial_id=trial.id,
            scenario_version_id=scenario_version.id,
            candidate_user_id=None,
            candidate_name=candidate.name,
            invite_email=candidate.email,
            candidate_email=candidate.email,
            candidate_auth0_email=candidate.email,
            token=_candidate_token(config, candidate),
            status="completed",
            started_at=_now() - timedelta(days=4),
            completed_at=_now(),
            claimed_at=_now() - timedelta(days=4),
            expires_at=_now() + timedelta(days=7),
            invite_email_status="sent",
            invite_email_sent_at=_now() - timedelta(days=4),
            invite_email_last_attempt_at=_now() - timedelta(days=4),
            scheduled_start_at=_now() - timedelta(days=4),
            candidate_timezone=config.timezone,
            github_username=candidate.repo_suffix.replace("-", ""),
            consent_version="yc-demo-v1",
            consent_timestamp=_now() - timedelta(days=4),
            ai_notice_version="yc-demo-v1",
            day_windows_json=[
                {"dayIndex": day_index, "status": "submitted"}
                for day_index in range(1, 6)
            ],
            schedule_locked_at=_now() - timedelta(days=4),
        )
        db.add(candidate_session)
        await db.flush()
        candidate_sessions.append(candidate_session)

        repo_name = _candidate_repo_name(config, candidate)
        repo_result = await bootstrap_empty_candidate_repo(
            github_client=github_client,
            candidate_session=candidate_session,
            trial=trial,
            scenario_version=scenario_version,
            task=tasks[1],
            repo_prefix=config.repo_prefix,
            destination_owner=config.git_owner,
            repo_name=repo_name,
        )
        repo_full_names.append(repo_result.repo_full_name)

        workspace_group = WorkspaceGroup(
            candidate_session_id=candidate_session.id,
            workspace_key=config.codespace_workspace_key,
            template_repo_full_name=None,
            repo_full_name=repo_result.repo_full_name,
            default_branch=repo_result.default_branch,
            bootstrap_commit_sha=repo_result.bootstrap_commit_sha,
            created_at=_now(),
        )
        db.add(workspace_group)
        await db.flush()
        workspace = Workspace(
            workspace_group_id=workspace_group.id,
            candidate_session_id=candidate_session.id,
            task_id=tasks[1].id,
            template_repo_full_name=None,
            repo_full_name=repo_result.repo_full_name,
            repo_id=repo_result.repo_id,
            default_branch=repo_result.default_branch,
            bootstrap_commit_sha=repo_result.bootstrap_commit_sha,
            codespace_name=repo_result.codespace_name,
            codespace_url=repo_result.codespace_url,
            codespace_state=repo_result.codespace_state,
            latest_commit_sha=_candidate_commit_sha(config, candidate, day=3),
            last_workflow_run_id=f"yc-demo-{candidate.label}-workflow",
            last_workflow_conclusion="success"
            if candidate.label == "candidate-a"
            else "neutral",
            last_test_summary_json=(
                f'{{"passed": {candidate.test_summary[2][0]}, "failed": {candidate.test_summary[2][1]}}}'
            ),
            created_at=_now(),
        )
        db.add(workspace)
        await db.flush()

        day2_commit_sha = _candidate_commit_sha(config, candidate, day=2)
        day3_commit_sha = _candidate_commit_sha(config, candidate, day=3)
        recording_key = _candidate_recording_key(config, candidate)
        submission_ids_by_day: dict[int, int] = {}
        day4_transcript_id: int | None = None
        submissions = _candidate_submissions(
            config,
            candidate,
            repo_full_name=repo_result.repo_full_name,
            bootstrap_commit_sha=repo_result.bootstrap_commit_sha or "",
            day2_commit_sha=day2_commit_sha,
            day3_commit_sha=day3_commit_sha,
            recording_key=recording_key,
        )
        for day_index, task in enumerate(tasks, start=1):
            submission_spec = submissions[day_index]
            submission_recording_id: int | None = None
            if day_index == 4:
                recording = RecordingAsset(
                    candidate_session_id=candidate_session.id,
                    task_id=task.id,
                    storage_key=recording_key,
                    content_type="video/mp4",
                    bytes=2_048_000,
                    asset_kind="recording",
                    duration_seconds=120,
                    status="ready",
                    consent_version="yc-demo-v1",
                    consent_timestamp=_now() - timedelta(days=1),
                    ai_notice_version="yc-demo-v1",
                    retention_expires_at=_now() + timedelta(days=30),
                )
                db.add(recording)
                await db.flush()
                transcript = Transcript(
                    recording_id=recording.id,
                    text=(
                        f"{candidate.name} explained the design, tradeoffs, and next steps "
                        f"for the {config.company_name} demo."
                    ),
                    segments_json=[
                        {"start": 0, "end": 60, "text": candidate.summary_line},
                        {
                            "start": 60,
                            "end": 120,
                            "text": "The evidence trail is grounded in the submitted artifacts.",
                        },
                    ],
                    model_name="demo-transcribe",
                    status="ready",
                )
                db.add(transcript)
                await db.flush()
                submission_recording_id = recording.id
                day4_transcript_id = transcript.id
                submission_spec["content_json"]["transcriptRecordingId"] = recording.id
            submission = Submission(
                candidate_session_id=candidate_session.id,
                task_id=task.id,
                recording_id=submission_recording_id,
                submitted_at=_now() - timedelta(days=5 - day_index),
                content_text=submission_spec["content_text"],
                content_json=submission_spec["content_json"],
                code_repo_path=submission_spec["code_repo_path"],
                commit_sha=submission_spec["commit_sha"],
                final_sha=submission_spec["commit_sha"] if day_index == 3 else None,
                workflow_run_id=(
                    f"yc-demo-{candidate.label}-day{day_index}"
                    if day_index in {2, 3}
                    else None
                ),
                workflow_run_attempt=1 if day_index in {2, 3} else None,
                workflow_run_status="completed" if day_index in {2, 3} else None,
                workflow_run_conclusion="success" if day_index in {2, 3} else None,
                workflow_run_completed_at=_now() if day_index in {2, 3} else None,
                diff_summary_json=submission_spec["diff_summary_json"],
                tests_passed=submission_spec["tests_passed"],
                tests_failed=submission_spec["tests_failed"],
                test_output=submission_spec["test_output"],
                last_run_at=_now() if day_index in {2, 3} else None,
            )
            db.add(submission)
            await db.flush()
            submission_ids_by_day[day_index] = submission.id

            if day_index in {2, 3}:
                await db.execute(
                    delete(CandidateDayAudit).where(
                        CandidateDayAudit.candidate_session_id == candidate_session.id,
                        CandidateDayAudit.day_index == day_index,
                    )
                )
                db.add(
                    CandidateDayAudit(
                        candidate_session_id=candidate_session.id,
                        day_index=day_index,
                        cutoff_at=_now() - timedelta(days=5 - day_index),
                        cutoff_commit_sha=(
                            day2_commit_sha if day_index == 2 else day3_commit_sha
                        ),
                        eval_basis_ref=(
                            f"{repo_result.repo_full_name}@"
                            f"{day2_commit_sha if day_index == 2 else day3_commit_sha}"
                        ),
                    )
                )
                await db.flush()

        day_rows, reviewer_rows = _build_report_rows(
            candidate=candidate,
            repo_full_name=repo_result.repo_full_name,
            bootstrap_commit_sha=repo_result.bootstrap_commit_sha or "",
            day2_commit_sha=day2_commit_sha,
            day3_commit_sha=day3_commit_sha,
            submission_ids_by_day=submission_ids_by_day,
            transcript_id=day4_transcript_id or 0,
        )
        raw_report_json = {
            "overallWinoeScore": candidate.overall_score,
            "recommendation": candidate.recommendation,
            "confidence": candidate.confidence,
            "dayScores": day_rows,
            "reviewerReports": reviewer_rows,
        }
        run = await create_run(
            db,
            candidate_session_id=candidate_session.id,
            scenario_version_id=scenario_version.id,
            model_name="demo-winoe-report",
            model_version="demo-1",
            prompt_version="demo-1",
            rubric_version="demo-1",
            day2_checkpoint_sha=day2_commit_sha,
            day3_final_sha=day3_commit_sha,
            cutoff_commit_sha=day3_commit_sha,
            transcript_reference=f"transcript:{recording_key}",
            job_id=None,
            basis_fingerprint=_stable_hex(
                candidate.email, repo_result.repo_full_name, "basis", length=64
            ),
            overall_winoe_score=candidate.overall_score,
            recommendation=candidate.internal_recommendation,
            confidence=candidate.confidence,
            generated_at=_now(),
            raw_report_json=raw_report_json,
            status=EVALUATION_RUN_STATUS_COMPLETED,
            started_at=_now() - timedelta(hours=1),
            completed_at=_now(),
            metadata_json={
                "aiPolicyProvider": "demo-seed",
                "aiPolicySnapshotDigest": (
                    scenario_version.ai_policy_snapshot_json or {}
                ).get("snapshotDigest"),
                "rubricSnapshots": [
                    {
                        "scope": "winoe",
                        "rubricKind": "demo",
                        "rubricKey": candidate.label,
                        "rubricVersion": "demo-1",
                    }
                ],
            },
            commit=False,
        )
        await add_day_scores(
            db,
            run=run,
            day_scores=day_rows,
            commit=False,
        )
        for reviewer_row in reviewer_rows:
            db.add(
                EvaluationReviewerReport(
                    run_id=run.id,
                    reviewer_agent_key=reviewer_row["reviewer_agent_key"],
                    day_index=reviewer_row["day_index"],
                    submission_kind=reviewer_row["submission_kind"],
                    score=reviewer_row["score"],
                    dimensional_scores_json=reviewer_row["dimensional_scores_json"],
                    evidence_citations_json=reviewer_row["evidence_citations_json"],
                    assessment_text=reviewer_row["assessment_text"],
                    strengths_json=reviewer_row["strengths_json"],
                    risks_json=reviewer_row["risks_json"],
                    raw_output_json={
                        "summary": candidate.summary_line,
                        "candidate": candidate.name,
                    },
                )
            )
        await upsert_marker(
            db,
            candidate_session_id=candidate_session.id,
            generated_at=_now(),
            commit=False,
        )
        candidate_session.completed_at = _now()
        candidate_session.status = "completed"

    await db.commit()
    return DemoSeedSummary(
        company_id=company.id,
        trial_id=trial.id,
        candidate_session_ids=[candidate.id for candidate in candidate_sessions],
        repo_full_names=repo_full_names,
    )


__all__ = [
    "DemoCandidateProfile",
    "DemoSeedConfig",
    "DemoSeedSummary",
    "_clear_demo_scope",
    "_reset_database",
    "seed_yc_demo_dataset",
]
