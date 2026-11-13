import pytest

from tests.conftest import auth_headers

pytestmark = pytest.mark.asyncio


async def test_both_campaign_creation_paths_record_creator(client, db_session):
    headers = auth_headers("alice@example.org", ("lv-berlin",))

    direct_response = await client.post(
        "/campaigns", data={"district_slug": "lv-berlin"}, headers=headers
    )
    direct_id = direct_response.headers["location"].rsplit("/", 1)[-1]
    direct_detail = await client.get(f"/campaigns/{direct_id}", headers=headers)
    assert "Erstellt von alice@example.org" in direct_detail.text

    wizard_response = await client.post(
        "/campaigns/new", data={"district_slug": "lv-berlin"}, headers=headers
    )
    wizard_id = wizard_response.headers["location"].split("/")[2]
    wizard_detail = await client.get(f"/campaigns/{wizard_id}", headers=headers)
    assert "Erstellt von alice@example.org" in wizard_detail.text


async def test_fork_records_the_forking_user_as_creator(client, db_session):
    source_headers = auth_headers("source-author", ("lv-berlin",))
    forker_headers = auth_headers("forking-user", ("lv-berlin",))

    source_response = await client.post(
        "/campaigns", data={"district_slug": "lv-berlin"}, headers=source_headers
    )
    source_id = source_response.headers["location"].rsplit("/", 1)[-1]

    fork_response = await client.post(
        f"/campaigns/{source_id}/fork",
        data={"target_district_slug": "lv-berlin"},
        headers=forker_headers,
    )
    fork_id = fork_response.headers["location"].rsplit("/", 1)[-1]

    detail = await client.get(f"/campaigns/{fork_id}", headers=forker_headers)
    assert "Erstellt von forking-user" in detail.text
    assert "Erstellt von source-author" not in detail.text


async def test_creation_stores_the_display_name(client, db_session):
    """The write path stores the acting user's display name (arch-01)."""
    headers = auth_headers("user-1", ("lv-berlin",), display_name="Alice Beispiel")

    response = await client.post("/campaigns", data={"district_slug": "lv-berlin"}, headers=headers)
    campaign_id = response.headers["location"].rsplit("/", 1)[-1]
    detail = await client.get(f"/campaigns/{campaign_id}", headers=headers)
    assert "Erstellt von Alice Beispiel" in detail.text
    assert "Erstellt von user-1" not in detail.text


async def test_fork_stores_the_forking_users_display_name(client, db_session):
    """Clones/forks carry the *acting* user's name, not the source's."""
    source_headers = auth_headers("source-author", ("lv-berlin",), display_name="Source Author")
    forker_headers = auth_headers("forker", ("lv-berlin",), display_name="Forker Person")

    source_response = await client.post(
        "/campaigns", data={"district_slug": "lv-berlin"}, headers=source_headers
    )
    source_id = source_response.headers["location"].rsplit("/", 1)[-1]

    fork_response = await client.post(
        f"/campaigns/{source_id}/fork",
        data={"target_district_slug": "lv-berlin"},
        headers=forker_headers,
    )
    fork_id = fork_response.headers["location"].rsplit("/", 1)[-1]

    detail = await client.get(f"/campaigns/{fork_id}", headers=forker_headers)
    assert "Erstellt von Forker Person" in detail.text
    assert "Erstellt von Source Author" not in detail.text


async def test_display_name_falls_back_to_raw_id_without_headers(client, db_session):
    headers = auth_headers("plain-id", ("lv-berlin",))

    response = await client.post("/campaigns", data={"district_slug": "lv-berlin"}, headers=headers)
    campaign_id = response.headers["location"].rsplit("/", 1)[-1]
    detail = await client.get(f"/campaigns/{campaign_id}", headers=headers)
    assert "Erstellt von plain-id" in detail.text
