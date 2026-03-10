"""Add scenario edit audit table.

Revision ID: 202603090003
Revises: 202603090002
Create Date: 2026-03-09 20:35:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202603090003"
down_revision: str | Sequence[str] | None = "202603090002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scenario_edit_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scenario_version_id", sa.Integer(), nullable=False),
        sa.Column("recruiter_id", sa.Integer(), nullable=False),
        sa.Column("patch_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["scenario_version_id"], ["scenario_versions.id"]),
        sa.ForeignKeyConstraint(["recruiter_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scenario_edit_audit_scenario_version_created_at",
        "scenario_edit_audit",
        ["scenario_version_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_scenario_edit_audit_recruiter_created_at",
        "scenario_edit_audit",
        ["recruiter_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scenario_edit_audit_recruiter_created_at",
        table_name="scenario_edit_audit",
    )
    op.drop_index(
        "ix_scenario_edit_audit_scenario_version_created_at",
        table_name="scenario_edit_audit",
    )
    op.drop_table("scenario_edit_audit")
