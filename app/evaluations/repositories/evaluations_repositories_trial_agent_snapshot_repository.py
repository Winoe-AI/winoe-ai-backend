"""Application module for trial agent snapshot persistence workflows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .evaluations_repositories_trial_agent_snapshot_model import TrialAgentSnapshot


async def list_trial_agent_snapshots(
    db: AsyncSession,
    *,
    trial_id: int,
) -> list[TrialAgentSnapshot]:
    stmt = (
        select(TrialAgentSnapshot)
        .where(TrialAgentSnapshot.trial_id == int(trial_id))
        .order_by(TrialAgentSnapshot.agent_name.asc(), TrialAgentSnapshot.id.asc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def delete_trial_agent_snapshots(
    db: AsyncSession,
    *,
    trial_id: int,
) -> None:
    await db.execute(
        delete(TrialAgentSnapshot).where(TrialAgentSnapshot.trial_id == int(trial_id))
    )


async def replace_trial_agent_snapshots(
    db: AsyncSession,
    *,
    trial_id: int,
    snapshots: Sequence[Mapping[str, Any]],
    commit: bool = False,
) -> list[TrialAgentSnapshot]:
    await delete_trial_agent_snapshots(db, trial_id=trial_id)
    rows: list[TrialAgentSnapshot] = []
    for entry in snapshots:
        row = TrialAgentSnapshot(
            trial_id=int(trial_id),
            agent_name=str(entry["agent_name"]).strip(),
            agent_type=str(entry["agent_type"]).strip(),
            model_provider=str(entry["model_provider"]).strip(),
            model_name=str(entry["model_name"]).strip(),
            model_version=str(entry["model_version"]).strip(),
            prompt_version=str(entry["prompt_version"]).strip(),
            prompt_content=str(entry["prompt_content"]).strip(),
            prompt_content_hash=str(entry["prompt_content_hash"]).strip(),
            rubric_version=str(entry["rubric_version"]).strip(),
            rubric_content=str(entry["rubric_content"]).strip(),
            rubric_content_hash=str(entry["rubric_content_hash"]).strip(),
            locked_at=entry.get("locked_at"),
        )
        rows.append(row)
        db.add(row)
    if commit:
        await db.commit()
        for row in rows:
            await db.refresh(row)
    else:
        await db.flush()
    return rows


async def get_required_trial_agent_snapshot(
    db: AsyncSession,
    *,
    trial_id: int,
    agent_name: str,
) -> TrialAgentSnapshot:
    stmt = select(TrialAgentSnapshot).where(
        TrialAgentSnapshot.trial_id == int(trial_id),
        TrialAgentSnapshot.agent_name == agent_name,
    )
    snapshot = (await db.execute(stmt)).scalar_one_or_none()
    if snapshot is None:
        raise LookupError(
            f"Missing trial agent snapshot for trial_id={trial_id} agent={agent_name}"
        )
    return snapshot


__all__ = [
    "delete_trial_agent_snapshots",
    "get_required_trial_agent_snapshot",
    "list_trial_agent_snapshots",
    "replace_trial_agent_snapshots",
]
