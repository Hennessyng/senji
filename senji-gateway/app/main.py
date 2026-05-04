import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.api.health import router as health_router
from app.config import settings
from app.logging import setup_logging
from app.middleware.auth import BearerAuthMiddleware
from app.middleware.error_handler import RequestLoggingMiddleware, add_exception_handlers
from app.routes.convert import router as convert_router
from app.routes.ingest import router as ingest_router
from app.services.job_queue import JobQueue
from app.services.ollama_client import OllamaClient
from app.services.vault_writer import VaultWriter

_NO_CACHE_PATHS = {"/app.js", "/style.css"}


class _NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path in _NO_CACHE_PATHS:
            response.headers["Cache-Control"] = "no-cache"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    vault_writer = VaultWriter(settings.vault_path)
    ollama_client = OllamaClient()
    try:
        await ollama_client.health_check()
    except Exception:
        ollama_client.available = False
    job_queue = JobQueue(
        settings.sqlite_db_path,
        vault_writer=vault_writer,
        ollama_client=ollama_client,
    )
    app.state.vault_writer = vault_writer
    app.state.ollama_client = ollama_client
    app.state.job_queue = job_queue
    async def _sweeper_loop() -> None:
        while True:
            await asyncio.sleep(60)
            swept = job_queue.sweep_stale_jobs(timeout_minutes=15)
            if swept:
                import logging
                logging.getLogger("senji.pics.sweeper").warning(
                    "Swept stale jobs", extra={"count": swept}
                )

    worker_task = asyncio.create_task(job_queue.worker())
    sweeper_task = asyncio.create_task(_sweeper_loop())
    try:
        yield
    finally:
        for task in (worker_task, sweeper_task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="Senji Gateway", lifespan=lifespan)
app.state.settings = settings
app.add_middleware(_NoCacheStaticMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(BearerAuthMiddleware, token=settings.senji_token)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
add_exception_handlers(app)

setup_logging(settings.log_level)

app.include_router(health_router)
app.include_router(convert_router)
app.include_router(ingest_router)



# Mount static files (dashboard) from the static directory
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
