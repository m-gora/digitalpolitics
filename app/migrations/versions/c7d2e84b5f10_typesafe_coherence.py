"""replace embedding similarity with TypeSafe coherence scoring

Revision ID: c7d2e84b5f10
Revises: 16bb36c3d9f4
Create Date: 2026-10-22

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c7d2e84b5f10"
down_revision: str | Sequence[str] | None = "16bb36c3d9f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("campaigns", "domain_embedding")
    op.drop_column("campaigns", "narrative_embedding")
    # Cosine scores are not comparable with the normalized TypeSafe rubric scores;
    # run `python -m dpp.campaign.backfill_coherence` to recompute them.
    op.execute(
        "UPDATE initiatives SET domain_similarity_score = NULL, "
        "narrative_similarity_score = NULL, coherence_computed_at = NULL"
    )
    op.add_column(
        "initiatives",
        sa.Column("outlier_campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_initiatives_outlier_campaign_id",
        "initiatives",
        "campaigns",
        ["outlier_campaign_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_initiatives_outlier_campaign_id", "initiatives", type_="foreignkey")
    op.drop_column("initiatives", "outlier_campaign_id")
    op.add_column("campaigns", sa.Column("narrative_embedding", Vector(1536), nullable=True))
    op.add_column("campaigns", sa.Column("domain_embedding", Vector(1536), nullable=True))
