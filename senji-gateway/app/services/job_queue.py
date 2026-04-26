import asyncio
import base64
import contextlib
import json
import logging
import mimetypes
import os
import shutil
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_JST = ZoneInfo("Asia/Tokyo")
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import httpx
import pymupdf
import pymupdf4llm

from app.config import settings
from app.errors import IngestError, OllamaUnavailableError, WikiError
from app.services.embedding_service import EmbeddingService
from app.services.index_service import append_to_index, append_to_log
from app.services.readability_client import convert_html as readability_convert
from app.services.trafilatura_service import extract_article
from app.services.wiki_service import generate_wiki_entry
from app.utils.slugify import make_slug

if TYPE_CHECKING:
    from app.services.ollama_client import OllamaClient
    from app.services.vault_writer import VaultWriter


_IMAGE_CONTENT_TYPE_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

_VLM_PROMPT = (
    "Describe this image in detail. Extract any visible text under an "
    "'OCR' heading. Output markdown."
)

logger = logging.getLogger("senji.pics.job_queue")
ingest_logger = logging.getLogger("senji.pics.ingest_url")
ingest_file_logger = logging.getLogger("senji.pics.ingest_file")

_FETCH_TIMEOUT_SECONDS = 10.0
_FETCH_RETRIES = 3
_USER_AGENT = "Mozilla/5.0 (compatible; Senji/1.0)"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    source_url TEXT,
    source_path TEXT,
    original_filename TEXT,
    tags TEXT NOT NULL,
    status TEXT NOT NULL,
    files_written TEXT NOT NULL,
    error_detail TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);
