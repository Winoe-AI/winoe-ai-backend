"""Add workspace_groups and workspace_group_id for unified coding repo.

Revision ID: 202603080001
Revises: 202603050003
Create Date: 2026-03-08 00:01:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202603080001"
down_revision: str | Sequence[str] | None = "202603050003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_groups",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("candidate_session_id", sa.Integer(), nullable=False),
        sa.Column("workspace_key", sa.String(length=64), nullable=False),
        sa.Column("template_repo_full_name", sa.String(length=255), nullable=False),
        sa.Column("repo_full_name", sa.String(length=255), nullable=False),
        sa.Column("default_branch", sa.String(length=120), nullable=True),
        sa.Column("base_template_sha", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["candidate_session_id"], ["candidate_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_session_id",
            "workspace_key",
            name="uq_workspace_groups_session_key",
        ),
    )

    op.add_column(
        "workspaces",
        sa.Column("workspace_group_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_workspaces_workspace_group_id",
        "workspaces",
        "workspace_groups",
        ["workspace_group_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_workspaces_workspace_group_id",
        "workspaces",
        ["workspace_group_id"],
        unique=False,
    )
    # No backfill: grouping is applied to new sessions only for MVP safety.


def downgrade() -> None:
    op.drop_index("ix_workspaces_workspace_group_id", table_name="workspaces")
    op.drop_constraint(
        "fk_workspaces_workspace_group_id", "workspaces", type_="foreignkey"
    )
    op.drop_column("workspaces", "workspace_group_id")
    op.drop_table("workspace_groups")
