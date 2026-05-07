import logging
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger("senji.readability")


@dataclass
class ReadabilityResult:
    markdown: str
    title: str


async def convert_html(readability_url: str, html: str) -> ReadabilityResult:
    """POST HTML to Readability sidecar, return markdown + title."""
    logger.info("Sending HTML to Readability at %s", readability_url)
    async with httpx.AsyncClient(timeout=settings.readability_timeout_seconds) as client:
        response = await client.post(
            f"{readability_url}/convert",
            json={"html": html},
        )
        response.raise_for_status()
        data = response.json()
        logger.info("Readability conversion OK, title=%s", data.get("title"))
        return ReadabilityResult(markdown=data["markdown"], title=data["title"])
