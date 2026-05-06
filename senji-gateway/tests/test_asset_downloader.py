"""
Tests for app.services.asset_downloader.localize_assets.

Spec (locked, see commit history / conversation context):
- Folder layout: attachments/<slug>/
- Filename:      img-NNN-<sha1[:8]>.ext   (NNN = 1-based sequential)
- Link format:   ![alt](attachments/<slug>/img-NNN-<hash>.ext)  -- relative, alt preserved
- Detection:     data: URIs decoded; remote URLs use Content-Type image/* (else URL ext fallback);
                 SVG allowed; HTML served at .jpg URL is rejected.
- Errors:        retry settings.asset_retry_count times, then leave Obsidian callout
                 `> [!warning] Image unavailable: <url>` (original markdown image stripped).
- Timeout:       settings.asset_timeout_seconds (default 60); no size cap.
- Concurrency:   asyncio.Semaphore(settings.asset_concurrency)  (default 4).
- Dedup:         caller may pass a shared `cache: dict[url, rel_path]`; same URL across
                 wiki+raw passes downloads exactly once.
- Function is pure (no globals, no I/O outside vault_path/<slug>/).

Function under test:

    async def localize_assets(
        markdown: str,
        slug: str,
        vault_path: str | Path,
        *,
        cache: dict[str, str] | None = None,
        http_client: httpx.AsyncClient | None = None,   # injectable for tests
    ) -> tuple[str, dict[str, str]]:
        '''
        Returns (rewritten_markdown, status_map).
        status_map: url -> "ok" | "failed" | "cached"
        Mutates `cache` in place when provided.
        '''
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

# 1x1 transparent PNG -- minimal valid binary so Content-Type sniffing & hashing both work.
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)
JPEG_HEADER = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00trailer"
SVG_BYTES = b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>'


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def slug() -> str:
    return "my-test-slug"


def _attachments(vault: Path, slug: str) -> Path:
    return vault / "attachments" / slug


def _sha8(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()[:8]


@pytest.mark.asyncio
async def test_no_images_returns_markdown_unchanged(vault, slug):
    from app.services.asset_downloader import localize_assets

    md = "# Title\n\nJust text, no images.\n"
    out, status = await localize_assets(md, slug, vault)
    assert out == md
    assert status == {}
    assert not _attachments(vault, slug).exists()


@pytest.mark.asyncio
async def test_empty_markdown_returns_empty(vault, slug):
    from app.services.asset_downloader import localize_assets

    out, status = await localize_assets("", slug, vault)
    assert out == ""
    assert status == {}


@pytest.mark.asyncio
async def test_remote_image_downloaded_and_link_rewritten(
    vault, slug, httpx_mock: HTTPXMock
):
    from app.services.asset_downloader import localize_assets

    url = "https://cdn.example.com/pic.png"
    httpx_mock.add_response(
        url=url, content=PNG_1PX, headers={"Content-Type": "image/png"}
    )

    md = f"intro\n\n![alt](#{{0}})\n\nend\n".replace("#{0}", url)
    out, status = await localize_assets(md, slug, vault)

    expected_name = f"img-001-{_sha8(PNG_1PX)}.png"
    rel = f"attachments/{slug}/{expected_name}"
    assert f"![alt]({rel})" in out
    assert url not in out
    assert status[url] == "ok"
    saved = _attachments(vault, slug) / expected_name
    assert saved.exists()
    assert saved.read_bytes() == PNG_1PX


@pytest.mark.asyncio
async def test_alt_text_preserved_including_empty(vault, slug, httpx_mock: HTTPXMock):
    from app.services.asset_downloader import localize_assets

    url1 = "https://cdn.example.com/with-alt.png"
    url2 = "https://cdn.example.com/empty-alt.png"
    httpx_mock.add_response(url=url1, content=PNG_1PX, headers={"Content-Type": "image/png"})
    httpx_mock.add_response(url=url2, content=JPEG_HEADER, headers={"Content-Type": "image/png"})

    md = f"![Guqin score]({url1})\n\n![]({url2})\n"
    out, _ = await localize_assets(md, slug, vault)

    assert "![Guqin score](attachments/" in out
    assert "![](attachments/" in out


@pytest.mark.asyncio
async def test_filename_uses_seq_index_and_hash_suffix(
    vault, slug, httpx_mock: HTTPXMock
):
    from app.services.asset_downloader import localize_assets

    url1 = "https://x.test/a.png"
    url2 = "https://x.test/b.png"
    body1 = PNG_1PX
    body2 = PNG_1PX + b"\x00different"
    httpx_mock.add_response(url=url1, content=body1, headers={"Content-Type": "image/png"})
    httpx_mock.add_response(url=url2, content=body2, headers={"Content-Type": "image/png"})

    md = f"![]({url1})\n\n![]({url2})\n"
    await localize_assets(md, slug, vault)

    files = sorted(p.name for p in _attachments(vault, slug).iterdir())
    assert files == [
        f"img-001-{_sha8(body1)}.png",
        f"img-002-{_sha8(body2)}.png",
    ]


@pytest.mark.asyncio
async def test_extension_from_url_when_content_type_missing(
    vault, slug, httpx_mock: HTTPXMock
):
    from app.services.asset_downloader import localize_assets

    url = "https://cms.example.com/upload/image.jpg"
    httpx_mock.add_response(url=url, content=JPEG_HEADER, headers={})

    md = f"![]({url})\n"
    out, status = await localize_assets(md, slug, vault)
    assert status[url] == "ok"
    saved = list(_attachments(vault, slug).iterdir())
    assert len(saved) == 1
    assert saved[0].suffix == ".jpg"


@pytest.mark.asyncio
async def test_svg_allowed(vault, slug, httpx_mock: HTTPXMock):
    from app.services.asset_downloader import localize_assets

    url = "https://x.test/icon.svg"
    httpx_mock.add_response(url=url, content=SVG_BYTES, headers={"Content-Type": "image/svg+xml"})

    md = f"![]({url})\n"
    out, status = await localize_assets(md, slug, vault)
    assert status[url] == "ok"
    saved = list(_attachments(vault, slug).iterdir())
    assert saved[0].suffix == ".svg"
    assert saved[0].read_bytes() == SVG_BYTES


@pytest.mark.asyncio
async def test_data_uri_decoded_to_file(vault, slug):
    from app.services.asset_downloader import localize_assets

    payload = base64.b64encode(PNG_1PX).decode()
    data_uri = f"data:image/png;base64,{payload}"
    md = f"![inline]({data_uri})\n"

    out, status = await localize_assets(md, slug, vault)

    assert status[data_uri] == "ok"
    saved = list(_attachments(vault, slug).iterdir())
    assert len(saved) == 1
    assert saved[0].suffix == ".png"
    assert saved[0].read_bytes() == PNG_1PX
    assert "data:image" not in out
    assert f"attachments/{slug}/" in out


@pytest.mark.asyncio
async def test_html_served_at_jpg_url_rejected(vault, slug, httpx_mock: HTTPXMock):
    from app.services.asset_downloader import localize_assets

    url = "https://broken.example.com/missing.jpg"
    httpx_mock.add_response(
        url=url,
        content=b"<html><body>404 Not Found</body></html>",
        headers={"Content-Type": "text/html; charset=utf-8"},
    )

    md = f"![alt]({url})\n"
    out, status = await localize_assets(md, slug, vault)

    assert status[url] == "failed"
    assert f"> [!warning] Image unavailable: {url}" in out
    assert f"![alt]({url})" not in out
    assert not _attachments(vault, slug).exists() or not any(
        _attachments(vault, slug).iterdir()
    )


@pytest.mark.asyncio
async def test_404_replaced_with_warning_callout(vault, slug, httpx_mock: HTTPXMock):
    from app.services.asset_downloader import localize_assets

    url = "https://gone.example.com/x.png"
    # Three responses because retry_count default is 2 -> 1 + 2 retries = 3 attempts.
    for _ in range(3):
        httpx_mock.add_response(url=url, status_code=404)

    md = f"before\n\n![oops]({url})\n\nafter\n"
    out, status = await localize_assets(md, slug, vault)

    assert status[url] == "failed"
    assert f"> [!warning] Image unavailable: {url}" in out
    assert "before" in out and "after" in out


@pytest.mark.asyncio
async def test_timeout_replaced_with_warning_callout(
    vault, slug, httpx_mock: HTTPXMock
):
    from app.services.asset_downloader import localize_assets

    url = "https://slow.example.com/x.png"
    for _ in range(3):
        httpx_mock.add_exception(httpx.ReadTimeout("too slow"), url=url)

    md = f"![]({url})\n"
    out, status = await localize_assets(md, slug, vault)

    assert status[url] == "failed"
    assert f"> [!warning] Image unavailable: {url}" in out


@pytest.mark.asyncio
async def test_retry_succeeds_on_second_attempt(vault, slug, httpx_mock: HTTPXMock):
    from app.services.asset_downloader import localize_assets

    url = "https://flaky.example.com/x.png"
    httpx_mock.add_exception(httpx.ConnectError("flake"), url=url)
    httpx_mock.add_response(
        url=url, content=PNG_1PX, headers={"Content-Type": "image/png"}
    )

    md = f"![]({url})\n"
    out, status = await localize_assets(md, slug, vault)

    assert status[url] == "ok"
    assert "[!warning]" not in out
    assert _attachments(vault, slug).exists()


@pytest.mark.asyncio
async def test_dedup_via_shared_cache(vault, slug, httpx_mock: HTTPXMock):
    """
    Pass 1 = raw note, pass 2 = wiki note.  Same URL appears in both.
    pytest-httpx asserts every registered response is consumed -- so registering
    only ONE response proves the second pass did not re-download.
    """
    from app.services.asset_downloader import localize_assets

    url = "https://shared.example.com/cover.png"
    httpx_mock.add_response(
        url=url, content=PNG_1PX, headers={"Content-Type": "image/png"}
    )

    cache: dict[str, str] = {}
    md_raw = f"raw note\n\n![cover]({url})\n"
    md_wiki = f"wiki entry referencing same image\n\n![cover]({url})\n"

    out_raw, st_raw = await localize_assets(md_raw, slug, vault, cache=cache)
    out_wiki, st_wiki = await localize_assets(md_wiki, slug, vault, cache=cache)

    expected_rel = f"attachments/{slug}/img-001-{_sha8(PNG_1PX)}.png"
    assert expected_rel in out_raw
    assert expected_rel in out_wiki
    assert st_raw[url] == "ok"
    assert st_wiki[url] == "cached"
    saved = list(_attachments(vault, slug).iterdir())
    assert len(saved) == 1


@pytest.mark.asyncio
async def test_dedup_within_single_pass(vault, slug, httpx_mock: HTTPXMock):
    from app.services.asset_downloader import localize_assets

    url = "https://repeat.example.com/x.png"
    httpx_mock.add_response(
        url=url, content=PNG_1PX, headers={"Content-Type": "image/png"}
    )

    md = f"![first]({url})\n\nbody\n\n![second]({url})\n"
    out, status = await localize_assets(md, slug, vault)

    assert status[url] == "ok"
    saved = list(_attachments(vault, slug).iterdir())
    assert len(saved) == 1
    assert out.count(f"attachments/{slug}/img-001-") == 2


@pytest.mark.asyncio
async def test_html_img_tag_src_rewritten(vault, slug, httpx_mock: HTTPXMock):
    from app.services.asset_downloader import localize_assets

    url = "https://cdn.example.com/figure.png"
    httpx_mock.add_response(
        url=url, content=PNG_1PX, headers={"Content-Type": "image/png"}
    )

    md = (
        "intro\n\n"
        f'<figure><img src="{url}" alt="caption"><figcaption>x</figcaption></figure>\n\n'
        "end\n"
    )
    out, status = await localize_assets(md, slug, vault)

    rel = f"attachments/{slug}/img-001-{_sha8(PNG_1PX)}.png"
    assert status[url] == "ok"
    assert f'src="{rel}"' in out
    assert url not in out
    assert "<figure>" in out and "<figcaption>" in out
    assert (vault / rel).exists()


@pytest.mark.asyncio
async def test_fenced_code_block_images_not_rewritten(
    vault, slug, httpx_mock: HTTPXMock
):
    from app.services.asset_downloader import localize_assets

    url_in_code = "https://example.com/literal-example.png"
    url_real = "https://real.example.com/actual.png"
    httpx_mock.add_response(
        url=url_real, content=PNG_1PX, headers={"Content-Type": "image/png"}
    )

    md = (
        f"![real]({url_real})\n\n"
        "Here is how to embed an image:\n\n"
        "```markdown\n"
        f"![ignored]({url_in_code})\n"
        "```\n\n"
        "end\n"
    )
    out, status = await localize_assets(md, slug, vault)

    assert status.get(url_real) == "ok"
    assert url_in_code not in status
    assert f"![ignored]({url_in_code})" in out
    assert f"attachments/{slug}/img-001-" in out
    saved = list(_attachments(vault, slug).iterdir())
    assert len(saved) == 1


@pytest.mark.asyncio
async def test_local_paths_left_unchanged(vault, slug, httpx_mock: HTTPXMock):
    from app.services.asset_downloader import localize_assets

    remote = "https://example.com/real.png"
    httpx_mock.add_response(
        url=remote, content=PNG_1PX, headers={"Content-Type": "image/png"}
    )

    md = (
        f"![remote]({remote})\n\n"
        "![pdf-extract](image_001.png)\n\n"
        "![root-relative](/static/foo.jpg)\n\n"
        "![doc-relative](./fig.svg)\n"
    )
    out, status = await localize_assets(md, slug, vault)

    assert status == {remote: "ok"}
    assert "![pdf-extract](image_001.png)" in out
    assert "![root-relative](/static/foo.jpg)" in out
    assert "![doc-relative](./fig.svg)" in out
    assert remote not in out
    assert f"attachments/{slug}/img-001-" in out
