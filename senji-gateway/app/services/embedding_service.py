import asyncio
import hashlib
import json
import logging
import pickle
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from app.config import settings

logger = logging.getLogger("senji.pics.embedding_service")

_CREATE_EMBEDDINGS_TABLE = """
CREATE TABLE IF NOT EXISTS embeddings (
    id INTEGER PRIMARY KEY,
    text_hash TEXT UNIQUE,
    text TEXT,
    vector BLOB,
    created_at TEXT
);
"""

_CREATE_EMBEDDING_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS embedding_jobs (
    id INTEGER PRIMARY KEY,
    job_id TEXT,
    status TEXT,
    texts_count INTEGER,
    texts_json TEXT,
    created_at TEXT,
    completed_at TEXT,
    error TEXT
);
"""


class EmbeddingService:
    def __init__(
        self,
        db_path: str | None = None,
        vault_path: str | None = None,
        ollama_client: Any = None,
        model_name: str | None = None,
        _model: Any = None,
    ) -> None:
        self._db_path = db_path or settings.sqlite_db_path
        self._vault_path = vault_path or settings.vault_path
        self._ollama_client = ollama_client
        self._model_name = model_name or settings.embedding_model
        self._model = _model
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _init_db(self) -> None:
        try:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        try:
            with self._conn() as conn:
                conn.execute(_CREATE_EMBEDDINGS_TABLE)
                conn.execute(_CREATE_EMBEDDING_JOBS_TABLE)
                conn.commit()
        except sqlite3.OperationalError as exc:
            logger.warning(
                "EmbeddingService DB init failed — DB operations unavailable",
                extra={"db_path": self._db_path, "error": str(exc)},
            )

    def _get_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415
            self._model = SentenceTransformer(self._model_name)
        return self._model

    @staticmethod
    def _text_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def embed_text(self, text: str) -> list[float]:
        if not text or not text.strip():
            raise ValueError("Cannot embed empty text")
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._get_model()
        batch_size = settings.embedding_batch_size

        def _encode() -> list[list[float]]:
            arr = model.encode(texts, batch_size=batch_size, show_progress_bar=False)
            return [row.tolist() for row in arr]

        return await asyncio.to_thread(_encode)

    async def cache_embedding(self, text: str, vector: list[float]) -> None:
        text_hash = self._text_hash(text)
        blob = pickle.dumps(vector)
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO embeddings (text_hash, text, vector, created_at) VALUES (?, ?, ?, ?)",
                (text_hash, text, blob, now),
            )
            conn.commit()

    async def get_embedding(self, text: str) -> list[float] | None:
        text_hash = self._text_hash(text)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT vector FROM embeddings WHERE text_hash=?", (text_hash,)
            ).fetchone()
        if row is None:
            return None
        return pickle.loads(row[0])  # noqa: S301

    async def queue_embeddings(self, job_id: str, texts: list[str]) -> str:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO embedding_jobs (job_id, status, texts_count, texts_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (job_id, "pending", len(texts), json.dumps(texts), now),
            )
            conn.commit()
        logger.debug("Embedding job queued", extra={"job_id": job_id, "texts_count": len(texts)})
        return job_id

    async def _process_once(self) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, job_id, texts_json FROM embedding_jobs WHERE status='pending' ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if row is None:
                return False
            row_id, job_id, texts_json = row
            conn.execute(
                "UPDATE embedding_jobs SET status='processing' WHERE id=?", (row_id,)
            )
            conn.commit()

        texts: list[str] = json.loads(texts_json)
        try:
            vectors = await self.embed_batch(texts)
            for text, vector in zip(texts, vectors):
                await self.cache_embedding(text, vector)
            now = datetime.now(tz=timezone.utc).isoformat()
            with self._conn() as conn:
                conn.execute(
                    "UPDATE embedding_jobs SET status='completed', completed_at=? WHERE id=?",
                    (now, row_id),
                )
                conn.commit()
            logger.info("Embedding job completed", extra={"job_id": job_id})
        except Exception as exc:
            logger.error(
                "Embedding job failed",
                extra={"job_id": job_id, "error": str(exc)},
                exc_info=True,
            )
            now = datetime.now(tz=timezone.utc).isoformat()
            with self._conn() as conn:
                conn.execute(
                    "UPDATE embedding_jobs SET status='failed', completed_at=?, error=? WHERE id=?",
                    (now, str(exc), row_id),
                )
                conn.commit()
        return True

    async def process_embedding_queue(self) -> None:
        logger.info("Embedding queue worker started")
        while True:
            try:
                had_work = await self._process_once()
                if not had_work:
                    await asyncio.sleep(1.0)
            except Exception as exc:
                logger.error(
                    "Embedding worker loop error",
                    extra={"error": str(exc)},
                    exc_info=True,
                )
                await asyncio.sleep(1.0)

