import logging
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger("senji.fetcher")

_USER_AGENT = "Mozilla/5.0 (compatible; Senji/1.0)"


@dataclass
class FetchResult:
    html: str
    final_url: str
    content_type: str


def _needs_js_render(url: str) -> bool:
    hostname = urlparse(url).hostname or ""
    return any(
        hostname == domain or hostname.endswith("." + domain)
        for domain in settings.js_render_domains
    )


async def _fetch_via_renderer(url: str) -> FetchResult:
    logger.info("JS renderer fetch: %s", url)
    async with httpx.AsyncClient(timeout=settings.renderer_timeout_seconds) as client:
        response = await client.post(
            f"{settings.renderer_url}/render",
            json={"url": url},
        )
        response.raise_for_status()
        data = response.json()
    return FetchResult(
        html=data["html"],
        final_url=data["finalUrl"],
        content_type="text/html",
    )


async def fetch_url(url: str) -> FetchResult:
    if _needs_js_render(url):
        return await _fetch_via_renderer(url)
    logger.info("Fetching URL: %s", url)
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=settings.fetcher_timeout_seconds,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        final_url = str(response.url)
        logger.info("Fetched OK: %s → %s", url, final_url)
        return FetchResult(
            html=response.text,
            final_url=final_url,
            content_type=content_type,
        )
