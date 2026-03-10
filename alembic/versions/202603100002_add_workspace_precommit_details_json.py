"""Add workspace precommit details JSON snapshot.

Revision ID: 202603100002
Revises: 202603100001
Create Date: 2026-03-10 00:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202603100002"
down_revision: str | Sequence[str] | None = "202603100001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("precommit_details_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "precommit_details_json")
