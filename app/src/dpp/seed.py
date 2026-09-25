"""Seed example hierarchy + campaign data for demoing the prototype.

Run with: uv run python -m dpp.seed
Idempotent: does nothing if "LV Berlin" already exists.
"""

import asyncio

from sqlalchemy import select

from dpp.campaign.models import (
    Campaign,
    CampaignStatus,
    District,
    Initiative,
    InitiativeCampaign,
    Retrospective,
)
from dpp.db import async_session_factory


async def seed() -> None:
    async with async_session_factory() as session:
        existing = await session.execute(select(District).where(District.name == "LV Berlin"))
        if existing.scalar_one_or_none() is not None:
            print("Seed data already present, skipping.")
            return

        lv_berlin = District(name="LV Berlin")
        bv_fk = District(name="BV Friedrichshain-Kreuzberg", parent=lv_berlin)
        bv_mitte = District(name="BV Mitte", parent=lv_berlin)
        ov_kreuzberg = District(name="OV Kreuzberg", parent=bv_fk)
        ov_friedrichshain = District(name="OV Friedrichshain", parent=bv_fk)
        ov_wedding = District(name="OV Wedding", parent=bv_mitte)

        session.add_all([lv_berlin, bv_fk, bv_mitte, ov_kreuzberg, ov_friedrichshain, ov_wedding])
        await session.flush()

        # Two campaigns clustered into a district-anchored initiative (canv-01:
        # membership may include campaigns from the anchor and descendants).
        mietendeckel = Campaign(
            district_id=bv_fk.id,
            status=CampaignStatus.DRAFT,
            thema="Mietendeckel für Friedrichshain-Kreuzberg",
            ziel="Politisch: Verlängerung des Mietendeckels durchsetzen. "
            "Kommunikativ: Mieter:innen über ihre Rechte aufklären.",
            zielgruppen="Mieter:innen in Altbaubeständen, junge Familien",
            kanaele="Infostände, Mieterberatung, soziale Medien",
            momentum="Mieterverein, lokale Wohnungsbaugenossenschaften",
            motiv="Steigende Mieten bedrohen die soziale Durchmischung des Kiezes",
        )
        leerstand = Campaign(
            district_id=bv_fk.id,
            status=CampaignStatus.DRAFT,
            thema="Leerstand melden Kampagne",
            ziel="Politisch: Leerstehende Wohnungen dem Markt zuführen. "
            "Kommunikativ: Meldeverfahren bekannt machen.",
            zielgruppen="Nachbarschaften mit auffälligem Leerstand",
            kanaele="Nachbarschaftstreffen, Flyer, Bezirksamt-Kooperation",
            momentum="Nachbarschaftsinitiativen, Mieterverein",
            motiv="Wohnraum ist knapp, Leerstand ist ein sichtbares Ärgernis",
        )
        gruenflaechen = Campaign(
            district_id=ov_kreuzberg.id,
            status=CampaignStatus.DRAFT,
            thema="Mehr Grünflächen in Kreuzberg",
            ziel="Politisch: Neue Grünflächen im Bezirk verankern.",
        )
        kiezfest = Campaign(
            district_id=ov_wedding.id,
            status=CampaignStatus.FINISHED,
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
            district_id=bv_fk.id,
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


if __name__ == "__main__":
    asyncio.run(seed())
