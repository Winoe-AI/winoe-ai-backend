"""Add preferred_display_name to candidate_sessions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "202605150001_prefdisp"
down_revision = "202605150001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "candidate_sessions",
        sa.Column("preferred_display_name", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("candidate_sessions", "preferred_display_name")
