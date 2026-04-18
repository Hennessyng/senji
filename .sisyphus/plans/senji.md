# Senji (煎じ) — Self-hosted Markdown Converter

## TL;DR

> **Quick Summary**: Build a self-hosted Docker service that converts web pages and documents to best-class Obsidian-ready Markdown. Dual-engine architecture: Mozilla Readability + Turndown.js for HTML/web, IBM Docling Serve for PDF/documents. Includes a web dashboard for manual conversion.
> 
> **Deliverables**:
> - FastAPI gateway service with bearer auth
> - Node.js Readability + Turndown conversion service
> - Docling Serve integration for PDF/DOCX/PPTX
> - Web dashboard (vanilla HTML/CSS/JS) with URL/Upload/Paste tabs
> - Docker Compose for one-command deployment
> - Media download pipeline (images saved for offline Obsidian reading)
> - Full test suite (TDD, pytest + mocha/jest)
> 
> **Estimated Effort**: Large
> **Parallel Execution**: YES — 4 waves
> **Critical Path**: T1 scaffolding → T6 Readability core → T9 Gateway routing → T14 media download → T17 dashboard → T20 Docker E2E

---

## Context

### Original Request
User wants to replace an existing CLI-based Obsidian clipper (`shortcuts/clip.py`, 928 lines) with a self-hosted Docker service. The service will be called from iOS/macOS Shortcuts via REST API, deployed on Proxmox behind a Cloudflare tunnel at `markdown.myloft.cloud`. Priority is best-class quality for both human and AI agent readability.

### Interview Summary
**Key Discussions**:
- **Engine choice**: MarkItDown rejected (PDF tables broken, beta quality, 600 issues). Dual-service architecture chosen for best quality per input type.
- **Readability**: Node.js `@mozilla/readability` (canonical implementation, same as Safari Reader). NOT Python port.
- **HTML→MD**: Turndown.js in the Node service (natural companion to Readability, same ecosystem).
- **Media**: Download ALL images so Obsidian shows exact page offline. API returns `{markdown, media[]}`.
- **URL fetching**: Gateway fetches HTML, passes to Readability service. Gateway controls timeouts, user-agent, redirects. Readability is a pure transformation service.
- **Auth**: Bearer token (env var), no Cloudflare Access, no user management.
- **Dashboard**: Web UI with URL/Upload/Paste tabs, preview toggle, copy/download, light/dark theme, mobile-friendly.
- **clip.py**: DROP entirely — senji replaces it. shortcuts/ directory removed.
- **Engineering**: TDD, SRP, structured logging for agentic self-correction (Reflexion pattern).

**Research Findings**:
- Docling Serve v1.16.1 (April 2026): `ghcr.io/docling-project/docling-serve`, FastAPI, `/v1/convert/file` endpoint
- Readability.js: canonical article extraction, requires jsdom for headless DOM
- Turndown.js: best HTML→Markdown converter in Node ecosystem
- No existing REST wrapper is production-ready (missing auth, health checks)

### Metis Review
**Identified Gaps** (addressed):
- HTML→MD converter unspecified → Resolved: Turndown.js in Node service
- Media API contract undefined → Resolved: JSON `{markdown, media[{filename, url, data}]}`
- URL fetch responsibility unclear → Resolved: Gateway fetches, passes HTML to Readability
- Docling response format unvalidated → Added: validation task to check actual API response
- Container startup ordering → Added: health checks + depends_on with condition
- Edge cases (paywalled, SPA, lazy images) → Noted in guardrails, handled gracefully with errors

---

## Work Objectives

### Core Objective
Build a production-quality, self-hosted markdown conversion service with a web dashboard, optimized for Obsidian note-taking. Replace the existing CLI clipper entirely.

### Concrete Deliverables
- `senji-gateway/` — FastAPI service (Python 3.12)
- `senji-readability/` — Node.js conversion service
- `senji-gateway/static/` — Static HTML/CSS/JS dashboard
- `docker-compose.yml` — One-command deployment
- `tests/` — pytest (gateway) + mocha (readability)
- `.env.example` — Configuration template

### Definition of Done
- [ ] `git clone && docker compose up -d` starts all 3 services
- [ ] `curl /health` returns `{"status":"ok","services":{"readability":"ok","docling":"ok"}}`
- [ ] Web URL → Markdown with frontmatter + downloaded images
- [ ] PDF upload → Markdown with tables and OCR
- [ ] Dashboard converts URL/file/paste in browser
- [ ] Bearer token rejects unauthenticated requests with 401
- [ ] All tests pass in Docker

### Must Have
- Bearer token authentication on all API endpoints
- Obsidian frontmatter (source, title, clipped, type, tags) on all output
- Image/media download for offline reading
- Health check endpoints for all services
- Structured JSON logging with severity levels
- Docker Compose with proper startup ordering
- Mobile-friendly dashboard

### Must NOT Have (Guardrails)
- NO database — stateless API, no persistence, no conversion history
- NO user management, sessions, or multi-tenant auth — single bearer token only
- NO custom PDF parser — Docling Serve handles all document types
- NO WebSocket/SSE — synchronous HTTP requests with reasonable timeouts
- NO rate limiting, request queuing, or job systems in v1
- NO batch processing — single URL/file per request
- NO custom frontmatter templates — hardcoded fields only
- NO AI tagging or NLP — tags are static (`clipping` + type)
- NO npm/webpack/vite build step for frontend — vanilla HTML/CSS/JS only
- NO EPUB/MOBI support in v1 — PDF + DOCX + PPTX only via Docling
- NO modification of clip.py — it's being dropped, not migrated
- NO WYSIWYG markdown editor in dashboard — preview uses marked.js or `<pre>` block

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest configured in pyproject.toml)
- **Automated tests**: TDD — tests first for all new code
- **Frameworks**: pytest (Python/gateway), mocha+chai or jest (Node/readability)
- **Each task follows**: RED (failing test) → GREEN (minimal impl) → REFACTOR

### Logging Strategy (Agentic TDD)
- All services use structured JSON logging: `{"level":"INFO","module":"gateway.fetch","msg":"...","ts":"..."}`
- Errors include stack traces and operation context
- Agent reads logs via `docker compose logs <service>` to diagnose failures
- Log format designed for machine parsing in self-correction loops

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **API endpoints**: Bash (curl) — send requests, assert status + response fields
- **Frontend/UI**: Playwright — navigate, interact, assert DOM, screenshot
- **Services**: Bash (docker compose logs) — verify structured log output
- **Docker**: Bash — verify containers running, health checks passing

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — start immediately, all parallel):
├── Task 1: Project scaffolding + git init + repo structure [quick]
├── Task 2: API contract definitions (request/response schemas) [quick]
├── Task 3: Docker Compose skeleton (3 services, networking, env) [quick]
├── Task 4: Readability service scaffolding (Node.js setup) [quick]
├── Task 5: Gateway service scaffolding (FastAPI setup) [quick]

Wave 2 (Core Services — after Wave 1, MAX PARALLEL):
├── Task 6: Readability service: core conversion logic (depends: 4) [deep]
├── Task 7: Gateway: structured logging module (depends: 5) [quick]
├── Task 8: Gateway: bearer token auth middleware (depends: 5) [quick]
├── Task 9: Gateway: URL fetch + route to Readability (depends: 2, 5) [deep]
├── Task 10: Gateway: HTML paste endpoint (depends: 2, 5) [unspecified-high]
├── Task 11: Gateway: file upload + route to Docling (depends: 2, 5) [unspecified-high]

Wave 3 (Features + UI — after Wave 2, MAX PARALLEL):
├── Task 12: Gateway: Obsidian frontmatter generation (depends: 9) [quick]
├── Task 13: Gateway: media/image download pipeline (depends: 9) [deep]
├── Task 14: Gateway: error handling (timeouts, 4xx/5xx, validation) (depends: 9, 11) [unspecified-high]
├── Task 15: Dashboard: HTML/CSS layout + URL conversion tab (depends: 9) [visual-engineering]
├── Task 16: Dashboard: Upload + Paste tabs (depends: 11, 15) [visual-engineering]
├── Task 17: Dashboard: Preview toggle + Copy/Download + Dark mode (depends: 15) [visual-engineering]

Wave 4 (Integration + Cleanup — after Wave 3):
├── Task 18: Docker Compose: health checks + depends_on + volumes (depends: all) [unspecified-high]
├── Task 19: E2E tests: full pipeline (URL + PDF + paste) (depends: 18) [deep]
├── Task 20: Cleanup: remove shortcuts/, update pyproject.toml, push to GitHub (depends: 19) [quick]

Wave FINAL (After ALL tasks — 4 parallel reviews, then user okay):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
→ Present results → Get explicit user okay

Critical Path: T1 → T5 → T9 → T13 → T15 → T18 → T19 → F1-F4 → user okay
Parallel Speedup: ~65% faster than sequential
Max Concurrent: 6 (Wave 2)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 2-5 | 1 |
| 2 | — | 9, 10, 11 | 1 |
| 3 | — | 18 | 1 |
| 4 | — | 6 | 1 |
| 5 | — | 7, 8, 9, 10, 11 | 1 |
| 6 | 4 | 9, 10 | 2 |
| 7 | 5 | 9, 10, 11 | 2 |
| 8 | 5 | 9, 10, 11 | 2 |
| 9 | 2, 5, 6, 7, 8 | 12, 13, 14, 15 | 2 |
| 10 | 2, 5, 6, 7, 8 | 16 | 2 |
| 11 | 2, 5, 7, 8 | 14, 16 | 2 |
| 12 | 9 | 19 | 3 |
| 13 | 9 | 19 | 3 |
| 14 | 9, 11 | 19 | 3 |
| 15 | 9 | 16, 17 | 3 |
| 16 | 11, 15 | 19 | 3 |
| 17 | 15 | 19 | 3 |
| 18 | all Wave 3 | 19 | 4 |
| 19 | 18 | 20 | 4 |
| 20 | 19 | F1-F4 | 4 |

### Agent Dispatch Summary

