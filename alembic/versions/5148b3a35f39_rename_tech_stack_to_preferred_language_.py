"""rename_tech_stack_to_preferred_language_framework

Revision ID: 5148b3a35f39
Revises: 439821122cc4
Create Date: 2026-05-04 13:49:59.966479

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '5148b3a35f39'
down_revision: Union[str, Sequence[str], None] = '439821122cc4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()

def _column_names(inspector, table_name: str) -> set[str]:
    return {col['name'] for col in inspector.get_columns(table_name)}

def _upgrade_table(conn, inspector, table_name: str) -> None:
    if not _table_exists(inspector, table_name):
        return
        
    columns = _column_names(inspector, table_name)
    has_old = 'tech_stack' in columns
    has_new = 'preferred_language_framework' in columns
    
    if has_old and not has_new:
        op.alter_column(table_name, 'tech_stack', new_column_name='preferred_language_framework')
    elif has_old and has_new:
        conn.execute(sa.text(f"""
            UPDATE {table_name}
            SET preferred_language_framework = tech_stack
            WHERE (preferred_language_framework IS NULL OR preferred_language_framework = '')
              AND tech_stack IS NOT NULL
        """))
        op.drop_column(table_name, 'tech_stack')

def _downgrade_table(conn, inspector, table_name: str) -> None:
    if not _table_exists(inspector, table_name):
        return
        
    columns = _column_names(inspector, table_name)
    has_old = 'tech_stack' in columns
    has_new = 'preferred_language_framework' in columns
    
    if has_new and not has_old:
        op.alter_column(table_name, 'preferred_language_framework', new_column_name='tech_stack')
    elif has_new and has_old:
        conn.execute(sa.text(f"""
            UPDATE {table_name}
            SET tech_stack = preferred_language_framework
            WHERE (tech_stack IS NULL OR tech_stack = '')
              AND preferred_language_framework IS NOT NULL
        """))
        op.drop_column(table_name, 'preferred_language_framework')

def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    _upgrade_table(conn, inspector, 'trials')
    _upgrade_table(conn, inspector, 'scenario_versions')

def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    _downgrade_table(conn, inspector, 'trials')
    _downgrade_table(conn, inspector, 'scenario_versions')
