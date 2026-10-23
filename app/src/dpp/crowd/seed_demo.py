"""Create a running demo campaign, questionnaire and sample GPS responses.

Run with: uv run python -m dpp.crowd.seed_demo
Safe to rerun: existing sample responses are preserved.
"""
import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta

from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from dpp.campaign.models import Campaign, CampaignStatus, District
from dpp.crowd.models import Question, Questionnaire, QuestionnaireStatus, Response
from dpp.db import async_session_factory


async def seed_demo() -> None:
    async with async_session_factory() as session:
        district = await session.scalar(select(District).where(District.name == "BV Friedrichshain-Kreuzberg"))
        if district is None:
            district = District(name="BV Friedrichshain-Kreuzberg")
            session.add(district)
            await session.flush()
        campaign = await session.scalar(select(Campaign).where(Campaign.thema == "Kiezgrün – Demo Crowdsourcing"))
        if campaign is None:
            campaign = Campaign(
                district_id=district.id,
                status=CampaignStatus.RUNNING,
                created_by="demo",
                thema="Kiezgrün – Demo Crowdsourcing",
                ziel="Rückmeldungen zu Grünflächen im Kiez sammeln.",
                data_harvest="Befragungsdaten ohne direkte Identifikatoren; Aufbewahrungsdauer vor Livebetrieb prüfen.",
            )
            session.add(campaign)
            await session.flush()
        else:
            campaign.status = CampaignStatus.RUNNING
        q = await session.scalar(
            select(Questionnaire).options(selectinload(Questionnaire.questions))
            .where(Questionnaire.title == "Grün im Kiez? (Demo)", Questionnaire.created_by == "demo")
        )
        if q is None:
            q = Questionnaire(
                title="Grün im Kiez? (Demo)",
                intro="Was sollte sich bei den Grünflächen in deinem Kiez ändern?",
                status=QuestionnaireStatus.ACTIVE,
                created_by="demo",
                campaign_id=campaign.id,
                collection_started_at=datetime.now(UTC) - timedelta(days=30),
                questions=[
                    Question(position=1, prompt="Was fehlt dir an den Grünflächen?", question_type="text", required=True, options=[]),
                    Question(
                        position=2,
                        prompt="Wie häufig nutzt du einen Park im Kiez?",
                        question_type="single_choice",
                        required=True,
                        options=[
                            {"id": "often", "label": "Mehrmals pro Woche"},
                            {"id": "sometimes", "label": "Etwa einmal pro Woche"},
                            {"id": "rarely", "label": "Seltener"},
                        ],
                    ),
                ],
            )
            session.add(q)
            await session.flush()
        count = await session.scalar(select(Response.id).where(Response.questionnaire_id == q.id).limit(1))
        if count is None:
            rng = random.Random(20261022)
            text_answers = [
                "Mehr Sitzgelegenheiten im Schatten.",
                "Ein Trinkbrunnen wäre hilfreich.",
                "Mehr Platz für Kinder zum Spielen.",
                "Die Wege sollten barriereärmer werden.",
                "Mehr Bäume gegen die Sommerhitze.",
            ]
            options = [option["id"] for option in q.questions[1].options]
            now = datetime.now(UTC)
            records = []
            for i in range(180):
                lat = 52.49 + rng.random() * 0.07
                lon = 13.36 + rng.random() * 0.09
                captured = now - timedelta(days=rng.randrange(0, 28), minutes=rng.randrange(0, 1440))
                records.append(
                    Response(
                        questionnaire_id=q.id,
                        client_id=uuid.uuid5(uuid.NAMESPACE_URL, f"crowd-demo-{i}"),
                        location=WKTElement(f"POINT({round(lon,4)} {round(lat,4)})", srid=4326),
                        accuracy_m=float(rng.randrange(6, 45)),
                        captured_at=captured,
                        answers={
                            str(q.questions[0].id): {"text": rng.choice(text_answers), "options": [], "via_voice": False},
                            str(q.questions[1].id): {"text": None, "options": [rng.choice(options)], "via_voice": False},
                        },
                    )
                )
            session.add_all(records)
        await session.commit()
        print(f"Demo questionnaire ready: /crowd/r/{q.token}")


if __name__ == "__main__":
    asyncio.run(seed_demo())
