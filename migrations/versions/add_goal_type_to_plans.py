"""Add goal_type to plans table

Revision ID: add_goal_type_to_plans
Revises: 
Create Date: 2026-04-26 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_goal_type_to_plans'
down_revision = 'f3629094103d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    if 'plans' not in inspector.get_table_names():
        return
    columns = {col['name'] for col in inspector.get_columns('plans')}
    if 'goal_type' in columns:
        return
    op.add_column('plans', sa.Column('goal_type', sa.String(), nullable=True))


def downgrade() -> None:
    # Remove goal_type column from plans table
    op.drop_column('plans', 'goal_type')
