from unittest.mock import patch

import httpx
import pytest

from app.main import app


def build_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


AUTH_HEADERS = {"Authorization": "Bearer dev-token"}


@pytest.mark.asyncio
async def test_unhandled_exception_returns_500() -> None:
    with patch(
        "app.routes.convert.fetch_url", side_effect=RuntimeError("boom")
    ):
        async with build_client() as client:
            response = await client.post(
                "/api/convert/url",
                json={"url": "https://example.com"},
                headers=AUTH_HEADERS,
            )

    assert response.status_code == 500
    body = response.json()
    assert body == {"error": "internal_error", "detail": "Internal server error"}


@pytest.mark.asyncio
async def test_unhandled_exception_does_not_leak_traceback() -> None:
    with patch(
        "app.routes.convert.fetch_url", side_effect=ValueError("secret-info")
    ):
        async with build_client() as client:
            response = await client.post(
                "/api/convert/url",
                json={"url": "https://example.com"},
                headers=AUTH_HEADERS,
            )

    body = response.text
    assert "secret-info" not in body
    assert "Traceback" not in body


@pytest.mark.asyncio
async def test_error_response_shape_matches_schema() -> None:
    with patch(
        "app.routes.convert.fetch_url", side_effect=RuntimeError("boom")
    ):
        async with build_client() as client:
            response = await client.post(
                "/api/convert/url",
                json={"url": "https://example.com"},
                headers=AUTH_HEADERS,
            )

    body = response.json()
    assert isinstance(body.get("error"), str)
    assert isinstance(body.get("detail"), str)
    assert set(body.keys()) == {"error", "detail"}


@pytest.mark.asyncio
async def test_validation_error_returns_422() -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/url",
            json={},
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 422
