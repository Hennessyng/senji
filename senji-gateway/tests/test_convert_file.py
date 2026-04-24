
import httpx
import pytest

from app.main import app

AUTH = {"Authorization": "Bearer dev-token"}


def build_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.asyncio
async def test_file_upload_returns_501() -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/file",
            files={"file": ("test.pdf", b"fake pdf content", "application/pdf")},
            headers=AUTH,
        )

    assert response.status_code == 501
    data = response.json()
    assert data["error"] == "not_implemented"
