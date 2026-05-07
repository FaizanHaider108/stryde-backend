"""snapshot route data for posts

Revision ID: e1a5c9b77f10
Revises: f3629094103d
Create Date: 2026-05-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e1a5c9b77f10"
down_revision: Union[str, Sequence[str], None] = "f3629094103d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("route_snapshot_id", sa.Uuid(), nullable=True))
    op.add_column("posts", sa.Column("route_snapshot_name", sa.String(), nullable=True))
    op.add_column("posts", sa.Column("route_snapshot_distance_km", sa.Float(), nullable=True))
    op.add_column("posts", sa.Column("route_snapshot_elevation_gain_m", sa.Float(), nullable=True))
    op.add_column("posts", sa.Column("route_snapshot_start_lat", sa.Float(), nullable=True))
    op.add_column("posts", sa.Column("route_snapshot_start_lng", sa.Float(), nullable=True))
    op.add_column("posts", sa.Column("route_snapshot_end_lat", sa.Float(), nullable=True))
    op.add_column("posts", sa.Column("route_snapshot_end_lng", sa.Float(), nullable=True))
    op.add_column("posts", sa.Column("route_snapshot_map_data", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE posts
        SET
          route_snapshot_id = routes.id,
          route_snapshot_name = routes.name,
          route_snapshot_distance_km = routes.distance_km,
          route_snapshot_elevation_gain_m = routes.elevation_gain_m,
          route_snapshot_start_lat = routes.start_lat,
          route_snapshot_start_lng = routes.start_lng,
          route_snapshot_end_lat = routes.end_lat,
          route_snapshot_end_lng = routes.end_lng,
          route_snapshot_map_data = routes.map_data
        FROM routes
        WHERE posts.route_id = routes.id
        """
    )

    op.drop_constraint("fk_posts_route_id_routes", "posts", type_="foreignkey")
    op.create_foreign_key(
        "fk_posts_route_id_routes",
        "posts",
        "routes",
        ["route_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_posts_route_id_routes", "posts", type_="foreignkey")
    op.create_foreign_key(
        "fk_posts_route_id_routes",
        "posts",
        "routes",
        ["route_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_column("posts", "route_snapshot_map_data")
    op.drop_column("posts", "route_snapshot_end_lng")
    op.drop_column("posts", "route_snapshot_end_lat")
    op.drop_column("posts", "route_snapshot_start_lng")
    op.drop_column("posts", "route_snapshot_start_lat")
    op.drop_column("posts", "route_snapshot_elevation_gain_m")
    op.drop_column("posts", "route_snapshot_distance_km")
    op.drop_column("posts", "route_snapshot_name")
    op.drop_column("posts", "route_snapshot_id")
