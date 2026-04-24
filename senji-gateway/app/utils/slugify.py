"""Slug/filename utilities for safe, readable slugs from any language."""
from slugify import slugify
from unidecode import unidecode


def make_slug(title: str, date_prefix: str | None = None) -> str:
    """Generate a safe, readable slug from a title.
    
    Handles CJK transliteration (pinyin), accents, and strips unsafe filesystem chars.
    
    Args:
        title: Input title (supports CJK, accented characters, etc.)
        date_prefix: Optional date prefix (format: "YYYY-MM-DD")
    
    Returns:
        Safe filename slug (max 80 chars, lowercase, ASCII-only, hyphenated)
    
    Examples:
        >>> make_slug("深度学习入门")
        'shen-du-xue-xi-ru-men'
        >>> make_slug("Le résumé")
        'le-resume'
        >>> make_slug("title", date_prefix="2026-04-23")
        '2026-04-23-title'
    """
    unsafe_filesystem_chars = {'/', '\\', ':', '*', '?', '"', '<', '>', '|', '\0'}
    title_cleaned = title
    for char in unsafe_filesystem_chars:
        title_cleaned = title_cleaned.replace(char, ' ')

    title_transliterated = unidecode(title_cleaned)
    slug = slugify(title_transliterated, lowercase=True, word_boundary=True)
    slug = slug.strip('-')[:80]

    if date_prefix:
        slug = f"{date_prefix}-{slug}"

    return slug
