from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[4]
    / "alembic/versions/202604130001_unify_trials_schema_and_child_fks.py"
)
_MIGRATION_SPEC = importlib.util.spec_from_file_location(
    "issue_277_migration", _MIGRATION_PATH
)
assert _MIGRATION_SPEC and _MIGRATION_SPEC.loader
issue_277_migration = importlib.util.module_from_spec(_MIGRATION_SPEC)
_MIGRATION_SPEC.loader.exec_module(issue_277_migration)


def _operations(bind: sa.Connection) -> Operations:
    return Operations(MigrationContext.configure(bind))


def _table_names(bind: sa.Connection) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _column_names(bind: sa.Connection, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def _index_names(bind: sa.Connection, table_name: str) -> set[str]:
    reflected = {
        index["name"]
        for index in sa.inspect(bind).get_indexes(table_name)
        if index.get("name")
    }
    if bind.dialect.name != "sqlite":
        return reflected
    sqlite_indexes = bind.execute(
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
    ).scalars()
    return reflected | set(sqlite_indexes)


def _sqlite_index_sql(
    bind: sa.Connection,
    *,
    table_name: str,
    index_name: str,
) -> str | None:
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


def _normalize_sql(sql_text: str) -> str:
    return "".join(
        character
        for character in sql_text.lower()
        if not character.isspace() and character != '"'
    )


class _RecordingOp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def __getattr__(self, name: str):
        def _record(*args: object, **kwargs: object) -> None:
            self.calls.append((name, args, kwargs))

        return _record


def _foreign_keys(bind: sa.Connection, table_name: str) -> list[dict[str, object]]:
    return [fk for fk in sa.inspect(bind).get_foreign_keys(table_name) if fk]


def _build_parent_table(
    metadata: sa.MetaData,
    name: str,
    *,
    include_active_scenario_required_check: bool = False,
) -> sa.Table:
    columns: list[sa.SchemaItem] = [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("role", sa.String(255), nullable=True),
        sa.Column("tech_stack", sa.String(255), nullable=True),
        sa.Column("seniority", sa.String(100), nullable=True),
        sa.Column("scenario_template", sa.String(255), nullable=True),
        sa.Column("template_key", sa.String(255), nullable=True),
        sa.Column("focus", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("active_scenario_version_id", sa.Integer(), nullable=True),
        sa.Column("pending_scenario_version_id", sa.Integer(), nullable=True),
        sa.Column("generating_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ready_for_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminated_reason", sa.Text(), nullable=True),
        sa.Column("terminated_by_recruiter_id", sa.Integer(), nullable=True),
        sa.Column("terminated_by_talent_partner_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    ]
    if include_active_scenario_required_check:
        columns.append(
            sa.CheckConstraint(
                "status IN ('draft','generating') OR active_scenario_version_id IS NOT NULL",
                name="ck_trials_active_scenario_required",
            )
        )
    return sa.Table(name, metadata, *columns)


def _build_scenario_versions_table(
    metadata: sa.MetaData,
    *,
    parent_columns: tuple[str, ...],
    parent_fk_table: str | None = None,
) -> sa.Table:
    columns: list[sa.Column] = [
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
    ]
    for parent_column in parent_columns:
        foreign_key = (
            sa.ForeignKey(f"{parent_fk_table}.id") if parent_fk_table else None
        )
        columns.append(
            sa.Column(parent_column, sa.Integer(), foreign_key, nullable=True)
        )
    columns.extend(
        [
            sa.Column("version_index", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(50), nullable=False),
            sa.Column("storyline_md", sa.Text(), nullable=False),
            sa.Column("task_prompts_json", sa.JSON(), nullable=False),
            sa.Column("rubric_json", sa.JSON(), nullable=False),
            sa.Column("focus_notes", sa.Text(), nullable=False),
            sa.Column("template_key", sa.String(255), nullable=False),
            sa.Column("tech_stack", sa.String(255), nullable=False),
            sa.Column("seniority", sa.String(100), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        ]
    )
    return sa.Table("scenario_versions", metadata, *columns)


def _build_candidate_sessions_table(
    metadata: sa.MetaData,
    *,
    parent_columns: tuple[str, ...],
    parent_fk_table: str | None = None,
) -> sa.Table:
    columns: list[sa.Column] = [
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
    ]
    for parent_column in parent_columns:
        foreign_key = (
            sa.ForeignKey(f"{parent_fk_table}.id") if parent_fk_table else None
        )
        columns.append(
            sa.Column(parent_column, sa.Integer(), foreign_key, nullable=True)
        )
    columns.extend(
        [
            sa.Column("scenario_version_id", sa.Integer(), nullable=True),
            sa.Column("invite_email", sa.String(255), nullable=False),
            sa.Column("status", sa.String(50), nullable=False),
            sa.Column("candidate_name", sa.String(255), nullable=True),
            sa.Column("token", sa.String(255), nullable=True),
        ]
    )
    return sa.Table("candidate_sessions", metadata, *columns)


def _build_tasks_table(
    metadata: sa.MetaData,
    *,
    parent_columns: tuple[str, ...],
    parent_fk_table: str | None = None,
) -> sa.Table:
    columns: list[sa.Column] = [
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
    ]
    for parent_column in parent_columns:
        foreign_key = (
            sa.ForeignKey(f"{parent_fk_table}.id") if parent_fk_table else None
        )
        columns.append(
            sa.Column(parent_column, sa.Integer(), foreign_key, nullable=True)
        )
    columns.extend(
        [
            sa.Column("day_index", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(255), nullable=True),
        ]
    )
    return sa.Table("tasks", metadata, *columns)


def _trial_row(
    row_id: int, *, title: str = "Trial", status: str = "active_inviting"
) -> dict[str, object]:
    return {
        "id": row_id,
        "company_id": 1,
        "title": title,
        "role": "Engineer",
        "tech_stack": "python",
        "seniority": "mid",
        "scenario_template": "default",
        "template_key": "template-default",
        "focus": "correctness",
        "created_by": 1,
        "status": status,
        "active_scenario_version_id": None,
        "pending_scenario_version_id": None,
        "generating_at": None,
        "ready_for_review_at": None,
        "activated_at": datetime(2026, 1, 2, tzinfo=UTC),
        "terminated_at": None,
        "terminated_reason": None,
        "terminated_by_recruiter_id": None,
        "terminated_by_talent_partner_id": None,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }


def test_issue_277_upgrade_noops_for_fresh_canonical_schema():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    trials = _build_parent_table(metadata, "trials")
    _build_scenario_versions_table(metadata, parent_columns=("trial_id",))
    candidate_sessions = _build_candidate_sessions_table(
        metadata, parent_columns=("trial_id",)
    )
    tasks = _build_tasks_table(metadata, parent_columns=("trial_id",))
    sa.Index("ix_tasks_trial_day_index", tasks.c.trial_id, tasks.c.day_index)
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(trials.insert(), [_trial_row(1)])
        conn.execute(
            candidate_sessions.insert(),
            [
                {
                    "trial_id": 1,
                    "scenario_version_id": None,
                    "invite_email": "candidate@winoe.ai",
                    "status": "invited",
                    "candidate_name": "A",
                    "token": "t1",
                }
            ],
        )
        conn.execute(
            tasks.insert(),
            [{"trial_id": 1, "day_index": 1, "title": "Task 1"}],
        )

        issue_277_migration.run_upgrade(_operations(conn), conn)

        assert "simulations" not in _table_names(conn)
        scenario_trial_ids = (
            conn.execute(sa.text("SELECT trial_id FROM scenario_versions ORDER BY id"))
            .scalars()
            .all()
        )
        assert scenario_trial_ids == [1]

        active_scenario = conn.execute(
            sa.text("SELECT active_scenario_version_id FROM trials WHERE id = 1")
        ).scalar_one()
        candidate_scenario = conn.execute(
            sa.text("SELECT scenario_version_id FROM candidate_sessions WHERE id = 1")
        ).scalar_one()
        assert active_scenario is not None
        assert candidate_scenario == active_scenario


def test_issue_277_upgrade_repairs_legacy_simulations_and_child_columns():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    simulations = _build_parent_table(metadata, "simulations")
    scenario_versions = _build_scenario_versions_table(
        metadata,
        parent_columns=("simulation_id",),
        parent_fk_table="simulations",
    )
    candidate_sessions = _build_candidate_sessions_table(
        metadata,
        parent_columns=("simulation_id",),
        parent_fk_table="simulations",
    )
    tasks = _build_tasks_table(
        metadata,
        parent_columns=("simulation_id",),
        parent_fk_table="simulations",
    )

    sa.Index(
        "ix_tasks_simulation_day_index",
        tasks.c.simulation_id,
        tasks.c.day_index,
    )
    sa.Index(
        "uq_candidate_sessions_simulation_invite_email",
        candidate_sessions.c.simulation_id,
        candidate_sessions.c.invite_email,
        unique=True,
    )
    sa.Index(
        "uq_candidate_sessions_simulation_invite_email_ci",
        candidate_sessions.c.simulation_id,
        candidate_sessions.c.invite_email,
        unique=True,
    )
    sa.Index(
        "uq_scenario_versions_simulation_version_index",
        scenario_versions.c.simulation_id,
        scenario_versions.c.version_index,
        unique=True,
    )
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(sa.text("PRAGMA foreign_keys=ON"))
        conn.execute(simulations.insert(), [_trial_row(11, title="Legacy Trial")])
        conn.execute(
            scenario_versions.insert(),
            [
                {
                    "simulation_id": 11,
                    "version_index": 1,
                    "status": "ready",
                    "storyline_md": "# Legacy",
                    "task_prompts_json": [],
                    "rubric_json": {},
                    "focus_notes": "focus",
                    "template_key": "template-default",
                    "tech_stack": "python",
                    "seniority": "mid",
                    "created_at": datetime(2026, 1, 1, tzinfo=UTC),
                    "locked_at": None,
                }
            ],
        )
        conn.execute(
            candidate_sessions.insert(),
            [
                {
                    "simulation_id": 11,
                    "scenario_version_id": None,
                    "invite_email": "legacy@winoe.ai",
                    "status": "invited",
                    "candidate_name": "Legacy",
                    "token": "legacy-token",
                }
            ],
        )
        conn.execute(
            tasks.insert(),
            [{"simulation_id": 11, "day_index": 1, "title": "Legacy Task"}],
        )

        issue_277_migration.run_upgrade(_operations(conn), conn)

        table_names = _table_names(conn)
        assert "trials" in table_names
        assert "simulations" not in table_names

        assert _column_names(conn, "scenario_versions") >= {"trial_id"}
        assert "simulation_id" not in _column_names(conn, "scenario_versions")
        assert _column_names(conn, "candidate_sessions") >= {"trial_id"}
        assert "simulation_id" not in _column_names(conn, "candidate_sessions")
        assert _column_names(conn, "tasks") >= {"trial_id"}
        assert "simulation_id" not in _column_names(conn, "tasks")

        task_indexes = _index_names(conn, "tasks")
        candidate_indexes = _index_names(conn, "candidate_sessions")
        scenario_indexes = _index_names(conn, "scenario_versions")
        assert "ix_tasks_trial_day_index" in task_indexes
        assert "ix_tasks_simulation_day_index" not in task_indexes
        assert "uq_candidate_sessions_trial_invite_email_ci" in candidate_indexes
        assert (
            "uq_candidate_sessions_simulation_invite_email_ci" not in candidate_indexes
        )
        assert "uq_scenario_versions_trial_version_index" in scenario_indexes
        assert "uq_scenario_versions_simulation_version_index" not in scenario_indexes
        canonical_ci_sql = _sqlite_index_sql(
            conn,
            table_name="candidate_sessions",
            index_name="uq_candidate_sessions_trial_invite_email_ci",
        )
        assert canonical_ci_sql is not None
        assert "(trial_id,lower(invite_email))" in _normalize_sql(canonical_ci_sql)

        scenario_trial_id = conn.execute(
            sa.text("SELECT trial_id FROM scenario_versions WHERE id = 1")
        ).scalar_one()
        assert scenario_trial_id == 11

        scenario_foreign_keys = _foreign_keys(conn, "scenario_versions")
        assert any(
            fk.get("referred_table") == "trials"
            and fk.get("constrained_columns") == ["trial_id"]
            for fk in scenario_foreign_keys
        )

        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                sa.text(
                    """
                    INSERT INTO scenario_versions (
                        trial_id,
                        version_index,
                        status,
                        storyline_md,
                        task_prompts_json,
                        rubric_json,
                        focus_notes,
                        template_key,
                        tech_stack,
                        seniority,
                        created_at,
                        locked_at
                    ) VALUES (
                        11,
                        1,
                        'ready',
                        '# Duplicate',
                        '[]',
                        '{}',
                        'focus',
                        'template-default',
                        'python',
                        'mid',
                        '2026-01-01T00:00:00+00:00',
                        NULL
                    )
                    """
                )
            )
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                sa.text(
                    """
                    INSERT INTO candidate_sessions (
                        trial_id,
                        scenario_version_id,
                        invite_email,
                        status,
                        candidate_name,
                        token
                    ) VALUES (
                        11,
                        NULL,
                        'LEGACY@WINOE.AI',
                        'invited',
                        'Duplicate Case',
                        'legacy-token-2'
                    )
                    """
                )
            )

        active_scenario = conn.execute(
            sa.text("SELECT active_scenario_version_id FROM trials WHERE id = 11")
        ).scalar_one()
        candidate_scenario = conn.execute(
            sa.text("SELECT scenario_version_id FROM candidate_sessions WHERE id = 1")
        ).scalar_one()
        assert active_scenario is not None
        assert candidate_scenario == active_scenario


def test_issue_277_upgrade_finishes_partially_repaired_state():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    trials = _build_parent_table(metadata, "trials")
    _build_parent_table(metadata, "simulations")
    scenario_versions = _build_scenario_versions_table(
        metadata, parent_columns=("trial_id", "simulation_id")
    )
    candidate_sessions = _build_candidate_sessions_table(
        metadata, parent_columns=("trial_id", "simulation_id")
    )
    tasks = _build_tasks_table(metadata, parent_columns=("trial_id", "simulation_id"))

    sa.Index(
        "ix_tasks_simulation_day_index",
        tasks.c.simulation_id,
        tasks.c.day_index,
    )
    sa.Index(
        "uq_candidate_sessions_simulation_invite_email",
        candidate_sessions.c.simulation_id,
        candidate_sessions.c.invite_email,
        unique=True,
    )
    sa.Index(
        "uq_candidate_sessions_simulation_invite_email_ci",
        candidate_sessions.c.simulation_id,
        candidate_sessions.c.invite_email,
        unique=True,
    )
    sa.Index(
        "uq_scenario_versions_simulation_version_index",
        scenario_versions.c.simulation_id,
        scenario_versions.c.version_index,
        unique=True,
    )
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(trials.insert(), [_trial_row(21, title="Partial")])
        conn.execute(
            scenario_versions.insert(),
            [
                {
                    "trial_id": None,
                    "simulation_id": 21,
                    "version_index": 1,
                    "status": "ready",
                    "storyline_md": "# Partial",
                    "task_prompts_json": [],
                    "rubric_json": {},
                    "focus_notes": "focus",
                    "template_key": "template-default",
                    "tech_stack": "python",
                    "seniority": "mid",
                    "created_at": datetime(2026, 1, 1, tzinfo=UTC),
                    "locked_at": None,
                }
            ],
        )
        conn.execute(
            candidate_sessions.insert(),
            [
                {
                    "trial_id": None,
                    "simulation_id": 21,
                    "scenario_version_id": None,
                    "invite_email": "partial@winoe.ai",
                    "status": "invited",
                    "candidate_name": "Partial",
                    "token": "partial-token",
                }
            ],
        )
        conn.execute(
            tasks.insert(),
            [
                {
                    "trial_id": None,
                    "simulation_id": 21,
                    "day_index": 1,
                    "title": "Task",
                }
            ],
        )

        issue_277_migration.run_upgrade(_operations(conn), conn)

        assert "simulations" not in _table_names(conn)
        assert "simulation_id" not in _column_names(conn, "scenario_versions")
        assert "simulation_id" not in _column_names(conn, "candidate_sessions")
        assert "simulation_id" not in _column_names(conn, "tasks")

        scenario_trial_id = conn.execute(
            sa.text("SELECT trial_id FROM scenario_versions WHERE id = 1")
        ).scalar_one()
        candidate_trial_id = conn.execute(
            sa.text("SELECT trial_id FROM candidate_sessions WHERE id = 1")
        ).scalar_one()
        task_trial_id = conn.execute(
            sa.text("SELECT trial_id FROM tasks WHERE id = 1")
        ).scalar_one()
        assert scenario_trial_id == 21
        assert candidate_trial_id == 21
        assert task_trial_id == 21


def test_issue_277_upgrade_repairs_canonical_empty_split_parent_with_mapping():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    trials = _build_parent_table(metadata, "trials")
    simulations = _build_parent_table(metadata, "simulations")
    metadata.create_all(engine)

    with engine.begin() as conn:
        legacy_row = _trial_row(30, title="Legacy Only", status="draft")
        legacy_row["activated_at"] = None
        legacy_row["terminated_by_recruiter_id"] = 912
        legacy_row["terminated_by_talent_partner_id"] = None
        conn.execute(simulations.insert(), [legacy_row])

        issue_277_migration.run_upgrade(_operations(conn), conn)

        assert "simulations" not in _table_names(conn)
        trial_count = conn.execute(
            sa.select(sa.func.count()).select_from(trials)
        ).scalar_one()
        assert trial_count == 1
        title = conn.execute(
            sa.text("SELECT title FROM trials WHERE id = 30")
        ).scalar_one()
        assert title == "Legacy Only"
        assert "terminated_by_recruiter_id" not in _column_names(conn, "trials")
        terminated_by_talent_partner_id = conn.execute(
            sa.text("SELECT terminated_by_talent_partner_id FROM trials WHERE id = 30")
        ).scalar_one()
        assert terminated_by_talent_partner_id == 912


def test_issue_277_upgrade_repairs_canonical_empty_split_parent_null_active_pointer():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    _build_parent_table(
        metadata,
        "trials",
        include_active_scenario_required_check=True,
    )
    simulations = _build_parent_table(metadata, "simulations")
    scenario_versions = _build_scenario_versions_table(
        metadata,
        parent_columns=("simulation_id",),
    )
    candidate_sessions = _build_candidate_sessions_table(
        metadata,
        parent_columns=("simulation_id",),
    )
    sa.Index(
        "uq_candidate_sessions_simulation_invite_email",
        candidate_sessions.c.simulation_id,
        candidate_sessions.c.invite_email,
        unique=True,
    )
    sa.Index(
        "uq_candidate_sessions_simulation_invite_email_ci",
        candidate_sessions.c.simulation_id,
        candidate_sessions.c.invite_email,
        unique=True,
    )
    sa.Index(
        "uq_scenario_versions_simulation_version_index",
        scenario_versions.c.simulation_id,
        scenario_versions.c.version_index,
        unique=True,
    )
    metadata.create_all(engine)

    with engine.begin() as conn:
        legacy_row = _trial_row(
            37,
            title="Legacy Ready",
            status="ready_for_review",
        )
        legacy_row["ready_for_review_at"] = datetime(2026, 1, 2, tzinfo=UTC)
        legacy_row["activated_at"] = None
        conn.execute(simulations.insert(), [legacy_row])
        conn.execute(
            scenario_versions.insert(),
            [
                {
                    "simulation_id": 37,
                    "version_index": 1,
                    "status": "ready",
                    "storyline_md": "# Legacy Ready",
                    "task_prompts_json": [],
                    "rubric_json": {},
                    "focus_notes": "focus",
                    "template_key": "template-default",
                    "tech_stack": "python",
                    "seniority": "mid",
                    "created_at": datetime(2026, 1, 1, tzinfo=UTC),
                    "locked_at": None,
                }
            ],
        )
        conn.execute(
            candidate_sessions.insert(),
            [
                {
                    "simulation_id": 37,
                    "scenario_version_id": None,
                    "invite_email": "legacy-ready@winoe.ai",
                    "status": "invited",
                    "candidate_name": "Legacy Ready",
                    "token": "legacy-ready-token",
                }
            ],
        )

        issue_277_migration.run_upgrade(_operations(conn), conn)

        assert "simulations" not in _table_names(conn)
        active_scenario = conn.execute(
            sa.text("SELECT active_scenario_version_id FROM trials WHERE id = 37")
        ).scalar_one()
        assert active_scenario == 1
        scenario_trial_id = conn.execute(
            sa.text("SELECT trial_id FROM scenario_versions WHERE id = 1")
        ).scalar_one()
        assert scenario_trial_id == 37
        candidate_scenario = conn.execute(
            sa.text("SELECT scenario_version_id FROM candidate_sessions WHERE id = 1")
        ).scalar_one()
        assert candidate_scenario == active_scenario


def test_issue_277_upgrade_fails_loudly_when_required_active_pointer_cannot_be_derived():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    _build_parent_table(
        metadata,
        "trials",
        include_active_scenario_required_check=True,
    )
    simulations = _build_parent_table(metadata, "simulations")
    _build_scenario_versions_table(
        metadata,
        parent_columns=("simulation_id",),
        parent_fk_table="simulations",
    )
    metadata.create_all(engine)

    with engine.begin() as conn:
        legacy_row = _trial_row(
            38,
            title="Legacy Missing Scenario",
            status="terminated",
        )
        legacy_row["terminated_at"] = datetime(2026, 1, 3, tzinfo=UTC)
        conn.execute(simulations.insert(), [legacy_row])

        with pytest.raises(
            RuntimeError,
            match="cannot derive active_scenario_version_id",
        ):
            issue_277_migration.run_upgrade(_operations(conn), conn)


def test_issue_277_upgrade_repairs_pure_legacy_parent_with_mapping():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    simulations = _build_parent_table(metadata, "simulations")
    metadata.create_all(engine)

    with engine.begin() as conn:
        legacy_row = _trial_row(33, title="Pure Legacy Mapping")
        legacy_row["terminated_by_recruiter_id"] = 777
        legacy_row["terminated_by_talent_partner_id"] = None
        conn.execute(simulations.insert(), [legacy_row])

        issue_277_migration.run_upgrade(_operations(conn), conn)

        assert "trials" in _table_names(conn)
        assert "simulations" not in _table_names(conn)
        assert "terminated_by_recruiter_id" not in _column_names(conn, "trials")
        terminated_by_talent_partner_id = conn.execute(
            sa.text("SELECT terminated_by_talent_partner_id FROM trials WHERE id = 33")
        ).scalar_one()
        assert terminated_by_talent_partner_id == 777


def test_issue_277_upgrade_allows_identical_non_empty_split_parent_state():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    trials = _build_parent_table(metadata, "trials")
    simulations = _build_parent_table(metadata, "simulations")
    metadata.create_all(engine)

    with engine.begin() as conn:
        canonical_row = _trial_row(32, title="Same")
        canonical_row["terminated_by_recruiter_id"] = None
        canonical_row["terminated_by_talent_partner_id"] = 44

        legacy_row = _trial_row(32, title="Same")
        legacy_row["terminated_by_recruiter_id"] = 44
        legacy_row["terminated_by_talent_partner_id"] = None

        conn.execute(trials.insert(), [canonical_row])
        conn.execute(simulations.insert(), [legacy_row])

        issue_277_migration.run_upgrade(_operations(conn), conn)

        assert "simulations" not in _table_names(conn)
        trial_count = conn.execute(
            sa.select(sa.func.count()).select_from(trials)
        ).scalar_one()
        assert trial_count == 1
        title = conn.execute(
            sa.text("SELECT title FROM trials WHERE id = 32")
        ).scalar_one()
        assert title == "Same"
        assert "terminated_by_recruiter_id" not in _column_names(conn, "trials")
        terminated_by_talent_partner_id = conn.execute(
            sa.text("SELECT terminated_by_talent_partner_id FROM trials WHERE id = 32")
        ).scalar_one()
        assert terminated_by_talent_partner_id == 44


def test_issue_277_upgrade_fails_for_unknown_legacy_only_parent_data_when_canonical_empty():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    _build_parent_table(metadata, "trials")
    simulations = _build_parent_table(metadata, "simulations")
    simulations.append_column(sa.Column("legacy_notes", sa.String(255), nullable=True))
    metadata.create_all(engine)

    with engine.begin() as conn:
        legacy_row = _trial_row(34, title="Legacy Notes")
        legacy_row["legacy_notes"] = "non-null legacy-only data"
        conn.execute(simulations.insert(), [legacy_row])

        with pytest.raises(RuntimeError, match="unmapped legacy-only columns"):
            issue_277_migration.run_upgrade(_operations(conn), conn)

        assert "legacy_notes" not in _column_names(conn, "trials")


def test_issue_277_upgrade_fails_for_unknown_legacy_only_parent_data_in_pure_legacy_path():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    simulations = _build_parent_table(metadata, "simulations")
    simulations.append_column(sa.Column("legacy_notes", sa.String(255), nullable=True))
    metadata.create_all(engine)

    with engine.begin() as conn:
        legacy_row = _trial_row(36, title="Pure Legacy Unknown")
        legacy_row["legacy_notes"] = "non-null legacy-only data"
        conn.execute(simulations.insert(), [legacy_row])

        with pytest.raises(RuntimeError, match="unmapped legacy-only columns"):
            issue_277_migration.run_upgrade(_operations(conn), conn)

        assert "trials" not in _table_names(conn)
        assert "simulations" in _table_names(conn)
        assert "legacy_notes" in _column_names(conn, "simulations")


def test_issue_277_upgrade_fails_identical_non_empty_split_parent_with_unknown_legacy_data():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    trials = _build_parent_table(metadata, "trials")
    simulations = _build_parent_table(metadata, "simulations")
    simulations.append_column(sa.Column("legacy_notes", sa.String(255), nullable=True))
    metadata.create_all(engine)

    with engine.begin() as conn:
        row = _trial_row(35, title="Same Core Data")
        conn.execute(trials.insert(), [row])

        legacy_row = _trial_row(35, title="Same Core Data")
        legacy_row["legacy_notes"] = "non-null legacy-only data"
        conn.execute(simulations.insert(), [legacy_row])

        with pytest.raises(RuntimeError, match="unmapped legacy-only columns"):
            issue_277_migration.run_upgrade(_operations(conn), conn)


def test_issue_277_upgrade_fails_for_divergent_non_empty_split_parent_state():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    trials = _build_parent_table(metadata, "trials")
    simulations = _build_parent_table(metadata, "simulations")
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(trials.insert(), [_trial_row(31, title="Canonical")])
        conn.execute(simulations.insert(), [_trial_row(31, title="Legacy Different")])

        with pytest.raises(RuntimeError, match="Unsafe split parent schema detected"):
            issue_277_migration.run_upgrade(_operations(conn), conn)


def test_issue_277_downgrade_restores_legacy_parent_and_child_columns():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    simulations = _build_parent_table(metadata, "simulations")
    _build_scenario_versions_table(metadata, parent_columns=("simulation_id",))
    candidate_sessions = _build_candidate_sessions_table(
        metadata, parent_columns=("simulation_id",)
    )
    tasks = _build_tasks_table(metadata, parent_columns=("simulation_id",))

    sa.Index(
        "ix_tasks_simulation_day_index",
        tasks.c.simulation_id,
        tasks.c.day_index,
    )
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(simulations.insert(), [_trial_row(41, title="Downgrade")])
        conn.execute(
            candidate_sessions.insert(),
            [
                {
                    "simulation_id": 41,
                    "scenario_version_id": None,
                    "invite_email": "down@winoe.ai",
                    "status": "invited",
                    "candidate_name": "Down",
                    "token": "down-token",
                }
            ],
        )
        conn.execute(
            tasks.insert(),
            [{"simulation_id": 41, "day_index": 1, "title": "Task"}],
        )

        ops = _operations(conn)
        issue_277_migration.run_upgrade(ops, conn)
        issue_277_migration.run_downgrade(ops, conn)

        assert "simulations" in _table_names(conn)
        assert "trials" not in _table_names(conn)

        assert "simulation_id" in _column_names(conn, "scenario_versions")
        assert "trial_id" not in _column_names(conn, "scenario_versions")
        assert "simulation_id" in _column_names(conn, "candidate_sessions")
        assert "trial_id" not in _column_names(conn, "candidate_sessions")
        assert "simulation_id" in _column_names(conn, "tasks")
        assert "trial_id" not in _column_names(conn, "tasks")

        task_indexes = _index_names(conn, "tasks")
        assert "ix_tasks_simulation_day_index" in task_indexes
        assert "ix_tasks_trial_day_index" not in task_indexes
        candidate_indexes = _index_names(conn, "candidate_sessions")
        assert "uq_candidate_sessions_simulation_invite_email_ci" in candidate_indexes
        assert "uq_candidate_sessions_trial_invite_email_ci" not in candidate_indexes
        legacy_ci_sql = _sqlite_index_sql(
            conn,
            table_name="candidate_sessions",
            index_name="uq_candidate_sessions_simulation_invite_email_ci",
        )
        assert legacy_ci_sql is not None
        assert "(simulation_id,lower(invite_email))" in _normalize_sql(legacy_ci_sql)

        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                sa.text(
                    """
                    INSERT INTO candidate_sessions (
                        simulation_id,
                        scenario_version_id,
                        invite_email,
                        status,
                        candidate_name,
                        token
                    ) VALUES (
                        41,
                        NULL,
                        'DOWN@WINOE.AI',
                        'invited',
                        'Duplicate Case',
                        'down-token-2'
                    )
                    """
                )
            )


def test_issue_277_ensure_fk_renames_legacy_named_semantic_match(monkeypatch):
    op = _RecordingOp()
    bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    foreign_keys = [
        {
            "name": "fk_scenario_versions_simulation_id_simulations",
            "constrained_columns": ["trial_id"],
            "referred_table": "trials",
            "referred_columns": ["id"],
        }
    ]
    rename_calls: list[tuple[str, str, str]] = []

    monkeypatch.setattr(issue_277_migration, "_table_exists", lambda _b, _t: True)
    monkeypatch.setattr(
        issue_277_migration, "_column_names", lambda _b, _t: {"trial_id"}
    )
    monkeypatch.setattr(
        issue_277_migration,
        "_foreign_keys",
        lambda _b, _t: [dict(foreign_key) for foreign_key in foreign_keys],
    )

    def _rename(
        _bind: object,
        *,
        table_name: str,
        old_name: str,
        new_name: str,
    ) -> None:
        rename_calls.append((table_name, old_name, new_name))
        for foreign_key in foreign_keys:
            if foreign_key["name"] == old_name:
                foreign_key["name"] = new_name

    monkeypatch.setattr(issue_277_migration, "_rename_postgresql_constraint", _rename)

    issue_277_migration._ensure_fk(
        op,
        bind,
        name="fk_scenario_versions_trial_id_trials",
        table_name="scenario_versions",
        referred_table="trials",
        local_columns=["trial_id"],
        remote_columns=["id"],
        legacy_name="fk_scenario_versions_simulation_id_simulations",
    )

    assert rename_calls == [
        (
            "scenario_versions",
            "fk_scenario_versions_simulation_id_simulations",
            "fk_scenario_versions_trial_id_trials",
        )
    ]
    assert not [call for call in op.calls if call[0] == "create_foreign_key"]


def test_issue_277_ensure_fk_drops_semantic_duplicate_with_legacy_name(monkeypatch):
    op = _RecordingOp()
    bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    foreign_keys = [
        {
            "name": "fk_scenario_versions_trial_id_trials",
            "constrained_columns": ["trial_id"],
            "referred_table": "trials",
            "referred_columns": ["id"],
        },
        {
            "name": "fk_scenario_versions_simulation_id_simulations",
            "constrained_columns": ["trial_id"],
            "referred_table": "trials",
            "referred_columns": ["id"],
        },
    ]

    monkeypatch.setattr(issue_277_migration, "_table_exists", lambda _b, _t: True)
    monkeypatch.setattr(
        issue_277_migration, "_column_names", lambda _b, _t: {"trial_id"}
    )
    monkeypatch.setattr(
        issue_277_migration,
        "_foreign_keys",
        lambda _b, _t: [dict(foreign_key) for foreign_key in foreign_keys],
    )
    monkeypatch.setattr(
        issue_277_migration,
        "_rename_postgresql_constraint",
        lambda *_args, **_kwargs: None,
    )

    issue_277_migration._ensure_fk(
        op,
        bind,
        name="fk_scenario_versions_trial_id_trials",
        table_name="scenario_versions",
        referred_table="trials",
        local_columns=["trial_id"],
        remote_columns=["id"],
        legacy_name="fk_scenario_versions_simulation_id_simulations",
    )

    assert (
        "drop_constraint",
        ("fk_scenario_versions_simulation_id_simulations", "scenario_versions"),
        {"type_": "foreignkey"},
    ) in op.calls


def test_issue_277_ensure_fk_restores_legacy_name_on_downgrade(monkeypatch):
    op = _RecordingOp()
    bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    foreign_keys = [
        {
            "name": "fk_tasks_trial_id_trials",
            "constrained_columns": ["simulation_id"],
            "referred_table": "simulations",
            "referred_columns": ["id"],
        }
    ]
    rename_calls: list[tuple[str, str, str]] = []

    monkeypatch.setattr(issue_277_migration, "_table_exists", lambda _b, _t: True)
    monkeypatch.setattr(
        issue_277_migration,
        "_column_names",
        lambda _b, _t: {"simulation_id"},
    )
    monkeypatch.setattr(
        issue_277_migration,
        "_foreign_keys",
        lambda _b, _t: [dict(foreign_key) for foreign_key in foreign_keys],
    )

    def _rename(
        _bind: object,
        *,
        table_name: str,
        old_name: str,
        new_name: str,
    ) -> None:
        rename_calls.append((table_name, old_name, new_name))
        for foreign_key in foreign_keys:
            if foreign_key["name"] == old_name:
                foreign_key["name"] = new_name

    monkeypatch.setattr(issue_277_migration, "_rename_postgresql_constraint", _rename)

    issue_277_migration._ensure_fk(
        op,
        bind,
        name="fk_tasks_simulation_id_simulations",
        table_name="tasks",
        referred_table="simulations",
        local_columns=["simulation_id"],
        remote_columns=["id"],
        legacy_name="fk_tasks_trial_id_trials",
    )

    assert rename_calls == [
        (
            "tasks",
            "fk_tasks_trial_id_trials",
            "fk_tasks_simulation_id_simulations",
        )
    ]
    assert not [call for call in op.calls if call[0] == "create_foreign_key"]
