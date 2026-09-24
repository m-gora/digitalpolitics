import pytest

from tests.conftest import auth_headers, make_district

pytestmark = pytest.mark.asyncio


async def test_read_requires_authentication(client):
    resp = await client.get("/campaigns")
    assert resp.status_code == 401


async def test_read_is_global_for_any_authenticated_user(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    resp = await client.get("/campaigns", headers=auth_headers("someone", district_scopes=set()))
    assert resp.status_code == 200  # arch-02: read is global, no district scope required
    resp = await client.get("/districts", headers=auth_headers("someone", district_scopes=set()))
    assert resp.status_code == 200
    assert berlin.name in resp.text


async def test_write_denied_outside_district_scope(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    resp = await client.post(
        "/campaigns",
        data={"district_id": str(berlin.id)},
        headers=auth_headers("outsider", district_scopes=set()),
    )
    assert resp.status_code == 403


async def test_write_allowed_within_district_scope(client, db_session):
    berlin = await make_district(db_session, "LV Berlin")
    resp = await client.post(
        "/campaigns",
        data={"district_id": str(berlin.id)},
        headers=auth_headers("anna", district_scopes={str(berlin.id)}),
    )
    assert resp.status_code == 303


async def test_hierarchical_inheritance_is_purely_header_driven(client, db_session):
    """Per adr-03, the backend does NOT expand inheritance itself -- it trusts
    the pre-expanded X-District-Scopes list. This test documents that a scope
    only containing the parent's ID does *not* grant access to a child unless
    the child ID is also present in the header (that expansion is the auth
    layer's job, exercised separately via dpp.campaign.hierarchy in
    test_hierarchy.py).
    """
    berlin = await make_district(db_session, "LV Berlin")
    kreuzberg = await make_district(db_session, "OV Kreuzberg", parent=berlin)

    # Only the parent ID in scope -> child write is denied at this layer.
    resp = await client.post(
        "/campaigns",
        data={"district_id": str(kreuzberg.id)},
        headers=auth_headers("jonas", district_scopes={str(berlin.id)}),
    )
    assert resp.status_code == 403

    # Both IDs present (as a real pre-expanded header would contain) -> allowed.
    resp = await client.post(
        "/campaigns",
        data={"district_id": str(kreuzberg.id)},
        headers=auth_headers("jonas", district_scopes={str(berlin.id), str(kreuzberg.id)}),
    )
    assert resp.status_code == 303
