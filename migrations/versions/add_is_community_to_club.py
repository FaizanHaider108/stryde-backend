"""Add is_community flag to clubs table."""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_is_community_flag'
down_revision = 'f3629094103d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add is_community column with default False
    op.add_column('clubs', sa.Column('is_community', sa.Boolean(), server_default='false', nullable=False))
    # Create index for faster queries
    op.create_index(op.f('ix_clubs_is_community'), 'clubs', ['is_community'])


def downgrade() -> None:
    # Drop the index and column
    op.drop_index(op.f('ix_clubs_is_community'), table_name='clubs')
    op.drop_column('clubs', 'is_community')
