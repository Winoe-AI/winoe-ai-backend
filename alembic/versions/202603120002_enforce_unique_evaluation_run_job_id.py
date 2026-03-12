"""Enforce unique non-null evaluation run job id.

Revision ID: 202603120002
Revises: 202603120001
Create Date: 2026-03-12 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "202603120002"
down_revision: str | Sequence[str] | None = "202603120001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_evaluation_runs_job_id", table_name="evaluation_runs")
    op.create_index(
        "ix_evaluation_runs_job_id",
        "evaluation_runs",
        ["job_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_runs_job_id", table_name="evaluation_runs")
    op.create_index(
        "ix_evaluation_runs_job_id",
        "evaluation_runs",
        ["job_id"],
        unique=False,
    )
