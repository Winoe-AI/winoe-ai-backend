"""Add workflow completion columns to submissions.

Revision ID: 202603130001
Revises: 202603120003
Create Date: 2026-03-13 00:01:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202603130001"
down_revision: str | Sequence[str] | None = "202603120003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column("workflow_run_attempt", sa.Integer(), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column("workflow_run_status", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column("workflow_run_conclusion", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column("workflow_run_completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("submissions", "workflow_run_completed_at")
    op.drop_column("submissions", "workflow_run_conclusion")
    op.drop_column("submissions", "workflow_run_status")
    op.drop_column("submissions", "workflow_run_attempt")
