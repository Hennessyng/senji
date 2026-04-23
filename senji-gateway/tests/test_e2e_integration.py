"""
E2E Integration Tests — senji-pics pipeline.

Covers the full ingest → job queue → vault write → LLM wiki → embeddings flow.
Uses ASGI transport (no real HTTP server) with controlled mocks for external
services (Ollama, URL fetcher, PDF extractor, embeddings).

Scenarios:
  1. URL Ingest E2E — full happy path
  2. PDF Ingest E2E — full happy path
  3. Ollama Unavailable — raw-only fallback
  4. Concurrent Requests — 3 parallel POSTs
  5. Duplicate Prevention — index.md not duplicated
"""

import asyncio
import io
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.errors import OllamaUnavailableError
from app.main import app
from app.services.job_queue import JobQueue
from app.services.vault_writer import VaultWriter

AUTH = {"Authorization": "Bearer dev-token"}
TEST_URL = "https://example.com/test-article"
TEST_TITLE = "Test Article"
TEST_MARKDOWN = "# Test Article\n\nThis is the test article content for E2E testing."

# Minimal valid-enough PDF bytes (mocked extraction so content doesn't matter)
MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n%%EOF"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def build_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


def _make_mock_ollama() -> MagicMock:
    mock = MagicMock()
    mock.available = True
    mock.generate = AsyncMock(return_value="## Wiki\n\nSummary of the test article.")
    mock.health_check = AsyncMock(return_value=None)
    return mock


def patch_url_fetch(monkeypatch, title: str = TEST_TITLE, markdown: str = TEST_MARKDOWN) -> None:
    async def fake_fetch(self, url: str) -> str:
        return f"<html><body><article><h1>{title}</h1><p>Content.</p></article></body></html>"

    def fake_extract(html: str, source: str) -> dict:
        return {
            "markdown": markdown,
            "title": title,
            "author": "Test Author",
            "language": "en",
            "description": "Test description",
        }

    monkeypatch.setattr(JobQueue, "_fetch_html", fake_fetch)
    monkeypatch.setattr("app.services.job_queue.extract_article", fake_extract)


def patch_embeddings(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.job_queue.EmbeddingService.embed_text",
        AsyncMock(return_value=[0.1] * 384),
    )
    monkeypatch.setattr(
        "app.services.job_queue.EmbeddingService.save_embedding",
        MagicMock(return_value=None),
    )


