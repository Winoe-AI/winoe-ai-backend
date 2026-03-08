"""Enforce one canonical workspace row per workspace_group_id.

Revision ID: 202603080002
Revises: 202603080001
Create Date: 2026-03-08 00:15:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "202603080002"
down_revision: str | Sequence[str] | None = "202603080001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_workspaces_workspace_group_id", table_name="workspaces")
    op.create_index(
        "uq_workspaces_workspace_group_id",
        "workspaces",
        ["workspace_group_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_workspaces_workspace_group_id", table_name="workspaces")
    op.create_index(
        "ix_workspaces_workspace_group_id",
        "workspaces",
        ["workspace_group_id"],
        unique=False,
    )
