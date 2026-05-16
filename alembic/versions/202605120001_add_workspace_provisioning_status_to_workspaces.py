"""add workspace_provisioning_status to workspaces

Revision ID: 202605120001
Revises: 202605060001
Create Date: 2026-05-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202605120001"
down_revision: Union[str, Sequence[str], None] = "202605060001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("workspace_provisioning_status", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "workspace_provisioning_status")
