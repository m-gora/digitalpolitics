import pytest

from dpp.campaign.hierarchy import expand_district_scope
from tests.conftest import make_district

pytestmark = pytest.mark.asyncio


async def test_expand_district_scope_includes_all_descendants(db_session):
    berlin = await make_district(db_session, "LV Berlin")
    bv_fk = await make_district(db_session, "BV Friedrichshain-Kreuzberg", parent=berlin)
    ov_kreuzberg = await make_district(db_session, "OV Kreuzberg", parent=bv_fk)
    bv_mitte = await make_district(db_session, "BV Mitte", parent=berlin)

    scopes = await expand_district_scope(db_session, berlin.id)

    assert scopes == {str(berlin.id), str(bv_fk.id), str(ov_kreuzberg.id), str(bv_mitte.id)}


async def test_expand_district_scope_leaf_has_no_extra_descendants(db_session):
    berlin = await make_district(db_session, "LV Berlin")
    bv_fk = await make_district(db_session, "BV Friedrichshain-Kreuzberg", parent=berlin)
    ov_kreuzberg = await make_district(db_session, "OV Kreuzberg", parent=bv_fk)

    scopes = await expand_district_scope(db_session, ov_kreuzberg.id)

    assert scopes == {str(ov_kreuzberg.id)}
