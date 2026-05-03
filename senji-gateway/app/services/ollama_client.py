import asyncio
import json
import logging
import time

import httpx

from app.config import settings
from app.errors import OllamaUnavailableError

logger = logging.getLogger("senji.pics.ollama_client")

_HEALTH_RETRIES = 3
_BACKOFF_DELAYS = (0.5, 1.0, 2.0)
_HEALTH_TIMEOUT = 5.0
_GENERATE_TIMEOUT = 120.0


class OllamaClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.available: bool = False
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(1)

    async def health_check(self) -> bool:
        for attempt in range(_HEALTH_RETRIES):
            retries_left = _HEALTH_RETRIES - attempt - 1
            try:
                async with httpx.AsyncClient(timeout=_HEALTH_TIMEOUT) as client:
                    resp = await client.get(f"{self.base_url}/api/tags")
                    resp.raise_for_status()
                self.available = True
                logger.info(
                    "Ollama health check passed",
                    extra={
                        "action": "health_check",
                        "status": "ok",
                        "retries_left": retries_left,
                        "error_msg": None,
                    },
                )
                return True
            except (
                httpx.ConnectError,
                httpx.HTTPStatusError,
                httpx.TimeoutException,
                httpx.RequestError,
            ) as exc:
                logger.warning(
                    "Ollama health check failed: %s",
                    exc,
                    extra={
                        "action": "health_check",
                        "status": "fail",
                        "retries_left": retries_left,
                        "error_msg": str(exc),
                    },
                )
                if retries_left > 0:
                    await asyncio.sleep(_BACKOFF_DELAYS[attempt])

        self.available = False
        return False

    async def _stream_generate(self, payload: dict) -> str:
        chunks: list[str] = []
        async with httpx.AsyncClient(timeout=_GENERATE_TIMEOUT) as client, client.stream(
            "POST", f"{self.base_url}/api/generate", json=payload
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                data = json.loads(line)
                if chunk := data.get("response"):
                    chunks.append(chunk)
        return "".join(chunks)

    async def _stream_chat(self, payload: dict) -> str:
        chunks: list[str] = []
        async with httpx.AsyncClient(timeout=_GENERATE_TIMEOUT) as client, client.stream(
            "POST", f"{self.base_url}/api/chat", json=payload
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                data = json.loads(line)
                if chunk := (data.get("message") or {}).get("content"):
                    chunks.append(chunk)
        return "".join(chunks)

    async def generate(
        self, system_prompt: str, user_msg: str, model: str = "qwen3:8b"
    ) -> str:
        if not self.available:
            raise OllamaUnavailableError("Ollama is marked unavailable")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            "stream": True,
            "options": {
                "temperature": 0.2,
                "repeat_penalty": 1.3,
                "num_predict": 1024,
                "num_ctx": 8192,
            },
        }
        async with self._semaphore:
            start = time.monotonic()
            try:
                result = await self._stream_chat(payload)
            except httpx.ConnectError as exc:
                self.available = False
                logger.error(
                    "Ollama connection lost during generate",
                    extra={"model": model, "error_msg": str(exc)},
                )
                raise OllamaUnavailableError(str(exc)) from exc
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "Ollama generate complete",
                extra={
                    "model": model,
                    "tokens_generated": len(result.split()),
                    "latency_ms": latency_ms,
                },
            )
            return result

    async def describe_image(
        self,
        image_base64: str,
        model: str = "qwen2.5-vl:7b",
        prompt: str = "Describe this image in detail.",
    ) -> str:
        if not self.available:
            raise OllamaUnavailableError("Ollama is marked unavailable")
        payload = {
            "model": model,
            "prompt": prompt,
            "images": [image_base64],
            "stream": True,
        }
        async with self._semaphore:
            start = time.monotonic()
            try:
                result = await self._stream_generate(payload)
            except httpx.ConnectError as exc:
                self.available = False
                logger.error(
                    "Ollama connection lost during describe_image",
                    extra={"model": model, "error_msg": str(exc)},
                )
                raise OllamaUnavailableError(str(exc)) from exc
            latency_ms = int((time.monotonic() - start) * 1000)
            image_size_kb = len(image_base64) * 3 // 4 // 1024
            logger.info(
                "Ollama describe_image complete",
                extra={
                    "model": model,
                    "image_size_kb": image_size_kb,
                    "latency_ms": latency_ms,
                },
            )
            return result
