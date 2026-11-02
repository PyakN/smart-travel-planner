"""recategorize buildings mapped as artworks that open to visitors as landmarks

Casa Batlló and Casa Milà are mapped as `tourism=artwork` + `artwork_type=architecture`, so
the importer made them monuments: outdoor, with a 10-minute visit. Those with a building and
opening hours are landmarks now (app.catalog.open_building); this brings imported rows in
line without importing the cities again.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Inlined on purpose: migrations must not import app code that changes later. Monuments
# from `historic=monument|memorial` stay monuments, as the importer's rules have them.
OPEN_BUILDING = (
    "tags->>'tourism' = 'artwork' AND tags->>'artwork_type' = 'architecture' "
    "AND tags->>'building' IS NOT NULL AND tags->>'opening_hours' IS NOT NULL "
    "AND coalesce(tags->>'historic', '') NOT IN ('monument', 'memorial')"
)
# Landmarks for reasons of their own, which a downgrade leaves alone.
LANDMARK_HISTORIC = (
    "'castle', 'palace', 'fort', 'tower', 'city_gate', 'monastery', 'aqueduct', 'ruins', "
    "'archaeological_site', 'building'"
)


def _category(slug: str) -> str:
    return f"(SELECT id FROM categories WHERE slug = '{slug}')"


def upgrade() -> None:
    op.execute(
        f"UPDATE places SET category_id = {_category('landmark')}, updated_at = now() "
        f"WHERE category_id = {_category('monument')} AND {OPEN_BUILDING}"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE places SET category_id = {_category('monument')}, updated_at = now() "
        f"WHERE category_id = {_category('landmark')} AND {OPEN_BUILDING} "
        f"AND coalesce(tags->>'historic', '') NOT IN ({LANDMARK_HISTORIC})"
    )
