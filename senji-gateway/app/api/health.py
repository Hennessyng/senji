import os
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

_start_time = time.time()
VERSION = "0.1.0"

router = APIRouter()


def compute_health_http_status(checks: dict) -> int:
    """Decide HTTP status from individual check booleans.

    `checks` keys: vault_accessible, jobs_db_accessible, ollama_accessible.
    Return 200 = healthy (docker marks healthy), 503 = degraded (docker fails
    healthcheck → `restart: unless-stopped` recreates container).

    Policy: vault-only. Vault is the only must-have for writes. Ollama/db
    dips tolerated — service still serves cached reads / non-LLM endpoints.
    """
    return 503 if not checks.get("vault_accessible", False) else 200


@router.get("/health")
async def health(request: Request):
    settings = request.app.state.settings
    vault_path = Path(settings.vault_path)
    vault_accessible = vault_path.exists() and os.access(vault_path, os.W_OK)

    db_path = Path(settings.sqlite_db_path)
    jobs_db_accessible = db_path.exists()

    ollama_client = getattr(request.app.state, "ollama_client", None)
    ollama_accessible = bool(getattr(ollama_client, "available", False))

    index_exists = (vault_path / "index.md").exists() if vault_accessible else False

    overall = "healthy" if (vault_accessible and jobs_db_accessible) else "degraded"

    body = {
        "status": overall,
        "version": VERSION,
        "vault_accessible": vault_accessible,
        "vault_index_exists": index_exists,
        "ollama_accessible": ollama_accessible,
        "jobs_db_accessible": jobs_db_accessible,
        "uptime_seconds": int(time.time() - _start_time),
    }
    http_status = compute_health_http_status({
        "vault_accessible": vault_accessible,
        "jobs_db_accessible": jobs_db_accessible,
        "ollama_accessible": ollama_accessible,
    })
    return JSONResponse(content=body, status_code=http_status)
