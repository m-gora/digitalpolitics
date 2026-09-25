"""Initiative domain/narrative similarity: embedding generation + similarity math + the
recompute orchestration. See canv-01 and the provider decision in adr-05.
"""

import datetime as dt
import logging
import math
import uuid
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from dpp.ai import get_ai_provider
from dpp.campaign import events, membership
from dpp.campaign.models import Campaign, Initiative

logger = logging.getLogger(__name__)

def domain_text(campaign: Campaign) -> str:
    return (campaign.thema or "").strip()


def narrative_text(campaign: Campaign) -> str:
    parts = [
        f"Ziel: {campaign.ziel.strip()}" if campaign.ziel and campaign.ziel.strip() else "",
        (
            f"Storytelling: {campaign.storytelling.strip()}"
            if campaign.storytelling and campaign.storytelling.strip()
            else ""
        ),
    ]
    return "\n".join(part for part in parts if part)


async def embed_text(text: str) -> list[float] | None:
    provider = get_ai_provider()
    if provider is None:
        return None
    try:
        return await provider.embed(text)
    except Exception:
        logger.exception("Could not generate campaign similarity embedding.")
        return None


async def update_campaign_embeddings(campaign: Campaign) -> bool:
    """Refresh domain and narrative vectors. Returns True if either changed."""
    changed = False
    for attribute, text in (
        ("domain_embedding", domain_text(campaign)),
        ("narrative_embedding", narrative_text(campaign)),
    ):
        current = getattr(campaign, attribute)
        if not text:
            if current is not None:
                setattr(campaign, attribute, None)
                changed = True
            continue

        embedding = await embed_text(text)
        if embedding is not None:
            setattr(campaign, attribute, embedding)
            changed = True
    return changed


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


def campaign_similarity_to_peers(
    campaigns: list[Campaign], dimension: Literal["domain", "narrative"]
) -> dict[uuid.UUID, float]:
    """Return each campaign's mean similarity to peers for one dimension."""
    attribute = f"{dimension}_embedding"
    embedded_campaigns: list[tuple[Campaign, list[float]]] = []
    for campaign in campaigns:
        vector = getattr(campaign, attribute)
        if vector is not None:
            embedded_campaigns.append((campaign, vector))
    if len(embedded_campaigns) < 2:
        return {}

    scores: dict[uuid.UUID, float] = {}
    for campaign, vector in embedded_campaigns:
        peer_similarities = [
            cosine_similarity(vector, peer_vector)
            for peer_campaign, peer_vector in embedded_campaigns
            if peer_campaign.id != campaign.id
        ]
        scores[campaign.id] = sum(peer_similarities) / len(peer_similarities)
    return scores


async def recompute_coherence(session: AsyncSession, initiative: Initiative) -> float | None:
    """Recompute separate domain and narrative similarity scores (canv-01)."""
    members = await membership.get_member_campaigns(session, initiative.id)
    domain_vectors = [m.domain_embedding for m in members if m.domain_embedding is not None]
    narrative_vectors = [m.narrative_embedding for m in members if m.narrative_embedding is not None]
    domain_score = average_pairwise_similarity(domain_vectors)  # type: ignore[arg-type]
    narrative_score = average_pairwise_similarity(narrative_vectors)  # type: ignore[arg-type]

    initiative.domain_similarity_score = domain_score
    initiative.narrative_similarity_score = narrative_score
    initiative.coherence_computed_at = dt.datetime.now(dt.UTC)

    await events.publish_coherence_updated(str(initiative.id), domain_score, narrative_score)
    return narrative_score
