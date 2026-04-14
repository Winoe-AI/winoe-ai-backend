"""Add worker heartbeats table.

Revision ID: 202604140001
Revises: 202604130001
Create Date: 2026-04-14 00:01:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202604140001"
down_revision: str | Sequence[str] | None = "202604130001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE_NAME = "worker_heartbeats"
_INDEX_NAME = "ix_worker_heartbeats_service_last_heartbeat"
_REQUIRED_COLUMNS = {
    "service_name",
    "instance_id",
    "status",
    "started_at",
    "last_heartbeat_at",
    "created_at",
    "updated_at",
}
_EXPECTED_PRIMARY_KEY_COLUMNS = ["service_name", "instance_id"]


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
    indexes = sa.inspect(op.get_bind()).get_indexes(table_name)
    return any(index.get("name") == index_name for index in indexes)


def _validate_existing_worker_heartbeats_table() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = inspector.get_columns(_TABLE_NAME)
    column_names = {column["name"] for column in columns}
    missing_columns = sorted(_REQUIRED_COLUMNS - column_names)
    primary_key = inspector.get_pk_constraint(_TABLE_NAME).get("constrained_columns") or []

    if missing_columns or primary_key != _EXPECTED_PRIMARY_KEY_COLUMNS:
        raise RuntimeError(
            "worker_heartbeats already exists but does not match the expected schema. "
            "Repair local schema drift manually before applying revision 202604140001. "
            f"missing_columns={missing_columns or '[]'} "
            f"primary_key={primary_key!r} "
            f"expected_primary_key={_EXPECTED_PRIMARY_KEY_COLUMNS!r}"
        )


def upgrade() -> None:
    if not _has_table(_TABLE_NAME):
        op.create_table(
            _TABLE_NAME,
            sa.Column("service_name", sa.String(length=100), nullable=False),
            sa.Column("instance_id", sa.String(length=255), nullable=False),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'running'"),
            ),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
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
            sa.PrimaryKeyConstraint("service_name", "instance_id"),
        )
    else:
        _validate_existing_worker_heartbeats_table()

    if not _has_index(_TABLE_NAME, _INDEX_NAME):
        op.create_index(
            _INDEX_NAME,
            _TABLE_NAME,
            ["service_name", "last_heartbeat_at"],
            unique=False,
        )


def downgrade() -> None:
    if not _has_table(_TABLE_NAME):
        return
    if _has_index(_TABLE_NAME, _INDEX_NAME):
        op.drop_index(_INDEX_NAME, table_name=_TABLE_NAME)
    op.drop_table(_TABLE_NAME)
