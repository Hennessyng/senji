import logging
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger("senji.fetcher")

_USER_AGENT = "Mozilla/5.0 (compatible; Senji/1.0)"


@dataclass
class FetchResult:
    html: str
    final_url: str
    content_type: str


async def fetch_url(url: str) -> FetchResult:
    """Fetch URL content, follow redirects, return HTML + final URL."""
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
