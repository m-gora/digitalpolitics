"""The campaign module's SSE channel and event names. See arch-03/canv-01..05.

Uses the generic pub-sub mechanism from dpp.sse. If a future module needs
SSE too, it gets its own Channel instance here (arch-03: "SSE channels are
scoped by modules").
"""

import uuid

from dpp.sse import Channel

canvas_channel = Channel()


async def publish_field_updated(campaign_id: str, field_name: str) -> None:
    await canvas_channel.publish("campaign.field_updated", {"campaign_id": campaign_id, "field": field_name})


async def publish_status_changed(campaign_id: str, status: str) -> None:
    await canvas_channel.publish("campaign.status_changed", {"campaign_id": campaign_id, "status": status})


async def publish_summary_updated(campaign_id: str) -> None:
    await canvas_channel.publish("campaign.summary_updated", {"campaign_id": campaign_id})


async def publish_coherence_updated(
    initiative_id: str,
    domain_score: float | None,
    narrative_score: float | None,
    outlier_campaign_id: uuid.UUID | None = None,
) -> None:
    await canvas_channel.publish(
        "initiative.coherence_updated",
        {
            "initiative_id": initiative_id,
            "domain_similarity_score": domain_score,
            "narrative_similarity_score": narrative_score,
            "outlier_campaign_id": str(outlier_campaign_id) if outlier_campaign_id else None,
        },
    )
