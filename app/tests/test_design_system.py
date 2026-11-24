"""The styleguide is a development tool: it must never be reachable in a deployment."""


async def test_styleguide_is_not_mounted_outside_development(client):
    response = await client.get("/_design")
    assert response.status_code == 404
