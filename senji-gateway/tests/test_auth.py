import httpx
import pytest

from app.main import app


def build_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.asyncio
async def test_convert_url_rejects_missing_token() -> None:
    async with build_client() as client:
        response = await client.post("/api/convert/url")

    assert response.status_code == 401
    assert response.json() == {
        "detail": {
            "error": "unauthorized",
            "detail": "Invalid or missing bearer token",
        }
    }


@pytest.mark.asyncio
async def test_convert_url_rejects_wrong_token() -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/url", headers={"Authorization": "Bearer wrong-token"}
        )

    assert response.status_code == 401
    assert response.json() == {
        "detail": {
            "error": "unauthorized",
            "detail": "Invalid or missing bearer token",
        }
    }


@pytest.mark.asyncio
async def test_convert_url_allows_correct_token() -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/url", headers={"Authorization": "Bearer dev-token"}
        )

    assert response.status_code != 401


@pytest.mark.asyncio
async def test_health_is_exempt_without_token() -> None:
    async with build_client() as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_root_is_exempt_without_token() -> None:
    async with build_client() as client:
        response = await client.get("/")

    assert response.status_code == 200
