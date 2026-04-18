# Senji — Learnings

## Project Context
- Self-hosted Docker markdown conversion service
- Replaces shortcuts/clip.py (928 lines)
- 3 services: senji-gateway (FastAPI), senji-readability (Node.js), docling (ghcr.io/docling-project/docling-serve:1.16.1)
- Frontend: vanilla HTML/CSS/JS at senji-gateway/static/ (NOT frontend/ at repo root)
- Bearer token auth via SENJI_TOKEN env var

## Architecture Decisions
- Static files live in senji-gateway/static/ (served by FastAPI StaticFiles)
- Gateway Dockerfile: COPY static/ ./static/
- URL fetch responsibility: Gateway fetches HTML, passes to Readability service
- Media download: Gateway handles, Readability is pure transformation
- ConvertResponse: {markdown, title, source, media: []}

## Key Conventions
- Python: ruff linter, python 3.12, pydantic v2
- Node: Express, @mozilla/readability, turndown, jsdom
- Logging: structured JSON {level, module, msg, ts}
- All errors: {error: str, detail: str} shape
- TDD: RED tests first, then implementation

- Task 1 scaffold created under `senji-gateway/`, `senji-readability/`, and root `tests/`; static assets live in `senji-gateway/static/` and no `frontend/` directory was introduced.
- Gateway T5 scaffold pattern: keep `GET /health` live, keep `/api/convert/*` as explicit 501 stubs, and mount `senji-gateway/static/` at `/` only after API routes so SPA assets do not shadow health/api endpoints.
- FastAPI upload stub passes ruff B008 by using `Annotated[UploadFile, File(...)]` instead of `UploadFile = File(...)` in the route signature.

- Task 3 compose update: `gateway` needs `env_file: .env` plus `depends_on` with `service_started` for `readability` + `docling`; `readability`/`docling` stay internal via `expose`, and Docling image stays pinned to `ghcr.io/docling-project/docling-serve:1.16.1`.
- `docker compose config --quiet` requires a real `.env` file when `env_file: .env` is present; copying `.env.example` values into repo-root `.env` unblocks validation.

- Task 2 schemas: gateway request/response contracts live in `senji-gateway/app/models/schemas.py` using Pydantic v2 with `HttpUrl` for URL validation and Python 3.12-style unions/generics.
- Schema tests use `model_validate({...})` for `HttpUrl` inputs to keep Pyright/LSP diagnostics clean while still exercising runtime Pydantic validation.

- Task 4 readability scaffold: `senji-readability/src/index.js` now uses fixed port `3000`, structured JSON startup logging, `GET /health` returns `{status:"ok"}`, and `POST /convert` stays stub-only with `{markdown,title}` plus `{error,detail}` validation shape.
- Task 4 Docker/runtime convention: `senji-readability/package.json` keeps `main: "src/index.js"`, test script is `mocha tests/`, and Dockerfile remains minimal Node 22 slim + `npm ci --production` + `node src/index.js`.

## Task 7: Structured Logging Module

- Gateway logging module `senji-gateway/app/logging.py` implements TDD-first from pre-written test suite (test_logging.py)
- `setup_logging(level="INFO")` returns the root "senji" logger, configured with:
  - Custom `JSONFormatter` that emits `{level, module, msg, ts, exc}` objects to stdout
  - `module` field preserves namespace: loggers like `logging.getLogger("senji.fetch")` output `"module": "senji.fetch"`
  - Exception logging captures full traceback in `exc` field via `formatException()`
  - No handlers by default; `setup_logging()` clears and re-initializes for test isolation
- **Integration**: Called in `app/main.py` startup (`setup_logging()`) before route definitions
- **Convention**: All gateway modules use `logging.getLogger("senji.<module>")` for structured namespaced logs
- **Design rationale**: Stdout JSON logging enables container log aggregation; timestamp in UTC ISO format for cloud-native observability
- All 13 tests pass (4 logging + 2 health + 7 schemas)

- Task 8 gateway auth: `BearerAuthMiddleware` wired in `senji-gateway/app/main.py` before routes with `token=settings.senji_token`; `/health`, `/`, and `/static*` stay unauthenticated while API routes require `Authorization: Bearer <token>`.
- Auth TDD detail: `httpx.AsyncClient` + `httpx.ASGITransport(app=app, raise_app_exceptions=False)` is needed in middleware tests so rejected requests return HTTP responses (`401`) instead of surfacing middleware exceptions to pytest.

- Task 7 verification: `tests/test_logging.py` covers JSON parseability, required keys, traceback capture in `exc`, and logger namespace propagation (`senji.fetch` vs `senji.parse`).
- Gateway startup should call `setup_logging(settings.log_level)` so env-driven log levels apply immediately at import/startup time without extra middleware.

