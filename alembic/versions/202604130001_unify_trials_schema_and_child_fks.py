"""Unify schema on canonical trials table and repair child trial foreign keys.

Revision ID: 202604130001
Revises: 202604090001
Create Date: 2026-04-13 00:01:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from alembic import op
from app.core.db.migrations.reconcile_202603190001.constants import DEFAULT_TEMPLATE_KEY

revision: str = "202604130001"
down_revision: str | Sequence[str] | None = "202604090001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CANONICAL_PARENT_TABLE = "trials"
_LEGACY_PARENT_TABLE = "simulations"
_PARENT_LEGACY_TO_CANONICAL_COLUMN_MAP: dict[str, str] = {
    "terminated_by_recruiter_id": "terminated_by_talent_partner_id",
}
_CANONICAL_PARENT_COLUMN_ALLOWLIST: frozenset[str] = frozenset(
    {
        "id",
        "company_id",
        "title",
        "role",
        "tech_stack",
        "seniority",
        "scenario_template",
        "template_key",
        "focus",
        "company_context",
        "ai_prompt_overrides_json",
        "ai_notice_version",
        "ai_notice_text",
        "ai_eval_enabled_by_day",
        "day_window_start_local",
        "day_window_end_local",
        "day_window_overrides_enabled",
        "day_window_overrides_json",
        "created_by",
        "status",
        "active_scenario_version_id",
        "pending_scenario_version_id",
        "generating_at",
        "ready_for_review_at",
        "activated_at",
        "terminated_at",
        "terminated_reason",
        "terminated_by_talent_partner_id",
        "created_at",
    }
)

_PARENT_COMPARISON_COLUMN_CANDIDATES = (
    "id",
    "company_id",
    "title",
    "role",
    "tech_stack",
    "seniority",
    "scenario_template",
    "template_key",
    "focus",
    "created_by",
    "status",
    "active_scenario_version_id",
    "pending_scenario_version_id",
    "generating_at",
    "ready_for_review_at",
    "activated_at",
    "terminated_at",
    "terminated_reason",
    "terminated_by_talent_partner_id",
)
_ACTIVE_SCENARIO_REQUIRED_STATUSES = frozenset(
    {"ready_for_review", "active_inviting", "terminated"}
)


def _inspector(bind: Connection) -> sa.Inspector:
    return sa.inspect(bind)


def _is_postgresql(bind: Connection) -> bool:
    return bind.dialect.name == "postgresql"


def _table_exists(bind: Connection, table_name: str) -> bool:
    return table_name in set(_inspector(bind).get_table_names())


def _column_names(bind: Connection, table_name: str) -> set[str]:
    return {column["name"] for column in _inspector(bind).get_columns(table_name)}


def _column_type(
    bind: Connection,
    *,
    table_name: str,
    column_name: str,
) -> sa.types.TypeEngine:
    for column in _inspector(bind).get_columns(table_name):
        if column.get("name") == column_name:
            return column["type"]
    raise RuntimeError(f"Column '{column_name}' was not found on table '{table_name}'.")


def _sqlite_master_index_names(bind: Connection, table_name: str) -> set[str]:
    if bind.dialect.name != "sqlite":
        return set()
    rows = bind.execute(
        sa.text(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'index'
              AND tbl_name = :table_name
              AND name NOT LIKE 'sqlite_autoindex_%'
            """
        ),
        {"table_name": table_name},
    )
    return {str(row[0]) for row in rows if row[0]}


def _index_names(bind: Connection, table_name: str) -> set[str]:
    reflected_names = {
        index["name"]
        for index in _inspector(bind).get_indexes(table_name)
        if index.get("name")
    }
    return reflected_names | _sqlite_master_index_names(bind, table_name)


def _normalize_sql_text(sql_text: str) -> str:
    return "".join(
        character
        for character in sql_text.lower()
        if not character.isspace() and character != '"'
    )


def _index_definition_sql(
    bind: Connection,
    *,
    table_name: str,
    index_name: str,
) -> str | None:
    if bind.dialect.name == "sqlite":
        return bind.execute(
            sa.text(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type = 'index'
                  AND tbl_name = :table_name
                  AND name = :index_name
                """
            ),
            {"table_name": table_name, "index_name": index_name},
        ).scalar_one_or_none()
    if _is_postgresql(bind):
        return bind.execute(
            sa.text(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE tablename = :table_name
                  AND indexname = :index_name
                  AND schemaname = ANY(current_schemas(false))
                ORDER BY CASE WHEN schemaname = current_schema() THEN 0 ELSE 1 END
                LIMIT 1
                """
            ),
            {"table_name": table_name, "index_name": index_name},
        ).scalar_one_or_none()
    return None


def _index_is_case_insensitive_invite_unique(
    bind: Connection,
    *,
    table_name: str,
    index_name: str,
    parent_column: str,
) -> bool:
    index_sql = _index_definition_sql(
        bind,
        table_name=table_name,
        index_name=index_name,
    )
    if not index_sql:
        return False
    normalized = _normalize_sql_text(index_sql)
    return (
        "createuniqueindex" in normalized
        and f"({parent_column.lower()},lower(" in normalized
        and "invite_email" in normalized
    )


def _create_candidate_session_ci_unique_index(
    op_obj: object,
    *,
    parent_column: str,
    index_name: str,
) -> None:
    op_obj.create_index(
        index_name,
        "candidate_sessions",
        [parent_column, sa.text("lower(invite_email)")],
        unique=True,
    )


def _unique_constraint_names(bind: Connection, table_name: str) -> set[str]:
    return {
        unique["name"]
        for unique in _inspector(bind).get_unique_constraints(table_name)
        if unique.get("name")
    }


def _foreign_keys(bind: Connection, table_name: str) -> list[dict[str, object]]:
    return [
        foreign_key
        for foreign_key in _inspector(bind).get_foreign_keys(table_name)
        if foreign_key
    ]


def _foreign_key_names(bind: Connection, table_name: str) -> set[str]:
    return {
        str(foreign_key["name"])
        for foreign_key in _foreign_keys(bind, table_name)
        if foreign_key.get("name")
    }


def _rename_postgresql_index(bind: Connection, old_name: str, new_name: str) -> None:
    bind.execute(sa.text(f'ALTER INDEX "{old_name}" RENAME TO "{new_name}"'))


def _rename_postgresql_constraint(
    bind: Connection,
    *,
    table_name: str,
    old_name: str,
    new_name: str,
) -> None:
    bind.execute(
        sa.text(
            f'ALTER TABLE "{table_name}" RENAME CONSTRAINT "{old_name}" TO "{new_name}"'
        )
    )


def _rename_postgresql_sequence(bind: Connection, old_name: str, new_name: str) -> None:
    bind.execute(sa.text(f'ALTER SEQUENCE "{old_name}" RENAME TO "{new_name}"'))


