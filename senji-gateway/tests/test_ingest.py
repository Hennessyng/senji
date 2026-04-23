from unittest.mock import AsyncMock, Mock, MagicMock, patch

import httpx
import pytest

from app.main import app
from app.services.fetcher import FetchResult

AUTH = {"Authorization": "Bearer dev-token"}

_DEFAULT_FETCH = FetchResult(
    html="<article><h1>Article Title</h1><p>Article body content.</p></article>",
    final_url="https://example.com/article",
    content_type="text/html",
)


def build_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.asyncio
@patch(
    "app.routes.ingest.extract_article",
    new_callable=Mock,
    return_value={
        "markdown": "# Article Title\n\nArticle body content.",
        "title": "Article Title",
        "author": "John Doe",
    },
)
@patch("app.routes.ingest.fetch_url", new_callable=AsyncMock, return_value=_DEFAULT_FETCH)
async def test_valid_url_returns_200(mock_fetch, mock_extract) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/ingest/url",
            json={"url": "https://example.com/article"},
            headers=AUTH,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["markdown"] == "# Article Title\n\nArticle body content."
    assert data["title"] == "Article Title"
    assert data["source"] == "https://example.com/article"
    assert data["author"] == "John Doe"


@pytest.mark.asyncio
async def test_invalid_url_returns_422() -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/ingest/url",
            json={"url": "not-a-url"},
            headers=AUTH,
        )

    assert response.status_code == 422


@pytest.mark.asyncio
@patch(
    "app.routes.ingest.fetch_url",
    new_callable=AsyncMock,
    side_effect=httpx.TimeoutException("timed out"),
)
async def test_fetch_timeout_returns_504(mock_fetch) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/ingest/url",
            json={"url": "https://example.com"},
            headers=AUTH,
        )

    assert response.status_code == 504
    data = response.json()
    assert data["error"] == "fetch_timeout"


@pytest.mark.asyncio
async def test_http_error_returns_502() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 404
    exc = httpx.HTTPStatusError("404", request=MagicMock(), response=mock_response)
    
    with patch("app.routes.ingest.fetch_url", new_callable=AsyncMock, side_effect=exc):
        async with build_client() as client:
            response = await client.post(
                "/api/ingest/url",
                json={"url": "https://example.com"},
                headers=AUTH,
            )

        assert response.status_code == 502
        data = response.json()
        assert data["error"] == "fetch_error"


@pytest.mark.asyncio
@patch(
    "app.routes.ingest.extract_article",
    new_callable=Mock,
    side_effect=ValueError("Failed to extract article"),
)
@patch("app.routes.ingest.fetch_url", new_callable=AsyncMock, return_value=_DEFAULT_FETCH)
async def test_extraction_failure_returns_400(mock_fetch, mock_extract) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/ingest/url",
            json={"url": "https://example.com"},
            headers=AUTH,
        )

    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "extraction_failed"
