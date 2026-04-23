import asyncio
import sqlite3
from datetime import datetime

import pytest

from app.services.job_queue import IngestJob, JobQueue


def make_job(**kwargs) -> IngestJob:
    defaults: dict = dict(
        type="url",
        source_url="https://example.com",
        tags=["test"],
    )
    defaults.update(kwargs)
    return IngestJob(**defaults)


def test_job_creation_url_type() -> None:
    job = make_job(type="url", source_url="https://example.com")
    assert job.type == "url"
    assert job.source_url == "https://example.com"
    assert job.status == "queued"
    assert job.tags == ["test"]
    assert job.job_id


def test_job_creation_pdf_type() -> None:
    job = make_job(type="pdf", source_path="/tmp/foo.pdf", source_url=None)
    assert job.type == "pdf"
    assert job.source_path == "/tmp/foo.pdf"


def test_job_creation_image_type() -> None:
    job = make_job(type="image", source_path="/tmp/photo.jpg", source_url=None)
    assert job.type == "image"
    assert job.source_path == "/tmp/photo.jpg"


def test_job_creation_url_missing_source_raises() -> None:
    with pytest.raises(ValueError, match="source_url required"):
        IngestJob(type="url", tags=["test"])


def test_job_creation_pdf_missing_path_raises() -> None:
    with pytest.raises(ValueError, match="source_path required"):
        IngestJob(type="pdf", tags=["test"])


def test_job_creation_image_missing_path_raises() -> None:
    with pytest.raises(ValueError, match="source_path required"):
        IngestJob(type="image", tags=["test"])


def test_job_defaults() -> None:
    job = make_job()
    assert job.files_written == []
    assert job.error_detail is None
    assert job.started_at is None
    assert job.completed_at is None
    assert isinstance(job.created_at, datetime)


def test_job_ids_are_unique() -> None:
    a = make_job()
    b = make_job()
    assert a.job_id != b.job_id


def test_enqueue_returns_job_id(tmp_path) -> None:
    q = JobQueue(str(tmp_path / "jobs.db"))
    job = make_job()
    job_id = q.enqueue(job)
    assert job_id == job.job_id


def test_get_status_returns_job(tmp_path) -> None:
    q = JobQueue(str(tmp_path / "jobs.db"))
    job = make_job()
    q.enqueue(job)
    fetched = q.get_status(job.job_id)
    assert fetched.job_id == job.job_id
    assert fetched.type == job.type
    assert fetched.source_url == job.source_url
    assert fetched.tags == job.tags
    assert fetched.status == "queued"


def test_get_status_missing_raises(tmp_path) -> None:
    q = JobQueue(str(tmp_path / "jobs.db"))
    with pytest.raises(ValueError, match="not found"):
        q.get_status("nonexistent-id")


def test_enqueue_preserves_tags(tmp_path) -> None:
    q = JobQueue(str(tmp_path / "jobs.db"))
    job = make_job(tags=["alpha", "beta", "gamma"])
    q.enqueue(job)
    fetched = q.get_status(job.job_id)
    assert fetched.tags == ["alpha", "beta", "gamma"]


def test_enqueue_preserves_original_filename(tmp_path) -> None:
    q = JobQueue(str(tmp_path / "jobs.db"))
    job = make_job(
        type="pdf",
        source_url=None,
        source_path="/tmp/x.pdf",
        original_filename="my-report.pdf",
    )
    q.enqueue(job)
    fetched = q.get_status(job.job_id)
    assert fetched.original_filename == "my-report.pdf"


def test_mark_processing(tmp_path) -> None:
    q = JobQueue(str(tmp_path / "jobs.db"))
    job = make_job()
    q.enqueue(job)
    q.mark_processing(job.job_id)
    fetched = q.get_status(job.job_id)
    assert fetched.status == "processing"
    assert fetched.started_at is not None


def test_mark_completed(tmp_path) -> None:
    q = JobQueue(str(tmp_path / "jobs.db"))
    job = make_job()
    q.enqueue(job)
    q.mark_processing(job.job_id)
    q.mark_completed(job.job_id, files_written=["/vault/foo.md"])
    fetched = q.get_status(job.job_id)
    assert fetched.status == "completed"
    assert fetched.files_written == ["/vault/foo.md"]
    assert fetched.completed_at is not None


