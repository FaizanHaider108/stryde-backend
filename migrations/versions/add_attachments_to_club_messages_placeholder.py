"""placeholder: club message attachments (revision referenced by deployed DBs)

Some databases were stamped at this revision when a migration existed on another
branch. This no-op keeps Alembic history consistent so upgrades can reach head.

Revision ID: add_attachments_to_club_messages
Revises: add_notification_prefs
Create Date: 2026-05-14

"""
from alembic import op

revision = "add_attachments_to_club_messages"
down_revision = "add_notification_prefs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