def patch_pdf_extraction(monkeypatch, markdown: str = "# PDF Title\n\nExtracted content.") -> None:
    mock_doc = MagicMock()
    mock_doc.page_count = 2
    mock_doc.__enter__ = MagicMock(return_value=mock_doc)
    mock_doc.__exit__ = MagicMock(return_value=False)

    monkeypatch.setattr(
        "app.services.job_queue.pymupdf.open",
        MagicMock(return_value=mock_doc),
    )
    monkeypatch.setattr(
        "app.services.job_queue.pymupdf4llm.to_markdown",
        MagicMock(return_value=markdown),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def vault(tmp_path) -> VaultWriter:
    return VaultWriter(str(tmp_path / "vault"))


@pytest.fixture
def queue(tmp_path, vault) -> JobQueue:
    return JobQueue(
        str(tmp_path / "jobs.db"),
        vault_writer=vault,
        ollama_client=_make_mock_ollama(),
    )


@pytest.fixture
def app_state(queue, vault):
    prev_queue = getattr(app.state, "job_queue", None)
    prev_vault = getattr(app.state, "vault_writer", None)
    prev_ollama = getattr(app.state, "ollama_client", None)

    app.state.job_queue = queue
    app.state.vault_writer = vault
    app.state.ollama_client = queue._ollama_client

    yield

    if prev_queue is not None:
        app.state.job_queue = prev_queue
    if prev_vault is not None:
        app.state.vault_writer = prev_vault
    if prev_ollama is not None:
        app.state.ollama_client = prev_ollama


# ---------------------------------------------------------------------------
# Scenario 1: URL Ingest E2E
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_url_ingest_full_pipeline(
    app_state, queue, tmp_path, monkeypatch
) -> None:
    """
    POST /api/ingest/url → 202 → job queued → processed →
    raw saved, wiki saved, index.md updated, job completed.
    Total time must be <60 s.
    """
    patch_url_fetch(monkeypatch)
    patch_embeddings(monkeypatch)

    start = time.perf_counter()

    async with build_client() as client:
        response = await client.post(
            "/api/ingest/url",
            json={"url": TEST_URL, "tags": ["e2e", "test"]},
            headers=AUTH,
        )

    # 1. HTTP layer
    assert response.status_code == 202, response.text
    data = response.json()
    job_id = data["job_id"]
    assert data["status"] == "queued"

    # 2. Job exists in DB as queued
    job = queue.get_status(job_id)
    assert job.status == "queued"
    assert job.type == "url"
    assert job.source_url == TEST_URL

    # 3. Process (simulates the background worker)
    await queue.process_url_job(job_id)

    elapsed = time.perf_counter() - start
    assert elapsed < 60, f"Pipeline took {elapsed:.1f}s (limit 60 s)"

    # 4. Job terminal state
    job = queue.get_status(job_id)
    assert job.status in ("completed", "completed_raw_only"), (
        f"status={job.status!r}, detail={job.error_detail!r}"
    )
    assert len(job.files_written) >= 1

    vault_root = tmp_path / "vault"
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    # 5. Raw article saved to vault/raw/{YYYY-MM-DD}-{slug}.md
    raw_files = list((vault_root / "raw").glob("*.md"))
    assert len(raw_files) == 1, f"Expected 1 raw file, got {len(raw_files)}"
    raw_path = raw_files[0]
    assert raw_path.name.startswith(today), raw_path.name
    raw_content = raw_path.read_text(encoding="utf-8")
    assert raw_content.startswith("---\n"), "Missing YAML frontmatter"
    assert 'title: "Test Article"' in raw_content
    assert f'source: "{TEST_URL}"' in raw_content
    assert "# Test Article" in raw_content

    # 6. Wiki entry saved to vault/wiki/{slug}.md
    wiki_files = list((vault_root / "wiki").glob("*.md"))
    assert len(wiki_files) == 1, f"Expected 1 wiki file, got {len(wiki_files)}"
    wiki_content = wiki_files[0].read_text(encoding="utf-8")
    assert len(wiki_content.strip()) > 0

    # 7. index.md updated with article link
    index_path = vault_root / "index.md"
    assert index_path.exists(), "index.md was not created"
    index_content = index_path.read_text(encoding="utf-8")
    assert today in index_content, "Expected today's date in index.md"


# ---------------------------------------------------------------------------
# Scenario 2: PDF Ingest E2E
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pdf_ingest_full_pipeline(
    app_state, queue, tmp_path, monkeypatch
) -> None:
    """
    POST /api/ingest/file (PDF) → 202 → processed →
    raw saved, index.md updated, job completed.
    """
    patch_pdf_extraction(monkeypatch)
    patch_embeddings(monkeypatch)

    async with build_client() as client:
        response = await client.post(
            "/api/ingest/file",
            files={"file": ("sample.pdf", io.BytesIO(MINIMAL_PDF), "application/pdf")},
            data={"tags": ["pdf-test"]},
            headers=AUTH,
        )

    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    assert response.json()["status"] == "queued"

    await queue.process_pdf_job(job_id)

    job = queue.get_status(job_id)
    assert job.status in ("completed", "completed_raw_only"), (
        f"status={job.status!r}, detail={job.error_detail!r}"
    )

    vault_root = tmp_path / "vault"
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    raw_files = list((vault_root / "raw").glob("*.md"))
    assert len(raw_files) == 1, f"Expected 1 raw file, got {len(raw_files)}"
    raw_content = raw_files[0].read_text(encoding="utf-8")
    assert raw_content.startswith("---\n"), "Missing YAML frontmatter"
    assert 'type: "pdf"' in raw_content

    index_path = vault_root / "index.md"
    assert index_path.exists(), "index.md was not created"
    assert today in index_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Scenario 3: Ollama Unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ollama_unavailable_saves_raw_only(tmp_path, monkeypatch) -> None:
    """
    When Ollama is unavailable (generate_wiki_entry raises OllamaUnavailableError):
    - Raw article IS saved
    - Wiki file is NOT created
    - Job status is completed_raw_only
    """
    patch_url_fetch(monkeypatch)
    patch_embeddings(monkeypatch)

    # Bypass wiki_service's internal catch: raise directly from the patched import
    monkeypatch.setattr(
        "app.services.job_queue.generate_wiki_entry",
        AsyncMock(side_effect=OllamaUnavailableError("Ollama offline")),
    )

    vault = VaultWriter(str(tmp_path / "vault"))
    mock_ollama = _make_mock_ollama()
    mock_ollama.available = False
    degraded_queue = JobQueue(
        str(tmp_path / "jobs.db"),
        vault_writer=vault,
        ollama_client=mock_ollama,  # not None → wiki_attempted=True
    )

    prev_queue = getattr(app.state, "job_queue", None)
    prev_vault = getattr(app.state, "vault_writer", None)
    app.state.job_queue = degraded_queue
    app.state.vault_writer = vault

    try:
        async with build_client() as client:
            response = await client.post(
                "/api/ingest/url",
                json={"url": TEST_URL},
                headers=AUTH,
            )

        assert response.status_code == 202, response.text
        job_id = response.json()["job_id"]

        await degraded_queue.process_url_job(job_id)

        job = degraded_queue.get_status(job_id)
        assert job.status == "completed_raw_only", (
            f"Expected completed_raw_only, got {job.status!r}"
        )

        raw_files = list((tmp_path / "vault" / "raw").glob("*.md"))
        assert len(raw_files) == 1, "Raw file should exist even without Ollama"

        wiki_files = list((tmp_path / "vault" / "wiki").glob("*.md"))
        assert len(wiki_files) == 0, (
            f"Wiki should not be written when Ollama unavailable, found: {wiki_files}"
        )

    finally:
        if prev_queue is not None:
            app.state.job_queue = prev_queue
        if prev_vault is not None:
            app.state.vault_writer = prev_vault


# ---------------------------------------------------------------------------
# Scenario 4: Concurrent Requests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_url_ingests_all_complete(
    app_state, queue, tmp_path, monkeypatch
) -> None:
    """
    3 parallel POST requests → all queued with unique job IDs →
    processed sequentially → 3 raw files → all jobs completed.
    Total time <180 s.
    """
    urls = [
        "https://example.com/alpha",
        "https://example.com/beta",
        "https://example.com/gamma",
    ]
    titles = ["Alpha Article", "Beta Article", "Gamma Article"]

    url_to_title = dict(zip(urls, titles))

    async def fake_fetch(self, url: str) -> str:
        title = url_to_title[url]
        return f"<html><body><h1>{title}</h1><p>Body.</p></body></html>"

    def fake_extract(html: str, source: str) -> dict:
        title = url_to_title.get(source, "Unknown")
        return {
            "markdown": f"# {title}\n\nContent.",
            "title": title,
            "author": None,
            "language": "en",
            "description": None,
        }

    monkeypatch.setattr(JobQueue, "_fetch_html", fake_fetch)
    monkeypatch.setattr("app.services.job_queue.extract_article", fake_extract)
    patch_embeddings(monkeypatch)

    start = time.perf_counter()

    async with build_client() as client:
        responses = await asyncio.gather(*[
            client.post(
                "/api/ingest/url",
                json={"url": url},
                headers=AUTH,
            )
            for url in urls
        ])

    assert all(r.status_code == 202 for r in responses), (
        f"Expected all 202, got: {[r.status_code for r in responses]}"
    )

    job_ids = [r.json()["job_id"] for r in responses]
    assert len(set(job_ids)) == 3, f"Job IDs not unique: {job_ids}"

    # Process sequentially (mirrors the single-threaded worker)
    for job_id in job_ids:
        await queue.process_url_job(job_id)

    elapsed = time.perf_counter() - start
    assert elapsed < 180, f"Concurrent pipeline took {elapsed:.1f}s (limit 180 s)"

    for job_id in job_ids:
        job = queue.get_status(job_id)
        assert job.status in ("completed", "completed_raw_only"), (
            f"job {job_id}: status={job.status!r}, detail={job.error_detail!r}"
        )

    raw_files = list((tmp_path / "vault" / "raw").glob("*.md"))
    assert len(raw_files) == 3, (
        f"Expected 3 raw files (one per article), got {len(raw_files)}"
    )