def test_mark_failed(tmp_path) -> None:
    q = JobQueue(str(tmp_path / "jobs.db"))
    job = make_job()
    q.enqueue(job)
    q.mark_processing(job.job_id)
    q.mark_failed(job.job_id, error="trafilatura timeout")
    fetched = q.get_status(job.job_id)
    assert fetched.status == "failed"
    assert fetched.error_detail == "trafilatura timeout"
    assert fetched.completed_at is not None


def test_mark_completed_raw_only(tmp_path) -> None:
    q = JobQueue(str(tmp_path / "jobs.db"))
    job = make_job()
    q.enqueue(job)
    q.mark_processing(job.job_id)
    q.mark_completed_raw_only(job.job_id, files=["/vault/raw.md"])
    fetched = q.get_status(job.job_id)
    assert fetched.status == "completed_raw_only"
    assert fetched.files_written == ["/vault/raw.md"]


def test_full_queued_to_failed_transition(tmp_path) -> None:
    q = JobQueue(str(tmp_path / "jobs.db"))
    job = make_job()
    q.enqueue(job)
    assert q.get_status(job.job_id).status == "queued"
    q.mark_processing(job.job_id)
    assert q.get_status(job.job_id).status == "processing"
    q.mark_failed(job.job_id, error="boom")
    assert q.get_status(job.job_id).status == "failed"


def test_persistence_survives_reopen(tmp_path) -> None:
    db_path = str(tmp_path / "jobs.db")
    job = make_job()

    q1 = JobQueue(db_path)
    q1.enqueue(job)
    del q1

    q2 = JobQueue(db_path)
    fetched = q2.get_status(job.job_id)
    assert fetched.job_id == job.job_id
    assert fetched.source_url == job.source_url
    assert fetched.tags == job.tags
    assert fetched.status == "queued"


def test_persistence_status_update_survives_reopen(tmp_path) -> None:
    db_path = str(tmp_path / "jobs.db")
    job = make_job()

    q1 = JobQueue(db_path)
    q1.enqueue(job)
    q1.mark_processing(job.job_id)
    q1.mark_completed(job.job_id, files_written=["/vault/clip.md"])
    del q1

    q2 = JobQueue(db_path)
    fetched = q2.get_status(job.job_id)
    assert fetched.status == "completed"
    assert fetched.files_written == ["/vault/clip.md"]


def test_schema_indexes_exist(tmp_path) -> None:
    db_path = str(tmp_path / "jobs.db")
    JobQueue(db_path)
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='jobs'"
    ).fetchall()
    names = {r[0] for r in rows}
    conn.close()
    assert "idx_status" in names
    assert "idx_created_at" in names


def test_jobs_table_exists(tmp_path) -> None:
    db_path = str(tmp_path / "jobs.db")
    JobQueue(db_path)
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
    ).fetchone()
    conn.close()
    assert row is not None


async def test_worker_transitions_queued_to_completed(tmp_path) -> None:
    q = JobQueue(str(tmp_path / "jobs.db"))
    job = make_job()
    q.enqueue(job)

    worker_task = asyncio.create_task(q.worker())
    await asyncio.sleep(0.2)
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

    assert q.get_status(job.job_id).status == "completed"


async def test_worker_processes_multiple_jobs(tmp_path) -> None:
    q = JobQueue(str(tmp_path / "jobs.db"))
    jobs = [make_job() for _ in range(3)]
    for j in jobs:
        q.enqueue(j)

    worker_task = asyncio.create_task(q.worker())
    await asyncio.sleep(0.3)
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

    for j in jobs:
        assert q.get_status(j.job_id).status == "completed"


async def test_worker_ignores_already_completed(tmp_path) -> None:
    q = JobQueue(str(tmp_path / "jobs.db"))
    job = make_job()
    q.enqueue(job)
    q.mark_processing(job.job_id)
    q.mark_completed(job.job_id, files_written=["/vault/pre.md"])

    worker_task = asyncio.create_task(q.worker())
    await asyncio.sleep(0.2)
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

    fetched = q.get_status(job.job_id)
    assert fetched.files_written == ["/vault/pre.md"]
