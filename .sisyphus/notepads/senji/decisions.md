# Senji — Decisions

## Static Files Path (RESOLVED)
- Canonical: senji-gateway/static/ (NOT frontend/ at repo root)
- T1 scaffolds senji-gateway/static/
- T5 Dockerfile: COPY static/ ./static/
- T15 creates files in senji-gateway/static/

## T18 Category (RESOLVED)
- Category: unspecified-high (not quick)
- Scope: health checks, memory limits, Dockerfiles, env validation

## Docling Version
- Pin to: ghcr.io/docling-project/docling-serve:1.16.1
- T11 must verify actual API contract at runtime before coding

- Initial scaffold decision: keep gateway UI placeholders inside `senji-gateway/static/` and split services into FastAPI gateway + Node readability worker + Docling compose service.
