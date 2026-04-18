from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.logging import setup_logging
from app.middleware.auth import BearerAuthMiddleware
from app.middleware.error_handler import RequestLoggingMiddleware, add_exception_handlers
from app.routes.convert import router as convert_router

app = FastAPI(title="Senji Gateway")
app.state.settings = settings
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(BearerAuthMiddleware, token=settings.senji_token)
add_exception_handlers(app)

setup_logging(settings.log_level)

app.include_router(convert_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
