import pytest

from tests.conftest import auth_headers

pytestmark = pytest.mark.asyncio


async def test_read_requires_authentication(client):
    resp = await client.get("/campaigns")
    assert resp.status_code == 401


async def test_read_is_global_for_any_authenticated_user(client, db_session):
    resp = await client.get("/campaigns", headers=auth_headers("someone", ()))
    assert resp.status_code == 200  # arch-02: read is global, no district scope required


async def test_write_denied_outside_district_scope(client):
    resp = await client.post(
        "/campaigns",
        data={"district_slug": "bv-mitte"},
        headers=auth_headers("outsider", ()),
    )
    assert resp.status_code == 403


async def test_write_denied_for_unknown_district(client):
    # The scope set is built from the Gliederung config registry, so a
    # slug that isn't in the config can never pass the write check.
    resp = await client.post(
        "/campaigns",
        data={"district_slug": "not-a-real-district"},
        headers=auth_headers("someone", ("all",)),
    )
    assert resp.status_code == 403


async def test_write_allowed_within_district_scope(client):
    resp = await client.post(
        "/campaigns",
        data={"district_slug": "bv-mitte"},
        headers=auth_headers("anna", ("bv-mitte",)),
    )
    assert resp.status_code == 303


async def test_hierarchical_inheritance_from_groups_claim(client):
    """Per adr-03 (revised), the groups claim carries the raw group (a
    Gliederung slug); dpp.auth.headers expands inheritance via the config
    registry: a "bv-friedrichshain-kreuzberg" group grants write access to
    its child OV districts."""
    resp = await client.post(
        "/campaigns",
        data={"district_slug": "ov-kreuzberg"},
        headers=auth_headers("jonas", ("bv-friedrichshain-kreuzberg",)),
    )
    assert resp.status_code == 303
