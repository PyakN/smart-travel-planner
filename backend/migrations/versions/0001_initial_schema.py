"""initial schema: categories, places, routes, route_stops

Revision ID: 0001
Revises:
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Seed data is inlined on purpose: migrations must not import app code that changes later.
CATEGORIES = [
    ("museum", "Museum"),
    ("gallery", "Art gallery"),
    ("landmark", "Landmark"),
    ("monument", "Monument & memorial"),
    ("viewpoint", "Viewpoint"),
    ("religious", "Religious site"),
    ("park", "Park & garden"),
    ("culture", "Theatre & arts"),
    ("market", "Market"),
    ("attraction", "Attraction"),
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    categories = op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint("slug", name=op.f("uq_categories_slug")),
    )
    op.bulk_insert(categories, [{"slug": s, "name": n} for s, n in CATEGORIES])

    op.create_table(
        "places",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("osm_type", sa.String(length=10), nullable=False),
        sa.Column("osm_id", sa.BigInteger(), nullable=False),
        sa.Column("city", sa.String(length=50), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.Geography(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column(
            "tags", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("wikidata", sa.String(length=32), nullable=True),
        sa.Column("opening_hours", sa.Text(), nullable=True),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "osm_type IN ('node', 'way', 'relation')", name=op.f("ck_places_osm_type")
        ),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"], name=op.f("fk_places_category_id_categories")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_places")),
        sa.UniqueConstraint("osm_type", "osm_id", name="uq_places_osm"),
    )
    op.create_index("ix_places_geom", "places", ["geom"], postgresql_using="gist")
    op.create_index(op.f("ix_places_city"), "places", ["city"])
    op.create_index(op.f("ix_places_category_id"), "places", ["category_id"])

    op.create_table(
        "routes",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("city", sa.String(length=50), nullable=False),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column(
            "params", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("total_distance_m", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_routes")),
    )

    op.create_table(
        "route_stops",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("route_id", sa.BigInteger(), nullable=False),
        sa.Column("place_id", sa.BigInteger(), nullable=False),
        sa.Column("day", sa.SmallInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("day >= 1", name=op.f("ck_route_stops_day_positive")),
        sa.CheckConstraint("position >= 1", name=op.f("ck_route_stops_position_positive")),
        sa.ForeignKeyConstraint(
            ["place_id"],
            ["places.id"],
            name=op.f("fk_route_stops_place_id_places"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["route_id"],
            ["routes.id"],
            name=op.f("fk_route_stops_route_id_routes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_route_stops")),
        sa.UniqueConstraint("route_id", "day", "position", name="uq_route_stops_slot"),
    )
    op.create_index(op.f("ix_route_stops_route_id"), "route_stops", ["route_id"])


def downgrade() -> None:
    op.drop_table("route_stops")
    op.drop_table("routes")
    op.drop_table("places")
    op.drop_table("categories")
