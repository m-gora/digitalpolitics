"""Seed example campaign data for demoing the prototype.

Run with: uv run python -m dpp.seed
Idempotent: does nothing if the "Bauen und Wohnen" initiative already exists.
Districts come from the Gliederung config (dpp.gliederungen), not the database.
"""

import asyncio

from sqlalchemy import select

from dpp.campaign import coherence
from dpp.campaign.models import (
    Campaign,
    CampaignStatus,
    Initiative,
    InitiativeCampaign,
    Retrospective,
)
from dpp.config import get_settings
from dpp.db import async_session_factory

# Gliederung slugs — must exist in config/gliederungen.yaml (arch-02).
BV_FK = "bv-friedrichshain-kreuzberg"
OV_KREUZBERG = "ov-kreuzberg"
OV_WEDDING = "ov-wedding"


async def seed() -> None:
    async with async_session_factory() as session:
        existing = await session.execute(select(Initiative).where(Initiative.name == "Bauen und Wohnen"))
        if existing.scalar_one_or_none() is not None:
            print("Seed data already present, skipping.")
            return

        # Two campaigns clustered into a district-anchored initiative (canv-01:
        # membership may include campaigns from the anchor and descendants).
        mietendeckel = Campaign(
            district_slug=BV_FK,
            status=CampaignStatus.DRAFT,
            created_by="jonas",
            created_by_name="Jonas Krüger",
            thema="Mietendeckel für Friedrichshain-Kreuzberg",
            ziel="Politisch: Verlängerung des Mietendeckels durchsetzen. "
            "Kommunikativ: Mieter:innen über ihre Rechte aufklären.",
            zielgruppen="Mieter:innen in Altbaubeständen, junge Familien",
            kanaele="Infostände, Mieterberatung, soziale Medien",
            momentum="Mieterverein, lokale Wohnungsbaugenossenschaften",
            motiv="Steigende Mieten bedrohen die soziale Durchmischung des Kiezes",
        )
        leerstand = Campaign(
            district_slug=BV_FK,
            status=CampaignStatus.DRAFT,
            created_by="jonas",
            created_by_name="Jonas Krüger",
            thema="Leerstand melden Kampagne",
            ziel="Politisch: Leerstehende Wohnungen dem Markt zuführen. "
            "Kommunikativ: Meldeverfahren bekannt machen.",
            zielgruppen="Nachbarschaften mit auffälligem Leerstand",
            kanaele="Nachbarschaftstreffen, Flyer, Bezirksamt-Kooperation",
            momentum="Nachbarschaftsinitiativen, Mieterverein",
            motiv="Wohnraum ist knapp, Leerstand ist ein sichtbares Ärgernis",
        )
        gruenflaechen = Campaign(
            district_slug=OV_KREUZBERG,
            status=CampaignStatus.DRAFT,
            created_by="mira",
            created_by_name="Mira Noll",
            thema="Mehr Grünflächen in Kreuzberg",
            ziel="Politisch: Neue Grünflächen im Bezirk verankern.",
        )
        kiezfest = Campaign(
            district_slug=OV_WEDDING,
            status=CampaignStatus.FINISHED,
            created_by="peter",
            created_by_name="Peter Sailer",
            thema="Kiezfest Wedding",
            ziel="Politisch: Sichtbarkeit im Kiez erhöhen. Kommunikativ: Nahbarkeit zeigen.",
            zielgruppen="Anwohner:innen aller Altersgruppen",
            kanaele="Vor-Ort-Fest, Plakate, lokale Presse",
            momentum="Kiezinitiativen, lokale Vereine",
            motiv="Direkter Kontakt zu Bürger:innen abseits von Wahlkampfzeiten",
            service="Infostand, Kinderprogramm, Getränke",
            data_harvest="Kontaktdaten für Newsletter (freiwillig, opt-in)",
            tools="Newsletter-Tool, Kontaktbogen",
            phasen_flow="Ankündigung -> Fest -> Nachbericht mit Fotos",
            storytelling="Der Kiez feiert sich selbst",
        )

        session.add_all([mietendeckel, leerstand, gruenflaechen, kiezfest])
        await session.flush()

        kiezfest.retrospective = Retrospective(
            campaign_id=kiezfest.id,
            zielerreichung="Gut besucht (ca. 300 Gäste), Ziel der Sichtbarkeit erreicht.",
            was_lief_gut="Wetter, Ehrenamtliche, Kinderprogramm",
            was_lief_schlecht="Newsletter-Anmeldungen blieben hinter den Erwartungen zurück",
            handlungsempfehlungen="Nächstes Mal QR-Code-Anmeldung direkt am Stand anbieten",
        )
        session.add(kiezfest.retrospective)

        bauen_wohnen = Initiative(
            district_slug=BV_FK,
            name="Bauen und Wohnen",
            description="Bündelung aller wohnungspolitischen Kampagnen in Friedrichshain-Kreuzberg.",
        )
        session.add(bauen_wohnen)
        await session.flush()

        session.add_all(
            [
                InitiativeCampaign(initiative_id=bauen_wohnen.id, campaign_id=mietendeckel.id),
                InitiativeCampaign(initiative_id=bauen_wohnen.id, campaign_id=leerstand.id),
            ]
        )

        await session.commit()
        print("Seed data created.")
        print("Dev personas (see /_dev/impersonate): Anna Berg (LV Berlin), Jonas Krüger (BV F-K),")
        print("Mira Noll (OV Kreuzberg), Peter Sailer (BV Mitte).")

        # Score the demo initiative right away (canv-01), so the coherence
        # widget isn't empty until the first edit triggers a recompute.
        # Best effort: without TYPESAFE_API_KEY the app scores on first edit.
        if get_settings().typesafe_api_key:
            initiative = await session.get(Initiative, bauen_wohnen.id)
            if await coherence.recompute_and_publish(session, initiative):
                print("Initiative coherence scored.")
        else:
            print("TYPESAFE_API_KEY not set; coherence scores appear after the first edit")
            print("(or run: python -m dpp.campaign.backfill_coherence).")


if __name__ == "__main__":
    asyncio.run(seed())