"""
_CREATE_IDX_STATUS = "CREATE INDEX IF NOT EXISTS idx_status ON jobs(status);"
_CREATE_IDX_CREATED = "CREATE INDEX IF NOT EXISTS idx_created_at ON jobs(created_at DESC);"


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _dt_to_str(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _str_to_dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s is not None else None


@dataclass
class IngestJob:
    type: Literal["url", "pdf", "image"]
    tags: list[str]
    source_url: str | None = None
    source_path: str | None = None
    original_filename: str | None = None
    status: Literal["queued", "processing", "completed", "completed_raw_only", "failed"] = "queued"
    files_written: list[str] = field(default_factory=list)
    error_detail: str | None = None
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.type:
            raise ValueError("type is required")
        if self.type == "url" and not self.source_url:
            raise ValueError("source_url required for type='url'")
        if self.type in ("pdf", "image") and not self.source_path:
            raise ValueError("source_path required for type='pdf' or 'image'")


class JobQueue:
    def __init__(
        self,
        db_path: str,
        vault_writer: "VaultWriter | None" = None,
        ollama_client: "OllamaClient | None" = None,
        embedding_service: "EmbeddingService | None" = None,
    ) -> None:
        self._db_path = db_path
        self._vault_writer = vault_writer
        self._ollama_client = ollama_client
        self._embedding_service = embedding_service
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(_CREATE_TABLE)
            conn.execute(_CREATE_IDX_STATUS)
            conn.execute(_CREATE_IDX_CREATED)
            conn.commit()

    def enqueue(self, job: IngestJob) -> str:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, type, source_url, source_path, original_filename,
                    tags, status, files_written, error_detail,
                    created_at, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.job_id,
                    job.type,
                    job.source_url,
                    job.source_path,
                    job.original_filename,
                    json.dumps(job.tags),
                    job.status,
                    json.dumps(job.files_written),
                    job.error_detail,
                    _dt_to_str(job.created_at),
                    _dt_to_str(job.started_at),
                    _dt_to_str(job.completed_at),
                ),
            )
            conn.commit()
        logger.info("Job enqueued", extra={"job_id": job.job_id, "type": job.type})
        return job.job_id

    def get_status(self, job_id: str) -> IngestJob:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            raise ValueError(f"Job {job_id!r} not found")
        return self._row_to_job(row)

    def _row_to_job(self, row: tuple) -> IngestJob:
        (
            job_id, type_, source_url, source_path, original_filename,
            tags_json, status, files_json, error_detail,
            created_at_s, started_at_s, completed_at_s,
        ) = row
        return IngestJob(
            job_id=job_id,
            type=type_,
            source_url=source_url,
            source_path=source_path,
            original_filename=original_filename,
            tags=json.loads(tags_json),
            status=status,
            files_written=json.loads(files_json),
            error_detail=error_detail,
            created_at=_str_to_dt(created_at_s),
            started_at=_str_to_dt(started_at_s),
            completed_at=_str_to_dt(completed_at_s),
        )

    def mark_processing(self, job_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET status='processing', started_at=? WHERE job_id=?",
                (_dt_to_str(_now()), job_id),
            )
            conn.commit()
        logger.info("Job processing", extra={"job_id": job_id})

    def mark_completed(self, job_id: str, files_written: list[str]) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET status='completed', files_written=?, completed_at=? WHERE job_id=?",
                (json.dumps(files_written), _dt_to_str(_now()), job_id),
            )
            conn.commit()
        logger.info("Job completed", extra={"job_id": job_id, "files": files_written})

    def mark_failed(self, job_id: str, error: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET status='failed', error_detail=?, completed_at=? WHERE job_id=?",
                (error, _dt_to_str(_now()), job_id),
            )
            conn.commit()
        logger.error("Job failed", extra={"job_id": job_id, "error": error})

    def mark_completed_raw_only(self, job_id: str, files: list[str]) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET status='completed_raw_only', files_written=?, completed_at=? WHERE job_id=?",
                (json.dumps(files), _dt_to_str(_now()), job_id),
            )
            conn.commit()
        logger.info("Job completed_raw_only", extra={"job_id": job_id, "files": files})

    def _get_queued_jobs(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT job_id FROM jobs WHERE status='queued' ORDER BY created_at ASC"
            ).fetchall()
        return [r[0] for r in rows]

    async def _generate_and_save_wiki(
        self,
        slug: str,
        title: str,
        source: str,
        content: str,
        frontmatter: dict,
        language: str = "en",
    ) -> Path | None:
        if self._ollama_client is None or self._vault_writer is None:
            return None
        try:
            wiki_md = await generate_wiki_entry(
                self._ollama_client,
                title=title,
                source=source,
                content=content,
                language=language or "en",
            )
        except (OllamaUnavailableError, WikiError) as exc:
            logger.warning(
                "Wiki generation skipped — continuing raw-only",
                extra={"slug": slug, "source": source, "error_msg": str(exc)},
            )
            return None
        except Exception as exc:
            logger.warning(
                "Wiki generation unexpected failure — continuing raw-only",
                extra={"slug": slug, "source": source, "error_msg": str(exc)},
            )
            return None
        wiki_fm = dict(frontmatter)
        wiki_fm["date"] = datetime.now(tz=_JST).strftime("%Y-%m-%d")
        return self._vault_writer.save_wiki(slug, wiki_md, wiki_fm)

    async def _generate_and_save_embedding(
        self, wiki_path: Path, markdown: str, frontmatter: dict
    ) -> None:
        try:
            embedding_svc = EmbeddingService()
            embedding = await embedding_svc.embed_text(markdown)
            EmbeddingService.save_embedding(wiki_path, embedding, frontmatter)
            logger.debug("Embedding generated", extra={"path": str(wiki_path)})
        except Exception as exc:
            logger.warning(
                "Failed to generate embedding",
                extra={"path": str(wiki_path), "error": str(exc)},
            )

    async def _fetch_html(self, url: str) -> str:
        last_exc: Exception | None = None
        for attempt in range(_FETCH_RETRIES):
            try:
                async with httpx.AsyncClient(
                    timeout=_FETCH_TIMEOUT_SECONDS,
                    follow_redirects=True,
                    headers={"User-Agent": _USER_AGENT},
                ) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    return response.text
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_exc = exc
                ingest_logger.warning(
                    "Fetch attempt failed",
                    extra={"url": url, "attempt": attempt + 1, "error": str(exc)},
                )
                await asyncio.sleep(0.2 * (attempt + 1))
        raise IngestError(
            f"Failed to fetch URL after {_FETCH_RETRIES} attempts",
            detail=str(last_exc) if last_exc else None,
        )

    async def process_url_job(self, job_id: str) -> None:
        job = self.get_status(job_id)
        if job.type != "url" or not job.source_url:
            raise ValueError(f"Job {job_id} is not a URL ingest job")
        if self._vault_writer is None:
            raise RuntimeError("JobQueue has no vault_writer; cannot process URL jobs")

        self.mark_processing(job_id)
        try:
            html = await self._fetch_html(job.source_url)
            try:
                extracted = extract_article(html, job.source_url)
                markdown = extracted.get("markdown") or ""
                if not markdown.strip():
                    raise ValueError("trafilatura returned empty markdown")
            except ValueError:
                logger.warning(
                    "Trafilatura failed for %s, falling back to readability",
                    job.source_url,
                )
                try:
                    readable = await readability_convert(settings.readability_url, html)
                    extracted = {"markdown": readable.markdown, "title": readable.title}
                except Exception as exc:
                    raise IngestError(
                        "trafilatura returned empty content", detail=str(exc)
                    ) from exc

            markdown = extracted.get("markdown") or ""

            title = extracted.get("title") or "untitled"
            date_str = datetime.now(tz=_JST).strftime("%Y-%m-%d")
            slug = make_slug(title, date_prefix=date_str)
            fm = {
                "title": title,
                "source": job.source_url,
                "date": date_str,
                "type": "url",
                "tags": job.tags,
                "language": extracted.get("language"),
                "author": extracted.get("author"),
                "description": extracted.get("description"),
            }
            path = self._vault_writer.save_raw(slug, markdown, fm)
            await self._generate_and_save_embedding(path, markdown, fm)
            wiki_attempted = self._ollama_client is not None
            wiki_path = await self._generate_and_save_wiki(
                slug=slug,
                title=title,
                source=job.source_url,
                content=markdown,
                frontmatter=fm,
                language=extracted.get("language") or "en",
            )
            vault_path = str(self._vault_writer._root)
            append_to_index(vault_path, job_id, slug, title, "url")
            files_written = [str(path)] + ([str(wiki_path)] if wiki_path else [])
            if wiki_attempted and wiki_path is None:
                append_to_log(vault_path, job_id, slug, "url", "completed_raw_only", "")
                self.mark_completed_raw_only(job_id, files=files_written)
            else:
                append_to_log(vault_path, job_id, slug, "url", "completed", "")
                self.mark_completed(job_id, files_written=files_written)
            ingest_logger.info(
                "URL ingest complete",
                extra={
                    "job_id": job_id,
                    "url": job.source_url,
                    "path": str(path),
                    "wiki_path": str(wiki_path) if wiki_path else None,
                },
            )
            if self._embedding_service:
                try:
                    markdown_text = path.read_text(errors="replace").split("\n---\n", 1)[-1]
                    await self._embedding_service.queue_embeddings(job_id, [markdown_text])
                except Exception as _emb_exc:
                    logger.warning(
                        "Failed to queue embeddings",
                        extra={"job_id": job_id, "error": str(_emb_exc)},
                    )
        except IngestError as exc:
            detail = f"{exc.message}: {exc.detail}" if exc.detail else exc.message
            self.mark_failed(job_id, error=detail)
            ingest_logger.error(
                "URL ingest failed",
                extra={"job_id": job_id, "url": job.source_url, "error": detail},
            )
        except Exception as exc:
            self.mark_failed(job_id, error=str(exc))
            ingest_logger.error(
                "URL ingest crashed",
                extra={"job_id": job_id, "url": job.source_url, "error": str(exc)},
                exc_info=True,
            )

    async def process_pdf_job(self, job_id: str) -> None:
        job = self.get_status(job_id)
        if job.type != "pdf" or not job.source_path:
            raise ValueError(f"Job {job_id} is not a PDF ingest job")
        if self._vault_writer is None:
            raise RuntimeError("JobQueue has no vault_writer; cannot process PDF jobs")

        self.mark_processing(job_id)
        tmp_path = Path(job.source_path)
        try:
            try:
                with pymupdf.open(str(tmp_path)) as doc:
                    page_count = int(getattr(doc, "page_count", 0) or 0)
                    markdown = pymupdf4llm.to_markdown(doc)
            except Exception as exc:
                raise IngestError("pymupdf4llm extraction failed", detail=str(exc)) from exc

            if not markdown or not markdown.strip():
                raise IngestError("pymupdf4llm returned empty content")

            original = job.original_filename or tmp_path.name
            title = Path(original).stem or "untitled"
            date_str = datetime.now(tz=_JST).strftime("%Y-%m-%d")
            slug = make_slug(title, date_prefix=date_str)
            fm = {
                "title": title,
                "source": original,
                "date": date_str,
                "type": "pdf",
                "tags": job.tags,
                "pages": page_count,
            }
            path = self._vault_writer.save_raw(slug, markdown, fm)
            await self._generate_and_save_embedding(path, markdown, fm)
            wiki_attempted = self._ollama_client is not None
            wiki_path = await self._generate_and_save_wiki(
                slug=slug,
                title=title,
                source=original,
                content=markdown,
                frontmatter=fm,
                language="en",
            )
            vault_path = str(self._vault_writer._root)
            append_to_index(vault_path, job_id, slug, title, "pdf")
            files_written = [str(path)] + ([str(wiki_path)] if wiki_path else [])
            if wiki_attempted and wiki_path is None:
                append_to_log(vault_path, job_id, slug, "pdf", "completed_raw_only", "")
                self.mark_completed_raw_only(job_id, files=files_written)
            else:
                append_to_log(vault_path, job_id, slug, "pdf", "completed", "")
                self.mark_completed(job_id, files_written=files_written)
            ingest_file_logger.info(
                "PDF ingest complete",
                extra={
                    "job_id": job_id,
                    "original": original,
                    "pages": page_count,
                    "path": str(path),
                },
            )
            if self._embedding_service:
                try:
                    markdown_text = path.read_text(errors="replace").split("\n---\n", 1)[-1]
                    await self._embedding_service.queue_embeddings(job_id, [markdown_text])
                except Exception as _emb_exc:
                    logger.warning(
                        "Failed to queue embeddings",
                        extra={"job_id": job_id, "error": str(_emb_exc)},
                    )
        except IngestError as exc:
            detail = f"{exc.message}: {exc.detail}" if exc.detail else exc.message
            self.mark_failed(job_id, error=detail)
            ingest_file_logger.error(
                "PDF ingest failed",
                extra={
                    "job_id": job_id,
                    "original": job.original_filename,
                    "error": detail,
                },
            )
        except Exception as exc:
            self.mark_failed(job_id, error=str(exc))
            ingest_file_logger.error(
                "PDF ingest crashed",
                extra={
                    "job_id": job_id,
                    "original": job.original_filename,
                    "error": str(exc),
                },
                exc_info=True,
            )
        finally:
            with contextlib.suppress(OSError):
                if tmp_path.exists():
                    os.unlink(tmp_path)

    async def process_image_job(self, job_id: str) -> None:
        job = self.get_status(job_id)
        if job.type != "image" or not job.source_path:
            raise ValueError(f"Job {job_id} is not an image ingest job")
        if self._vault_writer is None:
            raise RuntimeError(
                "JobQueue has no vault_writer; cannot process image jobs"
            )
        if self._ollama_client is None:
            raise RuntimeError(
                "JobQueue has no ollama_client; cannot process image jobs"
            )

        self.mark_processing(job_id)
        tmp_path = Path(job.source_path)
        try:
            original = job.original_filename or tmp_path.name
            ext = Path(original).suffix.lower()
            content_type = _IMAGE_CONTENT_TYPE_BY_EXT.get(
                ext, mimetypes.guess_type(original)[0] or "application/octet-stream"
            )

            image_bytes = tmp_path.read_bytes()
            image_b64 = base64.b64encode(image_bytes).decode("ascii")

            try:
                markdown = await self._ollama_client.describe_image(
                    image_b64,
                    model=settings.ollama_vision_model,
                    prompt=_VLM_PROMPT,
                )
            except OllamaUnavailableError as exc:
                raise IngestError(
                    "Ollama unavailable during image describe",
                    detail=str(exc),
                ) from exc

            if not markdown or not markdown.strip():
                raise IngestError("Ollama VLM returned empty description")

            title = Path(original).stem or "untitled"
            date_str = datetime.now(tz=_JST).strftime("%Y-%m-%d")
            slug = make_slug(title, date_prefix=date_str)
            fm = {
                "title": title,
                "source": original,
                "date": date_str,
                "type": "image",
                "content_type": content_type,
                "tags": job.tags,
            }
            md_path = self._vault_writer.save_raw(slug, markdown, fm)

            asset_dir = self._vault_writer._assets
            asset_dir.mkdir(parents=True, exist_ok=True)
            asset_path = asset_dir / f"{slug}{ext}"
            shutil.copy2(tmp_path, asset_path)

            vault_path = str(self._vault_writer._root)
            append_to_index(vault_path, job_id, slug, title, "image")
            append_to_log(vault_path, job_id, slug, "image", "completed", "")
            self.mark_completed(
                job_id, files_written=[str(md_path), str(asset_path)]
            )
            ingest_file_logger.info(
                "Image ingest complete",
                extra={
                    "job_id": job_id,
                    "original": original,
                    "content_type": content_type,
                    "md_path": str(md_path),
                    "asset_path": str(asset_path),
                },
            )
        except IngestError as exc:
            detail = f"{exc.message}: {exc.detail}" if exc.detail else exc.message
            self.mark_failed(job_id, error=detail)
            ingest_file_logger.error(
                "Image ingest failed",
                extra={
                    "job_id": job_id,
                    "original": job.original_filename,
                    "error": detail,
                },
            )
        except Exception as exc:
            self.mark_failed(job_id, error=str(exc))
            ingest_file_logger.error(
                "Image ingest crashed",
                extra={
                    "job_id": job_id,
                    "original": job.original_filename,
                    "error": str(exc),
                },
                exc_info=True,
            )
        finally:
            with contextlib.suppress(OSError):
                if tmp_path.exists():
                    os.unlink(tmp_path)

    async def _dispatch_job(self, job_id: str) -> None:
        job = self.get_status(job_id)
        if job.type == "url" and self._vault_writer is not None:
            await self.process_url_job(job_id)
        elif job.type == "pdf" and self._vault_writer is not None:
            await self.process_pdf_job(job_id)
        elif (
            job.type == "image"
            and self._vault_writer is not None
            and self._ollama_client is not None
        ):
            await self.process_image_job(job_id)
        else:
            self.mark_processing(job_id)
            await asyncio.sleep(0)
            self.mark_completed(job_id, files_written=[])

    async def worker(self) -> None:
        logger.info("Worker started")
        while True:
            try:
                for job_id in self._get_queued_jobs():
                    await self._dispatch_job(job_id)
            except Exception as exc:
                logger.error("Worker loop error", extra={"error": str(exc)}, exc_info=True)
            await asyncio.sleep(0.05)
