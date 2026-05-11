"""add trial status completed for finished cohorts

Revision ID: 202605060001
Revises: 5148b3a35f39
Create Date: 2026-05-06

"""

from typing import Sequence, Union

from alembic import op

revision: str = "202605060001"
down_revision: Union[str, Sequence[str], None] = "5148b3a35f39"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_trials_status_lifecycle", "trials", type_="check")
    op.create_check_constraint(
        "ck_trials_status_lifecycle",
        "trials",
        "status IN ("
        "'draft','generating','ready_for_review','active_inviting','terminated','completed'"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint("ck_trials_status_lifecycle", "trials", type_="check")
    op.create_check_constraint(
        "ck_trials_status_lifecycle",
        "trials",
        "status IN ("
        "'draft','generating','ready_for_review','active_inviting','terminated'"
        ")",
    )
