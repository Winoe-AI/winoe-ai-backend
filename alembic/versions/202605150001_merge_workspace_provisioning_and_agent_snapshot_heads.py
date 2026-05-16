"""Merge heads 202605120001 and 202605130001.

Resolves parallel branches from 202605060001 (workspace provisioning status
vs trial agent snapshots / citations).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa  # noqa: F401

from alembic import op  # noqa: F401

revision: str = "202605150001"
down_revision: str | Sequence[str] | None = ("202605120001", "202605130001")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
