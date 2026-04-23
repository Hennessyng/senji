import json
import logging
from pathlib import Path

import httpx
import numpy as np

from app.config import settings
from app.errors import OllamaUnavailableError

logger = logging.getLogger("senji.pics.embedding")

_EMBED_TIMEOUT = 30.0


class EmbeddingService:
    """Generate and search vector embeddings using Ollama."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = settings.ollama_embed_model

    async def embed_text(self, text: str) -> list[float]:
        """Generate embedding vector for text using Ollama embeddings API."""
        if not text or not text.strip():
            raise ValueError("Cannot embed empty text")

        payload = {
            "model": self.model,
            "prompt": text.strip(),
        }

        try:
            async with httpx.AsyncClient(timeout=_EMBED_TIMEOUT) as client:
                resp = await client.post(
                    f"{self.base_url}/api/embed",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                embedding = data.get("embedding")
                if not embedding:
                    raise ValueError("No embedding returned from Ollama")
                return embedding
        except httpx.HTTPError as exc:
            logger.error(
                "Ollama embedding failed",
                extra={"model": self.model, "error": str(exc)},
            )
            raise OllamaUnavailableError(f"Embedding failed: {exc}") from exc

    @staticmethod
    def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        a = np.array(vec_a, dtype=np.float32)
        b = np.array(vec_b, dtype=np.float32)

        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(dot_product / (norm_a * norm_b))

    async def search_wiki_pages(
        self,
        question: str,
        wiki_dir: Path,
        top_k: int = 5,
        similarity_threshold: float = 0.0,
    ) -> list[tuple[Path, dict, float]]:
        """
        Search wiki pages by semantic similarity to question.

        Returns: List of (path, frontmatter, similarity_score) tuples sorted by score DESC.
        """
        if not wiki_dir.exists():
            return []

        question_embedding = await self.embed_text(question)

        results: list[tuple[Path, dict, float]] = []

        for wiki_file in wiki_dir.glob("*.md"):
            try:
                embed_file = wiki_file.with_suffix(".md.embed.json")
                if not embed_file.exists():
                    continue

                with open(embed_file, "r") as f:
                    embed_data = json.load(f)

                embedding = embed_data.get("embedding")
                frontmatter = embed_data.get("frontmatter", {})

                if not embedding:
                    continue

                similarity = self.cosine_similarity(question_embedding, embedding)

                if similarity >= similarity_threshold:
                    results.append((wiki_file, frontmatter, similarity))

            except Exception as exc:
                logger.warning(
                    "Failed to process wiki embedding",
                    extra={"file": str(wiki_file), "error": str(exc)},
                )
                continue

        results.sort(key=lambda x: x[2], reverse=True)
        return results[:top_k]

    @staticmethod
    def save_embedding(
        markdown_path: Path,
        embedding: list[float],
        frontmatter: dict,
    ) -> Path:
        """Save embedding + frontmatter to .embed.json sidecar."""
        embed_path = markdown_path.with_suffix(".md.embed.json")
        data = {
            "embedding": embedding,
            "frontmatter": frontmatter,
        }

        with open(embed_path, "w") as f:
            json.dump(data, f)

        logger.debug("Embedding saved", extra={"path": str(embed_path)})
        return embed_path
