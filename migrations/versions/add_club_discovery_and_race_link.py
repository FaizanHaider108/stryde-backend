"""Add runner_type/state/lat/lng to clubs for search, and race_id to club_messages.

Revision ID: add_club_discovery_fields
Revises: c8a1e2b9f0aa
Create Date: 2026-08-07

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_club_discovery_fields'
down_revision = 'c8a1e2b9f0aa'
branch_labels = None
depends_on = None

# Reuses the Postgres enum type created for users.runner_type in the initial
# migration — same labels, `create(checkfirst=True)` below is a no-op if it
# already exists (and a no-op entirely on SQLite, which has no native enum type).
_RUNNER_TYPE_ENUM = sa.Enum(
    'grinder', 'social_stryder', 'goal_crusher', 'flow_chaser', name='runnertype'
)


def upgrade() -> None:
    bind = op.get_bind()
    _RUNNER_TYPE_ENUM.create(bind, checkfirst=True)

    op.add_column('clubs', sa.Column('runner_type', _RUNNER_TYPE_ENUM, nullable=True))
    op.add_column('clubs', sa.Column('state', sa.String(), nullable=True))
    op.add_column('clubs', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('clubs', sa.Column('longitude', sa.Float(), nullable=True))
    op.create_index(op.f('ix_clubs_state'), 'clubs', ['state'])

    op.add_column('club_messages', sa.Column('race_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_club_messages_race_id'), 'club_messages', ['race_id'])
    op.create_foreign_key(
        'fk_club_messages_race_id_races',
        'club_messages',
        'races',
        ['race_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_club_messages_race_id_races', 'club_messages', type_='foreignkey')
    op.drop_index(op.f('ix_club_messages_race_id'), table_name='club_messages')
    op.drop_column('club_messages', 'race_id')

    op.drop_index(op.f('ix_clubs_state'), table_name='clubs')
    op.drop_column('clubs', 'longitude')
    op.drop_column('clubs', 'latitude')
    op.drop_column('clubs', 'state')
    op.drop_column('clubs', 'runner_type')
    # Do not drop the runnertype enum type — users.runner_type still depends on it.
