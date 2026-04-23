import os
import time
from pathlib import Path

from fastapi import APIRouter, Request

_start_time = time.time()
VERSION = "0.1.0"

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict:
    settings = request.app.state.settings
    vault_path = Path(settings.vault_path)
    vault_accessible = vault_path.exists() and os.access(vault_path, os.W_OK)

    db_path = Path(settings.sqlite_db_path)
    jobs_db_accessible = db_path.exists()

    ollama_client = request.app.state.ollama_client
    ollama_accessible = bool(getattr(ollama_client, "available", False))

    index_exists = (vault_path / "index.md").exists() if vault_accessible else False

    overall = "healthy" if (vault_accessible and jobs_db_accessible) else "degraded"

    return {
        "status": overall,
        "version": VERSION,
        "vault_accessible": vault_accessible,
        "vault_index_exists": index_exists,
        "ollama_accessible": ollama_accessible,
        "jobs_db_accessible": jobs_db_accessible,
        "uptime_seconds": int(time.time() - _start_time),
    }
