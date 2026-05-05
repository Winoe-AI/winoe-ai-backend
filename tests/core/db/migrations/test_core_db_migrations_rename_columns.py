from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa

from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION_PATH_1 = (
    Path(__file__).resolve().parents[4]
    / "alembic/versions/439821122cc4_rename_codespace_spec_json_to_project_.py"
)
_MIGRATION_SPEC_1 = importlib.util.spec_from_file_location(
    "migration_1", _MIGRATION_PATH_1
)
assert _MIGRATION_SPEC_1 and _MIGRATION_SPEC_1.loader
migration_1 = importlib.util.module_from_spec(_MIGRATION_SPEC_1)
_MIGRATION_SPEC_1.loader.exec_module(migration_1)


_MIGRATION_PATH_2 = (
    Path(__file__).resolve().parents[4]
    / "alembic/versions/5148b3a35f39_rename_tech_stack_to_preferred_language_.py"
)
_MIGRATION_SPEC_2 = importlib.util.spec_from_file_location(
    "migration_2", _MIGRATION_PATH_2
)
assert _MIGRATION_SPEC_2 and _MIGRATION_SPEC_2.loader
migration_2 = importlib.util.module_from_spec(_MIGRATION_SPEC_2)
_MIGRATION_SPEC_2.loader.exec_module(migration_2)


def _operations(bind: sa.Connection) -> Operations:
    return Operations(MigrationContext.configure(bind))


def test_migration_1_upgrade_old_only() -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table(
        "scenario_versions",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("codespace_spec_json", sa.JSON, nullable=True),
    )
    metadata.create_all(engine)

    with engine.begin() as conn:
        migration_1.op = _operations(conn)
        migration_1.upgrade()

        inspector = sa.inspect(conn)
        columns = {c["name"] for c in inspector.get_columns("scenario_versions")}
        assert "project_brief_md" in columns
        assert "codespace_spec_json" not in columns


def test_migration_1_upgrade_both() -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    table = sa.Table(
        "scenario_versions",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("codespace_spec_json", sa.JSON, nullable=True),
        sa.Column("project_brief_md", sa.String, nullable=True),
    )
    metadata.create_all(engine)

    with engine.begin() as conn:
        # Insert as raw dict so sa.JSON handles it correctly
        conn.execute(
            table.insert().values(
                id=1, codespace_spec_json={"a": 1}, project_brief_md=None
            )
        )
        conn.execute(
            table.insert().values(
                id=2, codespace_spec_json={"b": 2}, project_brief_md="existing"
            )
        )

        migration_1.op = _operations(conn)
        migration_1.upgrade()

        inspector = sa.inspect(conn)
        columns = {c["name"] for c in inspector.get_columns("scenario_versions")}
        assert "project_brief_md" in columns
        assert "codespace_spec_json" not in columns

        result = conn.execute(
            sa.text("SELECT id, project_brief_md FROM scenario_versions ORDER BY id")
        ).fetchall()
        # In sqlite, CAST(JSON AS TEXT) might result in the stringified JSON
        val = result[0][1]
        assert "a" in val and "1" in val
        assert result[1][1] == "existing"


def test_migration_2_upgrade_old_only() -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table(
        "trials",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tech_stack", sa.String, nullable=True),
    )
    sa.Table(
        "scenario_versions",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tech_stack", sa.String, nullable=True),
    )
    metadata.create_all(engine)

    with engine.begin() as conn:
        migration_2.op = _operations(conn)
        migration_2.upgrade()

        inspector = sa.inspect(conn)
        for table_name in ("trials", "scenario_versions"):
            columns = {c["name"] for c in inspector.get_columns(table_name)}
            assert "preferred_language_framework" in columns
            assert "tech_stack" not in columns


def test_migration_2_upgrade_both() -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    trials_table = sa.Table(
        "trials",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tech_stack", sa.String, nullable=True),
        sa.Column("preferred_language_framework", sa.String, nullable=True),
    )
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(
            trials_table.insert().values(
                id=1, tech_stack="python", preferred_language_framework=None
            )
        )
        conn.execute(
            trials_table.insert().values(
                id=2, tech_stack="ruby", preferred_language_framework="rust"
            )
        )

        migration_2.op = _operations(conn)
        migration_2.upgrade()

        inspector = sa.inspect(conn)
        columns = {c["name"] for c in inspector.get_columns("trials")}
        assert "preferred_language_framework" in columns
        assert "tech_stack" not in columns

        result = conn.execute(
            sa.text("SELECT id, preferred_language_framework FROM trials ORDER BY id")
        ).fetchall()
        assert result[0][1] == "python"
        assert result[1][1] == "rust"
