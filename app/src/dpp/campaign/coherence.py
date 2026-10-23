"""Initiative domain/narrative similarity: TypeSafe rubric scoring + recompute orchestration.
See canv-01 and adr-06.
"""

import datetime as dt
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from typesafe_sdk import AsyncTypeSafeClient, Choice, Score

from dpp.campaign import events, membership
from dpp.campaign.models import Campaign, Initiative
from dpp.config import get_settings

logger = logging.getLogger(__name__)

NO_OUTLIER = "none_clear"
MIN_MEMBERS_FOR_SCORE = 2
MIN_MEMBERS_FOR_OUTLIER = 3

DOMAIN_LEVELS = [
    {
        "what": "The campaign Thema statements concern unrelated subjects, with almost no shared domain.",
        "examples": ["one campaign is about heat safety and another about parking capacity"],
    },
    {
        "what": "Only a broad political setting overlaps; the campaign subjects are mostly different.",
        "examples": ["several urban issues with no clear common subject"],
    },
    {
        "what": "Some subject matter is shared, but significant differences in campaign topics remain.",
        "examples": ["partly overlapping policy areas"],
    },
    {
        "what": "The campaigns share a clear subject domain, though they focus on different aspects of it.",
        "examples": ["cooling centers and shade as parts of neighborhood heat protection"],
    },
    {
        "what": "The Thema statements describe a tightly shared subject domain with only narrow variations.",
        "examples": ["multiple campaigns focused on neighborhood heat protection"],
    },
]

NARRATIVE_LEVELS = [
    {
        "what": "Campaign goals or stories conflict with the initiative or point in unrelated directions.",
        "examples": ["one campaign rejects the shared purpose"],
    },
    {
        "what": "The connection to the initiative is weak; goals or stories largely diverge.",
        "examples": ["only a vague shared political setting"],
    },
    {
        "what": "Some goals support the initiative, but the group has substantial narrative divergence.",
        "examples": ["partial alignment with at least one unclear or competing goal"],
    },
    {
        "what": "Campaign goals and stories generally reinforce the initiative, with differences in emphasis.",
        "examples": ["distinct contributions to a shared objective"],
    },
    {
        "what": "Goals and stories strongly reinforce a specific shared purpose within the initiative.",
        "examples": ["all campaigns clearly advance a coherent common objective"],
    },
]


@dataclass(frozen=True)
class CoherenceResult:
    """Scores are normalized to 0-1; None means the dimension is unavailable."""

    domain_score: float | None = None
    narrative_score: float | None = None
    outlier_campaign_id: uuid.UUID | None = None


def _clean(value: str | None) -> str:
    return (value or "").strip()


def has_domain_text(campaign: Campaign) -> bool:
    return bool(_clean(campaign.thema))


def has_narrative_text(campaign: Campaign) -> bool:
    return bool(_clean(campaign.ziel) or _clean(campaign.storytelling))


def _campaign_labels(campaigns: list[Campaign]) -> dict[str, Campaign]:
    return {f"C{index}": campaign for index, campaign in enumerate(campaigns, start=1)}


def typesafe_state(initiative: Initiative, labeled: dict[str, Campaign]) -> dict[str, Any]:
    """Only the Thema, Ziel and Storytelling text leaves the app (adr-04)."""
    return {
        "initiative": {"name": initiative.name, "description": _clean(initiative.description)},
        "campaigns": [
            {
                "id": label,
                "thema": _clean(campaign.thema),
                "ziel": _clean(campaign.ziel),
                "storytelling": _clean(campaign.storytelling),
            }
            for label, campaign in labeled.items()
        ],
    }


def build_questions(labeled: dict[str, Campaign], *, domain: bool, narrative: bool, outlier: bool) -> dict:
    questions: dict[str, Score | Choice] = {}
    if domain:
        questions["domain_similarity"] = Score(
            instructions=(
                "How similar in subject matter are the member campaigns? Compare only the "
                "campaign `thema` values in `campaigns` and ignore campaigns whose `thema` is "
                "empty. Use `initiative.description` only as context for the domain; ignore "
                "campaign goals and narratives."
            ),
            criteria=DOMAIN_LEVELS,
        )
    if narrative:
        questions["narrative_similarity"] = Score(
            instructions=(
                "How coherently do the member campaigns' goals and stories work together toward "
                "`initiative.description`? Evaluate only each campaign's `ziel` and `storytelling`, "
                "ignoring empty values and `thema`. Consider whether the group advances a "
                "coherent shared purpose."
            ),
            criteria=NARRATIVE_LEVELS,
        )
    if outlier:
        questions["initiative_outlier"] = _outlier_question(labeled)
    return questions


