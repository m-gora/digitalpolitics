"""add indexed full-text search for campaigns

Revision ID: 16bb36c3d9f4
Revises: a4e9c13901aa
Create Date: 2026-09-25 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "16bb36c3d9f4"
down_revision: str | Sequence[str] | None = "a4e9c13901aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEARCH_VECTOR_EXPRESSION = (
    "to_tsvector('german'::regconfig, "
    "coalesce(thema, '') || ' ' || coalesce(ziel, '') || ' ' || "
    "coalesce(zielgruppen, '') || ' ' || coalesce(kanaele, '') || ' ' || "
    "coalesce(momentum, '') || ' ' || coalesce(motiv, '') || ' ' || "
    "coalesce(service, '') || ' ' || coalesce(data_harvest, '') || ' ' || "
    "coalesce(tools, '') || ' ' || coalesce(phasen_flow, '') || ' ' || "
    "coalesce(storytelling, '') || ' ' || coalesce(ai_summary, ''))"
)


def upgrade() -> None:
    op.add_column(
        "campaigns",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(SEARCH_VECTOR_EXPRESSION, persisted=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_campaigns_search_vector",
        "campaigns",
        ["search_vector"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_campaigns_search_vector", table_name="campaigns")
    op.drop_column("campaigns", "search_vector")
