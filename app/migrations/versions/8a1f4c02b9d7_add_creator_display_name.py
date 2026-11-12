"""add creator display name to campaigns and questionnaires

Revision ID: 8a1f4c02b9d7
Revises: b73f0d2c1a48
Create Date: 2026-11-13

Non-authoritative display name captured at write time (see arch-01/adr-03).
Existing rows stay NULL and keep rendering the raw X-User-Id; the seed
scripts write names for freshly seeded data.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8a1f4c02b9d7"
down_revision: str | Sequence[str] | None = "b73f0d2c1a48"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("campaigns", sa.Column("created_by_name", sa.String(length=255), nullable=True))
    op.add_column("questionnaires", sa.Column("created_by_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("questionnaires", "created_by_name")
    op.drop_column("campaigns", "created_by_name")
