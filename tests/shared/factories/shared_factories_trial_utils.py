from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import build_ai_policy_snapshot, build_prompt_pack_entry
from app.evaluations.services.evaluations_services_trial_agent_snapshots_service import (
    materialize_trial_agent_snapshots,
)
from app.shared.database.shared_database_models_model import (
    ScenarioVersion,
    Task,
    Trial,
    User,
)
from app.trials.constants.trials_constants_trials_ai_config_constants import (
    AI_NOTICE_DEFAULT_TEXT,
    AI_NOTICE_DEFAULT_VERSION,
    default_ai_eval_enabled_by_day,
)
from app.trials.constants.trials_constants_trials_blueprints_constants import (
    DEFAULT_5_DAY_BLUEPRINT,
)
from app.trials.constants.trials_constants_trials_defaults_constants import (
    DEFAULT_TEMPLATE_KEY,
)
from app.trials.services.trials_services_trials_day_five_contract_service import (
    canonical_day_five_window_override,
)

_TRIAL_AGENT_KEYS_AND_NAMES = (
    ("prestart", "Prestart Project Brief Creator", "creator"),
    ("designDocReviewer", "Design Doc Reviewer", "reviewer"),
    ("codeImplementationReviewer", "Code Implementation Reviewer", "reviewer"),
    ("demoPresentationReviewer", "Handoff + Demo Reviewer", "reviewer"),
    ("reflectionEssayReviewer", "Reflection Reviewer", "reviewer"),
    ("winoeReport", "Winoe", "synthesis"),
)

_TRIAL_AGENT_RUNTIME_METADATA = {
    "prestart": ("anthropic", "claude-opus-4.6"),
    "designDocReviewer": ("anthropic", "claude-opus-4.6"),
    "codeImplementationReviewer": ("openai", "gpt-5.3-codex"),
    "demoPresentationReviewer": ("anthropic", "claude-sonnet-4.6"),
    "reflectionEssayReviewer": ("anthropic", "claude-sonnet-4.6"),
    "winoeReport": ("openai", "gpt-5.2"),
}


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_trial_agent_snapshots() -> list[SimpleNamespace]:
    snapshots: list[SimpleNamespace] = []
    for agent_key, agent_name, agent_type in _TRIAL_AGENT_KEYS_AND_NAMES:
        prompt_entry = build_prompt_pack_entry(agent_key)
        model_provider, model_name = _TRIAL_AGENT_RUNTIME_METADATA[agent_key]
        snapshots.append(
            SimpleNamespace(
                agent_name=agent_name,
                agent_type=agent_type,
                model_provider=model_provider,
                model_name=model_name,
                model_version=model_name,
                prompt_version=prompt_entry.prompt_version,
                prompt_content=prompt_entry.instructions_md,
                prompt_content_hash=_stable_hash(prompt_entry.instructions_md),
                rubric_version=prompt_entry.rubric_version,
                rubric_content=prompt_entry.rubric_md,
                rubric_content_hash=_stable_hash(prompt_entry.rubric_md),
                locked_at=datetime.now(UTC),
            )
        )
    return snapshots


async def create_trial(
    session: AsyncSession,
    *,
    created_by: User,
    title: str = "Backend Trial",
    role: str = "Backend Engineer",
    preferred_language_framework: str = "Node.js, PostgreSQL",
    seniority: str = "Mid",
    focus: str = "Deliver a backend feature over 5 days",
    template_key: str = DEFAULT_TEMPLATE_KEY,
    company_context: dict[str, str] | None = None,
    company_rubric_json: dict | None = None,
    ai_notice_version: str | None = None,
    ai_notice_text: str | None = None,
    ai_eval_enabled_by_day: dict[str, bool] | None = None,
) -> tuple[Trial, list[Task]]:
    ai_notice_version = ai_notice_version or AI_NOTICE_DEFAULT_VERSION
    ai_notice_text = ai_notice_text or AI_NOTICE_DEFAULT_TEXT
    ai_eval_enabled_by_day = ai_eval_enabled_by_day or default_ai_eval_enabled_by_day()
    sim = Trial(
        company_id=created_by.company_id,
        title=title,
        role=role,
        preferred_language_framework=preferred_language_framework,
        seniority=seniority,
        focus=focus,
        scenario_template="default-5day-node-postgres",
        created_by=created_by.id,
        status="generating",
        generating_at=datetime.now(UTC),
        template_key=template_key,
        company_context=company_context,
        company_rubric_json=company_rubric_json,
        ai_notice_version=ai_notice_version,
        ai_notice_text=ai_notice_text,
        ai_eval_enabled_by_day=ai_eval_enabled_by_day,
        day_window_overrides_enabled=True,
        day_window_overrides_json=canonical_day_five_window_override(),
    )
    session.add(sim)
    await session.flush()
    await materialize_trial_agent_snapshots(
        session,
        trial=sim,
    )
    tasks: list[Task] = []
    for blueprint_task in DEFAULT_5_DAY_BLUEPRINT:
        task = Task(
            trial_id=sim.id,
            day_index=blueprint_task["day_index"],
            type=blueprint_task["type"],
            title=blueprint_task["title"],
            description=blueprint_task["description"],
            template_repo=None,
        )
        session.add(task)
        tasks.append(task)
    await session.flush()
    scenario_version = ScenarioVersion(
        trial_id=sim.id,
        version_index=1,
        status="ready",
        storyline_md=f"# {sim.title}",
        project_brief_md=(
            "# Project Brief\n\n## Business Context\n\n" f"{sim.focus or sim.title}\n"
        ),
        task_prompts_json=[
            {
                "dayIndex": t.day_index,
                "type": t.type,
                "title": t.title,
                "description": t.description,
            }
            for t in sorted(tasks, key=lambda item: item.day_index)
        ],
        rubric_json={},
        focus_notes=sim.focus or "",
        template_key=sim.template_key,
        preferred_language_framework=sim.preferred_language_framework,
        seniority=sim.seniority,
        ai_policy_snapshot_json=build_ai_policy_snapshot(trial=sim),
    )
    session.add(scenario_version)
    await session.flush()
    sim.active_scenario_version_id = scenario_version.id
    sim.status = "active_inviting"
    sim.activated_at = datetime.now(UTC)
    await session.flush()
    tasks.sort(key=lambda t: t.day_index)
    return sim, tasks


__all__ = ["build_trial_agent_snapshots", "create_trial"]