- **Wave 1**: **5 tasks** — T1-T5 → `quick`
- **Wave 2**: **6 tasks** — T6 → `deep`, T7-T8 → `quick`, T9 → `deep`, T10-T11 → `unspecified-high`
- **Wave 3**: **6 tasks** — T12 → `quick`, T13 → `deep`, T14 → `unspecified-high`, T15-T17 → `visual-engineering`
- **Wave 4**: **3 tasks** — T18 → `unspecified-high`, T19 → `deep`, T20 → `quick`
- **FINAL**: **4 tasks** — F1 → `oracle`, F2-F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. Project Scaffolding + Git Init + Repo Structure

  **What to do**:
  - Create directory structure:
    ```
    senji/
    ├── senji-gateway/          # FastAPI service
    │   ├── app/
    │   │   ├── __init__.py
    │   │   ├── main.py         # FastAPI app entry
    │   │   ├── config.py       # Settings from env vars
    │   │   ├── middleware/
    │   │   ├── routes/
    │   │   ├── services/
    │   │   └── models/
    │   ├── tests/
    │   ├── Dockerfile
    │   ├── pyproject.toml
    │   └── requirements.txt
    ├── senji-readability/       # Node.js service
    │   ├── src/
    │   ├── tests/
    │   ├── Dockerfile
    │   └── package.json
    ├── senji-gateway/static/    # Static dashboard (served by gateway)
    │   ├── index.html
    │   ├── style.css
    │   └── app.js
    ├── docker-compose.yml
    ├── .env.example
    ├── .gitignore
    └── README.md
    ```
  - Initialize git repo: `git init`, add remote `https://github.com/Hennessyng/senji.git`
  - Create `.gitignore` (Python, Node, Docker, .env, __pycache__, node_modules)
  - Create `.env.example` with: `SENJI_TOKEN=your-bearer-token-here`, `DOCLING_URL=http://docling:5001`, `READABILITY_URL=http://readability:3000`
  - Rename parent folder from `PKM` to `senji` (if not already done)

  **Must NOT do**:
  - Do NOT write any business logic — scaffolding only (empty files with pass/placeholder)
  - Do NOT install dependencies yet — just declare them in config files
  - Do NOT create a README with excessive documentation

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: File creation and git init — no complex logic
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - None needed for scaffolding

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 4, 5)
  - **Blocks**: Tasks 2, 3, 4, 5 (directory structure must exist)
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `pyproject.toml` (root) — existing Python config, reuse ruff settings and python version
  - `shortcuts/clip.py:35-42` — existing structured logging pattern to inform gateway logging design

  **External References**:
  - FastAPI project structure: `https://fastapi.tiangolo.com/tutorial/bigger-applications/`

  **WHY Each Reference Matters**:
  - `pyproject.toml`: Copy ruff config and python version settings for consistency
  - `clip.py` logging: The `log(level, module, msg)` pattern should evolve into JSON structured logging

  **Acceptance Criteria**:
  - [ ] All directories exist as specified in the tree above
  - [ ] `git remote -v` shows `https://github.com/Hennessyng/senji.git`
  - [ ] `.gitignore` covers Python, Node, Docker, .env
  - [ ] `.env.example` contains SENJI_TOKEN, DOCLING_URL, READABILITY_URL

  **QA Scenarios**:

  ```
  Scenario: Directory structure exists
    Tool: Bash
    Preconditions: Repository initialized
    Steps:
      1. Run `find . -type d | sort` from repo root
      2. Assert output contains: senji-gateway/app, senji-gateway/tests, senji-gateway/static, senji-readability/src, senji-readability/tests
      3. Run `cat .env.example` and verify it contains "SENJI_TOKEN"
    Expected Result: All directories present, .env.example has required vars
    Failure Indicators: Missing directories, missing env vars
    Evidence: .sisyphus/evidence/task-1-directory-structure.txt

  Scenario: Git remote configured
    Tool: Bash
    Preconditions: git init completed
    Steps:
      1. Run `git remote -v`
      2. Assert output contains "github.com/Hennessyng/senji.git"
    Expected Result: Remote "origin" points to correct GitHub repo
    Failure Indicators: No remote, wrong URL
    Evidence: .sisyphus/evidence/task-1-git-remote.txt
  ```

  **Commit**: YES (groups with T2-T5)
  - Message: `chore(init): project scaffolding and service skeletons`
  - Files: all scaffolding files
  - Pre-commit: `docker compose config`

- [x] 2. API Contract Definitions (Request/Response Schemas)

  **What to do**:
  - Create `senji-gateway/app/models/schemas.py` with Pydantic models:
    ```python
    class ConvertURLRequest(BaseModel):
        url: HttpUrl
    
    class ConvertHTMLRequest(BaseModel):
        html: str
        source_url: str | None = None  # optional, for frontmatter
    
    class MediaItem(BaseModel):
        filename: str      # e.g. "article-img-1.jpg"
        content_type: str  # e.g. "image/jpeg"
        data: str          # base64-encoded
    
    class ConvertResponse(BaseModel):
        markdown: str
        title: str
        source: str
        media: list[MediaItem] = []
    
    class ErrorResponse(BaseModel):
        error: str
        detail: str
    
    class HealthResponse(BaseModel):
        status: str  # "ok" | "degraded"
        services: dict[str, str]  # {"readability": "ok", "docling": "ok"}
    ```
  - Create `senji-readability/src/schemas.js` with equivalent types (JSDoc or simple validation):
    ```javascript
    // Input: { html: string }
    // Output: { markdown: string, title: string }
    ```
  - Write TDD tests for schema validation (invalid URL, empty HTML, etc.)

  **Must NOT do**:
  - Do NOT add OpenAPI/Swagger customization beyond what FastAPI auto-generates
  - Do NOT add optional fields beyond what's specified — keep schemas minimal

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Schema definitions are straightforward Pydantic models
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3, 4, 5)
  - **Blocks**: Tasks 9, 10, 11
  - **Blocked By**: Task 1 (needs directory structure)

  **References**:

  **Pattern References**:
  - `shortcuts/clip.py:115-127` — existing `build_frontmatter()` function — the fields (source, title, clipped, type, tags) define what ConvertResponse must support

  **External References**:
  - Pydantic v2 models: `https://docs.pydantic-dev.github.io/latest/concepts/models/`

  **WHY Each Reference Matters**:
  - `clip.py` frontmatter: The 5 frontmatter fields (source, title, clipped, type, tags) are the proven set to carry forward

  **Acceptance Criteria**:
  - [ ] Test file: `senji-gateway/tests/test_schemas.py`
  - [ ] `pytest senji-gateway/tests/test_schemas.py` → PASS
  - [ ] ConvertURLRequest rejects invalid URLs
  - [ ] ConvertResponse serializes with all required fields

  **QA Scenarios**:

  ```
  Scenario: Schema validation rejects invalid URL
    Tool: Bash (pytest)
    Preconditions: schemas.py and test file exist
    Steps:
      1. Run `cd senji-gateway && python -m pytest tests/test_schemas.py -v`
      2. Assert test for invalid URL (e.g., "not-a-url") raises ValidationError
      3. Assert test for valid URL (e.g., "https://example.com") passes
    Expected Result: All schema validation tests pass
    Failure Indicators: ValidationError not raised for invalid input
    Evidence: .sisyphus/evidence/task-2-schema-tests.txt

  Scenario: ConvertResponse includes media array
    Tool: Bash (python)
    Preconditions: schemas.py exists
    Steps:
      1. Run python snippet: `ConvertResponse(markdown="# Test", title="Test", source="https://example.com", media=[]).model_dump_json()`
      2. Assert JSON output contains "markdown", "title", "source", "media" keys
    Expected Result: JSON serialization includes all fields
    Failure Indicators: Missing fields, serialization error
    Evidence: .sisyphus/evidence/task-2-response-serialize.txt
  ```

  **Commit**: YES (groups with T1, T3-T5)
  - Message: `chore(init): project scaffolding and service skeletons`
  - Files: `senji-gateway/app/models/schemas.py`, `senji-gateway/tests/test_schemas.py`
  - Pre-commit: `pytest senji-gateway/tests/test_schemas.py`

- [x] 3. Docker Compose Skeleton (3 Services, Networking, Env)

  **What to do**:
  - Create `docker-compose.yml` with 3 services:
    ```yaml
    services:
      gateway:
        build: ./senji-gateway
        ports: ["8000:8000"]
        env_file: .env
        depends_on:
          readability:
            condition: service_started
          docling:
            condition: service_started
        networks: [senji-net]
      
      readability:
        build: ./senji-readability
        expose: ["3000"]
        networks: [senji-net]
      
      docling:
        image: ghcr.io/docling-project/docling-serve:1.16.1  # PIN version
        expose: ["5001"]
        networks: [senji-net]
    
    networks:
      senji-net:
        driver: bridge
    ```
  - Create minimal Dockerfiles for gateway and readability (just FROM + WORKDIR for now)
  - Gateway Dockerfile: `FROM python:3.12-slim`
  - Readability Dockerfile: `FROM node:22-slim`
  - Verify with `docker compose config` (syntax validation)

  **Must NOT do**:
  - Do NOT use `latest` tag for Docling — pin to specific version
  - Do NOT add volumes, health checks, or restart policies yet (Task 18)
  - Do NOT expose Docling or Readability ports to host — internal network only

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Docker config files — no complex logic
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 4, 5)
  - **Blocks**: Task 18
  - **Blocked By**: Task 1 (needs directory structure)

  **References**:

  **External References**:
  - Docling Serve Docker image: `https://github.com/docling-project/docling-serve` — verify exact image name and tag
  - Docker Compose spec: `https://docs.docker.com/compose/compose-file/`

  **WHY Each Reference Matters**:
  - Docling Serve repo: Must verify the exact image path (`ghcr.io/docling-project/docling-serve`) and available tags. Pin to 1.16.1 or latest stable.

  **Acceptance Criteria**:
  - [ ] `docker compose config` exits with 0 (valid syntax)
  - [ ] 3 services defined: gateway, readability, docling
  - [ ] Docling uses pinned version tag (not `latest`)
  - [ ] Only gateway exposes port 8000 to host

  **QA Scenarios**:

  ```
  Scenario: Docker Compose validates successfully
    Tool: Bash
    Preconditions: docker-compose.yml exists
    Steps:
      1. Run `docker compose config --quiet` from repo root
      2. Assert exit code is 0
      3. Run `docker compose config --services` and assert output contains "gateway", "readability", "docling"
    Expected Result: Config valid, 3 services listed
    Failure Indicators: Non-zero exit, missing service names
    Evidence: .sisyphus/evidence/task-3-compose-config.txt

  Scenario: Docling image is pinned (not latest)
    Tool: Bash
    Preconditions: docker-compose.yml exists
    Steps:
      1. Run `grep "docling-serve" docker-compose.yml`
      2. Assert output does NOT contain ":latest"
      3. Assert output contains a specific version tag (e.g., ":1.16.1")
    Expected Result: Pinned version tag found
    Failure Indicators: ":latest" present or no tag specified
    Evidence: .sisyphus/evidence/task-3-docling-pinned.txt
  ```

  **Commit**: YES (groups with T1-T2, T4-T5)
  - Message: `chore(init): project scaffolding and service skeletons`
  - Files: `docker-compose.yml`, `senji-gateway/Dockerfile`, `senji-readability/Dockerfile`
  - Pre-commit: `docker compose config`

