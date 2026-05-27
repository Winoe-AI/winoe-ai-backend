"""Task 11 job hardening, evaluation state, and notification audit fields."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "202605240001_task11"
down_revision = "202605150001_prefdisp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("jobs", "max_attempts", server_default="3")
    op.create_table(
        "job_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(length=36),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_job_events_job_created_at", "job_events", ["job_id", "created_at"]
    )
    op.create_index(
        "ix_job_events_event_type_created_at",
        "job_events",
        ["event_type", "created_at"],
    )
    op.create_index("ix_job_events_correlation_id", "job_events", ["correlation_id"])

    op.create_table(
        "failed_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "original_job_id",
            sa.String(length=36),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "retry_job_id",
            sa.String(length=36),
            sa.ForeignKey("jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "retried_from_failed_job_id",
            sa.String(length=36),
            sa.ForeignKey("failed_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id"),
            nullable=True,
        ),
        sa.Column(
            "candidate_session_id",
            sa.Integer(),
            sa.ForeignKey("candidate_sessions.id"),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_traceback", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("originated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "failed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_failed_jobs_original_job_id",
        "failed_jobs",
        ["original_job_id"],
        unique=True,
    )
    op.create_index(
        "ix_failed_jobs_job_type_failed_at",
        "failed_jobs",
        ["job_type", "failed_at"],
    )
    op.create_index("ix_failed_jobs_correlation_id", "failed_jobs", ["correlation_id"])
    op.create_index("ix_failed_jobs_retry_job_id", "failed_jobs", ["retry_job_id"])

    op.create_table(
        "trial_evaluation_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "trial_id",
            sa.Integer(),
            sa.ForeignKey("trials.id"),
            nullable=False,
        ),
        sa.Column(
            "candidate_session_id",
            sa.Integer(),
            sa.ForeignKey("candidate_sessions.id"),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.String(length=64),
            nullable=False,
            server_default="awaiting_day_5_deadline",
        ),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("reviewer_status_json", sa.JSON(), nullable=True),
        sa.Column("winoe_synthesis_status", sa.String(length=50), nullable=True),
        sa.Column(
            "evidence_trail_validation_status",
            sa.String(length=50),
            nullable=True,
        ),
        sa.Column("report_finalization_status", sa.String(length=50), nullable=True),
        sa.Column("notification_status", sa.String(length=50), nullable=True),
        sa.Column("failure_context_json", sa.JSON(), nullable=True),
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
    )
    op.create_index(
        "uq_trial_evaluation_states_candidate_session_id",
        "trial_evaluation_states",
        ["candidate_session_id"],
        unique=True,
    )
    op.create_index(
        "ix_trial_evaluation_states_trial_state",
        "trial_evaluation_states",
        ["trial_id", "state"],
    )
    op.create_index(
        "ix_trial_evaluation_states_correlation_id",
        "trial_evaluation_states",
        ["correlation_id"],
    )

    op.add_column(
        "notification_delivery_audits",
        sa.Column("provider", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification_delivery_audits", "provider")
    op.drop_index(
        "ix_trial_evaluation_states_correlation_id",
        table_name="trial_evaluation_states",
    )
    op.drop_index(
        "ix_trial_evaluation_states_trial_state",
        table_name="trial_evaluation_states",
    )
    op.drop_index(
        "uq_trial_evaluation_states_candidate_session_id",
        table_name="trial_evaluation_states",
    )
    op.drop_table("trial_evaluation_states")
    op.drop_index("ix_failed_jobs_retry_job_id", table_name="failed_jobs")
    op.drop_index("ix_failed_jobs_correlation_id", table_name="failed_jobs")
    op.drop_index("ix_failed_jobs_job_type_failed_at", table_name="failed_jobs")
    op.drop_index("ix_failed_jobs_original_job_id", table_name="failed_jobs")
    op.drop_table("failed_jobs")
    op.drop_index("ix_job_events_correlation_id", table_name="job_events")
    op.drop_index("ix_job_events_event_type_created_at", table_name="job_events")
    op.drop_index("ix_job_events_job_created_at", table_name="job_events")
    op.drop_table("job_events")
    op.alter_column("jobs", "max_attempts", server_default="5")
