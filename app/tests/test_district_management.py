import pytest

from dpp.campaign.models import Campaign, Initiative
from tests.conftest import auth_headers, make_district

pytestmark = pytest.mark.asyncio


async def test_any_authenticated_user_can_create_a_root_district(client):
    response = await client.post(
        "/districts",
        data={"name": "LV Brandenburg", "parent_id": ""},
        headers=auth_headers("member-without-scopes", set()),
    )

    assert response.status_code == 303
    page = await client.get("/districts", headers=auth_headers("member-without-scopes", set()))
    assert "LV Brandenburg" in page.text


async def test_child_creation_requires_write_access_to_parent(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")

    denied = await client.post(
        "/districts",
        data={"name": "BV Mitte", "parent_id": str(berlin.id)},
        headers=auth_headers("outsider", set()),
    )
    assert denied.status_code == 403

    allowed = await client.post(
        "/districts",
        data={"name": "BV Mitte", "parent_id": str(berlin.id)},
        headers=auth_headers("berlin-member", {str(berlin.id)}),
    )
    assert allowed.status_code == 303
    page = await client.get("/districts", headers=auth_headers("berlin-member", {str(berlin.id)}))
    assert "BV Mitte" in page.text


async def test_rename_requires_write_access_and_updates_the_hierarchy(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")

    denied = await client.post(
        f"/districts/{berlin.id}/rename",
        data={"name": "Landesverband Berlin"},
        headers=auth_headers("outsider", set()),
    )
    assert denied.status_code == 403

    allowed = await client.post(
        f"/districts/{berlin.id}/rename",
        data={"name": "Landesverband Berlin"},
        headers=auth_headers("berlin-member", {str(berlin.id)}),
    )
    assert allowed.status_code == 303
    page = await client.get("/districts", headers=auth_headers("berlin-member", {str(berlin.id)}))
    assert "Landesverband Berlin" in page.text
    assert "LV Berlin" not in page.text


async def test_hierarchy_row_uses_a_single_edit_button_and_dialog(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    response = await client.get(
        "/districts", headers=auth_headers("berlin-member", {str(berlin.id)})
    )

    assert f'data-open-dialog="district-editor-{berlin.id}"' in response.text
    assert f'<dialog id="district-editor-{berlin.id}"' in response.text
    assert "district-editor-dialog" in response.text
    assert f'action="/districts/{berlin.id}/rename"' in response.text
    assert f'action="/districts/{berlin.id}/delete"' in response.text
    assert "showModal()" in response.text


async def test_district_with_children_cannot_be_deleted(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    await make_district(db_session, "BV Mitte", parent=berlin)
    headers = auth_headers("berlin-member", {str(berlin.id)})

    response = await client.post(f"/districts/{berlin.id}/delete", headers=headers)
    assert response.status_code == 303
    page = await client.get(response.headers["location"], headers=headers)
    assert "Untergliederungen zuerst einzeln" in page.text
    assert "LV Berlin" in page.text


@pytest.mark.parametrize("entity", ["campaign", "initiative"])
async def test_district_with_campaigns_or_initiatives_cannot_be_deleted(client, db_session, entity):
    berlin = await make_district(db_session, "LV Berlin")
    if entity == "campaign":
        db_session.add(Campaign(district_id=berlin.id))
    else:
        db_session.add(Initiative(district_id=berlin.id, name="Bauen und Wohnen"))
    await db_session.commit()
    headers = auth_headers("berlin-member", {str(berlin.id)})

    response = await client.post(f"/districts/{berlin.id}/delete", headers=headers)
    assert response.status_code == 303
    page = await client.get(response.headers["location"], headers=headers)
    assert "noch mit Kampagnen oder Initiativen verknüpft" in page.text
    assert "LV Berlin" in page.text


async def test_unused_leaf_district_can_be_deleted(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    headers = auth_headers("berlin-member", {str(berlin.id)})

    response = await client.post(f"/districts/{berlin.id}/delete", headers=headers)
    assert response.status_code == 303
    page = await client.get("/districts", headers=headers)
    assert "LV Berlin" not in page.text
