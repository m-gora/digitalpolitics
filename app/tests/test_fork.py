import pytest

from tests.conftest import auth_headers

pytestmark = pytest.mark.asyncio


async def test_fork_copies_fields_only(client, db_session):
    headers = auth_headers("anna", ("lv-berlin",))

    resp = await client.post("/campaigns", data={"district_slug": "lv-berlin"}, headers=headers)
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
        data={"target_district_slug": "ov-kreuzberg"},
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
    headers = auth_headers("anna", ("lv-berlin",))

    resp = await client.post("/campaigns", data={"district_slug": "lv-berlin"}, headers=headers)
    source_id = resp.headers["location"].rsplit("/", 1)[-1]

    # Outsider can read (global read) but not fork into a district they can't write to.
    outsider_headers = auth_headers("outsider", ())
    resp = await client.post(
        f"/campaigns/{source_id}/fork",
        data={"target_district_slug": "bv-mitte"},
        headers=outsider_headers,
    )
    assert resp.status_code == 403
