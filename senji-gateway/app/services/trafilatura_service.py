import logging
import re

import trafilatura
from trafilatura.metadata import extract_metadata

logger = logging.getLogger("senji.services.trafilatura")

_LAZY_ATTRS = re.compile(r'\bdata-(?:lazy-)?src\s*=\s*"(https?://[^"]+)"')


def _promote_lazy_images(html: str) -> str:
    return _LAZY_ATTRS.sub(lambda m: f'src="{m.group(1)}"', html)


def extract_article(html: str, source_url: str) -> dict:
    """Extract article metadata + markdown from HTML using trafilatura.
    
    Returns dict with: markdown, title, author, language, publish_date
    Raises ValueError if extraction fails.
    """
    try:
        html = _promote_lazy_images(html)
        doc = trafilatura.extract(
            html,
            output_format="markdown",
            include_comments=False,
            include_images=True,
            include_tables=True,
            include_formatting=True,
        )
        if not doc:
            raise ValueError("Trafilatura returned empty extraction")

        metadata = extract_metadata(html)

        return {
            "markdown": doc,
            "title": metadata.title or "Untitled",
            "author": metadata.author,
            "language": metadata.language,
            "publish_date": metadata.date,
        }
    except Exception as exc:
        logger.error(
            "Article extraction failed",
            extra={"source": source_url, "error": str(exc)},
            exc_info=True,
        )
        raise ValueError(f"Failed to extract article from {source_url}") from exc
