# Draft: Senji (煎じ) — Self-hosted Markdown Converter

## Requirements (confirmed)
- **Name**: senji (煎じ — "brewed down / distilled")
- **Repo**: https://github.com/Hennessyng/senji.git (private)
- **Primary use**: HTML webpages → Markdown (1st priority), PDF → Markdown (2nd priority)
- **Quality target**: Best-class for Obsidian — readable by humans AND AI agents
- **Auth**: Bearer token
- **Deployment**: Proxmox Docker via `git clone` + `docker compose up -d`
- **Domain**: markdown.myloft.cloud via Cloudflare tunnel
- **Resources**: Heavy is fine — Proxmox has ample compute
- **Dashboard**: Web UI with URL/Upload/Paste tabs, preview toggle, copy/download

## Architecture (confirmed)
- **Dual-service**: specialized engines for each input type
  - Service 1: Web/HTML → Mozilla Readability + HTML→Markdown converter + Obsidian frontmatter
  - Service 2: Docling Serve (IBM) → PDF/DOCX/PPTX with layout analysis, table extraction, OCR
- **API Gateway**: Thin FastAPI service routes by input type, adds consistent frontmatter
- **Frontend**: Vanilla HTML/CSS/JS (no build step), served from FastAPI static files

## Technical Decisions
- Private GitHub repo, build on Proxmox from source (no registry)
- Bearer token auth (not Cloudflare Access)
- Docling Serve via official Docker image `ghcr.io/docling-project/docling-serve`

## Existing Codebase
- Current: `shortcuts/clip.py` — 928-line CLI Obsidian clipper with custom HTML2Markdown parser
- Has: web clipping, PDF extraction, screenshot OCR, selection, read-later, thought/journal
- Tests: 13 test files in `shortcuts/tests/` with pytest
- Features to potentially preserve: frontmatter builder, image downloading, article extraction
- Config: Python 3.12 (mise), ruff linter, pytest

## Resolved Questions
- **clip.py**: DROP entirely — senji replaces it. Shortcuts will call REST API.
- **Readability**: Node.js (`@mozilla/readability` + `jsdom`) — canonical implementation, best quality
- **Media handling**: Download ALL related media (images, etc.) so Obsidian shows exact page offline
- **Frontmatter**: Keep current fields (source, title, clipped, type, tags) — proven useful
- **Test strategy**: TDD with Agentic self-correction loop (Reflexion pattern)
  - Structured logging enables AI agent to read errors and self-fix
  - SRP for modular, testable code
  - Both FE and BE testable in automated loops

## Engineering Principles
- **TDD**: Tests first, always
- **SRP**: Single responsibility per module
- **Structured logging**: Machine-readable logs for agentic debugging loops
- **Agentic TDD**: Design for AI self-correction — test → error → log → fix → retest

## Scope Boundaries
- INCLUDE: REST API, web dashboard, Docker deployment, Readability + Docling, media download, TDD
- EXCLUDE: iOS Shortcut creation (user handles), Cloudflare tunnel setup (user handles)
- DROP: shortcuts/clip.py and related .shortcut files — superseded by senji
