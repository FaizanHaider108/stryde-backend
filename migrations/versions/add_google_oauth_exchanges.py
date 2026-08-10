"""add google oauth exchanges (durable OAuth token handoff store)

Revision ID: add_google_oauth_exchanges
Revises: add_club_discovery_fields
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_google_oauth_exchanges'
down_revision: Union[str, Sequence[str], None] = 'add_club_discovery_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'google_oauth_exchanges',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('xcode', sa.String(), nullable=False),
        sa.Column('poll_id', sa.String(), nullable=True),
        sa.Column('access_token', sa.String(), nullable=True),
        sa.Column('refresh_token', sa.String(), nullable=True),
        sa.Column('after_path', sa.String(), nullable=False),
        sa.Column('error', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('xcode', name='uq_google_oauth_exchanges_xcode'),
        sa.UniqueConstraint('poll_id', name='uq_google_oauth_exchanges_poll_id'),
    )
    op.create_index(op.f('ix_google_oauth_exchanges_xcode'), 'google_oauth_exchanges', ['xcode'], unique=True)
    op.create_index(op.f('ix_google_oauth_exchanges_poll_id'), 'google_oauth_exchanges', ['poll_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_google_oauth_exchanges_poll_id'), table_name='google_oauth_exchanges')
    op.drop_index(op.f('ix_google_oauth_exchanges_xcode'), table_name='google_oauth_exchanges')
    op.drop_table('google_oauth_exchanges')