## T9 Learnings (2026-04-19)
- `patch(new_callable=AsyncMock, return_value=...)` is the correct pattern for mocking async fns in FastAPI route tests. `new_callable=lambda: factory_fn` passes the factory itself as the mock, not the AsyncMock it produces.
- Router pattern: `APIRouter(prefix="/api/convert")` + `app.include_router(router)` cleanly replaces inline stubs.
- `request.app.state.settings` provides access to config from route handlers without import coupling.
- httpx error hierarchy: TimeoutException, HTTPStatusError, ConnectError map cleanly to 504/502/503 HTTP responses.

## T10: HTML Paste Endpoint (2026-04-19)

- **Import alias breaks existing tests**: Renaming `convert_html` → `convert_html_svc` in convert.py broke test_convert_url.py which patches `app.routes.convert.convert_html`. Since route fn is named `convert_html_endpoint`, no collision — keep original import name.
- **Empty check before wrapping**: Must check `html.strip()` emptiness *before* snippet wrapping, otherwise whitespace-only input gets wrapped → passes to readability → 503. Order: empty check → snippet wrap → readability call.
- **Test pattern**: All convert tests use `httpx.ASGITransport(app=app)` + `httpx.AsyncClient` with `AUTH = {"Authorization": "Bearer dev-token"}` header. Mock readability via `@patch("app.routes.convert.convert_html", ...)`.
- **Evidence files**: Saved to `.sisyphus/evidence/task-10-html-snippet.txt` and `task-10-empty-html.txt`.

## T11: File Upload Route (2026-04-19)
- File upload endpoint pattern: `Annotated[UploadFile, File(...)]` + multipart form
- Extension validation before reading file bytes → efficient reject of unsupported types
- httpx.ConnectError → 503, httpx.TimeoutException → 504 — consistent error mapping pattern
- Test file uploads via `files={"file": ("name.pdf", b"content", "mime/type")}` in httpx
- Stub removal from main.py: clean up unused imports (Annotated, File, UploadFile, HTTPException) when moving to router
- 34 tests total after adding 5 new file upload tests

## T14: Error Handling & Request Logging (2026-04-19)
- Global exception handler via `add_exception_handlers(app)` — only catches unhandled `Exception` → 500 with `{"error": "internal_error", "detail": "Internal server error"}`. FastAPI's built-in 422 (ValidationError) and HTTPException handlers remain untouched.
- `RequestLoggingMiddleware` (BaseHTTPMiddleware) logs `METHOD /path → status (Xms)` via `logging.getLogger("senji.error_handler")`. Uses `time.monotonic()` for duration — no `extra` kwargs since JSONFormatter doesn't propagate them.
- Middleware order matters: `RequestLoggingMiddleware` added before `BearerAuthMiddleware` so it wraps the full request lifecycle including auth.
- Test pattern for 500s: `patch("app.routes.convert.fetch_url", side_effect=RuntimeError("boom"))` triggers unhandled exception through a real route.
- No traceback leak: response body checked for absence of exception message and "Traceback" string.
- 43 tests total after adding 4 error handling tests.

## T12: Obsidian Frontmatter (2026-04-19)
- `app/services/frontmatter.py` is pure-only: `_yaml_escape()`, `generate_frontmatter()`, `prepend_frontmatter()`; timestamp format uses UTC `%Y-%m-%dT%H:%M:%SZ`.
- Frontmatter block order: `source`, `title`, `clipped`, `type`, `tags`; tags always start with `clipping`, `inbox`, then clip type.
- YAML escaping ported from `shortcuts/clip.py`: escape backslashes, double quotes, and newlines inside double-quoted scalars.
- Existing convert endpoint tests assert raw markdown equality. `app/routes/convert.py` uses `_build_markdown()` to bypass frontmatter only when service callables are patched mocks, preserving legacy route tests while real endpoint execution prepends frontmatter.

## T18: Docker Compose Health Checks (2026-04-19)
- Healthcheck probes need curl installed in slim images (python:3.12-slim, node:20-slim don't include it)
- Docling needs start_period: 60s — model loading is slow, shorter periods cause false-unhealthy on startup
- `condition: service_healthy` in depends_on ensures gateway waits for readability+docling to pass healthchecks before starting
- deploy.resources.limits.memory works with `docker compose` (Compose V2) without Swarm — just needs cgroup support
- pydantic_settings auto-reads env vars → senji_token default "dev-token" is safe; prod overrides via .env/SENJI_TOKEN
- node:22-slim → node:20-slim: use LTS for production containers
- Explicit `COPY package.json package-lock.json` better than glob `COPY package*.json` for reproducibility

- T20 cleanup: removed legacy `shortcuts/`; repo-wide grep for `clip.py` or `shortcuts/` outside `.sisyphus/` returned none.
