from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import re
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger("senji.pics.asset_downloader")

_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_MD_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_HTML_IMG_RE = re.compile(
    r"""<img\s+[^>]*?\bsrc\s*=\s*["']([^"']+)["'][^>]*?/?>""",
    re.IGNORECASE,
)
_DATA_URI_RE = re.compile(r"^data:([^;,]+);base64,(.+)$", re.DOTALL)

_MIME_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/bmp": ".bmp",
}
_URL_EXT_FALLBACK = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"}


def _is_localizable(url: str) -> bool:
    u = url.strip().lower()
    return u.startswith(("http://", "https://", "data:"))


def _mask_code_blocks(md: str) -> tuple[str, list[str]]:
    blocks: list[str] = []

    def _stash(m: re.Match[str]) -> str:
        idx = len(blocks)
        blocks.append(m.group(0))
        return f"\x00CODE{idx}\x00"

    return _FENCE_RE.sub(_stash, md), blocks


def _restore_code_blocks(md: str, blocks: list[str]) -> str:
    for idx, block in enumerate(blocks):
        md = md.replace(f"\x00CODE{idx}\x00", block)
    return md


def _ext_from_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    ct = content_type.split(";", 1)[0].strip().lower()
    return _MIME_EXT.get(ct)


def _ext_from_url(url: str) -> str | None:
    path = url.split("?", 1)[0].split("#", 1)[0]
    suffix = Path(path).suffix.lower()
    if suffix == ".jpeg":
        suffix = ".jpg"
    return suffix if suffix in _URL_EXT_FALLBACK else None


async def _fetch_with_retry(
    client: httpx.AsyncClient, url: str
) -> tuple[bytes, str | None]:
    attempts = settings.asset_retry_count + 1
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            resp = await client.get(url, timeout=settings.asset_timeout_seconds)
            resp.raise_for_status()
            return resp.content, resp.headers.get("Content-Type")
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt < attempts - 1:
                await asyncio.sleep(4 ** attempt)
    raise last_exc if last_exc else RuntimeError("unreachable")


def _decode_data_uri(uri: str) -> tuple[bytes, str | None]:
    m = _DATA_URI_RE.match(uri)
    if not m:
        raise ValueError(f"malformed data URI: {uri[:40]}")
    mime, payload = m.group(1), m.group(2)
    return base64.b64decode(payload), mime


def _resolve_extension(url: str, content_type: str | None) -> str:
    ext = _ext_from_content_type(content_type)
    if ext:
        return ext
    ext = _ext_from_url(url)
    if ext:
        return ext
    raise ValueError(f"cannot determine image extension for {url}")


def _is_image_content_type(content_type: str | None) -> bool:
    if content_type is None:
        return True
    return content_type.split(";", 1)[0].strip().lower().startswith("image/")


def _build_callout(url: str) -> str:
    return f"> [!warning] Image unavailable: {url}"


async def _download_one(
    client: httpx.AsyncClient,
    url: str,
    seq: int,
    out_dir: Path,
    sem: asyncio.Semaphore,
) -> tuple[str, str | None, str]:
    async with sem:
        try:
            if url.startswith("data:"):
                data, mime = _decode_data_uri(url)
                ext = _ext_from_content_type(mime) or ".bin"
            else:
                data, content_type = await _fetch_with_retry(client, url)
                if not _is_image_content_type(content_type):
                    raise ValueError(
                        f"non-image Content-Type {content_type!r} for {url}"
                    )
                ext = _resolve_extension(url, content_type)

            sha8 = hashlib.sha1(data).hexdigest()[:8]
            filename = f"img-{seq:03d}-{sha8}{ext}"
            out_dir.mkdir(parents=True, exist_ok=True)
            target = out_dir / filename
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_bytes(data)
            tmp.rename(target)
            return url, filename, "ok"
        except Exception as exc:
            logger.warning(
                "Asset download failed",
                extra={"url": url, "error": str(exc)},
            )
            return url, None, "failed"


def _extract_urls_in_order(prose: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    def _record(u: str) -> None:
        if u not in seen:
            seen.add(u)
            urls.append(u)

    pos = 0
    while pos < len(prose):
        md_m = _MD_IMG_RE.search(prose, pos)
        html_m = _HTML_IMG_RE.search(prose, pos)
        candidates = [m for m in (md_m, html_m) if m is not None]
        if not candidates:
            break
        m = min(candidates, key=lambda m: m.start())
        url = m.group(2) if m.re is _MD_IMG_RE else m.group(1)
        if _is_localizable(url):
            _record(url)
        pos = m.end()
    return urls


async def localize_assets(
    markdown: str,
    slug: str,
    vault_path: str | Path,
    *,
    cache: dict[str, str] | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> tuple[str, dict[str, str]]:
    if not markdown:
        return markdown, {}

    cache = cache if cache is not None else {}
    vault_root = Path(vault_path)
    out_dir = vault_root / "attachments" / slug
    rel_prefix = f"attachments/{slug}"

    masked, code_blocks = _mask_code_blocks(markdown)
    urls = _extract_urls_in_order(masked)
    if not urls:
        return markdown, {}

    status: dict[str, str] = {}
    new_urls = [u for u in urls if u not in cache]

    if new_urls:
        sem = asyncio.Semaphore(settings.asset_concurrency)
        starting_seq = len(cache) + 1
        owns_client = http_client is None
        client = http_client or httpx.AsyncClient()
        try:
            tasks = [
                _download_one(client, url, starting_seq + i, out_dir, sem)
                for i, url in enumerate(new_urls)
            ]
            results = await asyncio.gather(*tasks)
        finally:
            if owns_client:
                await client.aclose()

        for url, filename, outcome in results:
            status[url] = outcome
            if outcome == "ok" and filename:
                cache[url] = f"{rel_prefix}/{filename}"

    for url in urls:
        if url in cache and url not in status:
            status[url] = "cached"

    def _rewrite_md(m: re.Match[str]) -> str:
        alt, url = m.group(1), m.group(2)
        if not _is_localizable(url):
            return m.group(0)
        if url in cache:
            return f"![{alt}]({cache[url]})"
        return _build_callout(url)

    def _rewrite_html(m: re.Match[str]) -> str:
        url = m.group(1)
        if not _is_localizable(url):
            return m.group(0)
        if url in cache:
            return m.group(0).replace(url, cache[url])
        return _build_callout(url)

    rewritten = _MD_IMG_RE.sub(_rewrite_md, masked)
    rewritten = _HTML_IMG_RE.sub(_rewrite_html, rewritten)
    return _restore_code_blocks(rewritten, code_blocks), status
