"""add photo columns to places

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = ("image_url", "image_page_url", "image_credit")


def upgrade() -> None:
    for column in COLUMNS:
        op.add_column("places", sa.Column(column, sa.Text(), nullable=True))


def downgrade() -> None:
    for column in reversed(COLUMNS):
        op.drop_column("places", column)