def _rename_parent_table_postgresql_artifacts(
    bind: Connection,
    *,
    old_table: str,
    new_table: str,
    index_renames: dict[str, str],
    constraint_renames: dict[str, str],
) -> None:
    if not _is_postgresql(bind):
        return

    pk_name = _inspector(bind).get_pk_constraint(new_table).get("name")
    if pk_name == f"{old_table}_pkey":
        _rename_postgresql_constraint(
            bind,
            table_name=new_table,
            old_name=f"{old_table}_pkey",
            new_name=f"{new_table}_pkey",
        )

    existing_indexes = _index_names(bind, new_table)
    for old_name, new_name in index_renames.items():
        if old_name in existing_indexes and new_name not in existing_indexes:
            _rename_postgresql_index(bind, old_name, new_name)

    existing_constraints = (
        _unique_constraint_names(bind, new_table)
        | _foreign_key_names(bind, new_table)
        | {
            check["name"]
            for check in _inspector(bind).get_check_constraints(new_table)
            if check.get("name")
        }
    )
    for old_name, new_name in constraint_renames.items():
        if old_name in existing_constraints and new_name not in existing_constraints:
            _rename_postgresql_constraint(
                bind,
                table_name=new_table,
                old_name=old_name,
                new_name=new_name,
            )

    sequence_old = f"{old_table}_id_seq"
    sequence_new = f"{new_table}_id_seq"
    sequence_exists = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.sequences
            WHERE sequence_name = :sequence_name
            """
        ),
        {"sequence_name": sequence_old},
    ).scalar_one_or_none()
    if sequence_exists:
        _rename_postgresql_sequence(bind, sequence_old, sequence_new)


def _row_count(bind: Connection, table_name: str) -> int:
    return int(
        bind.execute(sa.text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar_one()
    )


def _load_parent_rows_for_comparison(
    bind: Connection,
    *,
    table_name: str,
    columns: Sequence[str],
) -> dict[int, dict[str, object]]:
    table = sa.table(table_name, *(sa.column(column_name) for column_name in columns))
    rows = bind.execute(sa.select(*[table.c[column_name] for column_name in columns]))
    return {int(row["id"]): dict(row) for row in rows.mappings()}


def _non_null_row_count_for_column(
    bind: Connection,
    *,
    table_name: str,
    column_name: str,
) -> int:
    table = sa.table(table_name, sa.column(column_name))
    return int(
        bind.execute(
            sa.select(sa.func.count())
            .select_from(table)
            .where(table.c[column_name].is_not(None))
        ).scalar_one()
    )


def _assert_known_parent_mapping_targets_available(bind: Connection) -> None:
    if not _table_exists(bind, _LEGACY_PARENT_TABLE):
        return
    if not _table_exists(bind, _CANONICAL_PARENT_TABLE):
        return

    legacy_columns = _column_names(bind, _LEGACY_PARENT_TABLE)
    canonical_columns = _column_names(bind, _CANONICAL_PARENT_TABLE)
    missing_mappings = [
        f"{legacy_column}->{canonical_column}"
        for legacy_column, canonical_column in _PARENT_LEGACY_TO_CANONICAL_COLUMN_MAP.items()
        if legacy_column in legacy_columns and canonical_column not in canonical_columns
    ]
    if missing_mappings:
        raise RuntimeError(
            "Unsafe split parent schema detected: mapped legacy parent columns "
            "cannot be merged because canonical target columns are missing: "
            f"{', '.join(sorted(missing_mappings))}."
        )


def _assert_no_conflicting_legacy_mapped_parent_values(bind: Connection) -> None:
    if not _table_exists(bind, _LEGACY_PARENT_TABLE):
        return

    legacy_columns = _column_names(bind, _LEGACY_PARENT_TABLE)
    for (
        legacy_column,
        canonical_column,
    ) in _PARENT_LEGACY_TO_CANONICAL_COLUMN_MAP.items():
        if legacy_column not in legacy_columns:
            continue
        if canonical_column not in legacy_columns:
            continue

        conflicts = bind.execute(
            sa.text(
                f"""
                SELECT COUNT(*)
                FROM "{_LEGACY_PARENT_TABLE}"
                WHERE "{legacy_column}" IS NOT NULL
                  AND "{canonical_column}" IS NOT NULL
                  AND "{legacy_column}" <> "{canonical_column}"
                """
            )
        ).scalar_one()
        if int(conflicts) > 0:
            raise RuntimeError(
                "Unsafe split parent schema detected: legacy parent rows contain "
                "conflicting values across mapped columns "
                f"'{legacy_column}' and '{canonical_column}'."
            )


def _canonical_parent_columns_for_legacy_validation(bind: Connection) -> set[str]:
    if _table_exists(bind, _CANONICAL_PARENT_TABLE):
        return _column_names(bind, _CANONICAL_PARENT_TABLE)
    return set(_CANONICAL_PARENT_COLUMN_ALLOWLIST)


def _unknown_legacy_only_parent_columns(bind: Connection) -> list[str]:
    if not _table_exists(bind, _LEGACY_PARENT_TABLE):
        return []
    legacy_columns = _column_names(bind, _LEGACY_PARENT_TABLE)
    canonical_columns = _canonical_parent_columns_for_legacy_validation(bind)
    return sorted(
        column_name
        for column_name in legacy_columns - canonical_columns
        if column_name not in _PARENT_LEGACY_TO_CANONICAL_COLUMN_MAP
    )


def _assert_no_non_null_unknown_legacy_parent_data(bind: Connection) -> None:
    if not _table_exists(bind, _LEGACY_PARENT_TABLE):
        return

    unknown_legacy_only_columns = _unknown_legacy_only_parent_columns(bind)
    non_null_unknown_columns = [
        column_name
        for column_name in unknown_legacy_only_columns
        if _non_null_row_count_for_column(
            bind,
            table_name=_LEGACY_PARENT_TABLE,
            column_name=column_name,
        )
        > 0
    ]
    if non_null_unknown_columns:
        state_name = (
            "split parent"
            if _table_exists(bind, _CANONICAL_PARENT_TABLE)
            else "legacy-only parent"
        )
        raise RuntimeError(
            f"Unsafe {state_name} schema detected: legacy parent table contains "
            "non-null data in unmapped legacy-only columns: "
            f"{', '.join(non_null_unknown_columns)}."
        )


def _assert_split_parent_mapping_is_safe(bind: Connection) -> None:
    _assert_known_parent_mapping_targets_available(bind)
    _assert_no_conflicting_legacy_mapped_parent_values(bind)
    _assert_no_non_null_unknown_legacy_parent_data(bind)


def _assert_safe_split_parent_state(bind: Connection) -> None:
    if not (_table_exists(bind, _CANONICAL_PARENT_TABLE)):
        return
    if not (_table_exists(bind, _LEGACY_PARENT_TABLE)):
        return

    legacy_count = _row_count(bind, _LEGACY_PARENT_TABLE)
    canonical_count = _row_count(bind, _CANONICAL_PARENT_TABLE)
    if legacy_count == 0 or canonical_count == 0:
        return

    _assert_split_parent_mapping_is_safe(bind)

    legacy_columns = _column_names(bind, _LEGACY_PARENT_TABLE)
    canonical_columns = _column_names(bind, _CANONICAL_PARENT_TABLE)
    mapped_parent_column_pairs = [
        (legacy_column, canonical_column)
        for legacy_column, canonical_column in _PARENT_LEGACY_TO_CANONICAL_COLUMN_MAP.items()
        if legacy_column in legacy_columns and canonical_column in canonical_columns
    ]
    mapped_targets = {
        canonical_column for _, canonical_column in mapped_parent_column_pairs
    }
    comparison_columns = [
        column_name
        for column_name in _PARENT_COMPARISON_COLUMN_CANDIDATES
        if column_name in legacy_columns
        and column_name in canonical_columns
        and (column_name not in mapped_targets or column_name == "id")
    ]
    if "id" not in comparison_columns:
        raise RuntimeError(
            "Unsafe split parent schema detected: unable to compare legacy and "
            "canonical parent rows because 'id' is missing."
        )

    legacy_comparison_columns = list(
        dict.fromkeys(
            comparison_columns
            + [legacy_column for legacy_column, _ in mapped_parent_column_pairs]
            + [
                canonical_column
                for _, canonical_column in mapped_parent_column_pairs
                if canonical_column in legacy_columns
            ]
        )
    )
    canonical_comparison_columns = list(
        dict.fromkeys(
            comparison_columns
            + [canonical_column for _, canonical_column in mapped_parent_column_pairs]
        )
    )

    legacy_rows = _load_parent_rows_for_comparison(
        bind,
        table_name=_LEGACY_PARENT_TABLE,
        columns=legacy_comparison_columns,
    )
    canonical_rows = _load_parent_rows_for_comparison(
        bind,
        table_name=_CANONICAL_PARENT_TABLE,
        columns=canonical_comparison_columns,
    )

    legacy_ids = set(legacy_rows)
    canonical_ids = set(canonical_rows)
    if legacy_ids != canonical_ids:
        raise RuntimeError(
            "Unsafe split parent schema detected: legacy 'simulations' and "
            "canonical 'trials' contain different primary keys."
        )

    for row_id in sorted(legacy_ids):
        legacy_row = legacy_rows[row_id]
        canonical_row = canonical_rows[row_id]
        for column_name in comparison_columns:
            if column_name == "id":
                continue
            if legacy_row[column_name] != canonical_row[column_name]:
                raise RuntimeError(
                    "Unsafe split parent schema detected: legacy 'simulations' and "
                    "canonical 'trials' contain divergent non-empty data."
                )
        for legacy_column, canonical_column in mapped_parent_column_pairs:
            legacy_value = legacy_row.get(canonical_column)
            if legacy_value is None:
                legacy_value = legacy_row.get(legacy_column)
            if legacy_value != canonical_row[canonical_column]:
                raise RuntimeError(
                    "Unsafe split parent schema detected: mapped legacy parent "
                    f"column '{legacy_column}' does not match canonical column "
                    f"'{canonical_column}'."
                )


def _status_requires_active_scenario(status: object) -> bool:
    return str(status or "").strip() in _ACTIVE_SCENARIO_REQUIRED_STATUSES


def _scenario_version_parent_columns_for_merge(bind: Connection) -> tuple[str, ...]:
    if not _table_exists(bind, "scenario_versions"):
        return ()

    columns = _column_names(bind, "scenario_versions")
    if {"trial_id", "simulation_id"} <= columns:
        _assert_no_dual_fk_conflicts(bind, table_name="scenario_versions")

    return tuple(
        column_name
        for column_name in ("simulation_id", "trial_id")
        if column_name in columns
    )


def _derive_version_one_scenario_ids_for_parent_ids(
    bind: Connection, *, parent_ids: Sequence[int]
) -> dict[int, int]:
    normalized_parent_ids = sorted({int(parent_id) for parent_id in parent_ids})
    if not normalized_parent_ids:
        return {}

    parent_columns = _scenario_version_parent_columns_for_merge(bind)
    if not parent_columns:
        return {}

    metadata = sa.MetaData()
    scenario_versions = sa.Table("scenario_versions", metadata, autoload_with=bind)

    normalized_matches: sa.Select | sa.CompoundSelect | None = None
    for parent_column in parent_columns:
        select_for_parent_column = sa.select(
            scenario_versions.c[parent_column].label("parent_id"),
            scenario_versions.c.id.label("scenario_id"),
        ).where(
            scenario_versions.c[parent_column].in_(normalized_parent_ids),
            scenario_versions.c.version_index == 1,
        )
        if normalized_matches is None:
            normalized_matches = select_for_parent_column
        else:
            normalized_matches = normalized_matches.union_all(select_for_parent_column)

    if normalized_matches is None:
        return {}

    scenario_ids_by_parent: dict[int, set[int]] = {}
    for row in bind.execute(normalized_matches).mappings():
        parent_id = int(row["parent_id"])
        scenario_id = int(row["scenario_id"])
        scenario_ids_by_parent.setdefault(parent_id, set()).add(scenario_id)

    conflicting_parent_ids = [
        parent_id
        for parent_id, scenario_ids in scenario_ids_by_parent.items()
        if len(scenario_ids) > 1
    ]
    if conflicting_parent_ids:
        joined_parent_ids = ", ".join(
            str(parent_id) for parent_id in conflicting_parent_ids
        )
        raise RuntimeError(
            "Unsafe split parent schema detected: multiple version-1 "
            "scenario_versions rows map to legacy parent ids that require a single "
            f"active scenario pointer: {joined_parent_ids}."
        )

    return {
        parent_id: next(iter(scenario_ids))
        for parent_id, scenario_ids in scenario_ids_by_parent.items()
    }


def _populate_required_active_scenario_ids_for_merge(
    bind: Connection, *, rows_to_insert: list[dict[str, object]]
) -> None:
    if not rows_to_insert:
        return
    if "active_scenario_version_id" not in rows_to_insert[0]:
        return
    if "status" not in rows_to_insert[0]:
        return

    parent_ids_requiring_derivation = [
        int(row["id"])
        for row in rows_to_insert
        if row.get("id") is not None
        and row.get("active_scenario_version_id") is None
        and _status_requires_active_scenario(row.get("status"))
    ]
    if not parent_ids_requiring_derivation:
        return

    derived_scenario_ids = _derive_version_one_scenario_ids_for_parent_ids(
        bind, parent_ids=parent_ids_requiring_derivation
    )
    unresolved_rows: list[str] = []
    for row in rows_to_insert:
        if row.get("id") is None:
            continue
        if row.get("active_scenario_version_id") is not None:
            continue
        if not _status_requires_active_scenario(row.get("status")):
            continue

        parent_id = int(row["id"])
        derived_scenario_id = derived_scenario_ids.get(parent_id)
        if derived_scenario_id is None:
            unresolved_rows.append(
                f"{parent_id} (status={str(row.get('status') or '').strip() or '<null>'})"
            )
            continue

        row["active_scenario_version_id"] = derived_scenario_id

    if unresolved_rows:
        joined_rows = ", ".join(unresolved_rows)
        raise RuntimeError(
            "Unsafe split parent schema detected: cannot derive "
            "active_scenario_version_id before inserting legacy rows into canonical "
            "'trials'. Expected an existing version-1 'scenario_versions' row for: "
            f"{joined_rows}."
        )


def _merge_missing_trials_rows_from_legacy(bind: Connection) -> None:
    if not (_table_exists(bind, _LEGACY_PARENT_TABLE)):
        return
    if not (_table_exists(bind, _CANONICAL_PARENT_TABLE)):
        return

    _assert_split_parent_mapping_is_safe(bind)

    metadata = sa.MetaData()
    legacy = sa.Table(_LEGACY_PARENT_TABLE, metadata, autoload_with=bind)
    canonical = sa.Table(_CANONICAL_PARENT_TABLE, metadata, autoload_with=bind)
    legacy_alias = legacy.alias("legacy")
    canonical_alias = canonical.alias("canonical")

    canonical_target_to_legacy_source = {
        canonical_column: legacy_column
        for legacy_column, canonical_column in _PARENT_LEGACY_TO_CANONICAL_COLUMN_MAP.items()
    }
    insert_columns: list[str] = []
    select_columns: list[sa.ColumnElement] = []
    for canonical_column in canonical.c:
        canonical_name = canonical_column.name
        legacy_source_name = canonical_target_to_legacy_source.get(canonical_name)
        if legacy_source_name and legacy_source_name in legacy_alias.c:
            if canonical_name in legacy_alias.c:
                source_expression = sa.func.coalesce(
                    legacy_alias.c[canonical_name],
                    legacy_alias.c[legacy_source_name],
                )
            else:
                source_expression = legacy_alias.c[legacy_source_name]
            insert_columns.append(canonical_name)
            select_columns.append(source_expression.label(canonical_name))
            continue
        if canonical_name in legacy_alias.c:
            insert_columns.append(canonical_name)
            select_columns.append(legacy_alias.c[canonical_name])

    if "id" not in insert_columns:
        raise RuntimeError(
            "Cannot merge legacy rows into canonical parent table: missing shared 'id' "
            "column."
        )

    missing_id_exists = sa.exists(
        sa.select(sa.literal(1))
        .select_from(canonical_alias)
        .where(canonical_alias.c.id == legacy_alias.c.id)
    )
    select_missing_rows = sa.select(*select_columns).where(~missing_id_exists)
    rows_to_insert = [dict(row) for row in bind.execute(select_missing_rows).mappings()]
    if not rows_to_insert:
        return

    _populate_required_active_scenario_ids_for_merge(
        bind, rows_to_insert=rows_to_insert
    )
    bind.execute(sa.insert(canonical), rows_to_insert)


def _repair_split_parent_when_canonical_empty(bind: Connection) -> bool:
    if not _table_exists(bind, _CANONICAL_PARENT_TABLE):
        return False
    if not _table_exists(bind, _LEGACY_PARENT_TABLE):
        return False

    legacy_count = _row_count(bind, _LEGACY_PARENT_TABLE)
    canonical_count = _row_count(bind, _CANONICAL_PARENT_TABLE)
    if canonical_count != 0 or legacy_count == 0:
        return False

    _assert_split_parent_mapping_is_safe(bind)
    _merge_missing_trials_rows_from_legacy(bind)
    return True


def _drop_foreign_keys_for_column(
    op_obj: object,
    bind: Connection,
    *,
    table_name: str,
    column_name: str,
) -> None:
    if not _is_postgresql(bind):
        return
    for foreign_key in _foreign_keys(bind, table_name):
        name = foreign_key.get("name")
        constrained_columns = foreign_key.get("constrained_columns") or []
        if not name or column_name not in constrained_columns:
            continue
        op_obj.drop_constraint(name, table_name, type_="foreignkey")


def _drop_unique_constraints_for_column(
    op_obj: object,
    bind: Connection,
    *,
    table_name: str,
    column_name: str,
) -> None:
    if not _is_postgresql(bind):
        return
    for unique in _inspector(bind).get_unique_constraints(table_name):
        name = unique.get("name")
        columns = unique.get("column_names") or []
        if not name or column_name not in columns:
            continue
        op_obj.drop_constraint(name, table_name, type_="unique")


def _drop_indexes_for_column(
    op_obj: object,
    bind: Connection,
    *,
    table_name: str,
    column_name: str,
) -> None:
    for index in _inspector(bind).get_indexes(table_name):
        name = index.get("name")
        columns = index.get("column_names") or []
        if not name or column_name not in columns:
            continue
        op_obj.drop_index(name, table_name=table_name)


def _drop_columns(
    op_obj: object,
    bind: Connection,
    *,
    table_name: str,
    column_names: Sequence[str],
) -> None:
    if not _table_exists(bind, table_name):
        return
    for column_name in column_names:
        if column_name not in _column_names(bind, table_name):
            continue
        _drop_foreign_keys_for_column(
            op_obj,
            bind,
            table_name=table_name,
            column_name=column_name,
        )
        _drop_unique_constraints_for_column(
            op_obj,
            bind,
            table_name=table_name,
            column_name=column_name,
        )
        _drop_indexes_for_column(
            op_obj,
            bind,
            table_name=table_name,
            column_name=column_name,
        )
        op_obj.drop_column(table_name, column_name)


def _canonicalize_parent_legacy_mapped_columns(
    op_obj: object, bind: Connection
) -> None:
    if not _table_exists(bind, _CANONICAL_PARENT_TABLE):
        return

    for (
        legacy_column,
        canonical_column,
    ) in _PARENT_LEGACY_TO_CANONICAL_COLUMN_MAP.items():
        columns = _column_names(bind, _CANONICAL_PARENT_TABLE)
        if legacy_column not in columns:
            continue

        if canonical_column in columns:
            conflicts = bind.execute(
                sa.text(
                    f"""
                    SELECT COUNT(*)
                    FROM "{_CANONICAL_PARENT_TABLE}"
                    WHERE "{legacy_column}" IS NOT NULL
                      AND "{canonical_column}" IS NOT NULL
                      AND "{legacy_column}" <> "{canonical_column}"
                    """
                )
            ).scalar_one()
            if int(conflicts) > 0:
                raise RuntimeError(
                    "Unsafe split parent schema detected: canonical parent table "
                    "contains conflicting values across mapped columns "
                    f"'{legacy_column}' and '{canonical_column}'."
                )

            bind.execute(
                sa.text(
                    f"""
                    UPDATE "{_CANONICAL_PARENT_TABLE}"
                    SET "{canonical_column}" = COALESCE(
                        "{canonical_column}",
                        "{legacy_column}"
                    )
                    WHERE "{legacy_column}" IS NOT NULL
                    """
                )
            )
            _drop_foreign_keys_for_column(
                op_obj,
                bind,
                table_name=_CANONICAL_PARENT_TABLE,
                column_name=legacy_column,
            )
            _drop_unique_constraints_for_column(
                op_obj,
                bind,
                table_name=_CANONICAL_PARENT_TABLE,
                column_name=legacy_column,
            )
            _drop_indexes_for_column(
                op_obj,
                bind,
                table_name=_CANONICAL_PARENT_TABLE,
                column_name=legacy_column,
            )
            op_obj.drop_column(_CANONICAL_PARENT_TABLE, legacy_column)
            continue

        op_obj.alter_column(
            _CANONICAL_PARENT_TABLE,
            legacy_column,
            new_column_name=canonical_column,
            existing_type=_column_type(
                bind,
                table_name=_CANONICAL_PARENT_TABLE,
                column_name=legacy_column,
            ),
        )

        if not _is_postgresql(bind):
            continue

        old_fk_names = (
            f"fk_trials_{legacy_column}_users",
            f"fk_simulations_{legacy_column}_users",
        )
        new_fk_name = f"fk_trials_{canonical_column}_users"
        foreign_key_names = _foreign_key_names(bind, _CANONICAL_PARENT_TABLE)
        for old_fk_name in old_fk_names:
            if old_fk_name not in foreign_key_names:
                continue
            if new_fk_name in foreign_key_names:
                break
            _rename_postgresql_constraint(
                bind,
                table_name=_CANONICAL_PARENT_TABLE,
                old_name=old_fk_name,
                new_name=new_fk_name,
            )
            break


def _assert_no_dual_fk_conflicts(bind: Connection, *, table_name: str) -> None:
    conflicts = bind.execute(
        sa.text(
            f"""
            SELECT COUNT(*)
            FROM "{table_name}"
            WHERE trial_id IS NOT NULL
              AND simulation_id IS NOT NULL
              AND trial_id <> simulation_id
            """
        )
    ).scalar_one()
    if int(conflicts) > 0:
        raise RuntimeError(
            f"Unsafe split child schema detected on '{table_name}': both trial_id and "
            "simulation_id are populated with different values."
        )


def _backfill_trial_id_from_simulation_id(bind: Connection, *, table_name: str) -> None:
    bind.execute(
        sa.text(
            f"""
            UPDATE "{table_name}"
            SET trial_id = COALESCE(trial_id, simulation_id)
            WHERE simulation_id IS NOT NULL
            """
        )
    )


def _canonicalize_child_trial_fk_column(
    op_obj: object,
    bind: Connection,
    *,
    table_name: str,
) -> None:
    if not _table_exists(bind, table_name):
        return

    columns = _column_names(bind, table_name)
    has_trial_id = "trial_id" in columns
    has_simulation_id = "simulation_id" in columns

    if has_trial_id and has_simulation_id:
        _assert_no_dual_fk_conflicts(bind, table_name=table_name)
        _backfill_trial_id_from_simulation_id(bind, table_name=table_name)
        _drop_foreign_keys_for_column(
            op_obj, bind, table_name=table_name, column_name="simulation_id"
        )
        _drop_unique_constraints_for_column(
            op_obj, bind, table_name=table_name, column_name="simulation_id"
        )
        _drop_indexes_for_column(
            op_obj, bind, table_name=table_name, column_name="simulation_id"
        )
        op_obj.drop_column(table_name, "simulation_id")
        return

    if has_simulation_id and not has_trial_id:
        op_obj.alter_column(
            table_name,
            "simulation_id",
            new_column_name="trial_id",
            existing_type=sa.Integer(),
        )


def _drop_trial_foreign_keys_to_legacy_parent(
    op_obj: object,
    bind: Connection,
    *,
    table_name: str,
) -> None:
    if not _is_postgresql(bind):
        return
    if not _table_exists(bind, table_name):
        return
    for foreign_key in _foreign_keys(bind, table_name):
        name = foreign_key.get("name")
        constrained_columns = foreign_key.get("constrained_columns") or []
        referred_table = foreign_key.get("referred_table")
        if not name:
            continue
        if "trial_id" not in constrained_columns:
            continue
        if referred_table != _LEGACY_PARENT_TABLE:
            continue
        op_obj.drop_constraint(name, table_name, type_="foreignkey")


def _ensure_column(
    op_obj: object,
    bind: Connection,
    *,
    table_name: str,
    column: sa.Column,
) -> None:
    if not _table_exists(bind, table_name):
        return
    if column.name in _column_names(bind, table_name):
        return
    op_obj.add_column(table_name, column)


def _ensure_index(
    op_obj: object,
    bind: Connection,
    *,
    table_name: str,
    name: str,
    columns: list[object],
    unique: bool,
) -> None:
    if not _table_exists(bind, table_name):
        return
    if name in _index_names(bind, table_name):
        return
    op_obj.create_index(name, table_name, columns, unique=unique)


def _drop_index_if_exists(
    op_obj: object,
    bind: Connection,
    *,
    table_name: str,
    index_name: str,
) -> None:
    if not _table_exists(bind, table_name):
        return
    if index_name not in _index_names(bind, table_name):
        return
    op_obj.drop_index(index_name, table_name=table_name)


def _ensure_tasks_trial_day_index(op_obj: object, bind: Connection) -> None:
    if not _table_exists(bind, "tasks"):
        return
    columns = _column_names(bind, "tasks")
    if "trial_id" not in columns or "day_index" not in columns:
        return

    old_name = "ix_tasks_simulation_day_index"
    new_name = "ix_tasks_trial_day_index"

    names = _index_names(bind, "tasks")
    if old_name in names and new_name not in names:
        if _is_postgresql(bind):
            _rename_postgresql_index(bind, old_name, new_name)
        else:
            op_obj.create_index(
                new_name, "tasks", ["trial_id", "day_index"], unique=False
            )
            op_obj.drop_index(old_name, table_name="tasks")

    names = _index_names(bind, "tasks")
    if new_name not in names:
        op_obj.create_index(new_name, "tasks", ["trial_id", "day_index"], unique=False)

    _drop_index_if_exists(op_obj, bind, table_name="tasks", index_name=old_name)


def _ensure_candidate_session_invite_uniques(op_obj: object, bind: Connection) -> None:
    if not _table_exists(bind, "candidate_sessions"):
        return
    columns = _column_names(bind, "candidate_sessions")
    if "trial_id" not in columns or "invite_email" not in columns:
        return

    legacy_unique_name = "uq_candidate_sessions_simulation_invite_email"
    canonical_unique_name = "uq_candidate_session_trial_invite_email"

    if _is_postgresql(bind):
        unique_names = _unique_constraint_names(bind, "candidate_sessions")
        if (
            legacy_unique_name in unique_names
            and canonical_unique_name not in unique_names
        ):
            _rename_postgresql_constraint(
                bind,
                table_name="candidate_sessions",
                old_name=legacy_unique_name,
                new_name=canonical_unique_name,
            )
        unique_names = _unique_constraint_names(bind, "candidate_sessions")
        if canonical_unique_name not in unique_names:
            op_obj.create_unique_constraint(
                canonical_unique_name,
                "candidate_sessions",
                ["trial_id", "invite_email"],
            )
        unique_names = _unique_constraint_names(bind, "candidate_sessions")
        if legacy_unique_name in unique_names and canonical_unique_name in unique_names:
            op_obj.drop_constraint(
                legacy_unique_name,
                "candidate_sessions",
                type_="unique",
            )
    else:
        if canonical_unique_name not in _index_names(bind, "candidate_sessions"):
            op_obj.create_index(
                canonical_unique_name,
                "candidate_sessions",
                ["trial_id", "invite_email"],
                unique=True,
            )
        _drop_index_if_exists(
            op_obj,
            bind,
            table_name="candidate_sessions",
            index_name=legacy_unique_name,
        )

    legacy_ci_index = "uq_candidate_sessions_simulation_invite_email_ci"
    canonical_ci_index = "uq_candidate_sessions_trial_invite_email_ci"
    index_names = _index_names(bind, "candidate_sessions")
    if legacy_ci_index in index_names and canonical_ci_index not in index_names:
        if _is_postgresql(bind):
            _rename_postgresql_index(bind, legacy_ci_index, canonical_ci_index)
        else:
            _create_candidate_session_ci_unique_index(
                op_obj,
                parent_column="trial_id",
                index_name=canonical_ci_index,
            )
            op_obj.drop_index(legacy_ci_index, table_name="candidate_sessions")

    if canonical_ci_index in _index_names(
        bind, "candidate_sessions"
    ) and not _index_is_case_insensitive_invite_unique(
        bind,
        table_name="candidate_sessions",
        index_name=canonical_ci_index,
        parent_column="trial_id",
    ):
        op_obj.drop_index(canonical_ci_index, table_name="candidate_sessions")

    if canonical_ci_index not in _index_names(bind, "candidate_sessions"):
        _create_candidate_session_ci_unique_index(
            op_obj,
            parent_column="trial_id",
            index_name=canonical_ci_index,
        )

    _drop_index_if_exists(
        op_obj,
        bind,
        table_name="candidate_sessions",
        index_name=legacy_ci_index,
    )


def _ensure_scenario_versions_unique(op_obj: object, bind: Connection) -> None:
    if not _table_exists(bind, "scenario_versions"):
        return
    columns = _column_names(bind, "scenario_versions")
    if "trial_id" not in columns or "version_index" not in columns:
        return

    legacy_unique_name = "uq_scenario_versions_simulation_version_index"
    canonical_unique_name = "uq_scenario_versions_trial_version_index"

    if _is_postgresql(bind):
        unique_names = _unique_constraint_names(bind, "scenario_versions")
        if (
            legacy_unique_name in unique_names
            and canonical_unique_name not in unique_names
        ):
            _rename_postgresql_constraint(
                bind,
                table_name="scenario_versions",
                old_name=legacy_unique_name,
                new_name=canonical_unique_name,
            )
        unique_names = _unique_constraint_names(bind, "scenario_versions")
        if canonical_unique_name not in unique_names:
            op_obj.create_unique_constraint(
                canonical_unique_name,
                "scenario_versions",
                ["trial_id", "version_index"],
            )
        unique_names = _unique_constraint_names(bind, "scenario_versions")
        if legacy_unique_name in unique_names and canonical_unique_name in unique_names:
            op_obj.drop_constraint(
                legacy_unique_name,
                "scenario_versions",
                type_="unique",
            )
    else:
        index_names = _index_names(bind, "scenario_versions")
        if canonical_unique_name not in index_names:
            op_obj.create_index(
                canonical_unique_name,
                "scenario_versions",
                ["trial_id", "version_index"],
                unique=True,
            )
        _drop_index_if_exists(
            op_obj,
            bind,
            table_name="scenario_versions",
            index_name=legacy_unique_name,
        )


def _fk_matches(
    foreign_key: dict[str, object],
    *,
    local_columns: Sequence[str],
    referred_table: str,
    remote_columns: Sequence[str],
) -> bool:
    return (
        list(foreign_key.get("constrained_columns") or []) == list(local_columns)
        and str(foreign_key.get("referred_table")) == referred_table
        and list(foreign_key.get("referred_columns") or []) == list(remote_columns)
    )


def _ensure_fk(
    op_obj: object,
    bind: Connection,
    *,
    name: str,
    table_name: str,
    referred_table: str,
    local_columns: list[str],
    remote_columns: list[str],
    legacy_name: str | None = None,
) -> None:
    if not _is_postgresql(bind):
        return
    if not _table_exists(bind, table_name):
        return
    if not _table_exists(bind, referred_table):
        return

    columns = _column_names(bind, table_name)
    if any(column_name not in columns for column_name in local_columns):
        return

    foreign_keys = _foreign_keys(bind, table_name)
    foreign_key_names = {
        str(foreign_key["name"])
        for foreign_key in foreign_keys
        if foreign_key.get("name")
    }

    if (
        legacy_name
        and legacy_name in foreign_key_names
        and name not in foreign_key_names
    ):
        legacy_fk = next(
            (
                foreign_key
                for foreign_key in foreign_keys
                if foreign_key.get("name") == legacy_name
            ),
            None,
        )
        if legacy_fk and _fk_matches(
            legacy_fk,
            local_columns=local_columns,
            referred_table=referred_table,
            remote_columns=remote_columns,
        ):
            _rename_postgresql_constraint(
                bind,
                table_name=table_name,
                old_name=legacy_name,
                new_name=name,
            )
            foreign_keys = _foreign_keys(bind, table_name)
            foreign_key_names = {
                str(foreign_key["name"])
                for foreign_key in foreign_keys
                if foreign_key.get("name")
            }

    named_target_fk = next(
        (
            foreign_key
            for foreign_key in foreign_keys
            if foreign_key.get("name") == name
        ),
        None,
    )
    if named_target_fk and not _fk_matches(
        named_target_fk,
        local_columns=local_columns,
        referred_table=referred_table,
        remote_columns=remote_columns,
    ):
        op_obj.drop_constraint(name, table_name, type_="foreignkey")
        foreign_keys = _foreign_keys(bind, table_name)
        foreign_key_names = {
            str(foreign_key["name"])
            for foreign_key in foreign_keys
            if foreign_key.get("name")
        }

    matching_foreign_keys = [
        foreign_key
        for foreign_key in foreign_keys
        if _fk_matches(
            foreign_key,
            local_columns=local_columns,
            referred_table=referred_table,
            remote_columns=remote_columns,
        )
    ]
    target_name_exists = any(
        foreign_key.get("name") == name for foreign_key in matching_foreign_keys
    )
    if not target_name_exists:
        rename_candidate = next(
            (
                foreign_key
                for foreign_key in matching_foreign_keys
                if foreign_key.get("name")
            ),
            None,
        )
        if rename_candidate and name not in foreign_key_names:
            old_name = str(rename_candidate["name"])
            _rename_postgresql_constraint(
                bind,
                table_name=table_name,
                old_name=old_name,
                new_name=name,
            )
            foreign_keys = _foreign_keys(bind, table_name)
            matching_foreign_keys = [
                foreign_key
                for foreign_key in foreign_keys
                if _fk_matches(
                    foreign_key,
                    local_columns=local_columns,
                    referred_table=referred_table,
                    remote_columns=remote_columns,
                )
            ]
            target_name_exists = any(
                foreign_key.get("name") == name for foreign_key in matching_foreign_keys
            )
        if not target_name_exists:
            op_obj.create_foreign_key(
                name,
                table_name,
                referred_table,
                local_columns,
                remote_columns,
            )
            foreign_keys = _foreign_keys(bind, table_name)
            matching_foreign_keys = [
                foreign_key
                for foreign_key in foreign_keys
                if _fk_matches(
                    foreign_key,
                    local_columns=local_columns,
                    referred_table=referred_table,
                    remote_columns=remote_columns,
                )
            ]

    for foreign_key in matching_foreign_keys:
        foreign_key_name = foreign_key.get("name")
        if not foreign_key_name:
            continue
        if str(foreign_key_name) == name:
            continue
        op_obj.drop_constraint(str(foreign_key_name), table_name, type_="foreignkey")


def _ensure_required_foreign_keys(op_obj: object, bind: Connection) -> None:
    _ensure_fk(
        op_obj,
        bind,
        name="fk_trials_active_scenario_version_id",
        table_name="trials",
        referred_table="scenario_versions",
        local_columns=["active_scenario_version_id"],
        remote_columns=["id"],
        legacy_name="fk_simulations_active_scenario_version_id",
    )
    _ensure_fk(
        op_obj,
        bind,
        name="fk_trials_pending_scenario_version_id",
        table_name="trials",
        referred_table="scenario_versions",
        local_columns=["pending_scenario_version_id"],
        remote_columns=["id"],
        legacy_name="fk_simulations_pending_scenario_version_id",
    )
    _ensure_fk(
        op_obj,
        bind,
        name="fk_candidate_sessions_scenario_version_id",
        table_name="candidate_sessions",
        referred_table="scenario_versions",
        local_columns=["scenario_version_id"],
        remote_columns=["id"],
    )

    _ensure_fk(
        op_obj,
        bind,
        name="fk_scenario_versions_trial_id_trials",
        table_name="scenario_versions",
        referred_table="trials",
        local_columns=["trial_id"],
        remote_columns=["id"],
        legacy_name="fk_scenario_versions_simulation_id_simulations",
    )
    _ensure_fk(
        op_obj,
        bind,
        name="fk_candidate_sessions_trial_id_trials",
        table_name="candidate_sessions",
        referred_table="trials",
        local_columns=["trial_id"],
        remote_columns=["id"],
        legacy_name="fk_candidate_sessions_simulation_id_simulations",
    )
    _ensure_fk(
        op_obj,
        bind,
        name="fk_tasks_trial_id_trials",
        table_name="tasks",
        referred_table="trials",
        local_columns=["trial_id"],
        remote_columns=["id"],
        legacy_name="fk_tasks_simulation_id_simulations",
    )


def _assert_no_table_references(bind: Connection, *, table_name: str) -> None:
    references: list[str] = []
    for candidate_table in _inspector(bind).get_table_names():
        for foreign_key in _foreign_keys(bind, candidate_table):
            if foreign_key.get("referred_table") != table_name:
                continue
            reference_name = str(foreign_key.get("name") or "<unnamed_fk>")
            references.append(f"{candidate_table}.{reference_name}")

    if references:
        joined_refs = ", ".join(sorted(references))
        raise RuntimeError(
            f"Cannot remove legacy '{table_name}' table while foreign keys still "
            f"reference it: {joined_refs}."
        )


def _drop_legacy_parent_table_if_present(op_obj: object, bind: Connection) -> None:
    if not _table_exists(bind, _LEGACY_PARENT_TABLE):
        return
    if not _table_exists(bind, _CANONICAL_PARENT_TABLE):
        return
    _assert_no_table_references(bind, table_name=_LEGACY_PARENT_TABLE)
    op_obj.drop_table(_LEGACY_PARENT_TABLE)


def _backfill_scenario_versions_and_links(bind: Connection) -> None:
    if not _table_exists(bind, "trials"):
        return
    if not _table_exists(bind, "scenario_versions"):
        return
    if not _table_exists(bind, "candidate_sessions"):
        return

    trial_columns = _column_names(bind, "trials")
    scenario_columns = _column_names(bind, "scenario_versions")
    session_columns = _column_names(bind, "candidate_sessions")
    if "active_scenario_version_id" not in trial_columns:
        return
    if "trial_id" not in scenario_columns:
        return
    if "scenario_version_id" not in session_columns:
        return
    if "trial_id" not in session_columns:
        return

    metadata = sa.MetaData()
    trials = sa.Table("trials", metadata, autoload_with=bind)
    scenario_versions = sa.Table("scenario_versions", metadata, autoload_with=bind)
    candidate_sessions = sa.Table("candidate_sessions", metadata, autoload_with=bind)

    trial_rows = bind.execute(
        sa.select(
            trials.c.id,
            trials.c.status,
            trials.c.title,
            trials.c.role,
            trials.c.tech_stack,
            trials.c.seniority,
            trials.c.focus,
            trials.c.scenario_template,
            trials.c.template_key,
            trials.c.created_at,
            trials.c.activated_at,
            trials.c.terminated_at,
        )
    ).mappings()

    for row in trial_rows:
        trial_id = int(row["id"])
        existing_id = bind.execute(
            sa.select(scenario_versions.c.id).where(
                scenario_versions.c.trial_id == trial_id,
                scenario_versions.c.version_index == 1,
            )
        ).scalar_one_or_none()

        if existing_id is None:
            raw_status = str(row.get("status") or "").strip()
            locked_at = None
            if raw_status in {"active_inviting", "terminated"}:
                locked_at = (
                    row.get("activated_at")
                    or row.get("terminated_at")
                    or datetime.now(UTC)
                )
            storyline_md = (
                f"# {str(row.get('title') or '').strip()}\n\n"
                f"Role: {str(row.get('role') or '').strip()}\n"
                f"Template: {str(row.get('scenario_template') or '').strip()}"
            ).strip()

            existing_id = bind.execute(
                sa.insert(scenario_versions)
                .values(
                    trial_id=trial_id,
                    version_index=1,
                    status="locked" if locked_at else "ready",
                    storyline_md=storyline_md,
                    task_prompts_json=[],
                    rubric_json={},
                    focus_notes=str(row.get("focus") or ""),
                    template_key=str(row.get("template_key") or DEFAULT_TEMPLATE_KEY),
                    tech_stack=str(row.get("tech_stack") or ""),
                    seniority=str(row.get("seniority") or ""),
                    created_at=row.get("created_at") or datetime.now(UTC),
                    locked_at=locked_at,
                )
                .returning(scenario_versions.c.id)
            ).scalar_one()

        scenario_id = int(existing_id)
        bind.execute(
            sa.update(trials)
            .where(trials.c.id == trial_id)
            .values(
                active_scenario_version_id=sa.func.coalesce(
                    trials.c.active_scenario_version_id, scenario_id
                )
            )
        )
        bind.execute(
            sa.update(candidate_sessions)
            .where(candidate_sessions.c.trial_id == trial_id)
            .where(candidate_sessions.c.scenario_version_id.is_(None))
            .values(scenario_version_id=scenario_id)
        )


def run_upgrade(op_obj: object, bind: Connection) -> None:
    has_canonical_parent = _table_exists(bind, _CANONICAL_PARENT_TABLE)
    has_legacy_parent = _table_exists(bind, _LEGACY_PARENT_TABLE)
    if not has_canonical_parent and not has_legacy_parent:
        raise RuntimeError(
            "Cannot run schema unification: neither canonical 'trials' nor legacy "
            "'simulations' exists."
        )

    if has_canonical_parent:
        _canonicalize_parent_legacy_mapped_columns(op_obj, bind)

    if has_canonical_parent and has_legacy_parent:
        repaired_canonical_empty_state = _repair_split_parent_when_canonical_empty(bind)
        if not repaired_canonical_empty_state:
            _assert_safe_split_parent_state(bind)
            _merge_missing_trials_rows_from_legacy(bind)
    elif has_legacy_parent and not has_canonical_parent:
        unknown_legacy_parent_columns = _unknown_legacy_only_parent_columns(bind)
        _assert_no_non_null_unknown_legacy_parent_data(bind)
        op_obj.rename_table(_LEGACY_PARENT_TABLE, _CANONICAL_PARENT_TABLE)
        _rename_parent_table_postgresql_artifacts(
            bind,
            old_table=_LEGACY_PARENT_TABLE,
            new_table=_CANONICAL_PARENT_TABLE,
            index_renames={"ix_simulations_template_key": "ix_trials_template_key"},
            constraint_renames={
                "ck_simulations_status_lifecycle": "ck_trials_status_lifecycle",
                "fk_simulations_pending_scenario_version_id": "fk_trials_pending_scenario_version_id",
            },
        )
        _canonicalize_parent_legacy_mapped_columns(op_obj, bind)
        _drop_columns(
            op_obj,
            bind,
            table_name=_CANONICAL_PARENT_TABLE,
            column_names=unknown_legacy_parent_columns,
        )

    _ensure_column(
        op_obj,
        bind,
        table_name="trials",
        column=sa.Column("active_scenario_version_id", sa.Integer(), nullable=True),
    )
    _ensure_column(
        op_obj,
        bind,
        table_name="trials",
        column=sa.Column("pending_scenario_version_id", sa.Integer(), nullable=True),
    )
    _ensure_column(
        op_obj,
        bind,
        table_name="candidate_sessions",
        column=sa.Column("scenario_version_id", sa.Integer(), nullable=True),
    )

    for table_name in ("scenario_versions", "candidate_sessions", "tasks"):
        _canonicalize_child_trial_fk_column(op_obj, bind, table_name=table_name)
        _drop_trial_foreign_keys_to_legacy_parent(op_obj, bind, table_name=table_name)

    _ensure_tasks_trial_day_index(op_obj, bind)
    _ensure_candidate_session_invite_uniques(op_obj, bind)
    _ensure_scenario_versions_unique(op_obj, bind)
    _ensure_required_foreign_keys(op_obj, bind)

    _drop_legacy_parent_table_if_present(op_obj, bind)

    _backfill_scenario_versions_and_links(bind)

    _ensure_required_foreign_keys(op_obj, bind)
    _ensure_index(
        op_obj,
        bind,
        table_name="candidate_sessions",
        name="ix_candidate_sessions_scenario_version_id",
        columns=["scenario_version_id"],
        unique=False,
    )


def _canonicalize_child_legacy_fk_column(
    op_obj: object,
    bind: Connection,
    *,
    table_name: str,
) -> None:
    if not _table_exists(bind, table_name):
        return

    columns = _column_names(bind, table_name)
    has_trial_id = "trial_id" in columns
    has_simulation_id = "simulation_id" in columns

    if has_trial_id and has_simulation_id:
        conflicts = bind.execute(
            sa.text(
                f"""
                SELECT COUNT(*)
                FROM "{table_name}"
                WHERE trial_id IS NOT NULL
                  AND simulation_id IS NOT NULL
                  AND trial_id <> simulation_id
                """
            )
        ).scalar_one()
        if int(conflicts) > 0:
            raise RuntimeError(
                f"Cannot downgrade '{table_name}' because trial_id and simulation_id "
                "contain conflicting values."
            )
        bind.execute(
            sa.text(
                f"""
                UPDATE "{table_name}"
                SET simulation_id = COALESCE(simulation_id, trial_id)
                WHERE trial_id IS NOT NULL
                """
            )
        )
        _drop_foreign_keys_for_column(
            op_obj, bind, table_name=table_name, column_name="trial_id"
        )
        _drop_unique_constraints_for_column(
            op_obj, bind, table_name=table_name, column_name="trial_id"
        )
        _drop_indexes_for_column(
            op_obj, bind, table_name=table_name, column_name="trial_id"
        )
        op_obj.drop_column(table_name, "trial_id")
        return

    if has_trial_id and not has_simulation_id:
        op_obj.alter_column(
            table_name,
            "trial_id",
            new_column_name="simulation_id",
            existing_type=sa.Integer(),
        )


def _ensure_tasks_simulation_day_index(op_obj: object, bind: Connection) -> None:
    if not _table_exists(bind, "tasks"):
        return
    columns = _column_names(bind, "tasks")
    if "simulation_id" not in columns or "day_index" not in columns:
        return

    canonical_name = "ix_tasks_trial_day_index"
    legacy_name = "ix_tasks_simulation_day_index"

    names = _index_names(bind, "tasks")
    if canonical_name in names and legacy_name not in names:
        if _is_postgresql(bind):
            _rename_postgresql_index(bind, canonical_name, legacy_name)
        else:
            op_obj.create_index(
                legacy_name,
                "tasks",
                ["simulation_id", "day_index"],
                unique=False,
            )
            op_obj.drop_index(canonical_name, table_name="tasks")

    if legacy_name not in _index_names(bind, "tasks"):
        op_obj.create_index(
            legacy_name,
            "tasks",
            ["simulation_id", "day_index"],
            unique=False,
        )

    _drop_index_if_exists(
        op_obj,
        bind,
        table_name="tasks",
        index_name=canonical_name,
    )


def _ensure_candidate_session_legacy_uniques(op_obj: object, bind: Connection) -> None:
    if not _table_exists(bind, "candidate_sessions"):
        return
    columns = _column_names(bind, "candidate_sessions")
    if "simulation_id" not in columns or "invite_email" not in columns:
        return

    canonical_unique_name = "uq_candidate_session_trial_invite_email"
    legacy_unique_name = "uq_candidate_sessions_simulation_invite_email"

    if _is_postgresql(bind):
        unique_names = _unique_constraint_names(bind, "candidate_sessions")
        if (
            canonical_unique_name in unique_names
            and legacy_unique_name not in unique_names
        ):
            _rename_postgresql_constraint(
                bind,
                table_name="candidate_sessions",
                old_name=canonical_unique_name,
                new_name=legacy_unique_name,
            )
        unique_names = _unique_constraint_names(bind, "candidate_sessions")
        if legacy_unique_name not in unique_names:
            op_obj.create_unique_constraint(
                legacy_unique_name,
                "candidate_sessions",
                ["simulation_id", "invite_email"],
            )
        if canonical_unique_name in _unique_constraint_names(
            bind, "candidate_sessions"
        ) and legacy_unique_name in _unique_constraint_names(
            bind, "candidate_sessions"
        ):
            op_obj.drop_constraint(
                canonical_unique_name,
                "candidate_sessions",
                type_="unique",
            )
    else:
        if legacy_unique_name not in _index_names(bind, "candidate_sessions"):
            op_obj.create_index(
                legacy_unique_name,
                "candidate_sessions",
                ["simulation_id", "invite_email"],
                unique=True,
            )
        _drop_index_if_exists(
            op_obj,
            bind,
            table_name="candidate_sessions",
            index_name=canonical_unique_name,
        )

    canonical_ci = "uq_candidate_sessions_trial_invite_email_ci"
    legacy_ci = "uq_candidate_sessions_simulation_invite_email_ci"
    names = _index_names(bind, "candidate_sessions")
    if canonical_ci in names and legacy_ci not in names:
        if _is_postgresql(bind):
            _rename_postgresql_index(bind, canonical_ci, legacy_ci)
        else:
            _create_candidate_session_ci_unique_index(
                op_obj,
                parent_column="simulation_id",
                index_name=legacy_ci,
            )
            op_obj.drop_index(canonical_ci, table_name="candidate_sessions")

    if legacy_ci in _index_names(
        bind, "candidate_sessions"
    ) and not _index_is_case_insensitive_invite_unique(
        bind,
        table_name="candidate_sessions",
        index_name=legacy_ci,
        parent_column="simulation_id",
    ):
        op_obj.drop_index(legacy_ci, table_name="candidate_sessions")

    if legacy_ci not in _index_names(bind, "candidate_sessions"):
        _create_candidate_session_ci_unique_index(
            op_obj,
            parent_column="simulation_id",
            index_name=legacy_ci,
        )

    _drop_index_if_exists(
        op_obj,
        bind,
        table_name="candidate_sessions",
        index_name=canonical_ci,
    )


def _ensure_scenario_versions_legacy_unique(op_obj: object, bind: Connection) -> None:
    if not _table_exists(bind, "scenario_versions"):
        return
    columns = _column_names(bind, "scenario_versions")
    if "simulation_id" not in columns or "version_index" not in columns:
        return

    canonical_unique_name = "uq_scenario_versions_trial_version_index"
    legacy_unique_name = "uq_scenario_versions_simulation_version_index"

    if _is_postgresql(bind):
        names = _unique_constraint_names(bind, "scenario_versions")
        if canonical_unique_name in names and legacy_unique_name not in names:
            _rename_postgresql_constraint(
                bind,
                table_name="scenario_versions",
                old_name=canonical_unique_name,
                new_name=legacy_unique_name,
            )
        if legacy_unique_name not in _unique_constraint_names(
            bind, "scenario_versions"
        ):
            op_obj.create_unique_constraint(
                legacy_unique_name,
                "scenario_versions",
                ["simulation_id", "version_index"],
            )
        if canonical_unique_name in _unique_constraint_names(
            bind, "scenario_versions"
        ) and legacy_unique_name in _unique_constraint_names(bind, "scenario_versions"):
            op_obj.drop_constraint(
                canonical_unique_name,
                "scenario_versions",
                type_="unique",
            )
    else:
        if legacy_unique_name not in _index_names(bind, "scenario_versions"):
            op_obj.create_index(
                legacy_unique_name,
                "scenario_versions",
                ["simulation_id", "version_index"],
                unique=True,
            )
        _drop_index_if_exists(
            op_obj,
            bind,
            table_name="scenario_versions",
            index_name=canonical_unique_name,
        )


def _ensure_legacy_foreign_keys(op_obj: object, bind: Connection) -> None:
    _ensure_fk(
        op_obj,
        bind,
        name="fk_simulations_pending_scenario_version_id",
        table_name="simulations",
        referred_table="scenario_versions",
        local_columns=["pending_scenario_version_id"],
        remote_columns=["id"],
        legacy_name="fk_trials_pending_scenario_version_id",
    )

    _ensure_fk(
        op_obj,
        bind,
        name="fk_scenario_versions_simulation_id_simulations",
        table_name="scenario_versions",
        referred_table="simulations",
        local_columns=["simulation_id"],
        remote_columns=["id"],
        legacy_name="fk_scenario_versions_trial_id_trials",
    )
    _ensure_fk(
        op_obj,
        bind,
        name="fk_candidate_sessions_simulation_id_simulations",
        table_name="candidate_sessions",
        referred_table="simulations",
        local_columns=["simulation_id"],
        remote_columns=["id"],
        legacy_name="fk_candidate_sessions_trial_id_trials",
    )
    _ensure_fk(
        op_obj,
        bind,
        name="fk_tasks_simulation_id_simulations",
        table_name="tasks",
        referred_table="simulations",
        local_columns=["simulation_id"],
        remote_columns=["id"],
        legacy_name="fk_tasks_trial_id_trials",
    )


def run_downgrade(op_obj: object, bind: Connection) -> None:
    has_canonical_parent = _table_exists(bind, _CANONICAL_PARENT_TABLE)
    has_legacy_parent = _table_exists(bind, _LEGACY_PARENT_TABLE)

    if has_canonical_parent and has_legacy_parent:
        raise RuntimeError(
            "Cannot downgrade with both canonical 'trials' and legacy 'simulations' "
            "tables present."
        )
    if not has_canonical_parent and not has_legacy_parent:
        raise RuntimeError(
            "Cannot downgrade: neither canonical 'trials' nor legacy 'simulations' "
            "table exists."
        )

    if has_canonical_parent and not has_legacy_parent:
        op_obj.rename_table(_CANONICAL_PARENT_TABLE, _LEGACY_PARENT_TABLE)
        _rename_parent_table_postgresql_artifacts(
            bind,
            old_table=_CANONICAL_PARENT_TABLE,
            new_table=_LEGACY_PARENT_TABLE,
            index_renames={"ix_trials_template_key": "ix_simulations_template_key"},
            constraint_renames={
                "ck_trials_status_lifecycle": "ck_simulations_status_lifecycle",
                "fk_trials_pending_scenario_version_id": "fk_simulations_pending_scenario_version_id",
            },
        )

    for table_name in ("scenario_versions", "candidate_sessions", "tasks"):
        _canonicalize_child_legacy_fk_column(op_obj, bind, table_name=table_name)

    _ensure_tasks_simulation_day_index(op_obj, bind)
    _ensure_candidate_session_legacy_uniques(op_obj, bind)
    _ensure_scenario_versions_legacy_unique(op_obj, bind)
    _ensure_legacy_foreign_keys(op_obj, bind)


def upgrade() -> None:
    run_upgrade(op, op.get_bind())


def downgrade() -> None:
    run_downgrade(op, op.get_bind())
