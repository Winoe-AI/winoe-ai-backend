"""Application module for trial-level AI agent snapshot materialization workflows."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from app.ai import build_prompt_pack_entry, resolve_prompt_layers
from app.ai.ai_runtime_config_service import (
    resolve_scenario_generation_config,
    resolve_winoe_report_aggregator_config,
    resolve_winoe_report_code_implementation_config,
    resolve_winoe_report_day1_config,
    resolve_winoe_report_day4_config,
    resolve_winoe_report_day5_config,
)
from app.evaluations.repositories import (
    list_trial_agent_snapshots,
    replace_trial_agent_snapshots,
)
from app.evaluations.repositories.evaluations_repositories_trial_agent_snapshot_model import (
    TrialAgentSnapshot,
)
from app.shared.database.shared_database_models_model import CandidateSession

logger = logging.getLogger(__name__)

_AGENT_LABELS = {
    "prestart": ("Prestart Project Brief Creator", "creator"),
    "designDocReviewer": ("Design Doc Reviewer", "reviewer"),
    "codeImplementationReviewer": ("Code Implementation Reviewer", "reviewer"),
    "demoPresentationReviewer": ("Handoff + Demo Reviewer", "reviewer"),
    "reflectionEssayReviewer": ("Reflection Reviewer", "reviewer"),
    "winoeReport": ("Winoe", "synthesis"),
}

_AGENT_RUNTIME_RESOLVERS = {
    "prestart": resolve_scenario_generation_config,
    "designDocReviewer": resolve_winoe_report_day1_config,
    "codeImplementationReviewer": resolve_winoe_report_code_implementation_config,
    "demoPresentationReviewer": resolve_winoe_report_day4_config,
    "reflectionEssayReviewer": resolve_winoe_report_day5_config,
    "winoeReport": resolve_winoe_report_aggregator_config,
}


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _snapshot_row_matches_current(
    *,
    snapshot,
    expected_row: dict[str, Any],
) -> bool:
    return (
        getattr(snapshot, "agent_name", None) == expected_row["agent_name"]
        and getattr(snapshot, "agent_type", None) == expected_row["agent_type"]
        and getattr(snapshot, "model_provider", None) == expected_row["model_provider"]
        and getattr(snapshot, "model_name", None) == expected_row["model_name"]
        and getattr(snapshot, "model_version", None) == expected_row["model_version"]
        and getattr(snapshot, "prompt_version", None) == expected_row["prompt_version"]
        and getattr(snapshot, "rubric_version", None) == expected_row["rubric_version"]
        and getattr(snapshot, "prompt_content_hash", None)
        == expected_row["prompt_content_hash"]
        and getattr(snapshot, "rubric_content_hash", None)
        == expected_row["rubric_content_hash"]
        and getattr(snapshot, "prompt_content", None) == expected_row["prompt_content"]
        and getattr(snapshot, "rubric_content", None) == expected_row["rubric_content"]
    )


def _build_trial_snapshot_row(
    *,
    agent_key: str,
    company_prompt_overrides_json: dict[str, Any] | None,
    trial_prompt_overrides_json: dict[str, Any] | None,
) -> dict[str, Any]:
    prompt_entry = build_prompt_pack_entry(agent_key)
    resolved_instructions_md, resolved_rubric_md = resolve_prompt_layers(
        key=agent_key,
        base_instructions_md=prompt_entry.instructions_md,
        base_rubric_md=prompt_entry.rubric_md,
        company_overrides_json=company_prompt_overrides_json,
        trial_overrides_json=trial_prompt_overrides_json,
        run_context_md=None,
    )
    runtime = _AGENT_RUNTIME_RESOLVERS[agent_key]()
    agent_name, agent_type = _AGENT_LABELS[agent_key]
    locked_at = datetime.now(UTC)
    return {
        "agent_name": agent_name,
        "agent_type": agent_type,
        "model_provider": runtime.provider,
        "model_name": runtime.model,
        "model_version": runtime.model,
        "prompt_version": prompt_entry.prompt_version,
        "prompt_content": resolved_instructions_md,
        "prompt_content_hash": _stable_hash(resolved_instructions_md),
        "rubric_version": prompt_entry.rubric_version,
        "rubric_content": resolved_rubric_md,
        "rubric_content_hash": _stable_hash(resolved_rubric_md),
        "locked_at": locked_at,
    }


async def materialize_trial_agent_snapshots(
    db: AsyncSession,
    *,
    trial,
    company_prompt_overrides_json: dict[str, Any] | None = None,
    trial_prompt_overrides_json: dict[str, Any] | None = None,
    commit: bool = False,
) -> list[TrialAgentSnapshot]:
    """Create the immutable agent snapshot rows for one Trial."""
    existing_snapshots = await list_trial_agent_snapshots(db, trial_id=trial.id)
    expected_rows = [
        _build_trial_snapshot_row(
            agent_key=agent_key,
            company_prompt_overrides_json=company_prompt_overrides_json,
            trial_prompt_overrides_json=trial_prompt_overrides_json,
        )
        for agent_key in _AGENT_LABELS
    ]
    expected_agent_names = {row["agent_name"] for row in expected_rows}
    existing_agent_names = {
        snapshot.agent_name for snapshot in existing_snapshots if snapshot.agent_name
    }
    snapshots_are_current = (
        len(existing_snapshots) == len(expected_rows)
        and existing_agent_names == expected_agent_names
        and all(
            _snapshot_row_matches_current(snapshot=snapshot, expected_row=expected_row)
            for snapshot, expected_row in zip(
                sorted(
                    existing_snapshots,
                    key=lambda snapshot: (
                        str(snapshot.agent_name),
                        str(snapshot.agent_type),
                        str(snapshot.model_name),
                    ),
                ),
                sorted(expected_rows, key=lambda row: row["agent_name"]),
                strict=False,
            )
        )
    )
    if snapshots_are_current:
        attributes.set_committed_value(trial, "agent_snapshots", existing_snapshots)
        return existing_snapshots
    if existing_snapshots:
        has_candidate_session = (
            await db.execute(
                select(CandidateSession.id)
                .where(CandidateSession.trial_id == int(trial.id))
                .limit(1)
            )
        ).scalar_one_or_none() is not None
        if has_candidate_session:
            raise RuntimeError(
                "trial_agent_snapshots_stale_after_candidate_session_exists"
            )
        logger.warning(
            "repairing_trial_agent_snapshots trialId=%s existingCount=%s expectedCount=%s",
            trial.id,
            len(existing_snapshots),
            len(expected_rows),
        )
        snapshots = await replace_trial_agent_snapshots(
            db,
            trial_id=trial.id,
            snapshots=expected_rows,
            commit=commit,
        )
        attributes.set_committed_value(trial, "agent_snapshots", snapshots)
        return snapshots
    snapshots = await replace_trial_agent_snapshots(
        db,
        trial_id=trial.id,
        snapshots=expected_rows,
        commit=commit,
    )
    attributes.set_committed_value(trial, "agent_snapshots", snapshots)
    return snapshots


__all__ = ["materialize_trial_agent_snapshots"]
