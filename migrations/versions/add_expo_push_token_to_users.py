"""add expo_push_token to users

Revision ID: add_expo_push_token
Revises: e1a5c9b77f10, add_goal_type_to_plans, add_is_community_flag
Create Date: 2026-05-02

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_expo_push_token'
down_revision = ('e1a5c9b77f10', 'add_goal_type_to_plans', 'add_is_community_flag')
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('expo_push_token', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'expo_push_token')
