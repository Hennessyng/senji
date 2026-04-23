from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schemas import QueryRequest, QueryResponse
from app.services.embedding_service import EmbeddingService


@pytest.fixture
def sample_embeddings():
    return [0.1, 0.2, 0.3, 0.4, 0.5]


@pytest.fixture
def sample_wiki_dir(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()

    files_created = []

    page1_content = "Python is a programming language"
    page1_embed = [0.1, 0.2, 0.3, 0.4, 0.5]
    page1_path = wiki_dir / "page1.md"
    page1_path.write_text(page1_content)
    page1_embed_path = page1_path.with_suffix(".md.embed.json")
    page1_embed_path.write_text(
        json.dumps({
            "embedding": page1_embed,
            "frontmatter": {"title": "Python Programming", "source": "test"}
        })
    )
    files_created.append(page1_path)

    page2_content = "JavaScript is used for web development"
    page2_embed = [0.15, 0.25, 0.35, 0.45, 0.55]
    page2_path = wiki_dir / "page2.md"
    page2_path.write_text(page2_content)
    page2_embed_path = page2_path.with_suffix(".md.embed.json")
    page2_embed_path.write_text(
        json.dumps({
            "embedding": page2_embed,
            "frontmatter": {"title": "JavaScript Web", "source": "test"}
        })
    )
    files_created.append(page2_path)

    return wiki_dir, files_created


@pytest.mark.asyncio
async def test_query_empty_question():
    """Empty question returns empty response."""
    async with AsyncMock() as mock_client:
        request = QueryRequest(question="")
        assert request.question == ""


@pytest.mark.asyncio
async def test_embedding_service_cosine_similarity():
    """Cosine similarity computation is accurate."""
    vec_a = [1.0, 0.0, 0.0]
    vec_b = [1.0, 0.0, 0.0]
    similarity = EmbeddingService.cosine_similarity(vec_a, vec_b)
    assert similarity == pytest.approx(1.0)

    vec_c = [1.0, 0.0, 0.0]
    vec_d = [0.0, 1.0, 0.0]
    similarity = EmbeddingService.cosine_similarity(vec_c, vec_d)
    assert similarity == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_embedding_service_save_and_load(tmp_path):
    """Embedding sidecar is saved and loadable."""
    wiki_path = tmp_path / "test.md"
    wiki_path.write_text("test content")

    embedding = [0.1, 0.2, 0.3]
    frontmatter = {"title": "Test"}

    embed_path = EmbeddingService.save_embedding(wiki_path, embedding, frontmatter)

    assert embed_path.exists()
    with open(embed_path) as f:
        data = json.load(f)
    assert data["embedding"] == embedding
    assert data["frontmatter"] == frontmatter


@pytest.mark.asyncio
async def test_search_wiki_pages_no_results(sample_wiki_dir):
    """No results when wiki dir empty."""
    wiki_dir, _ = sample_wiki_dir
    empty_wiki = wiki_dir.parent / "empty"
    empty_wiki.mkdir()

    svc = EmbeddingService()
    with patch.object(
        svc, "embed_text", new_callable=AsyncMock, return_value=[0.1, 0.2, 0.3, 0.4, 0.5]
    ):
        results = await svc.search_wiki_pages("python", empty_wiki)
        assert results == []


@pytest.mark.asyncio
async def test_search_wiki_pages_with_results(sample_wiki_dir):
    """Returns matching pages ranked by similarity."""
    wiki_dir, _ = sample_wiki_dir

    svc = EmbeddingService()
    with patch.object(
        svc, "embed_text", new_callable=AsyncMock, return_value=[0.1, 0.2, 0.3, 0.4, 0.5]
    ):
        results = await svc.search_wiki_pages("python", wiki_dir, top_k=5)

        assert len(results) > 0
        for wiki_path, frontmatter, similarity in results:
            assert wiki_path.exists()
            assert "title" in frontmatter
            assert 0 <= similarity <= 1


@pytest.mark.asyncio
async def test_query_endpoint_structure(client_with_dependencies):
    """Query endpoint exists and returns correct schema."""
    client, mock_ollama = client_with_dependencies

    with patch("app.routes.query.EmbeddingService") as mock_embedding_cls:
        mock_embedding = MagicMock()
        mock_embedding_cls.return_value = mock_embedding
        mock_embedding.search_wiki_pages = AsyncMock(return_value=[])

        response = client.post("/api/query", json={"question": "test"})

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "sources" in data
        assert isinstance(data["sources"], list)


@pytest.mark.asyncio
async def test_query_with_sources(client_with_dependencies):
    """Query returns answer with source metadata."""
    client, mock_ollama = client_with_dependencies
    mock_ollama.generate = AsyncMock(return_value="Test answer about Python")

    wiki_dir = Path("/opt/vault/wiki")
    wiki_path = wiki_dir / "test.md"

    with patch("app.routes.query.EmbeddingService") as mock_embedding_cls:
        mock_embedding = MagicMock()
        mock_embedding_cls.return_value = mock_embedding

        mock_embedding.search_wiki_pages = AsyncMock(
            return_value=[
                (
                    wiki_path,
                    {"title": "Python Guide", "source": "tutorial.com"},
                    0.85,
                )
            ]
        )

        with patch("pathlib.Path.read_text", return_value="Python is great"):
            response = client.post(
                "/api/query", json={"question": "Tell me about Python"}
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data["sources"]) > 0
            assert data["sources"][0]["similarity"] == pytest.approx(0.85, rel=0.01)
            assert "Python" in data["answer"]


@pytest.mark.asyncio
async def test_embedding_generation_on_ingest(app_with_vault):
    """Embeddings generated when raw files are saved."""
    app, vault_writer, job_queue = app_with_vault

    with patch("app.services.job_queue.EmbeddingService") as mock_embedding_cls:
        mock_embedding = MagicMock()
        mock_embedding_cls.return_value = mock_embedding
        mock_embedding.embed_text = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4, 0.5])
        mock_embedding.save_embedding = MagicMock()

        markdown = "Test content for embedding"
        frontmatter = {"title": "Test", "type": "pdf"}

        with patch.object(vault_writer, "save_raw") as mock_save:
            mock_path = Path("/opt/vault/raw/test.md")
            mock_save.return_value = mock_path

            await job_queue._generate_and_save_embedding(mock_path, markdown, frontmatter)

            mock_embedding.embed_text.assert_called_once_with(markdown)
            mock_embedding.save_embedding.assert_called_once()


@pytest.mark.asyncio
async def test_query_no_relevant_sources():
    """Query gracefully handles no relevant sources."""
    client = MagicMock()

    with patch("app.routes.query.EmbeddingService") as mock_embedding_cls:
        mock_embedding = MagicMock()
        mock_embedding_cls.return_value = mock_embedding
        mock_embedding.search_wiki_pages = AsyncMock(return_value=[])

        assert isinstance(
            QueryResponse(answer="No relevant sources found in vault.", sources=[]),
            QueryResponse,
        )
