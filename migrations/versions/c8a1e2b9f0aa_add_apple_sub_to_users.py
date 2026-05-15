"""add apple_sub to users for Sign in with Apple account linking

Revision ID: c8a1e2b9f0aa
Revises: add_attachments_to_club_messages
Create Date: 2026-05-14

"""

from alembic import op
import sqlalchemy as sa

revision = "c8a1e2b9f0aa"
down_revision = "add_attachments_to_club_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("apple_sub", sa.String(length=255), nullable=True))
    op.create_index("ix_users_apple_sub", "users", ["apple_sub"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_apple_sub", table_name="users")
    op.drop_column("users", "apple_sub")
