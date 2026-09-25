import pytest

from tests.conftest import auth_headers, make_district

pytestmark = pytest.mark.asyncio


async def test_fork_copies_fields_only(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    kreuzberg = await make_district(db_session, "OV Kreuzberg", parent=berlin)
    headers = auth_headers("anna", {str(berlin.id), str(kreuzberg.id)})

    resp = await client.post("/campaigns", data={"district_id": str(berlin.id)}, headers=headers)
    source_id = resp.headers["location"].rsplit("/", 1)[-1]
    await client.post(
        f"/campaigns/{source_id}/fields",
        data={"thema": "Quellthema", "ziel": "Quellziel"},
        headers=headers,
    )

    detail = await client.get(f"/campaigns/{source_id}", headers=headers)
    assert f'data-open-dialog="campaign-template-dialog-{source_id}"' in detail.text
    assert f'<dialog id="campaign-template-dialog-{source_id}"' in detail.text
    assert "Ziel-Gliederung" in detail.text
    assert "OV Kreuzberg" in detail.text

    resp = await client.post(
        f"/campaigns/{source_id}/fork",
        data={"target_district_id": str(kreuzberg.id)},
        headers=headers,
    )
    assert resp.status_code == 303
    forked_id = resp.headers["location"].rsplit("/", 1)[-1]

    resp = await client.get(f"/campaigns/{forked_id}", headers=headers)
    assert "Quellthema" in resp.text
    assert "Quellziel" in resp.text
    assert "OV Kreuzberg" in resp.text  # placed in the new target district
    assert "Entwurf" in resp.text  # new campaign starts in Draft regardless of source status


async def test_fork_requires_write_access_to_target_district(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    mitte = await make_district(db_session, "BV Mitte", parent=berlin)
    headers = auth_headers("anna", {str(berlin.id)})

    resp = await client.post("/campaigns", data={"district_id": str(berlin.id)}, headers=headers)
    source_id = resp.headers["location"].rsplit("/", 1)[-1]

    # Outsider can read (global read) but not fork into a district they can't write to.
    outsider_headers = auth_headers("outsider", set())
    resp = await client.post(
        f"/campaigns/{source_id}/fork",
        data={"target_district_id": str(mitte.id)},
        headers=outsider_headers,
    )
    assert resp.status_code == 403
