"""merge heads

Revision ID: f3629094103d
Revises: 3a7f9bc14d2e, bba44890f782
Create Date: 2026-04-26 00:33:15.336318

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3629094103d'
down_revision: Union[str, Sequence[str], None] = ('3a7f9bc14d2e', 'bba44890f782')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
