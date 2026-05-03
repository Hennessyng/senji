import logging
import re
from typing import TYPE_CHECKING

from app.config import settings
from app.errors import OllamaUnavailableError, WikiError
from app.services.wiki_prompt import WIKI_PROMPT_TEMPLATE, WIKI_SYSTEM_PROMPT

if TYPE_CHECKING:
    from app.services.ollama_client import OllamaClient

logger = logging.getLogger("senji.pics.wiki_service")

_FENCE_OPEN_RE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n")
_FENCE_CLOSE_RE = re.compile(r"\n```\s*$")
# qwen3 emits <think>...</think> reasoning blocks before the actual response
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think_blocks(text: str) -> str:
    return _THINK_RE.sub("", text).strip()


def _strip_code_fences(text: str) -> str:
    text = _FENCE_OPEN_RE.sub("", text, count=1)
    text = _FENCE_CLOSE_RE.sub("", text, count=1)
    return text.strip()


def _fallback_markdown(title: str, source: str, content: str) -> str:
    body = content.strip() or "_(no content)_"
    return (
        f"## Summary\n\n"
        f"**{title}** — wiki generation unavailable; raw source content preserved below.\n\n"
        f"Source: {source}\n\n"
        f"## Raw Content\n\n"
        f"{body}\n"
    )


async def generate_wiki_entry(
    ollama_client: "OllamaClient",
    title: str,
    source: str,
    content: str,
    language: str = "en",
    prompt_template: str = WIKI_PROMPT_TEMPLATE,
) -> str:
    if not title.strip() or not content.strip():
        logger.warning(
            "Refusing to generate wiki entry for empty input",
            extra={
                "has_title": bool(title.strip()),
                "has_content": bool(content.strip()),
                "source": source,
            },
        )
        raise WikiError(
            "Empty title or content",
            detail="generate_wiki_entry requires non-empty title and content",
        )

    user_msg = prompt_template.format(
        title=title,
        source=source,
        content=content[:8000],
        language=language,
    )

    try:
        raw = await ollama_client.generate(
            WIKI_SYSTEM_PROMPT,
            user_msg,
            model=settings.ollama_model,
        )
    except OllamaUnavailableError as exc:
        logger.warning(
            "Ollama unavailable — using raw fallback for wiki entry",
            extra={"source": source, "title": title, "error_msg": str(exc)},
        )
        return _fallback_markdown(title, source, content)
    except Exception as exc:
        logger.error(
            "Wiki generation failed with unexpected error",
            extra={"source": source, "title": title, "error_msg": str(exc)},
            exc_info=True,
        )
        raise WikiError("Wiki generation failed", detail=str(exc)) from exc

    cleaned = _strip_code_fences(_strip_think_blocks(raw or ""))
    if not cleaned:
        logger.warning(
            "LLM returned empty wiki body — using raw fallback",
            extra={"source": source, "title": title},
        )
        return _fallback_markdown(title, source, content)

    logger.info(
        "Wiki entry generated",
        extra={
            "source": source,
            "title": title,
            "language": language,
            "bytes": len(cleaned),
        },
    )
    return cleaned
