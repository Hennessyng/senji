from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.main import app
from app.services.readability_client import ReadabilityResult

AUTH = {"Authorization": "Bearer dev-token"}

_DEFAULT_READABLE = ReadabilityResult(markdown="# Hello", title="Hello Page")


def build_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.asyncio
@patch(
    "app.routes.convert.convert_html",
    new_callable=AsyncMock,
    return_value=_DEFAULT_READABLE,
)
async def test_full_html_returns_200(mock_readability) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/html",
            json={"html": "<html><body><p>hello</p></body></html>"},
            headers=AUTH,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["markdown"] == "# Hello"
    assert data["title"] == "Hello Page"
    assert data["source"] == "paste"
    assert data["media"] == []


@pytest.mark.asyncio
@patch(
    "app.routes.convert.convert_html",
    new_callable=AsyncMock,
    return_value=_DEFAULT_READABLE,
)
async def test_html_snippet_auto_wrapped(mock_readability) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/html",
            json={"html": "<p>snippet</p>"},
            headers=AUTH,
        )

    assert response.status_code == 200
    # Verify the snippet was wrapped before sending to readability
    call_args = mock_readability.call_args
    sent_html = call_args[1].get("html") or call_args[0][1]
    assert "<html><body><p>snippet</p></body></html>" in sent_html


@pytest.mark.asyncio
async def test_empty_html_returns_200_empty_markdown() -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/html",
            json={"html": "   "},
            headers=AUTH,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["markdown"] == ""
    assert data["title"] == "Untitled"
    assert data["source"] == "paste"
    assert data["media"] == []


@pytest.mark.asyncio
@patch(
    "app.routes.convert.convert_html",
    new_callable=AsyncMock,
    return_value=_DEFAULT_READABLE,
)
async def test_with_source_url(mock_readability) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/html",
            json={"html": "<html><body>hi</body></html>", "source_url": "https://example.com"},
            headers=AUTH,
        )

    assert response.status_code == 200
    assert response.json()["source"] == "https://example.com"


@pytest.mark.asyncio
@patch(
    "app.routes.convert.convert_html",
    new_callable=AsyncMock,
    return_value=_DEFAULT_READABLE,
)
async def test_without_source_url_defaults_to_paste(mock_readability) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/html",
            json={"html": "<html><body>hi</body></html>"},
            headers=AUTH,
        )

    assert response.status_code == 200
    assert response.json()["source"] == "paste"


@pytest.mark.asyncio
@patch(
    "app.routes.convert.convert_html",
    new_callable=AsyncMock,
    side_effect=httpx.ConnectError("connection refused"),
)
async def test_readability_down_returns_503(mock_readability) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/convert/html",
            json={"html": "<html><body>hi</body></html>"},
            headers=AUTH,
        )

    assert response.status_code == 503
    data = response.json()
    assert data["error"] == "readability_unavailable"
