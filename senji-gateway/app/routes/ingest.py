import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl

from app.models.schemas import IngestResponse
from app.services.fetcher import fetch_url
from app.services.trafilatura_service import extract_article

logger = logging.getLogger("senji.routes.ingest")

router = APIRouter(prefix="/api/ingest")


class IngestURLRequest(BaseModel):
    url: HttpUrl


@router.post("/url", response_model=IngestResponse)
async def ingest_url(body: IngestURLRequest, request: Request) -> IngestResponse | JSONResponse:
    url = str(body.url)

    try:
        result = await fetch_url(url)
    except httpx.TimeoutException:
        logger.error("Timeout fetching URL: %s", url)
        return JSONResponse(
            status_code=504,
            content={"error": "fetch_timeout", "detail": "URL fetch timed out"},
        )
    except httpx.HTTPStatusError as exc:
        logger.error("HTTP error fetching URL: %s → %s", url, exc.response.status_code)
        return JSONResponse(
            status_code=502,
            content={"error": "fetch_error", "detail": str(exc)},
        )

    try:
        article = extract_article(result.html, result.final_url)
    except ValueError as exc:
        logger.error("Article extraction failed: %s", exc)
        return JSONResponse(
            status_code=400,
            content={"error": "extraction_failed", "detail": str(exc)},
        )

    return IngestResponse(
        markdown=article["markdown"],
        title=article["title"],
        source=result.final_url,
        author=article.get("author"),
        language=article.get("language"),
        publish_date=article.get("publish_date"),
    )
