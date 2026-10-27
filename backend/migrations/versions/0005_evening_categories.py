"""add evening categories: nightlife and restaurant

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Seed data is inlined on purpose: migrations must not import app code that changes later.
CATEGORIES = [
    ("nightlife", "Bar & nightlife"),
    ("restaurant", "Restaurant"),
]


def upgrade() -> None:
    categories = sa.table("categories", sa.column("slug", sa.String), sa.column("name", sa.String))
    op.bulk_insert(categories, [{"slug": s, "name": n} for s, n in CATEGORIES])


def downgrade() -> None:
    slugs = ", ".join(f"'{slug}'" for slug, _ in CATEGORIES)
    places = (
        "SELECT p.id FROM places p JOIN categories c ON c.id = p.category_id "
        f"WHERE c.slug IN ({slugs})"
    )
    op.execute(f"DELETE FROM route_stops WHERE place_id IN ({places})")
    op.execute(f"DELETE FROM places WHERE id IN ({places})")
    op.execute(f"DELETE FROM categories WHERE slug IN ({slugs})")
