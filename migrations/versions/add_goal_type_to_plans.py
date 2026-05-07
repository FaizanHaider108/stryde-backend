"""Add goal_type to plans table

Revision ID: add_goal_type_to_plans
Revises: 
Create Date: 2026-04-26 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_goal_type_to_plans'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add goal_type column to plans table
    op.add_column('plans', sa.Column('goal_type', sa.String(), nullable=True))


def downgrade() -> None:
    # Remove goal_type column from plans table
    op.drop_column('plans', 'goal_type')
