from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.main import app
from app.services.fetcher import FetchResult
from app.services.readability_client import ReadabilityResult

AUTH = {"Authorization": "Bearer dev-token"}

_DEFAULT_FETCH = FetchResult(
    html="<p>hello</p>", final_url="https://example.com/final", content_type="text/html"
)
_DEFAULT_READABLE = ReadabilityResult(markdown="# Hello", title="Hello Page")


def build_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.asyncio
@patch("app.routes.convert.convert_html", new_callable=AsyncMock, return_value=_DEFAULT_READABLE)
@patch("app.routes.convert.fetch_url", new_callable=AsyncMock, return_value=_DEFAULT_FETCH)
async def test_valid_url_returns_200(mock_fetch, mock_readability) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/url",
            json={"url": "https://example.com"},
            headers=AUTH,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["markdown"] == "# Hello"
    assert data["title"] == "Hello Page"
    assert data["source"] == "https://example.com/final"
    assert data["media"] == []


@pytest.mark.asyncio
async def test_invalid_url_returns_422() -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/url",
            json={"url": "not-a-url"},
            headers=AUTH,
        )

    assert response.status_code == 422


@pytest.mark.asyncio
@patch(
    "app.routes.convert.fetch_url",
    new_callable=AsyncMock,
    side_effect=httpx.TimeoutException("timed out"),
)
async def test_fetch_timeout_returns_504(mock_fetch) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/url",
            json={"url": "https://example.com"},
            headers=AUTH,
        )

    assert response.status_code == 504
    data = response.json()
    assert data["error"] == "fetch_timeout"
    assert data["detail"] == "URL fetch timed out"


@pytest.mark.asyncio
@patch(
    "app.routes.convert.convert_html",
    new_callable=AsyncMock,
    side_effect=httpx.ConnectError("connection refused"),
)
@patch("app.routes.convert.fetch_url", new_callable=AsyncMock, return_value=_DEFAULT_FETCH)
async def test_readability_down_returns_503(mock_fetch, mock_readability) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/url",
            json={"url": "https://example.com"},
            headers=AUTH,
        )

    assert response.status_code == 503
    data = response.json()
    assert data["error"] == "readability_unavailable"


@pytest.mark.asyncio
@patch("app.routes.convert.convert_html", new_callable=AsyncMock, return_value=_DEFAULT_READABLE)
@patch(
    "app.routes.convert.fetch_url",
    new_callable=AsyncMock,
    return_value=FetchResult(
        html="<p>redirected</p>",
        final_url="https://example.com/redirected",
        content_type="text/html",
    ),
)
async def test_redirect_followed_final_url_in_source(mock_fetch, mock_readability) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/url",
            json={"url": "https://example.com/old"},
            headers=AUTH,
        )

    assert response.status_code == 200
    assert response.json()["source"] == "https://example.com/redirected"


@pytest.mark.asyncio
@patch(
    "app.routes.convert.fetch_url",
    new_callable=AsyncMock,
    side_effect=httpx.HTTPStatusError(
        "Not Found",
        request=httpx.Request("GET", "https://example.com/404"),
        response=httpx.Response(404),
    ),
)
async def test_fetch_http_error_returns_502(mock_fetch) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/url",
            json={"url": "https://example.com/404"},
            headers=AUTH,
        )

    assert response.status_code == 502
    data = response.json()
    assert data["error"] == "fetch_error"
