import pytest
from httpx import AsyncClient, ASGITransport


@pytest.fixture
async def client():
    """Async test client for the FastAPI app.
    Import is deferred so Wave 0 can be written before app/main.py exists.
    """
    from app.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
