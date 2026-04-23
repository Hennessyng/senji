import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.models.schemas import IngestUrlRequest, IngestUrlResponse
from app.services.job_queue import IngestJob

logger = logging.getLogger("senji.pics.ingest_url")

router = APIRouter(prefix="/api/ingest")


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
