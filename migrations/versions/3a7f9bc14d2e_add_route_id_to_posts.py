"""add route_id to posts

Revision ID: 3a7f9bc14d2e
Revises: 15d6f2ce77c8
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3a7f9bc14d2e"
down_revision: Union[str, None] = "15d6f2ce77c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "posts",
        sa.Column("route_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_posts_route_id_routes",
        "posts",
        "routes",
        ["route_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_posts_route_id_routes", "posts", type_="foreignkey")
    op.drop_column("posts", "route_id")
