from __future__ import annotations

import base64
import logging
import re
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.models.schemas import MediaItem

logger = logging.getLogger("senji.media")

MAX_IMAGES = 50
MIN_SIZE_BYTES = 10_000

_IMG_PATTERN = re.compile(
    r'<img[^>]*(?:src|data-src)=["\']([^"\']+)["\'][^>]*/?>', re.IGNORECASE
)

_SKIP_KEYWORDS = {"pixel", "tracking"}
_SKIP_EXTENSIONS = {".svg"}

_EXT_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _detect_ext(url: str) -> str:
    lower = url.lower().split("?")[0]
    if ".jpg" in lower or ".jpeg" in lower:
        return ".jpg"
    if ".gif" in lower:
        return ".gif"
    if ".webp" in lower:
        return ".webp"
    if ".svg" in lower:
        return ".svg"
    return ".png"


def _should_skip(src: str) -> bool:
    if src.startswith("data:"):
        return True
    lower = src.lower()
    if any(kw in lower for kw in _SKIP_KEYWORDS):
        return True
    ext = _detect_ext(src)
    return ext in _SKIP_EXTENSIONS


def _resolve_url(src: str, base_url: str) -> str | None:
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}://{parsed.netloc}{src}"
    if src.startswith("http"):
        return src
    return None


def _content_type_for_ext(ext: str) -> str:
    return _EXT_MAP.get(ext, "image/png")


async def _download_one(
    client: httpx.AsyncClient, url: str, index: int
) -> MediaItem | None:
    try:
        resp = await client.get(url, timeout=settings.media_download_timeout_seconds)
        resp.raise_for_status()
    except Exception:
        logger.warning("Failed to download image: %s", url)
        return None

    data = resp.content
    if len(data) < MIN_SIZE_BYTES:
        logger.debug("Skipping small image (%d bytes): %s", len(data), url)
        return None

    ext = _detect_ext(url)
    content_type = resp.headers.get("content-type", _content_type_for_ext(ext))
    if ";" in content_type:
        content_type = content_type.split(";")[0].strip()

    return MediaItem(
        filename=f"image-{index}{ext}",
        content_type=content_type,
        data=base64.b64encode(data).decode("ascii"),
    )


async def extract_and_download_images(
    html: str, base_url: str
) -> tuple[str, list[MediaItem]]:
    matches = _IMG_PATTERN.findall(html)
    if not matches:
        return html, []

    urls_to_fetch: list[tuple[str, int]] = []
    index = 0
    for src in matches:
        if index >= MAX_IMAGES:
            break
        if _should_skip(src):
            continue
        resolved = _resolve_url(src, base_url)
        if resolved is None:
            continue
        index += 1
        urls_to_fetch.append((resolved, index))

    if not urls_to_fetch:
        return html, []

    media: list[MediaItem] = []
    async with httpx.AsyncClient() as client:
        for url, idx in urls_to_fetch:
            item = await _download_one(client, url, idx)
            if item is not None:
                media.append(item)

    return html, media
