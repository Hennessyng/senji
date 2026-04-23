import logging
import sqlite3
from unittest.mock import MagicMock

import numpy as np
import pytest

MOCK_DIM = 1024


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_embeddings.db")


@pytest.fixture
def mock_model():
    model = MagicMock()
    model.encode.side_effect = lambda texts, **kw: np.array(
        [[0.1] * MOCK_DIM] * len(texts)
    )
    return model


@pytest.fixture
def svc(db_path, mock_model):
    from app.services.embedding_service import EmbeddingService

    return EmbeddingService(db_path=db_path, _model=mock_model)


@pytest.mark.asyncio
async def test_embed_text_returns_vector(svc):
    result = await svc.embed_text("hello")
    assert isinstance(result, list)
    assert all(isinstance(v, float) for v in result)
    assert len(result) == MOCK_DIM


@pytest.mark.asyncio
async def test_batch_embed_returns_list_of_lists(svc, mock_model):
    mock_model.encode.side_effect = lambda texts, **kw: np.array(
        [[0.1] * MOCK_DIM, [0.2] * MOCK_DIM]
    )
    result = await svc.embed_batch(["text1", "text2"])
    assert len(result) == 2
    assert len(result[0]) == MOCK_DIM
    assert len(result[1]) == MOCK_DIM


@pytest.mark.asyncio
async def test_embedding_saved_to_sqlite(svc, db_path):
    vector = [0.5] * MOCK_DIM
    await svc.cache_embedding("test text", vector)
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT text FROM embeddings WHERE text=?", ("test text",)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "test text"


@pytest.mark.asyncio
async def test_embedding_lookup_retrieves_vector(svc):
    vector = [0.7] * MOCK_DIM
    await svc.cache_embedding("lookup text", vector)
    result = await svc.get_embedding("lookup text")
    assert result is not None
    assert len(result) == MOCK_DIM


@pytest.mark.asyncio
async def test_embedding_lookup_returns_none_if_missing(svc):
    result = await svc.get_embedding("not in db")
    assert result is None


@pytest.mark.asyncio
async def test_batch_queues_for_async_processing(svc, db_path):
    job_id = "test-job-999"
    returned = await svc.queue_embeddings(job_id, ["text1", "text2"])
    assert returned == job_id
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT status, texts_count FROM embedding_jobs WHERE job_id=?", (job_id,)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "pending"
    assert row[1] == 2


@pytest.mark.asyncio
async def test_worker_processes_queue_sequentially(svc, db_path):
    await svc.queue_embeddings("job-A", ["alpha"])
    await svc.queue_embeddings("job-B", ["beta"])
    await svc._process_once()
    await svc._process_once()
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT job_id, status FROM embedding_jobs ORDER BY created_at ASC"
    ).fetchall()
    conn.close()
    statuses = {r[0]: r[1] for r in rows}
    assert statuses["job-A"] == "completed"
    assert statuses["job-B"] == "completed"


@pytest.mark.asyncio
async def test_embedding_error_logged_not_crashed(svc, db_path, mock_model, caplog):
    mock_model.encode.side_effect = RuntimeError("GPU exploded")
    await svc.queue_embeddings("fail-job", ["some text"])
    with caplog.at_level(logging.ERROR, logger="senji.pics.embedding_service"):
        await svc._process_once()
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT status, error FROM embedding_jobs WHERE job_id=?", ("fail-job",)
    ).fetchone()
    conn.close()
    assert row[0] == "failed"
    assert "GPU exploded" in (row[1] or "")


@pytest.mark.asyncio
async def test_empty_texts_returns_empty_list(svc):
    result = await svc.embed_batch([])
    assert result == []
