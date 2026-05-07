"""add notification_prefs to users

Revision ID: add_notification_prefs
Revises: add_expo_push_token
Create Date: 2026-05-02

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_notification_prefs'
down_revision = 'add_expo_push_token'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('notification_prefs', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'notification_prefs')
