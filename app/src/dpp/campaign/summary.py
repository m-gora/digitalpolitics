"""AI-generated campaign summaries for quick scanning in the campaign list."""

import datetime as dt
import logging

from dpp.ai import get_ai_provider
from dpp.campaign.models import Campaign

logger = logging.getLogger(__name__)

SUMMARY_FIELDS = (
    ("thema", "Thema"),
    ("ziel", "Ziel"),
    ("zielgruppen", "Zielgruppen"),
    ("kanaele", "Kanäle"),
    ("momentum", "Momentum"),
    ("motiv", "Motiv"),
    ("service", "Service"),
    ("tools", "Tools"),
    ("phasen_flow", "Phasen & Flow"),
    ("storytelling", "Storytelling"),
)


def build_summary_prompt(campaign: Campaign) -> str:
    """Create a German short-summary prompt, deliberately excluding Data Harvest."""
    campaign_details = "\n".join(
        f"{label}: {getattr(campaign, field)}" for field, label in SUMMARY_FIELDS if getattr(campaign, field)
    )
    return (
        "Fasse die folgende politische Kampagne auf Deutsch in genau einem kurzen, vollständigen Satz mit "
        "höchstens 20 Wörtern zusammen. Bündele Thema, Ziel und den wichtigsten Ansatz, statt jedes Feld "
        "einzeln aufzuzählen. "
        "Nutze ausschließlich die angegebenen Informationen; ergänze oder erfinde keine Fakten. "
        "Beende den Satz mit einem passenden Satzzeichen und verwende keine Auslassungspunkte. "
        "Gib nur die Zusammenfassung aus.\n\n"
        f"{campaign_details}"
    )


async def update_campaign_summary(campaign: Campaign) -> bool:
    """Generate and store a summary when the complete canvas has changed."""
    if not campaign.canvas_complete:
        return False

    provider = get_ai_provider()
    if provider is None:
        return False

    try:
        summary = await provider.generate_text(build_summary_prompt(campaign))
    except Exception:
        logger.exception("Could not generate summary for campaign %s.", campaign.id)
        return False

    if not summary:
        return False

    campaign.ai_summary = " ".join(summary.split())
    campaign.ai_summary_generated_at = dt.datetime.now(dt.UTC)
    return True
