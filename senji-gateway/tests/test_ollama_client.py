import asyncio
import json

import httpx
import pytest

from app.errors import OllamaUnavailableError
from app.services.ollama_client import OllamaClient

BASE_URL = "http://fake-ollama:11434"


def make_stream(*chunks: str) -> bytes:
    lines = [json.dumps({"response": chunk}) for chunk in chunks]
    lines.append(json.dumps({"done": True}))
    return "\n".join(lines).encode()


@pytest.fixture
def client() -> OllamaClient:
    return OllamaClient(base_url=BASE_URL)


@pytest.fixture
def available_client() -> OllamaClient:
    c = OllamaClient(base_url=BASE_URL)
    c.available = True
    return c


@pytest.mark.asyncio
async def test_health_check_success(httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/api/tags",
        json={"models": [{"name": "qwen3:8b-q5_K_M"}]},
    )
    c = OllamaClient(base_url=BASE_URL)
    result = await c.health_check()
    assert result is True
    assert c.available is True


@pytest.mark.asyncio
async def test_health_check_failure_3_retries(httpx_mock, monkeypatch):
    async def no_sleep(_: float) -> None:
        pass

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    for _ in range(3):
        httpx_mock.add_exception(httpx.ConnectError("connection refused"))

    c = OllamaClient(base_url=BASE_URL)
    result = await c.health_check()

    assert result is False
    assert c.available is False


@pytest.mark.asyncio
async def test_health_check_exponential_backoff(httpx_mock, monkeypatch):
    sleep_calls: list[float] = []

    async def capture_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(asyncio, "sleep", capture_sleep)

    for _ in range(3):
        httpx_mock.add_exception(httpx.ConnectError("refused"))

    c = OllamaClient(base_url=BASE_URL)
    await c.health_check()

    assert sleep_calls == [0.5, 1.0]


@pytest.mark.asyncio
async def test_generate_success(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/api/generate",
        content=make_stream("Hello", ", ", "world!"),
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
async def test_describe_image_success(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/api/generate",
        content=make_stream("A cat ", "sitting on a mat."),
    )
    c = OllamaClient(base_url=BASE_URL)
    c.available = True
    result = await c.describe_image("base64img==", model="qwen2.5-vl:7b")
    assert result == "A cat sitting on a mat."


@pytest.mark.asyncio
async def test_describe_image_vision_api_shape(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/api/generate",
        content=make_stream("desc"),
    )
    c = OllamaClient(base_url=BASE_URL)
    c.available = True
    await c.describe_image("abc123==", model="qwen2.5-vl:7b")

    sent = httpx_mock.get_requests()
    assert len(sent) == 1
    payload = json.loads(sent[0].content)

    assert {"model", "prompt", "images", "stream"} <= set(payload.keys())
    assert payload["images"] == ["abc123=="]
    assert payload["stream"] is True
    assert isinstance(payload["images"], list)


@pytest.mark.asyncio
async def test_streaming_json_parse(httpx_mock):
    chunks = ["The ", "quick ", "brown ", "fox."]
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/api/generate",
        content=make_stream(*chunks),
    )
    c = OllamaClient(base_url=BASE_URL)
    result = await c._stream_generate(
        {"model": "any", "prompt": "go", "stream": True}
    )
    assert result == "The quick brown fox."
