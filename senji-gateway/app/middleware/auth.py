from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str):
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next):
        # Skip auth for health check and static files
        if request.url.path in ("/health", "/") or request.url.path.startswith("/static"):
            return await call_next(request)

        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer ") or auth[7:] != self.token:
            exc = HTTPException(
                status_code=401,
                detail={
                    "error": "unauthorized",
                    "detail": "Invalid or missing bearer token",
                },
            )
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

        return await call_next(request)
