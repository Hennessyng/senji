import logging
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from app.config import settings
from app.models.schemas import IngestFileResponse, IngestUrlRequest, IngestUrlResponse
from app.services.job_queue import IngestJob

logger = logging.getLogger("senji.pics.ingest")

router = APIRouter(prefix="/api/ingest")

_ALLOWED_PDF_TYPES = {"application/pdf"}
_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_UNSUPPORTED_IMAGE_TYPES = {"image/heic", "image/heif"}
_CHUNK_SIZE = 64 * 1024


@router.post("/url", status_code=202, response_model=IngestUrlResponse)
async def ingest_url(
    body: IngestUrlRequest, request: Request
) -> IngestUrlResponse | JSONResponse:
    queue = request.app.state.job_queue
    job = IngestJob(
        type="url",
        source_url=str(body.url),
        tags=list(body.tags),
    )
    queue.enqueue(job)
    logger.info(
        "Ingest URL accepted",
        extra={"job_id": job.job_id, "url": str(body.url), "tags": body.tags},
    )
    return IngestUrlResponse(job_id=job.job_id, status="queued")


@router.post("/file", status_code=202, response_model=IngestFileResponse)
async def ingest_file(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    tags: Annotated[list[str] | None, Form()] = None,
) -> IngestFileResponse | JSONResponse:
    if tags is None:
        tags = []
    content_type = (file.content_type or "").lower()

    if content_type in _ALLOWED_PDF_TYPES:
        job_type = "pdf"
    elif content_type in _ALLOWED_IMAGE_TYPES:
        ollama = getattr(request.app.state, "ollama_client", None)
        if ollama is None or not getattr(ollama, "available", False):
            logger.warning(
                "Ollama preflight failed for image ingest",
                extra={
                    "content_type": content_type,
                    "upload_filename": file.filename,
                },
            )
            return JSONResponse(
                status_code=503,
                content={
                    "error": "ollama_unavailable",
                    "detail": (
                        "Ollama VLM is required for image ingestion but is not "
                        "currently available"
                    ),
                },
            )
        job_type = "image"
    elif content_type in _UNSUPPORTED_IMAGE_TYPES:
        return JSONResponse(
            status_code=415,
            content={
                "error": "unsupported_media_type",
                "detail": (
                    "HEIC not supported — convert to JPEG/PNG/WebP "
                    "client-side"
                ),
            },
        )
    else:
        return JSONResponse(
            status_code=415,
            content={
                "error": "unsupported_media_type",
                "detail": f"content-type {content_type!r} not supported",
            },
        )

    max_bytes = settings.max_file_size_mb * 1024 * 1024
    tmp_dir = Path(tempfile.gettempdir()) / "senji-ingest"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "upload.pdf").suffix or ".pdf"
    tmp_fd, tmp_path_str = tempfile.mkstemp(suffix=suffix, dir=str(tmp_dir))
    tmp_path = Path(tmp_path_str)

    total = 0
    try:
        with open(tmp_fd, "wb") as out:
            while True:
                chunk = await file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    out.close()
                    tmp_path.unlink(missing_ok=True)
                    logger.warning(
                        "File too large",
                        extra={
                            "pdf_file": file.filename,
                            "limit_mb": settings.max_file_size_mb,
                        },
                    )
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": "file_too_large",
                            "detail": (
                                f"file exceeds {settings.max_file_size_mb}MB limit"
                            ),
                        },
                    )
                out.write(chunk)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    queue = request.app.state.job_queue
    job = IngestJob(
        type=job_type,
        source_path=str(tmp_path),
        original_filename=file.filename or tmp_path.name,
        tags=list(tags),
    )
    queue.enqueue(job)
    logger.info(
        "Ingest file accepted",
        extra={
            "job_id": job.job_id,
            "job_type": job_type,
            "content_type": content_type,
            "upload_filename": file.filename,
            "bytes": total,
            "tags": tags,
        },
    )
    return IngestFileResponse(job_id=job.job_id, status="queued")


@router.get("/jobs/{job_id}")
async def get_job_status(request: Request, job_id: str) -> JSONResponse:
    queue = request.app.state.job_queue
    try:
        job = queue.get_status(job_id)
        return JSONResponse(
            status_code=200,
            content={
                "job_id": job.job_id,
                "type": job.type,
                "status": job.status,
                "files_written": job.files_written,
                "error_detail": job.error_detail,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            },
        )
    except ValueError:
        logger.warning("Job not found", extra={"job_id": job_id})
        return JSONResponse(
            status_code=404,
            content={"error": "job_not_found", "detail": f"Job {job_id!r} not found"},
        )
