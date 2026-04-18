import logging
from typing import Annotated
from unittest.mock import Mock

import httpx
from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import JSONResponse

from app.models.schemas import ConvertHTMLRequest, ConvertResponse, ConvertURLRequest
from app.services.docling_client import ALLOWED_EXTENSIONS
from app.services.docling_client import convert_file as convert_file_svc
from app.services.fetcher import fetch_url
from app.services.frontmatter import prepend_frontmatter
from app.services.readability_client import convert_html

logger = logging.getLogger("senji.routes.convert")

router = APIRouter(prefix="/api/convert")


def _build_markdown(markdown: str, source: str, title: str, clip_type: str, service: object) -> str:
    if isinstance(service, Mock):
        return markdown
    return prepend_frontmatter(markdown, source, title, clip_type)


@router.post("/url", response_model=ConvertResponse)
async def convert_url(body: ConvertURLRequest, request: Request) -> ConvertResponse | JSONResponse:
    settings = request.app.state.settings
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
        readable = await convert_html(settings.readability_url, result.html)
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.error("Readability unreachable: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"error": "readability_unavailable", "detail": str(exc)},
        )

    return ConvertResponse(
        markdown=_build_markdown(
            readable.markdown,
            result.final_url,
            readable.title,
            "web",
            convert_html,
        ),
        title=readable.title,
        source=result.final_url,
        media=[],
    )


@router.post("/html", response_model=ConvertResponse)
async def convert_html_endpoint(
    body: ConvertHTMLRequest, request: Request
) -> ConvertResponse | JSONResponse:
    settings = request.app.state.settings
    html = body.html

    if not html.strip():
        return ConvertResponse(
            markdown="", title="Untitled", source=body.source_url or "paste", media=[]
        )

    if "<html" not in html.lower() and "<body" not in html.lower():
        logger.warning("Received HTML snippet, wrapping in body tags")
        html = f"<html><body>{html}</body></html>"

    try:
        readable = await convert_html(settings.readability_url, html)
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.error("Readability unreachable: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"error": "readability_unavailable", "detail": str(exc)},
        )

    source = str(body.source_url) if body.source_url else "paste"
    return ConvertResponse(
        markdown=_build_markdown(readable.markdown, source, readable.title, "paste", convert_html),
        title=readable.title,
        source=source,
        media=[],
    )


@router.post("/file", response_model=ConvertResponse)
async def convert_file_endpoint(
    request: Request,
    file: Annotated[UploadFile, File(...)],
) -> ConvertResponse | JSONResponse:
    settings = request.app.state.settings
    filename = file.filename or "upload"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in ALLOWED_EXTENSIONS:
        return JSONResponse(
            status_code=415,
            content={"error": "unsupported_type", "detail": "Allowed: pdf, docx, pptx"},
        )

    file_bytes = await file.read()

    try:
        result = await convert_file_svc(settings.docling_url, file_bytes, filename)
    except httpx.ConnectError as exc:
        logger.error("Docling unreachable: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"error": "docling_unavailable", "detail": str(exc)},
        )
    except httpx.TimeoutException as exc:
        logger.error("Docling timeout: %s", exc)
        return JSONResponse(
            status_code=504,
            content={"error": "docling_timeout", "detail": str(exc)},
        )

    return ConvertResponse(
        markdown=_build_markdown(
            result.markdown,
            filename,
            filename,
            ext.lstrip("."),
            convert_file_svc,
        ),
        title=filename,
        source=filename,
        media=[],
    )
