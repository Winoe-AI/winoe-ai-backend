"""rename_codespace_spec_json_to_project_brief_md

Revision ID: 439821122cc4
Revises: cc27f3eb200b
Create Date: 2026-05-04 13:49:32.169531

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '439821122cc4'
down_revision: Union[str, Sequence[str], None] = 'cc27f3eb200b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()

def _column_names(inspector, table_name: str) -> set[str]:
    return {col['name'] for col in inspector.get_columns(table_name)}

def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if not _table_exists(inspector, 'scenario_versions'):
        return
        
    columns = _column_names(inspector, 'scenario_versions')
    has_old = 'codespace_spec_json' in columns
    has_new = 'project_brief_md' in columns
    
    if has_old and not has_new:
        op.alter_column('scenario_versions', 'codespace_spec_json', new_column_name='project_brief_md')
    elif has_old and has_new:
        # Preserve data
        conn.execute(sa.text("""
            UPDATE scenario_versions
            SET project_brief_md = CAST(codespace_spec_json AS TEXT)
            WHERE (project_brief_md IS NULL OR project_brief_md = '')
              AND codespace_spec_json IS NOT NULL
        """))
        op.drop_column('scenario_versions', 'codespace_spec_json')

def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if not _table_exists(inspector, 'scenario_versions'):
        return
        
    columns = _column_names(inspector, 'scenario_versions')
    has_old = 'codespace_spec_json' in columns
    has_new = 'project_brief_md' in columns
    
    if has_new and not has_old:
        op.alter_column('scenario_versions', 'project_brief_md', new_column_name='codespace_spec_json')
    elif has_new and has_old:
        # Preserve data
        # For downgrade, we might need to cast back to JSON. 
        # In SQLite, CAST AS TEXT is fine. In Postgres, we might need CAST AS JSON.
        # Let's use a dialect check if needed, or just CAST(project_brief_md AS JSON)
        # But wait, if it's text, casting to JSON might fail if it's not valid JSON.
        # Let's just do a simple update if dialect is sqlite, else cast.
        if conn.dialect.name == 'postgresql':
            conn.execute(sa.text("""
                UPDATE scenario_versions
                SET codespace_spec_json = project_brief_md::json
                WHERE codespace_spec_json IS NULL
                  AND project_brief_md IS NOT NULL AND project_brief_md != ''
            """))
        else:
            conn.execute(sa.text("""
                UPDATE scenario_versions
                SET codespace_spec_json = project_brief_md
                WHERE codespace_spec_json IS NULL
                  AND project_brief_md IS NOT NULL AND project_brief_md != ''
            """))
        op.drop_column('scenario_versions', 'project_brief_md')
