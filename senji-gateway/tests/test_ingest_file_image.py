from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.errors import OllamaUnavailableError
from app.main import app
from app.services.job_queue import IngestJob, JobQueue
from app.services.vault_writer import VaultWriter

AUTH = {"Authorization": "Bearer dev-token"}

JPEG_STUB = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\x00" * 64
PNG_STUB = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP_STUB = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 64
HEIC_STUB = b"\x00\x00\x00\x20ftypheic" + b"\x00" * 32
OVERSIZED_IMG = b"\x00" * (51 * 1024 * 1024)


def build_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.fixture
def mock_queue():
    queue = MagicMock()
    queue.enqueue = MagicMock(return_value="job-img-123")
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


@pytest.fixture
def mock_ollama_up():
    ollama = MagicMock()
    ollama.available = True
    original = getattr(app.state, "ollama_client", None)
    app.state.ollama_client = ollama
    yield ollama
    if original is None:
        try:
            delattr(app.state, "ollama_client")
        except AttributeError:
            pass
    else:
        app.state.ollama_client = original


@pytest.fixture
def mock_ollama_down():
    ollama = MagicMock()
    ollama.available = False
    original = getattr(app.state, "ollama_client", None)
    app.state.ollama_client = ollama
    yield ollama
    if original is None:
        try:
            delattr(app.state, "ollama_client")
        except AttributeError:
            pass
    else:
        app.state.ollama_client = original


# -------------------- Handler tests --------------------


@pytest.mark.asyncio
async def test_post_image_returns_202_with_job_id(mock_queue, mock_ollama_up) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/ingest/file",
            headers=AUTH,
            files={"file": ("photo.jpg", JPEG_STUB, "image/jpeg")},
            data={"tags": ["photo", "test"]},
        )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["job_id"]
    assert body["status"] == "queued"
    assert mock_queue.enqueue.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filename,ctype,stub",
    [
        ("a.jpg", "image/jpeg", JPEG_STUB),
        ("b.png", "image/png", PNG_STUB),
        ("c.webp", "image/webp", WEBP_STUB),
    ],
)
async def test_accepts_jpeg_png_webp(
    mock_queue, mock_ollama_up, filename, ctype, stub
) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/ingest/file",
            headers=AUTH,
            files={"file": (filename, stub, ctype)},
        )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "queued"


@pytest.mark.asyncio
async def test_heic_returns_415_with_conversion_note(
    mock_queue, mock_ollama_up
) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/ingest/file",
            headers=AUTH,
            files={"file": ("pic.heic", HEIC_STUB, "image/heic")},
        )
    assert response.status_code == 415
    body = response.json()
    assert body["error"] == "unsupported_media_type"
    detail = (body.get("detail") or "").lower()
    assert "heic" in detail
    assert "convert" in detail


@pytest.mark.asyncio
async def test_ollama_down_preflight_returns_503(
    mock_queue, mock_ollama_down
) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/ingest/file",
            headers=AUTH,
            files={"file": ("p.png", PNG_STUB, "image/png")},
        )
    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "ollama_unavailable"
    # Queue must NOT have been hit on preflight failure.
    assert mock_queue.enqueue.call_count == 0


@pytest.mark.asyncio
async def test_file_over_50mb_rejected(mock_queue, mock_ollama_up) -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/ingest/file",
            headers=AUTH,
            files={"file": ("big.jpg", OVERSIZED_IMG, "image/jpeg")},
        )
    assert response.status_code == 413
    assert response.json().get("error") == "file_too_large"


@pytest.mark.asyncio
async def test_missing_bearer_token_returns_401() -> None:
    async with build_client() as client:
        response = await client.post(
            "/api/ingest/file",
            files={"file": ("p.jpg", JPEG_STUB, "image/jpeg")},
        )
    assert response.status_code == 401


# -------------------- Worker tests --------------------


@pytest.mark.asyncio
async def test_vlm_response_saved_as_raw_markdown(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault = VaultWriter(str(vault_root))

    ollama = MagicMock()
    ollama.available = True
    vlm_markdown = (
        "A sunset over a mountain range.\n\n## OCR\n\nWelcome to Yosemite"
    )
    ollama.describe_image = AsyncMock(return_value=vlm_markdown)

    q = JobQueue(
        str(tmp_path / "jobs.db"),
        vault_writer=vault,
        ollama_client=ollama,
    )

    img_path = tmp_path / "photo.jpg"
    img_path.write_bytes(JPEG_STUB)

    job = IngestJob(
        type="image",
        source_path=str(img_path),
        original_filename="Sunset-Yosemite.jpg",
        tags=["travel", "scenery"],
    )
    q.enqueue(job)
    await q.process_image_job(job.job_id)

    fetched = q.get_status(job.job_id)
    assert fetched.status == "completed", fetched.error_detail
    assert len(fetched.files_written) >= 1

    raw_md = Path(fetched.files_written[0])
    assert raw_md.exists()
    text = raw_md.read_text(encoding="utf-8")
    assert "---" in text
    assert 'type: "image"' in text
    assert 'content_type: "image/jpeg"' in text
    assert '"travel"' in text and '"scenery"' in text
    assert "sunset" in text.lower()
    assert "OCR" in text

    # Asset copy preserved alongside raw vault
    assets_dir = vault_root / "raw" / "assets"
    copies = list(assets_dir.glob("*.jpg"))
    assert len(copies) == 1, f"expected 1 jpg in assets, got {copies}"
    assert copies[0].read_bytes() == JPEG_STUB

    # Ollama was called with the VLM model from config
    call = ollama.describe_image.await_args
    assert call is not None
    kwargs = call.kwargs
    args = call.args
    model_used = kwargs.get("model") or (args[1] if len(args) > 1 else None)
    assert model_used == "qwen2.5vl:7b"

    # Temp file cleaned up
    assert not img_path.exists()


@pytest.mark.asyncio
async def test_ollama_down_mid_worker_fails_job(tmp_path: Path) -> None:
    vault = VaultWriter(str(tmp_path / "vault"))

    ollama = MagicMock()
    ollama.available = True
    ollama.describe_image = AsyncMock(
        side_effect=OllamaUnavailableError("connection lost")
    )

    q = JobQueue(
        str(tmp_path / "jobs.db"),
        vault_writer=vault,
        ollama_client=ollama,
    )

    img_path = tmp_path / "lost.png"
    img_path.write_bytes(PNG_STUB)

    job = IngestJob(
        type="image",
        source_path=str(img_path),
        original_filename="lost.png",
        tags=[],
    )
    q.enqueue(job)
    await q.process_image_job(job.job_id)

    fetched = q.get_status(job.job_id)
    assert fetched.status == "failed"
    err = (fetched.error_detail or "").lower()
    assert "ollama" in err or "unavailable" in err or "connection" in err

    # Temp file cleaned up even on failure
    assert not img_path.exists()
