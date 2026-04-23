import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.config import settings
from app.models.schemas import QueryRequest, QueryResponse
from app.services.embedding_service import EmbeddingService
from app.services.ollama_client import OllamaClient

logger = logging.getLogger("senji.pics.query")

router = APIRouter(prefix="/api")

_DEFAULT_TOP_K = 5
_SIMILARITY_THRESHOLD = 0.0


@router.post("/query", response_model=QueryResponse)
async def query_vault(body: QueryRequest, request: Request) -> QueryResponse:
    """
    RAG query endpoint: embed question, search wiki pages, stream LLM answer.
    
    Pipeline:
    1. Embed question using bge-m3
    2. Search wiki/*.md.embed.json for top-k similar pages
    3. Load page content
    4. Call qwen3:8b with context to generate answer
    """
    if not body.question or not body.question.strip():
        return QueryResponse(answer="", sources=[])

    embedding_svc = EmbeddingService()
    ollama = request.app.state.ollama_client

    vault_path = Path(settings.vault_path)
    wiki_dir = vault_path / "wiki"

    try:
        results = await embedding_svc.search_wiki_pages(
            body.question,
            wiki_dir,
            top_k=_DEFAULT_TOP_K,
            similarity_threshold=_SIMILARITY_THRESHOLD,
        )

        if not results:
            answer = "No relevant sources found in vault."
            return QueryResponse(answer=answer, sources=[])

        context_parts = []
        sources = []

        for wiki_path, frontmatter, score in results:
            try:
                content = wiki_path.read_text(encoding="utf-8")
                context_parts.append(content)
                sources.append({
                    "title": frontmatter.get("title", wiki_path.stem),
                    "similarity": float(f"{score:.3f}"),
                    "path": str(wiki_path.relative_to(vault_path)),
                })
            except Exception as exc:
                logger.warning(
                    "Failed to load wiki page",
                    extra={"path": str(wiki_path), "error": str(exc)},
                )

        if not context_parts:
            return QueryResponse(answer="Could not load source content.", sources=[])

        context = "\n\n---\n\n".join(context_parts)
        system_prompt = (
            "You are a helpful assistant answering questions based on provided documents. "
            "Answer concisely and cite sources when relevant."
        )
        user_msg = f"Question: {body.question}\n\nContext:\n{context}"

        answer = await ollama.generate(system_prompt, user_msg)

        return QueryResponse(answer=answer, sources=sources)

    except Exception as exc:
        logger.error(
            "Query failed",
            extra={"question": body.question, "error": str(exc)},
            exc_info=True,
        )
        return QueryResponse(
            answer=f"Error processing query: {exc}",
            sources=[],
        )


async def generate_streaming(body: QueryRequest, request: Request):
    """Stream answer token-by-token (optional alternative endpoint)."""
    embedding_svc = EmbeddingService()
    ollama = request.app.state.ollama_client

    vault_path = Path(settings.vault_path)
    wiki_dir = vault_path / "wiki"

    try:
        results = await embedding_svc.search_wiki_pages(
            body.question,
            wiki_dir,
            top_k=_DEFAULT_TOP_K,
        )

        if not results:
            yield "No relevant sources found.\n"
            return

        context_parts = []
        for wiki_path, _, _ in results:
            try:
                context_parts.append(wiki_path.read_text(encoding="utf-8"))
            except Exception:
                continue

        if not context_parts:
            yield "Could not load source content.\n"
            return

        context = "\n\n---\n\n".join(context_parts)
        system_prompt = (
            "You are a helpful assistant answering questions based on provided documents. "
            "Answer concisely and cite sources when relevant."
        )
        user_msg = f"Question: {body.question}\n\nContext:\n{context}"

        answer = await ollama.generate(system_prompt, user_msg)
        yield answer

    except Exception as exc:
        logger.error(
            "Streaming query failed",
            extra={"question": body.question, "error": str(exc)},
            exc_info=True,
        )
        yield f"Error: {exc}\n"
