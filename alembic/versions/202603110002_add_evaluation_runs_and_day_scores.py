"""Add evaluation runs and day scores persistence tables.

Revision ID: 202603110002
Revises: 202603110001
Create Date: 2026-03-11 13:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202603110002"
down_revision: str | Sequence[str] | None = "202603110001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_session_id", sa.Integer(), nullable=False),
        sa.Column("scenario_version_id", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=50), nullable=False, server_default="pending"
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("model_version", sa.String(length=255), nullable=False),
        sa.Column("prompt_version", sa.String(length=255), nullable=False),
        sa.Column("rubric_version", sa.String(length=255), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("day2_checkpoint_sha", sa.String(length=100), nullable=False),
        sa.Column("day3_final_sha", sa.String(length=100), nullable=False),
        sa.Column("cutoff_commit_sha", sa.String(length=100), nullable=False),
        sa.Column("transcript_reference", sa.String(length=255), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','failed')",
            name="ck_evaluation_runs_status",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="ck_evaluation_runs_completed_after_started",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_session_id"],
            ["candidate_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scenario_version_id"],
            ["scenario_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evaluation_runs_candidate_session_scenario_version",
        "evaluation_runs",
        ["candidate_session_id", "scenario_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_evaluation_runs_candidate_session_started_at",
        "evaluation_runs",
        ["candidate_session_id", "started_at"],
        unique=False,
    )

    op.create_table(
        "evaluation_day_scores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("rubric_results_json", sa.JSON(), nullable=False),
        sa.Column("evidence_pointers_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "day_index BETWEEN 1 AND 5",
            name="ck_evaluation_day_scores_day_index",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["evaluation_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "day_index",
            name="uq_evaluation_day_scores_run_day",
        ),
    )
    op.create_index(
        "ix_evaluation_day_scores_run_id",
        "evaluation_day_scores",
        ["run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_day_scores_run_id", table_name="evaluation_day_scores")
    op.drop_table("evaluation_day_scores")

    op.drop_index(
        "ix_evaluation_runs_candidate_session_started_at",
        table_name="evaluation_runs",
    )
    op.drop_index(
        "ix_evaluation_runs_candidate_session_scenario_version",
        table_name="evaluation_runs",
    )
    op.drop_table("evaluation_runs")
