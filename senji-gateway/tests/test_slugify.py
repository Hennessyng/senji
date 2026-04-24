"""Tests for slug/filename utilities."""
from app.utils.slugify import make_slug


class TestMakeSlug:
    """Test cases for make_slug() function."""

    def test_cjk_produces_ascii_slug(self):
        """CJK text should transliterate to ASCII slug matching ^[a-z0-9-]+$."""
        result = make_slug("深度学习入门")
        assert result.isascii()
        assert all(c.isalnum() or c == "-" for c in result)
        # Should produce recognizable pinyin
        assert len(result) > 0

    def test_french_accents_transliterated(self):
        """French accents should be properly transliterated."""
        result = make_slug("Le résumé")
        assert "resume" in result
        assert "é" not in result  # accent stripped

    def test_max_80_chars(self):
        """Slug should be truncated to max 80 characters."""
        long_title = "A" * 200
        result = make_slug(long_title)
        assert len(result) <= 80

    def test_unsafe_chars_stripped(self):
        """Unsafe filesystem characters should be removed."""
        unsafe_title = 'file/name*with?unsafe"chars<here>|and:backslash\\'
        result = make_slug(unsafe_title)
        # None of these chars should appear
        unsafe_chars = {'/', '*', '?', '"', '<', '>', '|', ':', '\\'}
        assert not any(c in result for c in unsafe_chars)

    def test_date_prefix_option(self):
        """Optional date prefix should be prepended to slug."""
        result = make_slug("title", date_prefix="2026-04-23")
        assert result.startswith("2026-04-23-")
        # Remaining slug should be valid
        slug_part = result.replace("2026-04-23-", "")
        assert all(c.isalnum() or c == "-" for c in slug_part)
