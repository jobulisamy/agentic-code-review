import pytest


@pytest.mark.anyio
async def test_health_returns_200(client):
    response = await client.get("/api/health")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_health_returns_service_name(client):
    response = await client.get("/api/health")
    data = response.json()
    assert data["status"] == "ok"
