"""Add notification delivery audit records.

Revision ID: 202604170001
Revises: 202604160001
Create Date: 2026-04-17 00:01:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202604170001"
down_revision: str | Sequence[str] | None = "202604160001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_delivery_audits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("notification_type", sa.String(length=100), nullable=False),
        sa.Column(
            "candidate_session_id",
            sa.Integer(),
            sa.ForeignKey("candidate_sessions.id"),
            nullable=True,
        ),
        sa.Column(
            "trial_id",
            sa.Integer(),
            sa.ForeignKey("trials.id"),
            nullable=True,
        ),
        sa.Column("recipient_email", sa.String(length=255), nullable=False),
        sa.Column("recipient_role", sa.String(length=50), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notification_delivery_audits_candidate_session_attempted_at",
        "notification_delivery_audits",
        ["candidate_session_id", "attempted_at"],
    )
    op.create_index(
        "ix_notification_delivery_audits_notification_type_attempted_at",
        "notification_delivery_audits",
        ["notification_type", "attempted_at"],
    )
    op.create_index(
        "ix_notification_delivery_audits_status_attempted_at",
        "notification_delivery_audits",
        ["status", "attempted_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_delivery_audits_status_attempted_at",
        table_name="notification_delivery_audits",
    )
    op.drop_index(
        "ix_notification_delivery_audits_notification_type_attempted_at",
        table_name="notification_delivery_audits",
    )
    op.drop_index(
        "ix_notification_delivery_audits_candidate_session_attempted_at",
        table_name="notification_delivery_audits",
    )
    op.drop_table("notification_delivery_audits")