def _outlier_question(labeled: dict[str, Campaign]) -> Choice:
    criteria: dict[str, dict[str, Any]] = {}
    for index, label in enumerate(labeled):
        criteria[label] = {
            "what": (
                f"Campaign {label} (state entry `campaigns[{index}]`) is the clearest "
                "relative outlier in how well the initiative's members cohere."
            ),
            "inspect": [
                f"`campaigns[{index}].thema`",
                f"`campaigns[{index}].ziel`",
                f"`campaigns[{index}].storytelling`",
            ],
            "not_for": (
                "Choosing a campaign just because it has a different but complementary focus. "
                "It should be clearly less coherent overall than the other members."
            ),
        }
    criteria[NO_OUTLIER] = {
        "what": "No single campaign is clearly less coherent than the others in this initiative.",
        "inspect": "`campaigns`",
        "not_for": "Forcing an outlier when the campaigns are comparably coherent.",
    }
    return Choice(
        instructions=(
            "Which campaign, if any, is the clearest relative outlier in this initiative? "
            "Compare members using only their `thema` for domain and their `ziel` plus "
            "`storytelling` for narrative alignment to `initiative.description`. Prefer "
            f"`{NO_OUTLIER}` when a campaign's different focus is complementary or no single "
            "campaign is clearly less coherent overall. This is a relative human-review "
            "candidate, not a judgment that the campaign is bad."
        ),
        criteria=criteria,
    )


def _normalized(score: float, levels: list[dict]) -> float:
    return min(max(score / (len(levels) - 1), 0.0), 1.0)


async def _ask_typesafe(state: dict[str, Any], questions: dict) -> Any | None:
    settings = get_settings()
    if not settings.typesafe_api_key:
        logger.warning("TYPESAFE_API_KEY not configured; initiative coherence scoring is disabled.")
        return None
    try:
        async with AsyncTypeSafeClient(api_key=settings.typesafe_api_key, model=settings.typesafe_model) as client:
            return await client.system_one(state=state, questions=questions)
    except Exception:
        logger.exception("Could not score initiative coherence with TypeSafe.")
        return None


async def score_initiative(initiative: Initiative, members: list[Campaign]) -> CoherenceResult | None:
    """Score one initiative. Returns None if TypeSafe is unavailable or fails, so
    callers keep the previously stored values.
    """
    campaigns = sorted(
        (m for m in members if has_domain_text(m) or has_narrative_text(m)),
        key=lambda m: str(m.id),
    )
    domain = sum(has_domain_text(m) for m in campaigns) >= MIN_MEMBERS_FOR_SCORE
    narrative = sum(has_narrative_text(m) for m in campaigns) >= MIN_MEMBERS_FOR_SCORE
    outlier = len(campaigns) >= MIN_MEMBERS_FOR_OUTLIER and (domain or narrative)
    if not (domain or narrative):
        return CoherenceResult()

    labeled = _campaign_labels(campaigns)
    response = await _ask_typesafe(
        typesafe_state(initiative, labeled),
        build_questions(labeled, domain=domain, narrative=narrative, outlier=outlier),
    )
    if response is None:
        return None

    try:
        domain_score = (
            _normalized(response.scores["domain_similarity"].score, DOMAIN_LEVELS) if domain else None
        )
        narrative_score = (
            _normalized(response.scores["narrative_similarity"].score, NARRATIVE_LEVELS) if narrative else None
        )
        outlier_campaign = (
            labeled.get(response.choices["initiative_outlier"].choice) if outlier else None
        )
    except (KeyError, AttributeError):
        logger.exception("Unexpected TypeSafe response for initiative coherence.")
        return None

    return CoherenceResult(
        domain_score=domain_score,
        narrative_score=narrative_score,
        outlier_campaign_id=outlier_campaign.id if outlier_campaign else None,
    )


async def recompute_coherence(session: AsyncSession, initiative: Initiative) -> bool:
    """Recompute domain/narrative scores and the outlier candidate (canv-01).
    Returns True if the stored values were refreshed; the caller commits.
    """
    members = await membership.get_member_campaigns(session, initiative.id)
    result = await score_initiative(initiative, members)
    if result is None:
        return False

    initiative.domain_similarity_score = result.domain_score
    initiative.narrative_similarity_score = result.narrative_score
    initiative.outlier_campaign_id = result.outlier_campaign_id
    initiative.coherence_computed_at = dt.datetime.now(dt.UTC)
    return True


async def recompute_and_publish(session: AsyncSession, initiative: Initiative) -> bool:
    """Recompute, commit, then notify SSE subscribers so they re-read committed data."""
    if not await recompute_coherence(session, initiative):
        return False
    await session.commit()
    await events.publish_coherence_updated(
        str(initiative.id),
        initiative.domain_similarity_score,
        initiative.narrative_similarity_score,
        initiative.outlier_campaign_id,
    )
    return True
