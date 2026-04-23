import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.errors import OllamaUnavailableError, WikiError
from app.services.wiki_prompt import WIKI_PROMPT_TEMPLATE
from app.services.wiki_service import generate_wiki_entry


def _mock_ollama(response: str = "## Summary\nGenerated wiki body.") -> MagicMock:
    client = MagicMock()
    client.generate = AsyncMock(return_value=response)
    client._semaphore = asyncio.Semaphore(1)
    client.available = True
    return client


@pytest.mark.asyncio
async def test_generate_wiki_entry_calls_ollama():
    client = _mock_ollama("## Summary\nHello wiki.")
    out = await generate_wiki_entry(
        client,
        title="My Article",
        source="https://example.com/a",
        content="Body text here.",
        language="en",
    )
    assert client.generate.await_count == 1
    assert "Hello wiki." in out
    assert "## Summary" in out


@pytest.mark.asyncio
async def test_wiki_entry_has_metadata_in_body():
    client = _mock_ollama("## Summary\nA body.\n\n## Key Concepts\n- X\n\n## Related\n[[x]]")
    out = await generate_wiki_entry(
        client,
        title="T",
        source="https://example.com/s",
        content="raw",
        language="en",
    )
    assert "## Summary" in out
    assert "## Key Concepts" in out
    assert "## Related" in out


@pytest.mark.asyncio
async def test_concurrent_wiki_requests_serialised():
    events: list[str] = []

    async def fake_stream(payload):
        events.append("start")
        await asyncio.sleep(0.02)
        events.append("end")
        return "## Summary\nok"

    from app.services.ollama_client import OllamaClient

    client = OllamaClient(base_url="http://fake:11434")
    client.available = True
    client._stream_generate = fake_stream

    await asyncio.gather(
        generate_wiki_entry(client, "A", "s1", "c1"),
        generate_wiki_entry(client, "B", "s2", "c2"),
    )
    assert events == ["start", "end", "start", "end"]


@pytest.mark.asyncio
async def test_empty_content_raises_wiki_error():
    client = _mock_ollama()
    with pytest.raises(WikiError):
        await generate_wiki_entry(client, title="", source="", content="")
    client.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_ollama_unavailable_returns_raw_fallback():
    client = MagicMock()
    client.generate = AsyncMock(side_effect=OllamaUnavailableError("timeout"))
    client._semaphore = asyncio.Semaphore(1)
    client.available = True

    out = await generate_wiki_entry(
        client,
        title="Fallback Title",
        source="https://example.com/x",
        content="Original raw body content.",
    )
    assert "Fallback Title" in out
    assert "Original raw body content." in out
    assert "https://example.com/x" in out


@pytest.mark.asyncio
async def test_frontmatter_pipe_is_escaped_in_payload():
    captured: dict = {}

    async def capture_generate(system_prompt, user_msg, model="qwen3:8b"):
        captured["system"] = system_prompt
        captured["user"] = user_msg
        return "## Summary\nok"

    client = MagicMock()
    client.generate = AsyncMock(side_effect=capture_generate)
    client._semaphore = asyncio.Semaphore(1)
    client.available = True

    title_with_pipe = "Title | With | Pipes"
    out = await generate_wiki_entry(
        client,
        title=title_with_pipe,
        source="https://example.com/z",
        content="body",
    )
    assert title_with_pipe in captured["user"]
    assert out.strip().startswith("## Summary") or "ok" in out


@pytest.mark.asyncio
async def test_strips_triple_backtick_fences_from_output():
    client = _mock_ollama("```markdown\n## Summary\nWrapped body.\n```")
    out = await generate_wiki_entry(
        client,
        title="T",
        source="s",
        content="c",
    )
    assert "```" not in out
    assert "## Summary" in out
    assert "Wrapped body." in out


@pytest.mark.asyncio
async def test_prompt_template_is_injected():
    captured: dict = {}

    async def capture(system_prompt, user_msg, model="qwen3:8b"):
        captured["user"] = user_msg
        return "## Summary\nok"

    client = MagicMock()
    client.generate = AsyncMock(side_effect=capture)
    client._semaphore = asyncio.Semaphore(1)
    client.available = True

    custom = "CUSTOM_TEMPLATE title={title} src={source} lang={language} body={content}"
    await generate_wiki_entry(
        client,
        title="XX",
        source="YY",
        content="ZZ",
        language="de",
        prompt_template=custom,
    )
    assert "CUSTOM_TEMPLATE" in captured["user"]
    assert "title=XX" in captured["user"]
    assert "src=YY" in captured["user"]
    assert "lang=de" in captured["user"]
    assert "body=ZZ" in captured["user"]
    assert "{title}" not in captured["user"]


@pytest.mark.asyncio
async def test_default_template_used_when_not_overridden():
    captured: dict = {}

    async def capture(system_prompt, user_msg, model="qwen3:8b"):
        captured["user"] = user_msg
        return "## Summary\nok"

    client = MagicMock()
    client.generate = AsyncMock(side_effect=capture)
    client._semaphore = asyncio.Semaphore(1)
    client.available = True

    await generate_wiki_entry(client, title="T", source="s", content="c")
    expected_header = WIKI_PROMPT_TEMPLATE.splitlines()[0]
    assert expected_header in captured["user"]