- [x] 4. Readability Service Scaffolding (Node.js Setup)

  **What to do**:
  - Create `senji-readability/package.json` with dependencies:
    - `@mozilla/readability` — article extraction
    - `jsdom` — headless DOM for Readability
    - `turndown` — HTML→Markdown conversion
    - `express` — HTTP server
    - Dev: `mocha`, `chai`, `sinon` — test framework
  - Create `senji-readability/src/index.js` — Express server skeleton:
    - `POST /convert` — accepts `{html: string}`, returns `{markdown: string, title: string}`
    - `GET /health` — returns `{status: "ok"}`
    - Listens on port 3000
  - Create `senji-readability/Dockerfile`:
    ```dockerfile
    FROM node:22-slim
    WORKDIR /app
    COPY package*.json ./
    RUN npm ci --production
    COPY src/ ./src/
    EXPOSE 3000
    CMD ["node", "src/index.js"]
    ```
  - Run `npm install` and verify `node src/index.js` starts without errors
  - Create placeholder test file `senji-readability/tests/convert.test.js`

  **Must NOT do**:
  - Do NOT implement conversion logic — just the Express server with stub endpoints
  - Do NOT add TypeScript — plain JavaScript with JSDoc comments
  - Do NOT add middleware (CORS, logging) yet — bare Express only

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Node.js project setup — boilerplate only
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3, 5)
  - **Blocks**: Task 6
  - **Blocked By**: Task 1 (needs directory structure)

  **References**:

  **External References**:
  - `@mozilla/readability`: `https://github.com/mozilla/readability` — API usage
  - `turndown`: `https://github.com/mixmark-io/turndown` — HTML→MD API
  - `jsdom`: `https://github.com/jsdom/jsdom` — DOM construction from HTML string

  **WHY Each Reference Matters**:
  - These three libraries form the conversion pipeline: HTML → jsdom DOM → Readability article → Turndown markdown. Understanding their APIs is needed to design the stub endpoint signature.

  **Acceptance Criteria**:
  - [ ] `cd senji-readability && npm ci` installs without errors
  - [ ] `node src/index.js` starts server on port 3000
  - [ ] `curl http://localhost:3000/health` returns `{"status":"ok"}`
  - [ ] `POST /convert` with `{"html":"<p>test</p>"}` returns 200 (stub response OK)

  **QA Scenarios**:

  ```
  Scenario: Readability service starts and responds to health check
    Tool: Bash
    Preconditions: npm ci completed
    Steps:
      1. Run `cd senji-readability && node src/index.js &` (background)
      2. Wait 2 seconds
      3. Run `curl -s http://localhost:3000/health`
      4. Assert response contains `"status":"ok"`
      5. Kill background process
    Expected Result: Health endpoint returns ok
    Failure Indicators: Connection refused, non-JSON response, missing status field
    Evidence: .sisyphus/evidence/task-4-readability-health.txt

  Scenario: Convert endpoint accepts POST with HTML body
    Tool: Bash
    Preconditions: Service running on port 3000
    Steps:
      1. Run `curl -s -X POST http://localhost:3000/convert -H "Content-Type: application/json" -d '{"html":"<p>hello</p>"}'`
      2. Assert HTTP status is 200
      3. Assert response is valid JSON with "markdown" and "title" keys
    Expected Result: Stub response with correct shape
    Failure Indicators: 404, 500, or missing keys in response
    Evidence: .sisyphus/evidence/task-4-convert-stub.txt
  ```

  **Commit**: YES (groups with T1-T3, T5)
  - Message: `chore(init): project scaffolding and service skeletons`
  - Files: `senji-readability/package.json`, `senji-readability/src/index.js`, `senji-readability/Dockerfile`
  - Pre-commit: `cd senji-readability && npm test`

- [x] 5. Gateway Service Scaffolding (FastAPI Setup)

  **What to do**:
  - Create `senji-gateway/pyproject.toml` with dependencies:
    - `fastapi` + `uvicorn[standard]` — web framework + ASGI server
    - `httpx` — async HTTP client (for calling Readability + Docling)
    - `python-multipart` — file upload support
    - `pydantic-settings` — env var config
    - Dev: `pytest`, `pytest-asyncio`, `httpx` (test client)
  - Create `senji-gateway/app/config.py`:
    ```python
    from pydantic_settings import BaseSettings
    
    class Settings(BaseSettings):
        senji_token: str = "dev-token"
        readability_url: str = "http://readability:3000"
        docling_url: str = "http://docling:5001"
        log_level: str = "INFO"
    ```
  - Create `senji-gateway/app/main.py` — FastAPI app skeleton:
    - Mount `static/` as static files at `/`
    - Include route stubs: `/health`, `/api/convert/url`, `/api/convert/html`, `/api/convert/file`
    - All route stubs return 501 Not Implemented for now
  - Create `senji-gateway/Dockerfile`:
    ```dockerfile
    FROM python:3.12-slim
    WORKDIR /app
    COPY requirements.txt .
    RUN pip install --no-cache-dir -r requirements.txt
    COPY app/ ./app/
    COPY static/ ./static/
    EXPOSE 8000
    CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
    ```
  - Create `senji-gateway/requirements.txt` from pyproject.toml deps
  - Create placeholder test: `senji-gateway/tests/test_health.py`

  **Must NOT do**:
  - Do NOT implement route logic — stubs returning 501 only
  - Do NOT add middleware yet (auth, logging handled in Tasks 7-8)
  - Do NOT copy static files into Docker yet — just reference the path

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: FastAPI boilerplate setup
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3, 4)
  - **Blocks**: Tasks 7, 8, 9, 10, 11
  - **Blocked By**: Task 1 (needs directory structure)

  **References**:

  **Pattern References**:
  - `pyproject.toml` (root) — reuse ruff config (`select = ["E", "F", "W", "I", "UP", "B", "SIM"]`, `line-length = 100`, `target-version = "py310"`)
  - `shortcuts/clip.py:35-42` — `log()` function pattern — will evolve into structured JSON logging in Task 7

  **External References**:
  - FastAPI startup: `https://fastapi.tiangolo.com/tutorial/first-steps/`
  - pydantic-settings: `https://docs.pydantic-dev.github.io/latest/concepts/pydantic_settings/`
  - Static files: `https://fastapi.tiangolo.com/tutorial/static-files/`

  **WHY Each Reference Matters**:
  - Root `pyproject.toml`: Ensures consistent linting config across old and new code
  - `clip.py` log pattern: Shows the existing convention to evolve from

  **Acceptance Criteria**:
  - [ ] `cd senji-gateway && pip install -r requirements.txt` succeeds
  - [ ] `uvicorn app.main:app` starts on port 8000
  - [ ] `curl http://localhost:8000/health` returns 200 with JSON
  - [ ] `curl http://localhost:8000/api/convert/url` returns 501

  **QA Scenarios**:

  ```
  Scenario: Gateway starts and health check responds
    Tool: Bash
    Preconditions: requirements installed
    Steps:
      1. Run `cd senji-gateway && uvicorn app.main:app --port 8000 &`
      2. Wait 3 seconds
      3. Run `curl -s http://localhost:8000/health`
      4. Assert response is JSON with "status" key
      5. Kill background process
    Expected Result: Health endpoint returns JSON status
    Failure Indicators: Connection refused, import errors, non-JSON response
    Evidence: .sisyphus/evidence/task-5-gateway-health.txt

  Scenario: Stub endpoints return 501
    Tool: Bash
    Preconditions: Gateway running on port 8000
    Steps:
      1. Run `curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/convert/url -H "Content-Type: application/json" -d '{"url":"https://example.com"}'`
      2. Assert status code is 501
      3. Repeat for `/api/convert/html` and `/api/convert/file`
    Expected Result: All 3 endpoints return 501
    Failure Indicators: 404 (route not defined), 500 (crash), 200 (implemented too early)
    Evidence: .sisyphus/evidence/task-5-stub-endpoints.txt
  ```

  **Commit**: YES (groups with T1-T4)
  - Message: `chore(init): project scaffolding and service skeletons`
  - Files: `senji-gateway/pyproject.toml`, `senji-gateway/app/main.py`, `senji-gateway/app/config.py`, `senji-gateway/Dockerfile`
  - Pre-commit: `cd senji-gateway && pytest tests/test_health.py`

- [x] 6. Readability Service: Core Conversion Logic

  **What to do**:
  - Implement the full conversion pipeline in `senji-readability/src/converter.js` (SRP — separate from Express server):
    ```javascript
    // converter.js — pure function, no HTTP concerns
    // Input: raw HTML string
    // Output: { markdown: string, title: string }
    
    const { JSDOM } = require('jsdom');
    const { Readability } = require('@mozilla/readability');
    const TurndownService = require('turndown');
    ```
  - Pipeline: HTML string → JSDOM parse → Readability extract article → Turndown convert to markdown
  - Configure Turndown rules:
    - Preserve code blocks with language hints
    - Convert tables to markdown tables
    - Handle images: preserve `src` and `alt` attributes in `![alt](src)` format
    - Headings, lists, blockquotes, bold, italic, links
  - Wire converter into Express `POST /convert` endpoint in `src/index.js`
  - Add structured JSON logging: `{"level":"INFO","module":"readability.convert","msg":"...","ts":"..."}`
  - Write TDD tests in `senji-readability/tests/convert.test.js`:
    - Simple HTML → expected markdown
    - Article with noise (nav, footer, ads) → clean article only
    - HTML with images → markdown with `![alt](src)`
    - HTML with code blocks → preserved in markdown
    - HTML with tables → markdown table
    - Empty/malformed HTML → graceful error, not crash
    - Title extraction from `<title>` and `<h1>`

  **Must NOT do**:
  - Do NOT handle media download — that's the gateway's job (Task 13)
  - Do NOT add URL fetching — Readability receives pre-fetched HTML
  - Do NOT add frontmatter — gateway handles that (Task 12)
  - Do NOT add custom post-processing regex (no clip.py patterns like share link removal)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Core conversion logic requires careful Readability + Turndown integration and thorough testing
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7, 8, 9, 10, 11)
  - **Blocks**: Tasks 9, 10
  - **Blocked By**: Task 4 (needs Node.js scaffolding)

  **References**:

  **Pattern References**:
  - `shortcuts/clip.py:133-271` — `HTML2Markdown` class — shows what HTML elements must be handled (headings, lists, code, pre, blockquote, links, images, tables). Turndown handles most natively, but this shows the expected output quality.
  - `shortcuts/clip.py:371-403` — `extract_article_html()` — Readability replaces this entirely. Shows what noise extraction looks like so you can verify Readability does it better.

  **External References**:
  - Readability API: `https://github.com/mozilla/readability#usage` — `new Readability(document).parse()` returns `{title, content, textContent, length, excerpt, byline, dir, siteName, lang, publishedTime}`
  - Turndown API: `https://github.com/mixmark-io/turndown#usage` — `turndownService.turndown(html)` with rule customization
  - jsdom: `https://github.com/jsdom/jsdom#basic-usage` — `new JSDOM(html)` then `dom.window.document`

  **WHY Each Reference Matters**:
  - `clip.py` HTML2Markdown: Shows the 15+ HTML elements that must convert correctly — use as a test checklist
  - Readability `.parse()`: Returns `content` (cleaned HTML), `title`, `byline` — these are the inputs to Turndown
  - Turndown rules: Default rules handle most cases; may need `turndown-plugin-gfm` for tables

  **Acceptance Criteria**:
  - [ ] `cd senji-readability && npm test` → all tests pass
  - [ ] Simple `<article><h1>Title</h1><p>Text</p></article>` → `# Title\n\nText`
  - [ ] Full webpage HTML with nav/footer → only article content extracted
  - [ ] `<pre><code>console.log('hi')</code></pre>` → markdown code block
  - [ ] `<table>` → markdown table
  - [ ] `<img src="x.jpg" alt="photo">` → `![photo](x.jpg)`
  - [ ] Empty HTML → returns `{markdown: "", title: "Untitled"}`, no crash

  **QA Scenarios**:

  ```
  Scenario: Full webpage converts to clean markdown
    Tool: Bash
    Preconditions: Readability service running on port 3000
    Steps:
      1. Create test HTML file with: <html><head><title>Test Article</title></head><body><nav>Menu</nav><article><h1>Test Article</h1><p>This is the content.</p><img src="photo.jpg" alt="A photo"></article><footer>Copyright</footer></body></html>
      2. POST to http://localhost:3000/convert with {"html": "<full HTML above>"}
      3. Assert response.title equals "Test Article"
      4. Assert response.markdown contains "# Test Article"
      5. Assert response.markdown contains "This is the content"
      6. Assert response.markdown contains "![A photo](photo.jpg)"
      7. Assert response.markdown does NOT contain "Menu" or "Copyright"
    Expected Result: Clean markdown with title, content, image; no nav/footer noise
    Failure Indicators: Nav/footer text present, missing image, wrong title
    Evidence: .sisyphus/evidence/task-6-full-conversion.txt

  Scenario: Malformed HTML doesn't crash
    Tool: Bash
    Preconditions: Service running
    Steps:
      1. POST to /convert with {"html": ""}
      2. Assert HTTP status is 200 (not 500)
      3. Assert response has "markdown" and "title" keys
      4. POST with {"html": "<div>unclosed"}
      5. Assert HTTP status is 200
    Expected Result: Graceful handling, no server crash
    Failure Indicators: 500 status, connection reset, unhandled exception in logs
    Evidence: .sisyphus/evidence/task-6-malformed-html.txt
  ```

  **Commit**: YES
  - Message: `feat(readability): core HTML→Markdown conversion service`
  - Files: `senji-readability/src/converter.js`, `senji-readability/tests/convert.test.js`, `senji-readability/src/index.js`
  - Pre-commit: `cd senji-readability && npm test`

