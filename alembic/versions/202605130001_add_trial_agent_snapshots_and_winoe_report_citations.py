"""Add trial agent snapshots and Winoe report citations.

Revision ID: 202605130001
Revises: 202605060001
Create Date: 2026-05-13 00:01:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202605130001"
down_revision: str | Sequence[str] | None = "202605060001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "trial_id",
            sa.Integer(),
            sa.ForeignKey("trials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_name", sa.String(length=255), nullable=False),
        sa.Column("agent_type", sa.String(length=50), nullable=False),
        sa.Column("model_provider", sa.String(length=100), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("model_version", sa.String(length=255), nullable=False),
        sa.Column("prompt_version", sa.String(length=255), nullable=False),
        sa.Column("prompt_content", sa.Text(), nullable=False),
        sa.Column("prompt_content_hash", sa.String(length=64), nullable=False),
        sa.Column("rubric_version", sa.String(length=255), nullable=False),
        sa.Column("rubric_content", sa.Text(), nullable=False),
        sa.Column("rubric_content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "trial_id",
            "agent_name",
            name="uq_agent_snapshots_trial_agent",
        ),
    )
    op.create_index("ix_agent_snapshots_trial_id", "agent_snapshots", ["trial_id"])
    op.create_index("ix_agent_snapshots_agent_name", "agent_snapshots", ["agent_name"])

    op.create_table(
        "citations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "report_id",
            sa.Integer(),
            sa.ForeignKey("winoe_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dimension", sa.String(length=100), nullable=False),
        sa.Column("artifact_type", sa.String(length=50), nullable=False),
        sa.Column("artifact_ref", sa.String(length=500), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_citations_report_dimension",
        "citations",
        ["report_id", "dimension"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_citations_report_dimension",
        table_name="citations",
    )
    op.drop_table("citations")

    op.drop_index("ix_agent_snapshots_agent_name", table_name="agent_snapshots")
    op.drop_index("ix_agent_snapshots_trial_id", table_name="agent_snapshots")
    op.drop_table("agent_snapshots")
