"""Mark precommit bundle storage as legacy only.

Revision ID: 202604290001
Revises: 202604200001
Create Date: 2026-04-29 00:01:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202604290001"
down_revision: str | Sequence[str] | None = "202604200001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEGACY_TABLE_COMMENT = (
    "Legacy table retained for historical rows only. "
    "Active runtime must not create or depend on precommit bundles."
)

_LEGACY_COLUMN_COMMENT = (
    "Legacy compatibility column retained for historical rows only."
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":  # pragma: no cover - db specific
        return

    op.execute(
        sa.text(
            "COMMENT ON TABLE precommit_bundles IS "
            f"{_LEGACY_TABLE_COMMENT!r}"
        )
    )
    op.execute(
        sa.text(
            "COMMENT ON COLUMN workspaces.precommit_sha IS "
            f"{_LEGACY_COLUMN_COMMENT!r}"
        )
    )
    op.execute(
        sa.text(
            "COMMENT ON COLUMN workspaces.precommit_details_json IS "
            f"{_LEGACY_COLUMN_COMMENT!r}"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":  # pragma: no cover - db specific
        return

    op.execute(sa.text("COMMENT ON TABLE precommit_bundles IS NULL"))
    op.execute(sa.text("COMMENT ON COLUMN workspaces.precommit_sha IS NULL"))
    op.execute(
        sa.text("COMMENT ON COLUMN workspaces.precommit_details_json IS NULL")
    )
