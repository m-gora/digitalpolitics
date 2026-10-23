"""Rescore every initiative's domain/narrative similarity with TypeSafe.

Run with: uv run python -m dpp.campaign.backfill_coherence
"""

import asyncio
import logging

from sqlalchemy import select

from dpp.campaign import coherence
from dpp.campaign.models import Initiative
from dpp.config import get_settings
from dpp.db import async_session_factory

logger = logging.getLogger(__name__)


async def backfill_coherence() -> tuple[int, int]:
    if not get_settings().typesafe_api_key:
        raise RuntimeError("Configure TYPESAFE_API_KEY before backfilling initiative coherence.")

    async with async_session_factory() as session:
        result = await session.execute(select(Initiative.id))
        initiative_ids = list(result.scalars())

    updated = 0
    skipped = 0
    for initiative_id in initiative_ids:
        async with async_session_factory() as session:
            initiative = await session.get(Initiative, initiative_id)
            if initiative is not None and await coherence.recompute_and_publish(session, initiative):
                updated += 1
            else:
                skipped += 1

    return updated, skipped


async def main() -> None:
    updated, skipped = await backfill_coherence()
    print(f"Initiative coherence backfill complete: {updated} scored, {skipped} skipped.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
