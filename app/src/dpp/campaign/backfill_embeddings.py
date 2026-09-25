"""Backfill missing campaign narrative embeddings and initiative scores.

Run with: uv run python -m dpp.campaign.backfill_embeddings
"""

import argparse
import asyncio
import logging

from sqlalchemy import and_, or_, select

from dpp.ai import get_ai_provider
from dpp.campaign import coherence, membership
from dpp.campaign.models import Campaign
from dpp.db import async_session_factory

logger = logging.getLogger(__name__)


async def backfill_embeddings(force: bool = False) -> tuple[int, int]:
    if get_ai_provider() is None:
        raise RuntimeError("Configure the selected AI provider and API key before backfilling embeddings.")

    query = select(Campaign.id)
    if not force:
        query = query.where(
            or_(
                and_(Campaign.domain_embedding.is_(None), Campaign.thema.is_not(None)),
                and_(
                    Campaign.narrative_embedding.is_(None),
                    or_(Campaign.ziel.is_not(None), Campaign.storytelling.is_not(None)),
                ),
            )
        )

    async with async_session_factory() as session:
        result = await session.execute(query)
        campaign_ids = list(result.scalars())

    updated = 0
    skipped = 0
    for campaign_id in campaign_ids:
        async with async_session_factory() as session:
            campaign = await session.get(Campaign, campaign_id)
            if campaign is None:
                skipped += 1
                continue

            changed = await coherence.update_campaign_embeddings(campaign)
            if not changed:
                skipped += 1
                await session.rollback()
                continue

            await session.flush()
            initiatives = await membership.initiatives_for_campaign(session, campaign.id)
            for initiative in initiatives:
                await coherence.recompute_coherence(session, initiative)
            await session.commit()
            updated += 1

    return updated, skipped


async def main(force: bool = False) -> None:
    updated, skipped = await backfill_embeddings(force=force)
    print(f"Campaign embedding backfill complete: {updated} generated, {skipped} skipped.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Backfill campaign domain and narrative embeddings")
    parser.add_argument("--force", action="store_true", help="regenerate every campaign embedding")
    args = parser.parse_args()
    asyncio.run(main(force=args.force))
