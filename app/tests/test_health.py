async def test_healthcheck_is_unauthenticated(client):
    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