- [x] 7. Gateway: Structured Logging Module

  **What to do**:
  - Create `senji-gateway/app/logging.py` — structured JSON logger:
    ```python
    import json, logging, sys
    from datetime import datetime, timezone
    
    class JSONFormatter(logging.Formatter):
        def format(self, record):
            return json.dumps({
                "level": record.levelname,
                "module": record.name,
                "msg": record.getMessage(),
                "ts": datetime.now(timezone.utc).isoformat(),
                "exc": self.formatException(record.exc_info) if record.exc_info else None,
            })
    
    def setup_logging(level: str = "INFO"):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        root = logging.getLogger("senji")
        root.setLevel(level)
        root.addHandler(handler)
        return root
    ```
  - Integrate into `app/main.py` — call `setup_logging()` on startup
  - All subsequent modules use `logging.getLogger("senji.<module>")` for namespaced logs
  - Write TDD tests:
    - Log output is valid JSON
    - Level, module, msg, ts fields present
    - Exception info included on error level
    - Different modules produce different `module` values

  **Must NOT do**:
  - Do NOT add log rotation or file handlers — stdout only (Docker captures it)
  - Do NOT add request logging middleware yet — just the logging setup

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single module, straightforward Python logging customization
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6, 8, 9, 10, 11)
  - **Blocks**: Tasks 9, 10, 11
  - **Blocked By**: Task 5 (needs gateway scaffolding)

  **References**:

  **Pattern References**:
  - `shortcuts/clip.py:35-42` — existing `log(level, module, msg)` function — evolve this pattern into proper JSON structured logging

  **WHY Each Reference Matters**:
  - Shows the existing convention (level + module prefix) to preserve in the new JSON format

  **Acceptance Criteria**:
  - [ ] `pytest senji-gateway/tests/test_logging.py` → PASS
  - [ ] Log output is valid JSON (parseable by `json.loads()`)
  - [ ] Each log entry has: level, module, msg, ts
  - [ ] Error logs include exc field with traceback

  **QA Scenarios**:

  ```
  Scenario: Log output is machine-parseable JSON
    Tool: Bash (pytest)
    Preconditions: logging.py exists
    Steps:
      1. Run `cd senji-gateway && python -m pytest tests/test_logging.py -v`
      2. Assert all tests pass
      3. Run a quick python snippet that calls logger.info("test") and captures stdout
      4. Parse stdout line as JSON, assert keys: level, module, msg, ts
    Expected Result: All logging tests pass, output is valid JSON
    Failure Indicators: Invalid JSON, missing fields, test failures
    Evidence: .sisyphus/evidence/task-7-logging-tests.txt

  Scenario: Error logs include exception traceback
    Tool: Bash (python)
    Preconditions: logging module importable
    Steps:
      1. Run python snippet that triggers logger.exception("fail", exc_info=True) inside a try/except
      2. Capture stdout, parse as JSON
      3. Assert "exc" field is not None and contains traceback text
    Expected Result: Exception info captured in structured log
    Failure Indicators: exc field is None, traceback missing
    Evidence: .sisyphus/evidence/task-7-error-logging.txt
  ```

  **Commit**: YES (groups with T8)
  - Message: `feat(gateway): structured logging and bearer auth`
  - Files: `senji-gateway/app/logging.py`, `senji-gateway/tests/test_logging.py`
  - Pre-commit: `pytest senji-gateway/tests/test_logging.py`

