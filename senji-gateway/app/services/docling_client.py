# senji-gateway/app/services/docling_client.py
#
# Verified Docling Serve API contract (docling-serve, image: ghcr.io/docling-project/docling-serve)
# Source: https://github.com/docling-project/docling-serve/blob/main/docs/usage.md
#
# Endpoint: POST /v1/convert/file
# Request:  multipart/form-data
#   - files:  one or more binary file uploads (field name "files")
#   - data:   options as form fields — to_formats=["md"] for markdown output
# Response (single file, JSON — ConvertDocumentResponse):
#   {
#     "document": <exported content — markdown string when to_formats=["md"]>,
#     "status": "success" | "partial_success" | "failure",
#     "processing_time": float (seconds),
#     "timings": {...} | null,
#     "errors": [...]
#   }
# Timeout: 120s (large PDFs are slow; Docling loads ML models)
# Raises: httpx.ConnectError if Docling unreachable
# Raises: httpx.TimeoutException on timeout
# Raises: httpx.HTTPStatusError on non-2xx

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger("senji.docling")

_TIMEOUT = 120.0

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx"}


@dataclass
class DoclingResult:
    markdown: str


async def convert_file(
    docling_url: str,
    file_bytes: bytes,
    filename: str,
) -> DoclingResult:
    """POST a file to Docling Serve and return extracted markdown."""
    logger.info("Sending file to Docling at %s, filename=%s", docling_url, filename)

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(
            f"{docling_url}/v1/convert/file",
            files={"files": (filename, file_bytes)},
            data={"to_formats": '["md"]'},
        )
        response.raise_for_status()

    data = response.json()
    document = data.get("document", "")

    # document may be a string (markdown) or a dict with md content
    if isinstance(document, dict):
        markdown = document.get("md_content", "") or document.get("content", "")
    else:
        markdown = str(document)

    logger.info(
        "Docling conversion OK, filename=%s, processing_time=%s",
        filename,
        data.get("processing_time"),
    )
    return DoclingResult(markdown=markdown)
