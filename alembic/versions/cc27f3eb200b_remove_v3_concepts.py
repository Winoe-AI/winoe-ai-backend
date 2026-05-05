"""remove_v3_concepts

Revision ID: cc27f3eb200b
Revises: 202604290001
Create Date: 2026-05-04 13:26:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'cc27f3eb200b'
down_revision = '202604290001'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Drop PrecommitBundle and CodespaceSpecification if they exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    
    if 'precommit_bundles' in tables:
        op.drop_table('precommit_bundles')
    if 'codespace_specifications' in tables:
        op.drop_table('codespace_specifications')

def downgrade() -> None:
    # This migration drops retired v3 concepts and is intentionally non-reversible.
    pass
