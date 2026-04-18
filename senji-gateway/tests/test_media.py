"""TDD tests for media download pipeline."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.models.schemas import MediaItem
from app.services.media import extract_and_download_images


def _fake_response(size_bytes: int = 15_000, content_type: str = "image/jpeg") -> httpx.Response:
    """Build a fake httpx.Response with given body size."""
    return httpx.Response(
        200,
        content=b"\xff\xd8" + b"\x00" * (size_bytes - 2),
        headers={"content-type": content_type},
        request=httpx.Request("GET", "https://example.com/img.jpg"),
    )


# ── no images ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_no_images() -> None:
    html = "<html><body><p>No images here</p></body></html>"
    result_html, media = await extract_and_download_images(html, "https://example.com")
    assert result_html == html
    assert media == []


# ── 3 images → 3 MediaItems ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_3_images() -> None:
    html = (
        '<html><body>'
        '<img src="https://example.com/a.jpg">'
        '<img src="https://example.com/b.png">'
        '<img src="https://example.com/c.webp">'
        '</body></html>'
    )

    async def fake_get(url, **kwargs):
        return _fake_response(15_000)

    with patch("app.services.media.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=fake_get)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        result_html, media = await extract_and_download_images(html, "https://example.com")

    assert result_html == html  # HTML unchanged
    assert len(media) == 3
    for item in media:
        assert isinstance(item, MediaItem)
        assert item.filename
        assert item.content_type
        assert item.data  # base64 string


# ── relative URL resolved ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_relative_url_resolved() -> None:
    html = '<html><body><img src="/photo.jpg"></body></html>'

    captured_urls: list[str] = []

    async def fake_get(url, **kwargs):
        captured_urls.append(str(url))
        return _fake_response(15_000)

    with patch("app.services.media.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=fake_get)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        _, media = await extract_and_download_images(html, "https://example.com")

    assert len(captured_urls) == 1
    assert captured_urls[0] == "https://example.com/photo.jpg"
    assert len(media) == 1


# ── protocol-relative URL resolved ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_protocol_relative_url_resolved() -> None:
    html = '<html><body><img src="//cdn.example.com/img.jpg"></body></html>'

    captured_urls: list[str] = []

    async def fake_get(url, **kwargs):
        captured_urls.append(str(url))
        return _fake_response(15_000)

    with patch("app.services.media.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=fake_get)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        _, media = await extract_and_download_images(html, "https://example.com")

    assert len(captured_urls) == 1
    assert captured_urls[0] == "https://cdn.example.com/img.jpg"
    assert len(media) == 1


# ── small image filtered ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_small_image_filtered() -> None:
    html = '<html><body><img src="https://example.com/tiny.jpg"></body></html>'

    async def fake_get(url, **kwargs):
        return _fake_response(5_000)  # < 10KB

    with patch("app.services.media.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=fake_get)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        _, media = await extract_and_download_images(html, "https://example.com")

    assert media == []


# ── download failure → graceful skip ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_download_failure_skipped() -> None:
    html = '<html><body><img src="https://example.com/broken.jpg"></body></html>'

    async def fake_get(url, **kwargs):
        raise httpx.ConnectError("connection refused")

    with patch("app.services.media.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=fake_get)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        # Must NOT raise
        _, media = await extract_and_download_images(html, "https://example.com")

    assert media == []


# ── data: URI skipped ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_data_uri_skipped() -> None:
    html = '<html><body><img src="data:image/png;base64,iVBORw0KGgo="></body></html>'

    with patch("app.services.media.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        _, media = await extract_and_download_images(html, "https://example.com")

    # Should never call httpx.get for data URIs
    mock_client.get.assert_not_called()
    assert media == []


# ── SVG skipped ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_svg_skipped() -> None:
    html = '<html><body><img src="https://example.com/logo.svg"></body></html>'

    with patch("app.services.media.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        _, media = await extract_and_download_images(html, "https://example.com")

    mock_client.get.assert_not_called()
    assert media == []


# ── tracking pixel skipped ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tracking_pixel_skipped() -> None:
    html = '<html><body><img src="https://example.com/pixel.gif"></body></html>'

    with patch("app.services.media.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        _, media = await extract_and_download_images(html, "https://example.com")

    mock_client.get.assert_not_called()
    assert media == []


# ── max 50 images enforced ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_max_50_images() -> None:
    imgs = "".join(f'<img src="https://example.com/img{i}.jpg">' for i in range(51))
    html = f"<html><body>{imgs}</body></html>"

    async def fake_get(url, **kwargs):
        return _fake_response(15_000)

    with patch("app.services.media.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=fake_get)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        _, media = await extract_and_download_images(html, "https://example.com")

    assert len(media) == 50
    assert mock_client.get.call_count == 50


# ── data-src attribute parsed ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_data_src_attribute_parsed() -> None:
    html = '<html><body><img data-src="https://example.com/lazy.jpg"></body></html>'

    async def fake_get(url, **kwargs):
        return _fake_response(15_000)

    with patch("app.services.media.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=fake_get)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        _, media = await extract_and_download_images(html, "https://example.com")

    assert len(media) == 1
    assert media[0].filename == "image-1.jpg"
