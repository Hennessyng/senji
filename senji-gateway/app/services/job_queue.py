import asyncio
import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

logger = logging.getLogger("senji.pics.job_queue")

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
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
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

    async def worker(self) -> None:
        logger.info("Worker started")
        while True:
            try:
                for job_id in self._get_queued_jobs():
                    self.mark_processing(job_id)
                    await asyncio.sleep(0)
                    self.mark_completed(job_id, files_written=[])
            except Exception as exc:
                logger.error("Worker loop error", extra={"error": str(exc)}, exc_info=True)
            await asyncio.sleep(0.05)
