from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.main import app
from app.services.job_queue import IngestJob, JobQueue
from app.services.vault_writer import VaultWriter

AUTH = {"Authorization": "Bearer dev-token"}
PDF_STUB = b"%PDF-1.4\n%stub\n"
OVERSIZED_PDF = b"\x00" * (51 * 1024 * 1024)


def build_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.fixture
def mock_queue():
    queue = MagicMock()
    queue.enqueue = MagicMock(return_value="job-abc-123")
    original = getattr(app.state, "job_queue", None)
    app.state.job_queue = queue
    yield queue
    if original is None:
        try:
            delattr(app.state, "job_queue")
        except AttributeError:
            pass
    else:
        app.state.job_queue = original


@pytest.mark.asyncio
async def test_post_pdf_returns_202_with_job_id(mock_queue) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/ingest/file",
            headers=AUTH,
            files={"file": ("doc.pdf", PDF_STUB, "application/pdf")},
            data={"tags": ["pdf", "test"]},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"]
    assert body["status"] == "queued"
    assert mock_queue.enqueue.call_count == 1


@pytest.mark.asyncio
async def test_non_pdf_content_type_returns_415(mock_queue) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/ingest/file",
            headers=AUTH,
            files={"file": ("archive.zip", b"PK\x03\x04", "application/zip")},
        )
    assert response.status_code == 415
    assert response.json().get("error") == "unsupported_media_type"


@pytest.mark.asyncio
async def test_file_over_50mb_rejected(mock_queue) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/ingest/file",
            headers=AUTH,
            files={"file": ("big.pdf", OVERSIZED_PDF, "application/pdf")},
        )
    assert response.status_code == 413
    assert response.json().get("error") == "file_too_large"


@pytest.mark.asyncio
async def test_missing_bearer_token_returns_401() -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/ingest/file",
            files={"file": ("doc.pdf", PDF_STUB, "application/pdf")},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_pymupdf4llm_empty_extraction_fails_job(tmp_path: Path) -> None:
    vault = VaultWriter(str(tmp_path / "vault"))
    q = JobQueue(str(tmp_path / "jobs.db"), vault_writer=vault)

    pdf_path = tmp_path / "empty.pdf"
    pdf_path.write_bytes(PDF_STUB)

    job = IngestJob(
        type="pdf",
        source_path=str(pdf_path),
        original_filename="empty.pdf",
        tags=["scan"],
    )
    q.enqueue(job)

    with patch("app.services.job_queue.pymupdf4llm") as mock_pm, \
         patch("app.services.job_queue.pymupdf") as mock_fitz:
        mock_pm.to_markdown.return_value = "   "
        mock_doc = MagicMock()
        mock_doc.page_count = 2
        mock_fitz.open.return_value.__enter__.return_value = mock_doc
        await q.process_pdf_job(job.job_id)

    fetched = q.get_status(job.job_id)
    assert fetched.status == "failed"
    assert "empty" in (fetched.error_detail or "").lower()


@pytest.mark.asyncio
async def test_raw_markdown_saved_with_frontmatter(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault = VaultWriter(str(vault_root))
    q = JobQueue(str(tmp_path / "jobs.db"), vault_writer=vault)

    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(PDF_STUB)

    job = IngestJob(
        type="pdf",
        source_path=str(pdf_path),
        original_filename="Q3-Report.pdf",
        tags=["finance", "q3"],
    )
    q.enqueue(job)

    with patch("app.services.job_queue.pymupdf4llm") as mock_pm, \
         patch("app.services.job_queue.pymupdf") as mock_fitz:
        mock_pm.to_markdown.return_value = "# Hello\n\nBody text from PDF."
        mock_doc = MagicMock()
        mock_doc.page_count = 7
        mock_fitz.open.return_value.__enter__.return_value = mock_doc
        await q.process_pdf_job(job.job_id)

    fetched = q.get_status(job.job_id)
    assert fetched.status == "completed", fetched.error_detail
    assert len(fetched.files_written) == 1
    saved = Path(fetched.files_written[0])
    assert saved.exists()
    text = saved.read_text(encoding="utf-8")
    assert "---" in text
    assert 'source: "Q3-Report.pdf"' in text
    assert 'type: "pdf"' in text
    assert "pages: 7" in text
    assert '"finance"' in text and '"q3"' in text
    assert "# Hello" in text
    assert "Body text from PDF." in text


@pytest.mark.asyncio
async def test_temp_file_cleaned_up_after_processing(tmp_path: Path) -> None:
    vault = VaultWriter(str(tmp_path / "vault"))
    q = JobQueue(str(tmp_path / "jobs.db"), vault_writer=vault)

    pdf_path = tmp_path / "cleanup.pdf"
    pdf_path.write_bytes(PDF_STUB)

    job = IngestJob(
        type="pdf",
        source_path=str(pdf_path),
        original_filename="cleanup.pdf",
        tags=[],
    )
    q.enqueue(job)

    with patch("app.services.job_queue.pymupdf4llm") as mock_pm, \
         patch("app.services.job_queue.pymupdf") as mock_fitz:
        mock_pm.to_markdown.return_value = "# Content"
        mock_doc = MagicMock()
        mock_doc.page_count = 1
        mock_fitz.open.return_value.__enter__.return_value = mock_doc
        await q.process_pdf_job(job.job_id)

    assert not pdf_path.exists()
