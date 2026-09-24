"""Initiative coherence score: embedding generation + similarity math + the
recompute orchestration. See canv-01.

Uses the OpenAI embeddings API for narrative embeddings. This is a
deliberate, scoped exception to arch-04's privacy-by-design principle: only
the narrative canvas fields (Thema, Ziel, Storytelling) are sent to a third
party, solely to compute a heuristic coherence score. See adr-04.
"""

import datetime as dt
import logging
import math

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from dpp.campaign import events, membership
from dpp.campaign.models import Campaign, Initiative
from dpp.config import get_settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI | None:
    global _client
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


def narrative_text(campaign: Campaign) -> str:
    parts = [campaign.thema, campaign.ziel, campaign.storytelling]
    return "\n".join(p for p in parts if p)


async def embed_text(text: str) -> list[float] | None:
    client = _get_client()
    if client is None:
        logger.warning("OPENAI_API_KEY not configured; skipping embedding generation.")
        return None
    settings = get_settings()
    response = await client.embeddings.create(model=settings.embedding_model, input=text)
    return response.data[0].embedding


async def update_campaign_embedding(campaign: Campaign) -> bool:
    """Recompute campaign.narrative_embedding. Returns True if it changed."""
    text = narrative_text(campaign)
    if not text:
        changed = campaign.narrative_embedding is not None
        campaign.narrative_embedding = None
        return changed
    embedding = await embed_text(text)
    if embedding is None:
        return False
    campaign.narrative_embedding = embedding
    return True


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def average_pairwise_similarity(vectors: list[list[float]]) -> float | None:
    """Average cosine similarity across all pairs. None if fewer than 2 vectors."""
    if len(vectors) < 2:
        return None
    total = 0.0
    count = 0
    for i in range(len(vectors)):
        for j in range(i + 1, len(vectors)):
            total += cosine_similarity(vectors[i], vectors[j])
            count += 1
    return total / count if count else None


async def recompute_coherence(session: AsyncSession, initiative: Initiative) -> float | None:
    """Recompute the AI-assisted coherence score for an initiative (canv-01).

    A heuristic estimate: the average pairwise cosine similarity of member
    campaigns' narrative embeddings. None if fewer than 2 members have an
    embedding yet.
    """
    members = await membership.get_member_campaigns(session, initiative.id)
    vectors = [m.narrative_embedding for m in members if m.narrative_embedding is not None]
    score = average_pairwise_similarity(vectors)  # type: ignore[arg-type]

    initiative.coherence_score = score
    initiative.coherence_computed_at = dt.datetime.now(dt.UTC)

    await events.publish_coherence_updated(str(initiative.id), score)
    return score