- [x] 8. Gateway: Bearer Token Auth Middleware

  **What to do**:
  - Create `senji-gateway/app/middleware/auth.py`:
    ```python
    from fastapi import Request, HTTPException
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
                raise HTTPException(status_code=401, detail={"error": "unauthorized", "detail": "Invalid or missing bearer token"})
            
            return await call_next(request)
    ```
  - Wire into `app/main.py` using `app.add_middleware(BearerAuthMiddleware, token=settings.senji_token)`
  - Write TDD tests:
    - Request without token → 401
    - Request with wrong token → 401
    - Request with correct token → passes through
    - `/health` without token → 200 (exempt)
    - `/` (dashboard) without token → 200 (exempt)

  **Must NOT do**:
  - Do NOT add rate limiting
  - Do NOT add session management or cookies
  - Do NOT add multiple tokens or user roles

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple middleware with clear logic
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6, 7, 9, 10, 11)
  - **Blocks**: Tasks 9, 10, 11
  - **Blocked By**: Task 5 (needs gateway scaffolding)

  **References**:

  **External References**:
  - FastAPI middleware: `https://fastapi.tiangolo.com/tutorial/middleware/`
  - Starlette BaseHTTPMiddleware: `https://www.starlette.io/middleware/`

  **WHY Each Reference Matters**:
  - FastAPI middleware docs: Shows the correct pattern for request interception in ASGI

  **Acceptance Criteria**:
  - [ ] `pytest senji-gateway/tests/test_auth.py` → PASS
  - [ ] Unauthenticated request to `/api/convert/url` → 401 with `{"error":"unauthorized"}`
  - [ ] Authenticated request with correct token → passes through
  - [ ] `/health` without token → 200

  **QA Scenarios**:

  ```
  Scenario: Unauthenticated API request rejected
    Tool: Bash (curl)
    Preconditions: Gateway running with SENJI_TOKEN=test-token-123
    Steps:
      1. Run `curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/convert/url -H "Content-Type: application/json" -d '{"url":"https://example.com"}'`
      2. Assert status is 401
      3. Run `curl -s http://localhost:8000/api/convert/url -X POST -H "Content-Type: application/json" -d '{"url":"https://example.com"}'`
      4. Assert response body contains "unauthorized"
    Expected Result: 401 with error message
    Failure Indicators: 200, 500, or missing error body
    Evidence: .sisyphus/evidence/task-8-auth-reject.txt

  Scenario: Authenticated request passes through
    Tool: Bash (curl)
    Preconditions: Gateway running with SENJI_TOKEN=test-token-123
    Steps:
      1. Run `curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/convert/url -H "Authorization: Bearer test-token-123" -H "Content-Type: application/json" -d '{"url":"https://example.com"}'`
      2. Assert status is NOT 401 (should be 501 from stub, not 401)
    Expected Result: Request reaches route handler (501 stub), not blocked by auth
    Failure Indicators: 401 despite correct token
    Evidence: .sisyphus/evidence/task-8-auth-pass.txt

  Scenario: Health and dashboard exempt from auth
    Tool: Bash (curl)
    Preconditions: Gateway running
    Steps:
      1. Run `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health` (no token)
      2. Assert status is 200
      3. Run `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/` (no token)
      4. Assert status is 200
    Expected Result: Both exempt paths return 200 without auth
    Failure Indicators: 401 on health or dashboard
    Evidence: .sisyphus/evidence/task-8-auth-exempt.txt
  ```

  **Commit**: YES (groups with T7)
  - Message: `feat(gateway): structured logging and bearer auth`
  - Files: `senji-gateway/app/middleware/auth.py`, `senji-gateway/tests/test_auth.py`
  - Pre-commit: `pytest senji-gateway/tests/test_auth.py`

- [x] 9. Gateway: URL Fetch + Route to Readability

  **What to do**:
  - Create `senji-gateway/app/services/fetcher.py` — URL fetching service (SRP):
    ```python
    # Responsibilities: fetch URL, follow redirects, return HTML + final URL + title
    # Uses httpx async client
    # User-Agent: Mozilla/5.0 (compatible browser string)
    # Timeout: 30 seconds
    # Follow redirects: yes, record final URL for frontmatter
    # Return: { html: str, final_url: str, content_type: str }
    ```
  - Create `senji-gateway/app/services/readability_client.py` — client for Readability service:
    ```python
    # POST to http://readability:3000/convert with { html: str }
    # Returns: { markdown: str, title: str }
    # Handles: connection errors, timeouts, non-200 responses
    ```
  - Create `senji-gateway/app/routes/convert.py` — implement `POST /api/convert/url`:
    1. Validate request body (`ConvertURLRequest`)
    2. Fetch URL via fetcher service
    3. Send HTML to Readability service
    4. Return `ConvertResponse` (markdown + title + source URL, no media/frontmatter yet)
  - Wire route into `app/main.py`
  - Write TDD tests:
    - Valid URL → fetches and converts (mock both fetcher and readability client)
    - Invalid URL → 422 validation error
    - Fetch timeout → appropriate error response
    - Readability service unreachable → appropriate error response
    - Redirect followed → final URL used as source

  **Must NOT do**:
  - Do NOT add media download yet (Task 13)
  - Do NOT add frontmatter yet (Task 12)
  - Do NOT handle file uploads (Task 11)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Core routing logic with async HTTP calls, error handling, and service integration
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6, 7, 8, 10, 11)
  - **Blocks**: Tasks 12, 13, 14, 15
  - **Blocked By**: Tasks 2, 5, 6, 7, 8

  **References**:

  **Pattern References**:
  - `shortcuts/clip.py:317-328` — `fetch_url()` — existing URL fetching with User-Agent and timeout. Port this pattern to async httpx.
  - `shortcuts/clip.py:330-338` — `extract_title()` — fallback title extraction from HTML `<title>` tag. Readability service returns title, but gateway should have a fallback.
  - `senji-gateway/app/models/schemas.py` — `ConvertURLRequest`, `ConvertResponse` — request/response contracts

  **External References**:
  - httpx async usage: `https://www.python-httpx.org/async/`
  - FastAPI dependency injection: `https://fastapi.tiangolo.com/tutorial/dependencies/`

  **WHY Each Reference Matters**:
  - `clip.py` fetcher: Shows the User-Agent string and timeout pattern to replicate
  - httpx: Gateway uses async HTTP to call both the fetcher and Readability service

  **Acceptance Criteria**:
  - [ ] `pytest senji-gateway/tests/test_convert_url.py` → PASS
  - [ ] POST `/api/convert/url` with valid URL + token → 200 with `{markdown, title, source}`
  - [ ] Invalid URL → 422
  - [ ] Readability service down → 503 with `{"error":"readability_unavailable"}`

  **QA Scenarios**:

  ```
  Scenario: URL conversion returns markdown
    Tool: Bash (curl)
    Preconditions: Gateway + Readability service running, SENJI_TOKEN set
    Steps:
      1. Run `curl -s http://localhost:8000/api/convert/url -H "Authorization: Bearer $SENJI_TOKEN" -H "Content-Type: application/json" -d '{"url":"https://example.com"}'`
      2. Parse response as JSON
      3. Assert "markdown" key exists and is non-empty
      4. Assert "title" key exists
      5. Assert "source" key equals "https://example.com" or final redirect URL
    Expected Result: Successful conversion with all response fields
    Failure Indicators: 500, empty markdown, missing fields
    Evidence: .sisyphus/evidence/task-9-url-convert.txt

  Scenario: Invalid URL returns 422
    Tool: Bash (curl)
    Preconditions: Gateway running
    Steps:
      1. Run `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/convert/url -H "Authorization: Bearer $SENJI_TOKEN" -H "Content-Type: application/json" -d '{"url":"not-a-valid-url"}'`
      2. Assert status is 422
    Expected Result: Validation error for malformed URL
    Failure Indicators: 200 or 500 instead of 422
    Evidence: .sisyphus/evidence/task-9-invalid-url.txt
  ```

  **Commit**: YES (groups with T10-T11)
  - Message: `feat(gateway): conversion endpoints (URL, HTML, file)`
  - Files: `senji-gateway/app/services/fetcher.py`, `senji-gateway/app/services/readability_client.py`, `senji-gateway/app/routes/convert.py`, `senji-gateway/tests/test_convert_url.py`
  - Pre-commit: `pytest senji-gateway/tests/test_convert_url.py`

- [x] 10. Gateway: HTML Paste Endpoint

  **What to do**:
  - Add `POST /api/convert/html` to `senji-gateway/app/routes/convert.py`:
    1. Validate request body (`ConvertHTMLRequest` — html: str, source_url: str | None)
    2. Send HTML directly to Readability service
    3. Return `ConvertResponse`
  - Handle edge case: raw HTML snippet vs full page
    - If HTML doesn't contain `<html>` or `<body>`, wrap in `<html><body>{html}</body></html>` before sending to Readability
    - Log a warning when wrapping: "Received HTML snippet, wrapping in body tags"
  - Write TDD tests:
    - Full HTML page → converts normally
    - HTML snippet (`<h1>Title</h1><p>Text</p>`) → wraps and converts
    - Empty HTML → returns empty markdown, no crash
    - With source_url → appears in response.source
    - Without source_url → source is "paste" or empty string

  **Must NOT do**:
  - Do NOT add URL fetching — this endpoint receives raw HTML only
  - Do NOT add media download — raw paste has no downloadable media context

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Endpoint logic with edge case handling (snippet wrapping)
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6, 7, 8, 9, 11)
  - **Blocks**: Task 16
  - **Blocked By**: Tasks 2, 5, 6, 7, 8

  **References**:

  **Pattern References**:
  - `senji-gateway/app/routes/convert.py` — `/api/convert/url` endpoint pattern (Task 9) — follow same structure
  - `senji-gateway/app/models/schemas.py` — `ConvertHTMLRequest`, `ConvertResponse`

  **WHY Each Reference Matters**:
  - Task 9's convert route: Reuse the same Readability client call pattern, just skip the fetch step

  **Acceptance Criteria**:
  - [ ] `pytest senji-gateway/tests/test_convert_html.py` → PASS
  - [ ] POST with full HTML page → 200 with markdown
  - [ ] POST with HTML snippet → 200 with markdown (auto-wrapped)
  - [ ] POST with empty HTML → 200 with empty markdown, no crash

  **QA Scenarios**:

  ```
  Scenario: HTML snippet converts correctly
    Tool: Bash (curl)
    Preconditions: Gateway + Readability running
    Steps:
      1. Run `curl -s http://localhost:8000/api/convert/html -H "Authorization: Bearer $SENJI_TOKEN" -H "Content-Type: application/json" -d '{"html":"<h1>Hello</h1><p>World</p>"}'`
      2. Parse response JSON
      3. Assert "markdown" contains "Hello" and "World"
    Expected Result: Snippet wrapped and converted successfully
    Failure Indicators: Empty markdown, 500 error
    Evidence: .sisyphus/evidence/task-10-html-snippet.txt

  Scenario: Empty HTML handled gracefully
    Tool: Bash (curl)
    Preconditions: Gateway + Readability running
    Steps:
      1. Run `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/convert/html -H "Authorization: Bearer $SENJI_TOKEN" -H "Content-Type: application/json" -d '{"html":""}'`
      2. Assert status is 200 (not 500)
    Expected Result: Graceful empty response
    Failure Indicators: 500 server error
    Evidence: .sisyphus/evidence/task-10-empty-html.txt
  ```

  **Commit**: YES (groups with T9, T11)
  - Message: `feat(gateway): conversion endpoints (URL, HTML, file)`
  - Files: `senji-gateway/app/routes/convert.py` (add endpoint), `senji-gateway/tests/test_convert_html.py`
  - Pre-commit: `pytest senji-gateway/tests/test_convert_html.py`

- [x] 11. Gateway: File Upload + Route to Docling

  **What to do**:
  - Create `senji-gateway/app/services/docling_client.py` — client for Docling Serve:
    ```python
    # POST file to Docling Serve's /v1/convert/file endpoint
    # Send as multipart/form-data
    # Docling returns structured response — extract markdown output
    # Handle: connection errors, timeouts (60s for large PDFs), non-200 responses
    ```
  - **IMPORTANT**: Before implementing, verify Docling Serve's actual API contract:
    - Pull `ghcr.io/docling-project/docling-serve:1.16.1`
    - Run it locally and check `/docs` (FastAPI auto-docs)
    - Verify: exact endpoint path, request format (multipart field name), response shape, output format parameter
    - Document findings in code comments
  - Add `POST /api/convert/file` to routes:
    1. Accept file upload via `UploadFile` (FastAPI)
    2. Validate file type: allow `.pdf`, `.docx`, `.pptx` only
    3. Forward file to Docling Serve
    4. Parse Docling response, extract markdown
    5. Return `ConvertResponse`
  - Write TDD tests:
    - PDF upload → markdown returned
    - DOCX upload → markdown returned
    - Unsupported file type (e.g., .exe) → 415 Unsupported Media Type
    - Docling service down → 503 with `{"error":"docling_unavailable"}`
    - File too large (>50MB) → 413

  **Must NOT do**:
  - Do NOT build a custom PDF parser — Docling handles everything
  - Do NOT add EPUB/MOBI support — only PDF, DOCX, PPTX in v1
  - Do NOT add batch file upload

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Requires verifying Docling API contract and integrating with external service
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6, 7, 8, 9, 10)
  - **Blocks**: Tasks 14, 16
  - **Blocked By**: Tasks 2, 5, 7, 8

  **References**:

  **External References**:
  - Docling Serve API: `https://github.com/docling-project/docling-serve` — check `/docs` endpoint after running the image
  - Docling Serve OpenAPI: Run `docker run -p 5001:5001 ghcr.io/docling-project/docling-serve:1.16.1` then `curl http://localhost:5001/docs`
  - FastAPI file uploads: `https://fastapi.tiangolo.com/tutorial/request-files/`

  **WHY Each Reference Matters**:
  - Docling Serve API: MUST verify actual endpoint path and response format before coding. Research found `/v1/convert/file` but this needs runtime validation.
  - FastAPI uploads: Shows `UploadFile` parameter pattern for multipart handling

  **Acceptance Criteria**:
  - [ ] `pytest senji-gateway/tests/test_convert_file.py` → PASS
  - [ ] PDF upload → 200 with markdown content
  - [ ] Unsupported file type → 415
  - [ ] Docling down → 503 with meaningful error
  - [ ] Docling API contract documented in code comments

  **QA Scenarios**:

  ```
  Scenario: PDF file converts to markdown
    Tool: Bash (curl)
    Preconditions: Gateway + Docling running, test PDF available
    Steps:
      1. Create a simple test PDF (or use a known sample PDF)
      2. Run `curl -s http://localhost:8000/api/convert/file -H "Authorization: Bearer $SENJI_TOKEN" -F "file=@test.pdf"`
      3. Parse response JSON
      4. Assert "markdown" key exists and is non-empty
      5. Assert "title" key exists
    Expected Result: PDF converted to markdown with extracted content
    Failure Indicators: Empty markdown, 500, Docling connection error
    Evidence: .sisyphus/evidence/task-11-pdf-convert.txt

  Scenario: Unsupported file type rejected
    Tool: Bash (curl)
    Preconditions: Gateway running
    Steps:
      1. Create a dummy .exe file: `echo "fake" > test.exe`
      2. Run `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/convert/file -H "Authorization: Bearer $SENJI_TOKEN" -F "file=@test.exe"`
      3. Assert status is 415
    Expected Result: Rejected with Unsupported Media Type
    Failure Indicators: 200 or 500 instead of 415
    Evidence: .sisyphus/evidence/task-11-unsupported-type.txt
  ```

  **Commit**: YES (groups with T9-T10)
  - Message: `feat(gateway): conversion endpoints (URL, HTML, file)`
  - Files: `senji-gateway/app/services/docling_client.py`, `senji-gateway/app/routes/convert.py` (add endpoint), `senji-gateway/tests/test_convert_file.py`
  - Pre-commit: `pytest senji-gateway/tests/test_convert_file.py`

- [x] 12. Gateway: Obsidian Frontmatter Generation

  **What to do**:
  - Create `senji-gateway/app/services/frontmatter.py` (SRP — pure function, no HTTP):
    ```python
    def generate_frontmatter(source: str, title: str, clip_type: str, extra_tags: list[str] | None = None) -> str:
        """Generate YAML frontmatter block for Obsidian.
        
        Fields: source, title, clipped (ISO datetime), type, tags
        Returns: string starting with --- and ending with ---
        """
    
    def prepend_frontmatter(markdown: str, source: str, title: str, clip_type: str) -> str:
        """Prepend frontmatter to markdown content."""
    ```
  - Integrate into all convert endpoints (URL, HTML, file):
    - After receiving markdown from Readability/Docling, prepend frontmatter
    - clip_type: "web" for URL, "paste" for HTML, "pdf"/"docx"/"pptx" for files
    - tags: `["clipping", "inbox"]` + type-specific tag
  - YAML escaping: handle titles with quotes, colons, special chars
  - Write TDD tests:
    - Frontmatter has all 5 fields (source, title, clipped, type, tags)
    - `clipped` is valid ISO 8601 datetime
    - Title with special chars (quotes, colons) properly escaped
    - Different clip_types produce correct type field
    - Output starts with `---\n` and contains closing `---\n`

  **Must NOT do**:
  - Do NOT add custom frontmatter templates — hardcoded fields only
  - Do NOT add AI-generated tags
  - Do NOT add configurable fields

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Pure function, straightforward string formatting with YAML escaping
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 13-17)
  - **Blocks**: Task 19
  - **Blocked By**: Task 9 (needs convert endpoints to integrate into)

  **References**:

  **Pattern References**:
  - `shortcuts/clip.py:110-127` — existing `_yaml_escape()` and `build_frontmatter()` — port this exact logic to the new module. The escaping rules and field set are proven.

  **WHY Each Reference Matters**:
  - `clip.py` frontmatter builder: The exact YAML escaping logic and field set to replicate. Don't reinvent — port.

  **Acceptance Criteria**:
  - [ ] `pytest senji-gateway/tests/test_frontmatter.py` → PASS
  - [ ] Frontmatter output starts with `---` and ends with `---`
  - [ ] All 5 fields present: source, title, clipped, type, tags
  - [ ] Title `He said "hello": world` correctly escaped in YAML
  - [ ] Convert endpoints now return markdown with frontmatter prepended

  **QA Scenarios**:

  ```
  Scenario: URL conversion includes frontmatter
    Tool: Bash (curl)
    Preconditions: Gateway + Readability running
    Steps:
      1. Run URL conversion: `curl -s http://localhost:8000/api/convert/url -H "Authorization: Bearer $SENJI_TOKEN" -H "Content-Type: application/json" -d '{"url":"https://example.com"}'`
      2. Extract "markdown" field from response
      3. Assert markdown starts with "---"
      4. Assert markdown contains "source:" and "title:" and "clipped:" and "type: web" and "tags:"
    Expected Result: Frontmatter present with all fields
    Failure Indicators: Missing frontmatter, missing fields, YAML syntax error
    Evidence: .sisyphus/evidence/task-12-frontmatter-url.txt

  Scenario: Special characters in title don't break YAML
    Tool: Bash (pytest)
    Preconditions: frontmatter.py exists
    Steps:
      1. Run `pytest senji-gateway/tests/test_frontmatter.py -v -k "special_chars"`
      2. Test with title: 'He said "hello": world & more'
      3. Assert output is valid YAML (parseable)
    Expected Result: YAML escaping handles all special chars
    Failure Indicators: YAML parse error, unescaped quotes
    Evidence: .sisyphus/evidence/task-12-yaml-escaping.txt
  ```

  **Commit**: YES (groups with T13)
  - Message: `feat(gateway): frontmatter generation and media download`
  - Files: `senji-gateway/app/services/frontmatter.py`, `senji-gateway/tests/test_frontmatter.py`
  - Pre-commit: `pytest senji-gateway/tests/test_frontmatter.py`

- [x] 13. Gateway: Media/Image Download Pipeline

  **What to do**:
  - Create `senji-gateway/app/services/media.py` — image download service (SRP):
    ```python
    async def extract_and_download_images(html: str, base_url: str) -> tuple[str, list[MediaItem]]:
        """Extract image URLs from HTML, download them, return updated HTML + media list.
        
        1. Parse HTML for <img> src and data-src attributes
        2. Resolve relative URLs against base_url
        3. Download each image via httpx (async, parallel)
        4. Filter: skip data: URIs, tracking pixels, images < 10KB
        5. Convert to base64, create MediaItem for each
        6. Update HTML img src to reference local filename
        7. Return: (updated_html, list[MediaItem])
        """
    ```
  - Integrate into URL convert endpoint:
    1. After fetching HTML, before sending to Readability: extract and download images
    2. Update image URLs in HTML to local filenames
    3. After Readability conversion, markdown will have `![alt](local-filename.jpg)`
    4. Include downloaded media in ConvertResponse.media array
  - Handle edge cases:
    - Relative URLs (`/img/photo.jpg`) → resolve against base URL
    - Protocol-relative (`//cdn.example.com/img.jpg`) → add `https:`
    - Download failures → log warning, keep original URL, continue
    - Timeout per image: 15 seconds
    - Max images per page: 50 (prevent abuse)
    - Skip SVGs (as clip.py does)
  - Write TDD tests:
    - HTML with 3 images → 3 MediaItems returned
    - Relative URL resolved correctly
    - Image < 10KB filtered out
    - Download failure → graceful skip with log
    - data: URI skipped
    - Max 50 images enforced

  **Must NOT do**:
  - Do NOT add image processing (resize, compress, format convert)
  - Do NOT cache images between requests (stateless)
  - Do NOT download images for paste endpoint (no base URL context)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Complex async pipeline with URL resolution, parallel downloads, error handling, size filtering
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 12, 14-17)
  - **Blocks**: Task 19
  - **Blocked By**: Task 9 (needs URL convert endpoint to integrate into)

  **References**:

  **Pattern References**:
  - `shortcuts/clip.py:406-463` — `download_images()` — existing image download logic with: regex extraction, relative URL resolution, size filtering (<10KB), extension detection, tracking pixel skip. Port this logic to async httpx.

  **WHY Each Reference Matters**:
  - `clip.py` download_images: Contains battle-tested filtering logic (tracking pixels, size threshold, SVG skip, extension detection) that should be ported directly. Don't reinvent these heuristics.

  **Acceptance Criteria**:
  - [ ] `pytest senji-gateway/tests/test_media.py` → PASS
  - [ ] HTML with images → MediaItems with base64 data returned
  - [ ] Relative URLs resolved against base_url
  - [ ] Images < 10KB filtered out
  - [ ] Download failures logged but don't crash the conversion

  **QA Scenarios**:

  ```
  Scenario: URL conversion includes downloaded images
    Tool: Bash (curl)
    Preconditions: Gateway + Readability running
    Steps:
      1. Convert a URL known to have images (e.g., a Wikipedia article)
      2. Run `curl -s http://localhost:8000/api/convert/url -H "Authorization: Bearer $SENJI_TOKEN" -H "Content-Type: application/json" -d '{"url":"https://en.wikipedia.org/wiki/Markdown"}'`
      3. Parse response JSON
      4. Assert "media" array has at least 1 item
      5. Assert each media item has "filename", "content_type", "data" keys
      6. Assert "data" field is valid base64 (decode doesn't error)
    Expected Result: Images downloaded and returned as base64
    Failure Indicators: Empty media array, invalid base64, missing fields
    Evidence: .sisyphus/evidence/task-13-media-download.txt

  Scenario: Failed image download doesn't break conversion
    Tool: Bash (curl)
    Preconditions: Gateway + Readability running
    Steps:
      1. Create HTML with an image pointing to unreachable URL: <img src="https://fake.invalid/img.jpg">
      2. POST to /api/convert/html with this HTML
      3. Assert HTTP status is 200 (not 500)
      4. Assert "markdown" is still returned (conversion succeeded despite image failure)
    Expected Result: Conversion succeeds, failed image skipped gracefully
    Failure Indicators: 500 error, empty response
    Evidence: .sisyphus/evidence/task-13-media-failure.txt
  ```

  **Commit**: YES (groups with T12)
  - Message: `feat(gateway): frontmatter generation and media download`
  - Files: `senji-gateway/app/services/media.py`, `senji-gateway/tests/test_media.py`
  - Pre-commit: `pytest senji-gateway/tests/test_media.py`

- [x] 14. Gateway: Error Handling (Timeouts, 4xx/5xx, Validation)

  **What to do**:
  - Create `senji-gateway/app/middleware/error_handler.py` — global exception handler:
    ```python
    # Catch all unhandled exceptions → return consistent ErrorResponse JSON
    # Map specific exceptions to HTTP status codes:
    # - ValidationError → 422
    # - httpx.TimeoutException → 504 Gateway Timeout
    # - httpx.ConnectError → 503 Service Unavailable
    # - FileUpload too large → 413
    # - Unsupported file type → 415
    # - General exception → 500 with logged traceback
    ```
  - Add request timeout configuration:
    - URL fetch: 30s
    - Readability conversion: 30s
    - Docling conversion: 120s (large PDFs)
    - Image download: 15s per image
  - Add request logging middleware:
    - Log every request: method, path, status, duration_ms
    - Structured JSON format matching Task 7's logger
  - Wire into `app/main.py`
  - Write TDD tests:
    - Timeout → 504 with `{"error":"timeout","detail":"..."}`
    - Service down → 503 with `{"error":"<service>_unavailable"}`
    - Validation error → 422 with field-level details
    - Unhandled exception → 500 with generic message (no stack trace in response)
    - All error responses match `ErrorResponse` schema

  **Must NOT do**:
  - Do NOT add retry logic — fail fast, let client retry
  - Do NOT add circuit breakers — YAGNI for v1
  - Do NOT expose stack traces in API responses — log them, return generic message

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Cross-cutting concern touching all endpoints, requires understanding of all error paths
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 12, 13, 15-17)
  - **Blocks**: Task 19
  - **Blocked By**: Tasks 9, 11 (needs endpoints to add error handling to)

  **References**:

  **Pattern References**:
  - `senji-gateway/app/models/schemas.py` — `ErrorResponse` schema — all errors must match this format
  - `senji-gateway/app/logging.py` — structured logger — errors must be logged with traceback via `logger.exception()`

  **External References**:
  - FastAPI exception handlers: `https://fastapi.tiangolo.com/tutorial/handling-errors/`
  - httpx exceptions: `https://www.python-httpx.org/exceptions/`

  **WHY Each Reference Matters**:
  - ErrorResponse schema: All error responses must serialize to this shape for consistent API contract
  - httpx exceptions: Must catch the right exception types (TimeoutException, ConnectError, HTTPStatusError)

  **Acceptance Criteria**:
  - [ ] `pytest senji-gateway/tests/test_errors.py` → PASS
  - [ ] All error responses match `ErrorResponse` schema
  - [ ] Timeouts return 504, service down returns 503, validation returns 422
  - [ ] No stack traces in HTTP responses
  - [ ] Stack traces logged via structured logger

  **QA Scenarios**:

  ```
  Scenario: Unreachable URL returns timeout/error
    Tool: Bash (curl)
    Preconditions: Gateway running
    Steps:
      1. Run `curl -s -w "\n%{http_code}" http://localhost:8000/api/convert/url -H "Authorization: Bearer $SENJI_TOKEN" -H "Content-Type: application/json" -d '{"url":"https://httpstat.us/504?sleep=60000"}'`
      2. Assert status is 504 or 502
      3. Parse response body as JSON
      4. Assert "error" key exists
      5. Assert response does NOT contain Python traceback text
    Expected Result: Clean error response with appropriate status
    Failure Indicators: 500 with traceback, hanging request
    Evidence: .sisyphus/evidence/task-14-timeout-error.txt

  Scenario: All errors follow ErrorResponse schema
    Tool: Bash (pytest)
    Preconditions: error handler and test fixtures exist
    Steps:
      1. Run `pytest senji-gateway/tests/test_errors.py -v`
      2. Assert all error response tests pass
      3. Each test verifies response matches {"error": str, "detail": str} shape
    Expected Result: Consistent error format across all error types
    Failure Indicators: Missing fields, inconsistent shape between error types
    Evidence: .sisyphus/evidence/task-14-error-schema.txt
  ```

  **Commit**: YES
  - Message: `feat(gateway): error handling and validation`
  - Files: `senji-gateway/app/middleware/error_handler.py`, `senji-gateway/tests/test_errors.py`
  - Pre-commit: `pytest senji-gateway/tests/test_errors.py`

- [x] 15. Dashboard — HTML Shell + URL Conversion Tab

  **What to do**:
  - Create `senji-gateway/static/index.html` — single-page dashboard with semantic HTML
  - Structure: header (logo + dark mode toggle), main with 3 tabs (URL / Upload / Paste), results area (preview + actions)
  - URL tab: input field + "Convert" button → `POST /api/convert/url` with bearer token from `<meta>` tag or JS config
  - Results area: raw markdown in `<pre><code>` block, "Copy" button (Clipboard API), "Download .md" button (Blob URL)
  - Create `senji-gateway/static/style.css` — CSS variables for light/dark theme, mobile-first responsive (375px+)
  - Dark mode: toggle button switches `data-theme` attribute on `<html>`, persist choice in `localStorage`
  - Create `senji-gateway/static/app.js` — vanilla JS, no build tools, no frameworks
  - Tab switching: show/hide with `aria-selected` + `role="tabpanel"` for accessibility
  - Loading state: disable button + show spinner during conversion
  - Error display: red banner with error message from API response
  - Mount static files in FastAPI: `app.mount("/", StaticFiles(directory="static", html=True))`

  **Must NOT do**:
  - No React, Vue, Svelte, or any framework
  - No npm, webpack, vite, or any build tool
  - No CSS framework (Tailwind, Bootstrap)
  - No WYSIWYG markdown preview — use `<pre>` block only
  - No template engine — plain HTML served as static files

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: Frontend UI work requiring layout, styling, and interactive behavior
  - **Skills**: [`playwright`]
    - `playwright`: Needed for QA scenario verification — browser interaction testing

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 12, 13, 14, 16, 17)
  - **Blocks**: T16, T17
  - **Blocked By**: T5 (gateway scaffolding for static mount)

  **References**:

  **Pattern References**:
  - `senji-gateway/app/main.py` — Add `StaticFiles` mount after all API routes
  - `senji-gateway/app/schemas.py` — API request/response shapes for JS fetch calls

  **API/Type References**:
  - `POST /api/convert/url` — `ConvertURLRequest` → `ConvertResponse` (from T2 schemas)
  - Bearer token header: `Authorization: Bearer <token>`

  **External References**:
  - MDN Clipboard API: `navigator.clipboard.writeText()` for copy button
  - MDN Blob/URL: `URL.createObjectURL(new Blob([md]))` for download button
  - CSS `prefers-color-scheme` media query for initial theme detection

  **WHY Each Reference Matters**:
  - `main.py` mount point — static files must be mounted AFTER API routes to avoid path conflicts
  - `schemas.py` — JS fetch calls must match exact request shape and parse exact response shape

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Dashboard loads and shows URL tab by default
    Tool: Playwright
    Preconditions: Gateway running with static files mounted
    Steps:
      1. Navigate to http://localhost:8000/
      2. Assert page title contains "Senji"
      3. Assert URL tab is visible and selected (`[aria-selected="true"]`)
      4. Assert URL input field exists (`input[type="url"]` or `input#url-input`)
      5. Assert Convert button exists and is enabled
    Expected Result: Dashboard renders with URL tab active
    Failure Indicators: 404, blank page, missing elements
    Evidence: .sisyphus/evidence/task-15-dashboard-loads.png

  Scenario: URL conversion works end-to-end via dashboard
    Tool: Playwright
    Preconditions: Gateway + Readability service running
    Steps:
      1. Navigate to http://localhost:8000/
      2. Type "https://example.com" into URL input field
      3. Click Convert button
      4. Wait for results area to appear (timeout: 15s)
      5. Assert results area contains markdown text starting with "---"
      6. Assert Copy button is visible
      7. Assert Download button is visible
    Expected Result: Markdown preview shows converted content with frontmatter
    Failure Indicators: Spinner never stops, error banner, empty results
    Evidence: .sisyphus/evidence/task-15-url-conversion.png

  Scenario: Dark mode toggle works
    Tool: Playwright
    Preconditions: Dashboard loaded
    Steps:
      1. Navigate to http://localhost:8000/
      2. Note initial background color of `<body>`
      3. Click dark mode toggle button
      4. Assert `<html>` has `data-theme="dark"` attribute
      5. Assert background color changed
      6. Reload page
      7. Assert dark mode persists (localStorage)
    Expected Result: Theme toggles and persists across reloads
    Failure Indicators: No visual change, localStorage not set
    Evidence: .sisyphus/evidence/task-15-dark-mode.png

  Scenario: Mobile viewport is usable
    Tool: Playwright
    Preconditions: Dashboard loaded
    Steps:
      1. Set viewport to 375x667 (iPhone SE)
      2. Navigate to http://localhost:8000/
      3. Assert no horizontal scrollbar
      4. Assert URL input and Convert button are visible and tappable
      5. Assert tabs are accessible (not cut off)
    Expected Result: Dashboard is fully functional at mobile width
    Failure Indicators: Horizontal scroll, overlapping elements, cut-off buttons
    Evidence: .sisyphus/evidence/task-15-mobile.png

  Scenario: Error state displays correctly
    Tool: Playwright
    Preconditions: Gateway running, Readability service DOWN
    Steps:
      1. Navigate to http://localhost:8000/
      2. Type "https://example.com" into URL input
      3. Click Convert button
      4. Wait for error response (timeout: 15s)
      5. Assert error banner appears with red/warning styling
      6. Assert error message text is human-readable (not raw JSON or traceback)
    Expected Result: Clean error message displayed to user
    Failure Indicators: Unhandled JS error, no feedback, raw JSON dump
    Evidence: .sisyphus/evidence/task-15-error-state.png
  ```

  **Commit**: YES (groups with T16, T17)
  - Message: `feat(dashboard): web UI with URL/upload/paste conversion`
  - Files: `senji-gateway/static/index.html`, `senji-gateway/static/style.css`, `senji-gateway/static/app.js`
  - Pre-commit: Playwright tests

- [x] 16. Dashboard — Upload Tab (File Conversion)

  **What to do**:
  - Add Upload tab to dashboard — file input (`<input type="file" accept=".pdf,.docx,.pptx">`) + drag-and-drop zone
  - Drag-and-drop: `dragover`/`drop` events on a styled drop zone, visual feedback on drag enter/leave
  - On file select or drop: `POST /api/convert/file` as `multipart/form-data` with bearer auth
  - Show file name and size before upload, show loading spinner during conversion
  - Display result in same results area as URL tab (shared component)
  - File size validation client-side: reject files >50MB with inline error message
  - Supported file types: PDF, DOCX, PPTX — reject others with "Unsupported format" message

  **Must NOT do**:
  - No multi-file upload — single file only
  - No progress bar (not worth complexity for v1)
  - No client-side file preview (no PDF.js)

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: Frontend interactive file handling with drag-and-drop UX
  - **Skills**: [`playwright`]
    - `playwright`: Browser-based QA verification

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential after T15
  - **Blocks**: T17
  - **Blocked By**: T15 (dashboard shell must exist)

  **References**:

  **Pattern References**:
  - `senji-gateway/static/app.js` — Extend existing JS with upload tab logic
  - `senji-gateway/static/index.html` — Add upload tab panel to existing tab structure

  **API/Type References**:
  - `POST /api/convert/file` — multipart form upload → `ConvertResponse`
  - File type validation: `.pdf`, `.docx`, `.pptx` only

  **External References**:
  - MDN Drag and Drop API: `dragover`, `drop`, `dataTransfer.files`
  - MDN FormData: `new FormData(); formData.append("file", file)`

  **WHY Each Reference Matters**:
  - `app.js` existing code — must integrate with shared tab switching and results display logic
  - FormData API — correct multipart encoding required for file upload endpoint

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Upload tab accepts and converts a PDF
    Tool: Playwright
    Preconditions: Gateway + Docling running, test PDF available
    Steps:
      1. Navigate to http://localhost:8000/
      2. Click Upload tab
      3. Use file chooser to select a test PDF file
      4. Assert file name appears in the UI
      5. Click Convert (or auto-submit)
      6. Wait for results (timeout: 120s — Docling can be slow)
      7. Assert markdown content appears in results area
    Expected Result: PDF converted to markdown and displayed
    Failure Indicators: Timeout, error banner, empty result
    Evidence: .sisyphus/evidence/task-16-pdf-upload.png

  Scenario: Drag-and-drop works
    Tool: Playwright
    Preconditions: Dashboard loaded, test PDF available
    Steps:
      1. Navigate to http://localhost:8000/
      2. Click Upload tab
      3. Simulate file drop on drop zone (Playwright `page.dispatchEvent` or `setInputFiles`)
      4. Assert file name appears
      5. Assert conversion starts
    Expected Result: Dropped file triggers conversion flow
    Failure Indicators: No response to drop, file ignored
    Evidence: .sisyphus/evidence/task-16-drag-drop.png

  Scenario: Unsupported file type rejected
    Tool: Playwright
    Preconditions: Dashboard loaded
    Steps:
      1. Navigate to http://localhost:8000/
      2. Click Upload tab
      3. Attempt to select a `.txt` file via file input
      4. Assert error message "Unsupported format" appears
      5. Assert no API call is made (check network tab or lack of loading spinner)
    Expected Result: Client-side rejection with clear message
    Failure Indicators: File sent to API, server error, no feedback
    Evidence: .sisyphus/evidence/task-16-unsupported-file.png

  Scenario: Oversized file rejected client-side
    Tool: Playwright
    Preconditions: Dashboard loaded
    Steps:
      1. Navigate to http://localhost:8000/
      2. Click Upload tab
      3. Select a file >50MB (or mock file size check)
      4. Assert error message about file size limit appears
      5. Assert no API call is made
    Expected Result: Client-side size validation prevents upload
    Failure Indicators: Large file uploaded, server 413
    Evidence: .sisyphus/evidence/task-16-oversized-file.png
  ```

  **Commit**: YES (groups with T15, T17)
  - Message: `feat(dashboard): web UI with URL/upload/paste conversion`
  - Files: `senji-gateway/static/index.html`, `senji-gateway/static/app.js`, `senji-gateway/static/style.css`
  - Pre-commit: Playwright tests

- [x] 17. Dashboard — Paste Tab + Final Polish

  **What to do**:
  - Add Paste tab — `<textarea>` for raw HTML input + Convert button
  - On submit: `POST /api/convert/html` with `{"html": textarea.value}` + bearer auth
  - Display result in shared results area
  - Add "Clear" button to reset all tabs + results
  - Final polish:
    - Favicon (simple SVG inline or data URI — no external file needed)
    - `<meta name="viewport">` for mobile
    - `<meta name="description">` for SEO-irrelevant but good practice
    - Keyboard shortcuts: `Cmd/Ctrl+Enter` to submit active tab
    - Focus management: auto-focus first input when switching tabs
    - Accessibility: proper ARIA labels, focus visible styles, skip-to-content

  **Must NOT do**:
  - No markdown preview rendering (no marked.js) — raw `<pre>` only
  - No syntax highlighting in the preview
  - No autosave or draft persistence

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: Frontend polish, accessibility, and interaction refinement
  - **Skills**: [`playwright`]
    - `playwright`: Final E2E browser verification

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential after T16
  - **Blocks**: T18
  - **Blocked By**: T16 (upload tab must exist for integration)

  **References**:

  **Pattern References**:
  - `senji-gateway/static/app.js` — Extend with paste tab + keyboard shortcuts
  - `senji-gateway/static/index.html` — Add paste tab panel + meta tags

  **API/Type References**:
  - `POST /api/convert/html` — `ConvertHTMLRequest` → `ConvertResponse`

  **External References**:
  - WAI-ARIA Tabs Pattern: `https://www.w3.org/WAI/ARIA/apg/patterns/tabs/`
  - MDN KeyboardEvent: `event.key === "Enter" && (event.metaKey || event.ctrlKey)`

  **WHY Each Reference Matters**:
  - ARIA tabs pattern — correct roles/attributes for screen reader compatibility
  - KeyboardEvent — cross-platform shortcut handling (Cmd on macOS, Ctrl elsewhere)

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Paste tab converts HTML to markdown
    Tool: Playwright
    Preconditions: Gateway + Readability service running
    Steps:
      1. Navigate to http://localhost:8000/
      2. Click Paste tab
      3. Type "<h1>Test Title</h1><p>Hello world</p>" into textarea
      4. Click Convert button
      5. Wait for results (timeout: 10s)
      6. Assert markdown contains "# Test Title" and "Hello world"
    Expected Result: HTML converted to markdown and displayed
    Failure Indicators: Empty result, error, raw HTML echoed back
    Evidence: .sisyphus/evidence/task-17-paste-conversion.png

  Scenario: Keyboard shortcut Cmd+Enter submits
    Tool: Playwright
    Preconditions: Dashboard loaded with URL tab active
    Steps:
      1. Navigate to http://localhost:8000/
      2. Type "https://example.com" into URL input
      3. Press Cmd+Enter (Meta+Enter)
      4. Assert conversion starts (loading spinner appears)
    Expected Result: Keyboard shortcut triggers conversion
    Failure Indicators: Nothing happens, page reloads
    Evidence: .sisyphus/evidence/task-17-keyboard-shortcut.png

  Scenario: Tab switching focuses correct input
    Tool: Playwright
    Preconditions: Dashboard loaded
    Steps:
      1. Navigate to http://localhost:8000/
      2. Click Upload tab — assert drop zone is visible
      3. Click Paste tab — assert textarea is focused
      4. Click URL tab — assert URL input is focused
    Expected Result: Each tab shows correct content and focuses input
    Failure Indicators: Wrong content shown, no focus, overlapping panels
    Evidence: .sisyphus/evidence/task-17-tab-focus.png

  Scenario: Clear button resets everything
    Tool: Playwright
    Preconditions: Dashboard loaded, a conversion completed (results visible)
    Steps:
      1. Complete a URL conversion (results showing)
      2. Click Clear button
      3. Assert URL input is empty
      4. Assert results area is hidden or empty
      5. Assert no loading state
    Expected Result: All inputs and results cleared
    Failure Indicators: Stale results visible, inputs not cleared
    Evidence: .sisyphus/evidence/task-17-clear-button.png
  ```

  **Commit**: YES (groups with T15, T16)
  - Message: `feat(dashboard): web UI with URL/upload/paste conversion`
  - Files: `senji-gateway/static/index.html`, `senji-gateway/static/app.js`, `senji-gateway/static/style.css`
  - Pre-commit: Playwright tests

- [x] 18. Docker Compose — Health Checks + Service Orchestration

  **What to do**:
  - Add health checks to all services in `docker-compose.yml`:
    - Gateway: `curl -sf http://localhost:8000/health`
    - Readability: `curl -sf http://localhost:3000/health`
    - Docling: `curl -sf http://localhost:5001/health` (verify actual Docling health endpoint)
  - Add `depends_on` with `condition: service_healthy` for startup ordering:
    - Gateway depends on Readability (healthy) + Docling (healthy)
  - Configure health check intervals: `interval: 10s`, `timeout: 5s`, `retries: 3`, `start_period: 60s` (Docling needs time to load models)
  - Add `restart: unless-stopped` to all services
  - Add Docker memory limits: gateway 512MB, readability 256MB, docling 8GB (for OCR models)
  - Add `.dockerignore` files for each service (exclude tests, docs, .git)
  - Create `Dockerfile` for gateway service: Python 3.12-slim, pip install, copy app + static
  - Create `Dockerfile` for readability service: Node 20-slim, npm ci --production, copy app
  - Verify Docling Serve uses pinned image tag `v1.16.1` (not `latest`)
  - Add `SENJI_TOKEN` as required env var with validation at startup

  **Must NOT do**:
  - No multi-stage builds (not worth complexity for this scale)
  - No Docker Swarm or Kubernetes configs
  - No container registry push (local build only for now)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Docker health checks, memory limits, Dockerfile creation, env validation — multiple concerns across services
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with T19, T20)
  - **Blocks**: F1-F4 (final verification needs working Docker)
  - **Blocked By**: T15 (static files must exist for gateway Dockerfile)

  **References**:

  **Pattern References**:
  - `docker-compose.yml` (T3) — Existing skeleton to extend with health checks
  - `senji-gateway/app/main.py` — Health endpoint location for Dockerfile CMD

  **API/Type References**:
  - Docling Serve health: verify `GET /health` exists at `ghcr.io/docling-project/docling-serve:v1.16.1`
  - Gateway `/health` response: `{"status":"ok","services":{"readability":"ok","docling":"ok"}}`

  **External References**:
  - Docker Compose healthcheck spec: `https://docs.docker.com/reference/compose-file/services/#healthcheck`
  - Docker memory limits: `deploy.resources.limits.memory` in Compose v3

  **WHY Each Reference Matters**:
  - `docker-compose.yml` skeleton — must extend, not rewrite, preserving existing service names and network config
  - Docling health endpoint — MUST verify actual endpoint path before configuring health check

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Docker Compose starts all services healthy
    Tool: Bash
    Preconditions: Docker installed, no port conflicts
    Steps:
      1. Run `docker compose build` from project root
      2. Run `SENJI_TOKEN=test-token docker compose up -d`
      3. Run `docker compose ps --format json | jq '.[].Health'` (retry for 120s)
      4. Assert all 3 services show "healthy"
      5. Run `curl -sf http://localhost:8000/health`
      6. Assert response contains `{"status":"ok"}`
    Expected Result: All 3 containers running and healthy
    Failure Indicators: Container in "unhealthy" or "starting" after 120s, health endpoint 5xx
    Evidence: .sisyphus/evidence/task-18-docker-healthy.txt

  Scenario: Gateway waits for dependencies before accepting requests
    Tool: Bash
    Preconditions: Clean Docker state
    Steps:
      1. Run `docker compose up -d`
      2. Immediately run `docker compose ps gateway --format json | jq '.Health'`
      3. Assert gateway is "starting" (not "healthy") while deps boot
      4. Wait for all healthy (timeout: 120s)
      5. Run a conversion request — assert 200
    Expected Result: Gateway doesn't serve until dependencies are ready
    Failure Indicators: Gateway healthy before Readability/Docling, 502 errors during startup
    Evidence: .sisyphus/evidence/task-18-startup-ordering.txt

  Scenario: Missing SENJI_TOKEN prevents startup
    Tool: Bash
    Preconditions: Docker Compose file exists
    Steps:
      1. Run `docker compose up gateway 2>&1` WITHOUT setting SENJI_TOKEN
      2. Assert gateway exits with error or logs missing token message
      3. Assert exit code is non-zero
    Expected Result: Fast-fail with clear error about missing configuration
    Failure Indicators: Gateway starts without auth token, silent default
    Evidence: .sisyphus/evidence/task-18-missing-token.txt
  ```

  **Commit**: YES
  - Message: `feat(docker): health checks, E2E tests, production config`
  - Files: `docker-compose.yml`, `senji-gateway/Dockerfile`, `senji-readability/Dockerfile`, `.dockerignore`
  - Pre-commit: `docker compose config --quiet` (validates YAML)

- [x] 19. End-to-End Integration Tests

  **What to do**:
  - Create `tests/test_e2e.py` — integration tests that run against live Docker services
  - Tests use `httpx` or `requests` to call the actual API (not mocked)
  - Test cases:
    1. Health check returns all services OK
    2. URL conversion: `https://example.com` → markdown with frontmatter
    3. HTML paste: simple HTML → markdown
    4. File upload: test PDF → markdown (include a small test PDF fixture)
    5. Auth rejection: request without token → 401
    6. Auth rejection: request with wrong token → 401
    7. Invalid URL: non-existent domain → appropriate error
    8. Unsupported file type: `.txt` upload → 415
    9. Frontmatter validation: all responses include `source`, `title`, `date`, `type` fields
    10. Media extraction: URL with images → response includes `media` array
  - Create `tests/fixtures/test.pdf` — small 1-page PDF for upload testing
  - Create `tests/conftest.py` — shared fixtures: `base_url`, `auth_headers`, `api_client`
  - Tests must be runnable with: `pytest tests/test_e2e.py -v`
  - Add `pytest-timeout` with 120s default (Docling can be slow)

  **Must NOT do**:
  - No mocking — these are REAL integration tests against running services
  - No Docker management in tests (assume services are already running)
  - No parallel test execution (avoid race conditions with shared services)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Integration testing requires understanding full system behavior and edge cases
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with T18, T20)
  - **Blocks**: F1-F4
  - **Blocked By**: T9, T10, T11, T14 (all API endpoints must exist)

  **References**:

  **Pattern References**:
  - `senji-gateway/app/schemas.py` — Response shapes to assert against
  - `senji-gateway/tests/test_*.py` — Unit test patterns to complement (not duplicate)

  **API/Type References**:
  - All 3 endpoints: `/api/convert/url`, `/api/convert/html`, `/api/convert/file`
  - `ConvertResponse`: `{markdown: str, media: [{filename, url, data}], metadata: {title, source, ...}}`
  - `ErrorResponse`: `{error: str, detail: str}`

  **External References**:
  - pytest-httpx or plain httpx for async API calls
  - pytest-timeout: `@pytest.mark.timeout(120)` for Docling-dependent tests

  **WHY Each Reference Matters**:
  - `schemas.py` — E2E tests must validate response shape matches the contract defined in T2
  - Unit tests — E2E tests cover different concerns (real service interaction, not mocked behavior)

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Full E2E test suite passes
    Tool: Bash
    Preconditions: All Docker services running and healthy
    Steps:
      1. Run `SENJI_TOKEN=test-token pytest tests/test_e2e.py -v --timeout=120`
      2. Assert all tests pass (10 test cases)
      3. Assert no warnings about unclosed connections
    Expected Result: 10 passed, 0 failed
    Failure Indicators: Any test failure, timeout, connection errors
    Evidence: .sisyphus/evidence/task-19-e2e-results.txt

  Scenario: E2E tests catch a real regression
    Tool: Bash
    Preconditions: Services running, intentionally break auth middleware
    Steps:
      1. Temporarily remove auth check from gateway
      2. Run E2E tests
      3. Assert auth rejection tests (tests 5, 6) FAIL
      4. Restore auth check
      5. Re-run — assert all pass again
    Expected Result: E2E tests detect missing auth — they're not false-passing
    Failure Indicators: Tests pass even with auth disabled
    Evidence: .sisyphus/evidence/task-19-regression-detection.txt
  ```

  **Commit**: YES (groups with T18)
  - Message: `feat(docker): health checks, E2E tests, production config`
  - Files: `tests/test_e2e.py`, `tests/conftest.py`, `tests/fixtures/test.pdf`
  - Pre-commit: `pytest tests/test_e2e.py -v`

- [ ] 20. Cleanup — Remove Legacy + Finalize Repository

  **What to do**:
  - Delete `shortcuts/` directory entirely (contains `clip.py` and related files)
  - Verify no remaining references to `clip.py` or `shortcuts/` anywhere in repo
  - Create `.env.example` with all required environment variables:
    ```
    SENJI_TOKEN=your-bearer-token-here
    DOCLING_IMAGE=ghcr.io/docling-project/docling-serve:v1.16.1
    ```
  - Create `.gitignore` with Python, Node, Docker, and IDE patterns
  - Verify `docker-compose.yml` references `.env` for token (not hardcoded)
  - Final `git status` — ensure no untracked files that should be committed
  - Final `git log --oneline` — verify commit history follows conventional commits
  - Tag release: `git tag v0.1.0`

  **Must NOT do**:
  - No README.md creation (not requested, avoid documentation bloat)
  - No CI/CD pipeline (not in scope for v1)
  - No changelog generation

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Cleanup and repo hygiene — straightforward file operations
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with T18, T19)
  - **Blocks**: F1-F4
  - **Blocked By**: T1 (repo must exist), T15-T17 (dashboard must be done before final cleanup)

  **References**:

  **Pattern References**:
  - `shortcuts/clip.py` — Verify this is the file being removed (928 lines, the old clipper)
  - `docker-compose.yml` — Verify env var references

  **WHY Each Reference Matters**:
  - `clip.py` — must confirm correct directory removal, no accidental deletion of other files
  - `docker-compose.yml` — token must come from `.env`, not be hardcoded in the compose file

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Legacy shortcuts directory is gone
    Tool: Bash
    Preconditions: Repository exists
    Steps:
      1. Run `test -d shortcuts && echo "EXISTS" || echo "GONE"`
      2. Assert output is "GONE"
      3. Run `grep -r "clip.py" . --include="*.py" --include="*.yml" --include="*.md" | grep -v ".sisyphus" | grep -v ".git"`
      4. Assert no results (no references to clip.py remain)
    Expected Result: shortcuts/ removed, no dangling references
    Failure Indicators: Directory exists, references found
    Evidence: .sisyphus/evidence/task-20-legacy-removed.txt

  Scenario: .env.example has all required variables
    Tool: Bash
    Preconditions: Repository exists
    Steps:
      1. Run `cat .env.example`
      2. Assert contains SENJI_TOKEN
      3. Assert contains DOCLING_IMAGE
      4. Run `grep -c "=" .env.example`
      5. Assert count matches expected number of variables
    Expected Result: All required env vars documented
    Failure Indicators: Missing variables, hardcoded secrets
    Evidence: .sisyphus/evidence/task-20-env-example.txt

  Scenario: Git history is clean
    Tool: Bash
    Preconditions: All commits made
    Steps:
      1. Run `git log --oneline | head -20`
      2. Assert all commits follow conventional commit format
      3. Run `git status --short`
      4. Assert no untracked/uncommitted files (except .env if created)
      5. Run `git tag -l`
      6. Assert v0.1.0 tag exists
    Expected Result: Clean repo with proper commit history and version tag
    Failure Indicators: Non-conventional commits, untracked files, missing tag
    Evidence: .sisyphus/evidence/task-20-git-clean.txt
  ```

  **Commit**: YES
  - Message: `chore(cleanup): remove legacy shortcuts, finalize repo`
  - Files: (deleted) `shortcuts/`, (added) `.env.example`, `.gitignore`
  - Pre-commit: `git status --short`

