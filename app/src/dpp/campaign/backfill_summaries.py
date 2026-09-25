"""One-time backfill for summaries of complete campaigns created before the
summary feature was enabled.

Run with: uv run python -m dpp.campaign.backfill_summaries
"""

import argparse
import asyncio
import logging

from sqlalchemy import or_, select

from dpp.ai import get_ai_provider
from dpp.campaign.models import Campaign
from dpp.campaign.summary import update_campaign_summary
from dpp.db import async_session_factory

logger = logging.getLogger(__name__)


async def backfill_summaries(force: bool = False) -> tuple[int, int]:
    if get_ai_provider() is None:
        raise RuntimeError("Configure the selected AI provider and API key before backfilling campaign summaries.")

    async with async_session_factory() as session:
        summary_needs_update = or_(
            Campaign.ai_summary.is_(None),
            Campaign.ai_summary.endswith("…"),
            Campaign.ai_summary.endswith("..."),
        )
        query = select(Campaign.id)
        if not force:
            query = query.where(summary_needs_update)
        result = await session.execute(query)
        candidate_ids = list(result.scalars())

    updated = 0
    skipped = 0
    for campaign_id in candidate_ids:
        async with async_session_factory() as session:
            campaign = await session.get(Campaign, campaign_id)
            if campaign is None or not campaign.canvas_complete:
                skipped += 1
                continue
            if await update_campaign_summary(campaign):
                await session.commit()
                updated += 1
            else:
                skipped += 1
                await session.rollback()

    return updated, skipped


async def main(force: bool = False) -> None:
    updated, skipped = await backfill_summaries(force=force)
    print(f"Campaign summary backfill complete: {updated} generated, {skipped} skipped.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Backfill campaign summaries")
    parser.add_argument("--force", action="store_true", help="regenerate every complete campaign summary")
    args = parser.parse_args()
    asyncio.run(main(force=args.force))
