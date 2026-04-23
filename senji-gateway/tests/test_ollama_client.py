import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.errors import OllamaUnavailableError
from app.services.ollama_client import OllamaClient

BASE_URL = "http://fake-ollama:11434"


def make_stream_lines(*chunks: str) -> list[str]:
    lines = [json.dumps({"response": chunk}) for chunk in chunks]
    lines.append(json.dumps({"done": True}))
    return lines


class _AsyncStreamResponse:
    def __init__(self, lines: list[str], capture: list | None = None):
        self._lines = lines
        self._capture = capture

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line


def _make_stream_client(lines: list[str], capture: list | None = None):
    def do_stream(method, url, **kwargs):
        if capture is not None:
            capture.append(kwargs.get("json", {}))
        return _AsyncStreamResponse(lines, capture)

    mock = MagicMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    mock.stream = MagicMock(side_effect=do_stream)
    return mock


def _make_health_client(exc=None):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    mock = MagicMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    mock.get = AsyncMock(side_effect=exc) if exc is not None else AsyncMock(return_value=resp)
    return mock


@pytest.fixture
def client() -> OllamaClient:
    return OllamaClient(base_url=BASE_URL)


@pytest.fixture
def available_client() -> OllamaClient:
    c = OllamaClient(base_url=BASE_URL)
    c.available = True
    return c


@pytest.mark.asyncio
async def test_health_check_success(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: _make_health_client())
    c = OllamaClient(base_url=BASE_URL)
    result = await c.health_check()
    assert result is True
    assert c.available is True


@pytest.mark.asyncio
async def test_health_check_failure_3_retries(monkeypatch):
    async def no_sleep(_: float) -> None:
        pass
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda *a, **kw: _make_health_client(exc=httpx.ConnectError("refused"))
    )
    c = OllamaClient(base_url=BASE_URL)
    result = await c.health_check()
    assert result is False
    assert c.available is False


@pytest.mark.asyncio
async def test_health_check_exponential_backoff(monkeypatch):
    sleep_calls: list[float] = []

    async def capture_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(asyncio, "sleep", capture_sleep)
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda *a, **kw: _make_health_client(exc=httpx.ConnectError("refused"))
    )
    c = OllamaClient(base_url=BASE_URL)
    await c.health_check()
    assert sleep_calls == [0.5, 1.0]


@pytest.mark.asyncio
async def test_generate_success(monkeypatch):
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda *a, **kw: _make_stream_client(make_stream_lines("Hello", ", ", "world!"))
    )
    c = OllamaClient(base_url=BASE_URL)
    c.available = True
    result = await c.generate("You are helpful.", "Say hello.", model="qwen3:8b")
    assert result == "Hello, world!"


@pytest.mark.asyncio
async def test_generate_unavailable_raises_error():
    c = OllamaClient(base_url=BASE_URL)
    c.available = False
    with pytest.raises(OllamaUnavailableError):
        await c.generate("sys", "msg", model="qwen3:8b")


@pytest.mark.asyncio
async def test_generate_concurrent_enforcement():
    events: list[str] = []

    async def fake_stream(payload: dict) -> str:
        events.append("start")
        await asyncio.sleep(0.02)
        events.append("end")
        return "ok"

    c = OllamaClient(base_url=BASE_URL)
    c.available = True
    c._stream_generate = fake_stream  # type: ignore[method-assign]

    await asyncio.gather(
        c.generate("sys", "msg1", model="m"),
        c.generate("sys", "msg2", model="m"),
    )
    assert events == ["start", "end", "start", "end"]


@pytest.mark.asyncio
async def test_describe_image_success(monkeypatch):
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda *a, **kw: _make_stream_client(make_stream_lines("A cat ", "sitting on a mat."))
    )
    c = OllamaClient(base_url=BASE_URL)
    c.available = True
    result = await c.describe_image("base64img==", model="qwen2.5-vl:7b")
    assert result == "A cat sitting on a mat."


@pytest.mark.asyncio
async def test_describe_image_vision_api_shape(monkeypatch):
    captured: list[dict] = []
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda *a, **kw: _make_stream_client(make_stream_lines("desc"), capture=captured)
    )
    c = OllamaClient(base_url=BASE_URL)
    c.available = True
    await c.describe_image("abc123==", model="qwen2.5-vl:7b")
    assert len(captured) == 1
    payload = captured[0]
    assert {"model", "prompt", "images", "stream"} <= set(payload.keys())
    assert payload["images"] == ["abc123=="]
    assert payload["stream"] is True


@pytest.mark.asyncio
async def test_streaming_json_parse(monkeypatch):
    chunks = ["The ", "quick ", "brown ", "fox."]
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda *a, **kw: _make_stream_client(make_stream_lines(*chunks))
    )
    c = OllamaClient(base_url=BASE_URL)
    result = await c._stream_generate({"model": "any", "prompt": "go", "stream": True})
    assert result == "The quick brown fox."