# ---------------------------------------------------------------------------
# Scenario 5: Duplicate Prevention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_url_index_entry_not_duplicated(
    app_state, queue, tmp_path, monkeypatch
) -> None:
    """
    Same URL posted twice → both processed →
    index.md contains slug exactly once (duplicate prevention).
    """
    patch_url_fetch(monkeypatch)
    patch_embeddings(monkeypatch)

    async with build_client() as client:
        r1 = await client.post(
            "/api/ingest/url",
            json={"url": TEST_URL},
            headers=AUTH,
        )
        r2 = await client.post(
            "/api/ingest/url",
            json={"url": TEST_URL},
            headers=AUTH,
        )

    assert r1.status_code == 202
    assert r2.status_code == 202

    job_id_1 = r1.json()["job_id"]
    job_id_2 = r2.json()["job_id"]
    assert job_id_1 != job_id_2, "Each POST should produce a distinct job ID"

    await queue.process_url_job(job_id_1)
    await queue.process_url_job(job_id_2)

    for jid in (job_id_1, job_id_2):
        job = queue.get_status(jid)
        assert job.status in ("completed", "completed_raw_only"), (
            f"job {jid}: {job.status!r} / {job.error_detail!r}"
        )

    index_path = tmp_path / "vault" / "index.md"
    assert index_path.exists(), "index.md must exist"

    index_content = index_path.read_text(encoding="utf-8")
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    # Count table rows that contain today's date (both jobs share the same slug)
    duplicate_lines = [
        line
        for line in index_content.splitlines()
        if line.startswith("|") and today in line
    ]
    assert len(duplicate_lines) == 1, (
        f"Expected 1 index entry for the slug, found {len(duplicate_lines)}:\n"
        f"{index_content}"
    )
