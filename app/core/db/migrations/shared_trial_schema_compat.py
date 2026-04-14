"""Compatibility helpers for canonical trial schema migration history."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.engine import Connection

_TRIAL_PARENT_TABLE_CANDIDATES = ("trials", "simulations")
_CANDIDATE_SESSION_PARENT_COLUMN_CANDIDATES = ("trial_id", "simulation_id")
_SCHEMA_REPAIR_REVISION = "202604130001"


def _inspector(bind: Connection) -> sa.Inspector | None:
    try:
        return sa.inspect(bind)
    except sa.exc.NoInspectionAvailable:
        return None


def _table_names(bind: Connection) -> set[str]:
    inspector = _inspector(bind)
    if inspector is None:
        return set()
    return set(inspector.get_table_names())


def resolve_trial_parent_table_name(bind: Connection) -> str:
    """Return the active parent table name for migration helpers."""
    table_names = _table_names(bind)
    if "trials" in table_names and "simulations" in table_names:
        raise RuntimeError(
            "Detected both canonical 'trials' and legacy 'simulations' tables. "
            f"Run schema repair migration {_SCHEMA_REPAIR_REVISION} before "
            "executing compatibility helpers."
        )
    for candidate in _TRIAL_PARENT_TABLE_CANDIDATES:
        if candidate in table_names:
            return candidate
    return "trials"


def resolve_candidate_session_parent_column_name(bind: Connection) -> str:
    """Return the candidate-session parent foreign-key column."""
    if "candidate_sessions" not in _table_names(bind):
        return "trial_id"

    inspector = _inspector(bind)
    if inspector is None:
        return "trial_id"
    columns = {column["name"] for column in inspector.get_columns("candidate_sessions")}
    if "trial_id" in columns and "simulation_id" in columns:
        raise RuntimeError(
            "Detected both canonical 'trial_id' and legacy 'simulation_id' columns "
            "on 'candidate_sessions'. Run schema repair migration "
            f"{_SCHEMA_REPAIR_REVISION} before executing compatibility helpers."
        )
    for candidate in _CANDIDATE_SESSION_PARENT_COLUMN_CANDIDATES:
        if candidate in columns:
            return candidate
    return "trial_id"


def resolve_pending_scenario_fk_name(parent_table_name: str) -> str:
    """Return the canonical pending-scenario FK name for the active schema."""
    if parent_table_name == "simulations":
        return "fk_simulations_pending_scenario_version_id"
    return "fk_trials_pending_scenario_version_id"
