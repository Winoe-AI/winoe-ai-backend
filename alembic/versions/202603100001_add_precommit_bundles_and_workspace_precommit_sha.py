"""Add precommit_bundles table and workspace precommit sha.

Revision ID: 202603100001
Revises: 202603090003
Create Date: 2026-03-10 00:01:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202603100001"
down_revision: str | Sequence[str] | None = "202603090003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "precommit_bundles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scenario_version_id", sa.Integer(), nullable=False),
        sa.Column("template_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("patch_text", sa.Text(), nullable=True),
        sa.Column("storage_ref", sa.String(length=500), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("base_template_sha", sa.String(length=100), nullable=True),
        sa.Column("applied_commit_sha", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["scenario_version_id"],
            ["scenario_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scenario_version_id",
            "template_key",
            name="uq_precommit_bundles_scenario_template",
        ),
        sa.CheckConstraint(
            "status IN ('draft','ready','disabled')",
            name="ck_precommit_bundles_status",
        ),
        sa.CheckConstraint(
            "(patch_text IS NOT NULL) OR (storage_ref IS NOT NULL)",
            name="ck_precommit_bundle_content_source",
        ),
    )
    op.create_index(
        "ix_precommit_bundles_lookup",
        "precommit_bundles",
        ["scenario_version_id", "template_key", "status"],
        unique=False,
    )
    op.create_index(
        "ix_precommit_bundles_scenario_version_id",
        "precommit_bundles",
        ["scenario_version_id"],
        unique=False,
    )
    op.add_column(
        "workspaces",
        sa.Column("precommit_sha", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "precommit_sha")
    op.drop_index(
        "ix_precommit_bundles_scenario_version_id",
        table_name="precommit_bundles",
    )
    op.drop_index("ix_precommit_bundles_lookup", table_name="precommit_bundles")
    op.drop_table("precommit_bundles")
