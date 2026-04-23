import time
from datetime import datetime, timezone

import httpx
import pytest

from app.main import app
from app.services.job_queue import IngestJob, JobQueue
from app.services.vault_writer import VaultWriter

AUTH = {"Authorization": "Bearer dev-token"}


@pytest.fixture
def app_with_queue(tmp_path):
    vault = VaultWriter(str(tmp_path / "vault"))
    queue = JobQueue(str(tmp_path / "jobs.db"), vault_writer=vault)
    previous_queue = getattr(app.state, "job_queue", None)
    previous_vault = getattr(app.state, "vault_writer", None)
    app.state.job_queue = queue
    app.state.vault_writer = vault
    try:
        yield app, queue, vault, tmp_path
    finally:
        if previous_queue is not None:
            app.state.job_queue = previous_queue
        if previous_vault is not None:
            app.state.vault_writer = previous_vault


def build_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.asyncio
async def test_post_url_returns_202_with_job_id(app_with_queue) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/ingest/url",
            json={"url": "https://example.com"},
            headers=AUTH,
        )

    assert response.status_code == 202
    data = response.json()
    assert isinstance(data["job_id"], str) and data["job_id"]
    assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_invalid_url_returns_422(app_with_queue) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/ingest/url",
            json={"url": "not-a-url"},
            headers=AUTH,
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_missing_bearer_token_returns_401(app_with_queue) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/ingest/url",
            json={"url": "https://example.com"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_enqueues_ingest_job(app_with_queue) -> None:
    _, queue, _, _ = app_with_queue
    async with build_client() as client:
        response = await client.post(
            "/api/ingest/url",
            json={"url": "https://example.com", "tags": ["alpha", "beta"]},
            headers=AUTH,
        )

    assert response.status_code == 202
    job_id = response.json()["job_id"]
    job = queue.get_status(job_id)
    assert job.type == "url"
    assert job.tags == ["alpha", "beta"]
    assert job.source_url.startswith("https://example.com")
    assert job.status == "queued"


@pytest.mark.asyncio
async def test_202_returns_under_100ms(app_with_queue) -> None:
    async with build_client() as client:
        start = time.perf_counter()
        response = await client.post(
            "/api/ingest/url",
            json={"url": "https://example.com"},
            headers=AUTH,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

    assert response.status_code == 202
    assert elapsed_ms < 100, f"handler took {elapsed_ms:.1f}ms (>=100ms)"


@pytest.mark.asyncio
async def test_trafilatura_empty_extraction_fails_job(app_with_queue, monkeypatch) -> None:
    _, queue, _, _ = app_with_queue

    async def fake_fetch(self, url):
        return "<html><body></body></html>"

    def fake_extract(html, source):
        return {
            "markdown": "",
            "title": "x",
            "author": None,
            "language": None,
            "publish_date": None,
        }

    monkeypatch.setattr(JobQueue, "_fetch_html", fake_fetch)
    monkeypatch.setattr("app.services.job_queue.extract_article", fake_extract)

    job = IngestJob(type="url", source_url="https://example.com", tags=[])
    queue.enqueue(job)
    await queue.process_url_job(job.job_id)

    status = queue.get_status(job.job_id)
    assert status.status == "failed"
    assert "empty" in (status.error_detail or "").lower()


@pytest.mark.asyncio
async def test_raw_markdown_saved_to_vault(app_with_queue, monkeypatch) -> None:
    _, queue, _, tmp_path = app_with_queue

    async def fake_fetch(self, url):
        return "<html><body><article><h1>Hello World</h1><p>Test.</p></article></body></html>"

    def fake_extract(html, source):
        return {
            "markdown": "# Hello World\n\nTest.",
            "title": "Hello World",
            "author": "Alice",
            "language": "en",
            "publish_date": "2026-04-23",
        }

    monkeypatch.setattr(JobQueue, "_fetch_html", fake_fetch)
    monkeypatch.setattr("app.services.job_queue.extract_article", fake_extract)

    job = IngestJob(
        type="url",
        source_url="https://example.com/article",
        tags=["clipping", "inbox"],
    )
    queue.enqueue(job)
    await queue.process_url_job(job.job_id)

    status = queue.get_status(job.job_id)
    assert status.status == "completed", (
        f"expected completed, got {status.status} / {status.error_detail}"
    )

    raw_files = list((tmp_path / "vault" / "raw").glob("*.md"))
    assert len(raw_files) == 1, f"expected 1 raw md file, got {len(raw_files)}"

    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    assert raw_files[0].name.startswith(today), raw_files[0].name
    assert raw_files[0].name.endswith(".md")

    content = raw_files[0].read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert 'title: "Hello World"' in content
    assert 'source: "https://example.com/article"' in content
    assert "type:" in content
    assert "# Hello World" in content