---

## Final Verification Wave

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, curl endpoint, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run linter + type checks + all tests. Review all changed files for: `as any`/`@ts-ignore`, empty catches, console.log in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names. Verify structured logging is consistent across services.
  Output: `Build [PASS/FAIL] | Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high` (+ `playwright` skill for dashboard)
  Start from clean state (`docker compose down -v && docker compose up -d`). Execute EVERY QA scenario from EVERY task. Test cross-service integration. Test edge cases: empty URL, huge PDF, invalid bearer token, Docling down. Save evidence to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual implementation. Verify 1:1 match. Check "Must NOT Have" compliance — search for databases, WebSocket, batch endpoints, EPUB handling, build tools. Flag unaccounted files. Verify shortcuts/ directory is removed.
  Output: `Tasks [N/N compliant] | Guardrails [N/N clean] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

| Commit | Tasks | Message | Pre-commit |
|--------|-------|---------|------------|
| 1 | T1-T5 | `chore(init): project scaffolding and service skeletons` | `docker compose config` |
| 2 | T6 | `feat(readability): core HTML→Markdown conversion service` | `cd senji-readability && npm test` |
| 3 | T7-T8 | `feat(gateway): structured logging and bearer auth` | `pytest tests/test_auth.py tests/test_logging.py` |
| 4 | T9-T11 | `feat(gateway): conversion endpoints (URL, HTML, file)` | `pytest tests/test_endpoints.py` |
| 5 | T12-T13 | `feat(gateway): frontmatter generation and media download` | `pytest tests/test_frontmatter.py tests/test_media.py` |
| 6 | T14 | `feat(gateway): error handling and validation` | `pytest tests/test_errors.py` |
| 7 | T15-T17 | `feat(dashboard): web UI with URL/upload/paste conversion` | Playwright tests |
| 8 | T18-T19 | `feat(docker): health checks, E2E tests, production config` | `docker compose up -d && pytest tests/test_e2e.py` |
| 9 | T20 | `chore(cleanup): remove legacy shortcuts, finalize repo` | `git status --short` |

---

## Success Criteria

### Verification Commands
```bash
# Clone and deploy
git clone https://github.com/Hennessyng/senji.git /tmp/senji-test
cd /tmp/senji-test && docker compose up -d
sleep 30

# Health check
curl -s http://localhost:8000/health
# Expected: {"status":"ok","services":{"readability":"ok","docling":"ok"}}

# Auth rejection
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/convert/url
# Expected: 401

# Web conversion
curl -s http://localhost:8000/api/convert/url \
  -H "Authorization: Bearer $SENJI_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}' | jq '.markdown' | head -5
# Expected: starts with "---\nsource:"

# PDF conversion
curl -s http://localhost:8000/api/convert/file \
  -H "Authorization: Bearer $SENJI_TOKEN" \
  -F "file=@test.pdf" | jq '.markdown' | head -5
# Expected: markdown content with tables preserved

# Dashboard loads
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/
# Expected: 200

# All tests pass
docker compose exec gateway pytest
docker compose exec readability npm test
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass (pytest + mocha)
- [ ] Docker Compose starts cleanly from fresh clone
- [ ] Dashboard works on mobile viewport (375px)
- [ ] shortcuts/ directory removed from repo
