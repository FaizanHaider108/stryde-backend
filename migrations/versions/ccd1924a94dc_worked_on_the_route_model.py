"""worked on the route model

Revision ID: ccd1924a94dc
Revises: 8d993d5db7ad
Create Date: 2026-03-06 02:32:32.791374

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'ccd1924a94dc'
down_revision: Union[str, Sequence[str], None] = '8d993d5db7ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ENVIRONMENT_ENUM = sa.Enum('max_shade', 'open_air', name='environmentenum')
_TERRAIN_ENUM = sa.Enum('paved', 'unpaved', name='terrainenum')
_ELEVATION_ENUM = sa.Enum('flat', 'hilly', name='elevationprofileenum')


def _has_fk_to(inspector, table_name: str, column: str, referred_table: str) -> bool:
    for fk in inspector.get_foreign_keys(table_name):
        if fk.get('referred_table') == referred_table and column in fk.get('constrained_columns', []):
            return True
    return False


def _create_enum_types(bind) -> None:
    _ENVIRONMENT_ENUM.create(bind, checkfirst=True)
    _TERRAIN_ENUM.create(bind, checkfirst=True)
    _ELEVATION_ENUM.create(bind, checkfirst=True)


def _alter_route_tag_columns_to_enums() -> None:
    """Initial migration created VARCHAR tag columns; convert them to Postgres enums."""
    op.alter_column(
        'routes',
        'environment',
        type_=_ENVIRONMENT_ENUM,
        existing_type=sa.String(),
        postgresql_using=(
            "CASE "
            "WHEN environment IS NULL OR environment = '' THEN NULL "
            "ELSE environment::environmentenum "
            "END"
        ),
        existing_nullable=True,
    )
    op.alter_column(
        'routes',
        'terrain',
        type_=_TERRAIN_ENUM,
        existing_type=sa.String(),
        postgresql_using=(
            "CASE "
            "WHEN terrain IS NULL OR terrain = '' THEN NULL "
            "ELSE terrain::terrainenum "
            "END"
        ),
        existing_nullable=True,
    )
    op.alter_column(
        'routes',
        'elevation_profile',
        type_=_ELEVATION_ENUM,
        existing_type=sa.String(),
        postgresql_using=(
            "CASE "
            "WHEN elevation_profile IS NULL OR elevation_profile = '' THEN NULL "
            "ELSE elevation_profile::elevationprofileenum "
            "END"
        ),
        existing_nullable=True,
    )


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    _create_enum_types(bind)

    if 'routes' not in tables:
        op.create_table(
            'routes',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('creator_id', sa.Uuid(), nullable=False),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('distance_km', sa.Float(), nullable=False),
            sa.Column('elevation_gain_m', sa.Float(), nullable=True),
            sa.Column('start_lat', sa.Float(), nullable=False),
            sa.Column('start_lng', sa.Float(), nullable=False),
            sa.Column('start_address', sa.String(), nullable=True),
            sa.Column('end_lat', sa.Float(), nullable=False),
            sa.Column('end_lng', sa.Float(), nullable=False),
            sa.Column('end_address', sa.String(), nullable=True),
            sa.Column('map_data', sa.String(), nullable=False),
            sa.Column('avoid_pollution', sa.Boolean(), nullable=True),
            sa.Column('environment', _ENVIRONMENT_ENUM, nullable=True),
            sa.Column('terrain', _TERRAIN_ENUM, nullable=True),
            sa.Column('elevation_profile', _ELEVATION_ENUM, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.ForeignKeyConstraint(['creator_id'], ['users.uid'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_routes_id'), 'routes', ['id'], unique=False)
    else:
        _alter_route_tag_columns_to_enums()

    if 'events' in tables and not _has_fk_to(inspector, 'events', 'route_id', 'routes'):
        op.create_foreign_key(None, 'events', 'routes', ['route_id'], ['id'], ondelete='RESTRICT')
    if 'runs' in tables and not _has_fk_to(inspector, 'runs', 'route_id', 'routes'):
        op.create_foreign_key(None, 'runs', 'routes', ['route_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if 'runs' in tables and _has_fk_to(inspector, 'runs', 'route_id', 'routes'):
        for fk in inspector.get_foreign_keys('runs'):
            if fk.get('referred_table') == 'routes' and 'route_id' in fk.get('constrained_columns', []):
                op.drop_constraint(fk['name'], 'runs', type_='foreignkey')
                break

    if 'events' in tables and _has_fk_to(inspector, 'events', 'route_id', 'routes'):
        for fk in inspector.get_foreign_keys('events'):
            if fk.get('referred_table') == 'routes' and 'route_id' in fk.get('constrained_columns', []):
                op.drop_constraint(fk['name'], 'events', type_='foreignkey')
                break

    if 'routes' not in tables:
        return

    # Only drop routes if this migration created them (no events/runs FKs from initial migration).
    if not _has_fk_to(inspector, 'events', 'route_id', 'routes'):
        op.drop_index(op.f('ix_routes_id'), table_name='routes')
        op.drop_table('routes')
    else:
        op.alter_column(
            'routes',
            'environment',
            type_=sa.String(),
            existing_type=_ENVIRONMENT_ENUM,
            postgresql_using='environment::text',
            existing_nullable=True,
        )
        op.alter_column(
            'routes',
            'terrain',
            type_=sa.String(),
            existing_type=_TERRAIN_ENUM,
            postgresql_using='terrain::text',
            existing_nullable=True,
        )
        op.alter_column(
            'routes',
            'elevation_profile',
            type_=sa.String(),
            existing_type=_ELEVATION_ENUM,
            postgresql_using='elevation_profile::text',
            existing_nullable=True,
        )

    _ELEVATION_ENUM.drop(bind, checkfirst=True)
    _TERRAIN_ENUM.drop(bind, checkfirst=True)
    _ENVIRONMENT_ENUM.drop(bind, checkfirst=True)
