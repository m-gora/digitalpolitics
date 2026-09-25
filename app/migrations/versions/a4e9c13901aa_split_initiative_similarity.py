"""split initiative similarity into domain and narrative dimensions

Revision ID: a4e9c13901aa
Revises: 37c60518787e
Create Date: 2026-09-25

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "a4e9c13901aa"
down_revision: str | Sequence[str] | None = "37c60518787e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "campaigns", sa.Column("domain_embedding", Vector(1536), nullable=True)
    )
    # Existing vectors combined Thema, Ziel, and Storytelling. They are not
    # comparable to the new narrative-only vectors and must be regenerated.
    op.execute("UPDATE campaigns SET narrative_embedding = NULL")
    op.add_column(
        "initiatives", sa.Column("domain_similarity_score", sa.Float(), nullable=True)
    )
    op.add_column(
        "initiatives",
        sa.Column("narrative_similarity_score", sa.Float(), nullable=True),
    )
    op.drop_column("initiatives", "coherence_score")


def downgrade() -> None:
    op.add_column(
        "initiatives", sa.Column("coherence_score", sa.Float(), nullable=True)
    )
    op.execute("UPDATE initiatives SET coherence_score = narrative_similarity_score")
    op.drop_column("initiatives", "narrative_similarity_score")
    op.drop_column("initiatives", "domain_similarity_score")
    op.drop_column("campaigns", "domain_embedding")
