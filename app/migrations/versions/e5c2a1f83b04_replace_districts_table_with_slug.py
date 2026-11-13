"""replace districts table with district_slug columns

Revision ID: e5c2a1f83b04
Revises: 8a1f4c02b9d7
Create Date: 2026-11-13

The Gliederung tree moves from the database to a config file
(dpp.gliederungen, injected via ConfigMap; see arch-02/adr-03). Campaigns
and initiatives reference district slugs as plain strings, validated at
write time by the scope check.

Upgrade backfills the new slug columns from the legacy `districts` table
(slugified display names, matching the slugs in config/gliederungen.yaml)
while that table still exists, then drops the districts table and the
district_id columns. Downgrade is best-effort only: it recreates the
districts table and re-links rows whose slug is registered (slug id is
regenerated, so historical IDs are not preserved).
"""

import re
import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "e5c2a1f83b04"
down_revision: str | Sequence[str] | None = "8a1f4c02b9d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _slugify(name: str) -> str:
    """Slugify a district display name the same way the config slugs do
    (e.g. 'BV Friedrichshain-Kreuzberg' -> 'bv-friedrichshain-kreuzberg')."""
    text = unicodedata.normalize("NFKD", name)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text


def upgrade() -> None:
    # 1. Add nullable slug columns.
    op.add_column("campaigns", sa.Column("district_slug", sa.String(length=255), nullable=True))
    op.add_column("initiatives", sa.Column("district_slug", sa.String(length=255), nullable=True))

    # 2. Backfill from the legacy districts table while it still exists,
    #    using the same slugify rules that produced the config slugs.
    conn = op.get_bind()
    district_slugs = {
        row[0]: _slugify(row[1])
        for row in conn.execute(sa.text("SELECT id, name FROM districts")).all()
    }
    for district_id, slug in district_slugs.items():
        conn.execute(
            sa.text("UPDATE campaigns SET district_slug = :slug WHERE district_id = :id"),
            {"slug": slug, "id": district_id},
        )
        conn.execute(
            sa.text("UPDATE initiatives SET district_slug = :slug WHERE district_id = :id"),
            {"slug": slug, "id": district_id},
        )

    # 3. Tighten to NOT NULL and index.
    op.alter_column("campaigns", "district_slug", nullable=False)
    op.alter_column("initiatives", "district_slug", nullable=False)
    op.create_index("ix_campaigns_district_slug", "campaigns", ["district_slug"])
    op.create_index("ix_initiatives_district_slug", "initiatives", ["district_slug"])

    # 4. Drop the FK'd district_id columns and the legacy table.
    op.drop_constraint("campaigns_district_id_fkey", "campaigns", type_="foreignkey")
    op.drop_column("campaigns", "district_id")
    op.drop_constraint("initiatives_district_id_fkey", "initiatives", type_="foreignkey")
    op.drop_column("initiatives", "district_id")
    op.drop_table("districts")


def downgrade() -> None:
    # Best-effort: recreate districts from registered config slugs is not
    # possible here (no config access); recreate the table shape and re-link
    # rows whose district_slug can be re-registered as a name.
    op.create_table(
        "districts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("districts.id", ondelete="CASCADE"), nullable=True),
    )
    op.add_column(
        "campaigns", sa.Column("district_id", UUID(as_uuid=True), sa.ForeignKey("districts.id", ondelete="RESTRICT"), nullable=True)
    )
    op.add_column(
        "initiatives", sa.Column("district_id", UUID(as_uuid=True), sa.ForeignKey("districts.id", ondelete="RESTRICT"), nullable=True)
    )

    conn = op.get_bind()
    # Re-register each distinct slug as a district whose name is the slug.
    conn.execute(
        sa.text(
            """
            INSERT INTO districts (id, name)
            SELECT gen_random_uuid(), slug
            FROM (SELECT DISTINCT district_slug AS slug FROM campaigns
                  UNION SELECT DISTINCT district_slug FROM initiatives) s
            WHERE slug IS NOT NULL
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE campaigns c SET district_id = d.id FROM districts d WHERE d.name = c.district_slug
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE initiatives i SET district_id = d.id FROM districts d WHERE d.name = i.district_slug
            """
        )
    )
    op.drop_index("ix_campaigns_district_slug", table_name="campaigns")
    op.drop_index("ix_initiatives_district_slug", table_name="initiatives")
    op.drop_column("campaigns", "district_slug")
    op.drop_column("initiatives", "district_slug")
