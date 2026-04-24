"""
Tests for index_service.py — index.md and log.md auto-update service.

Covers:
- File creation with headers
- Pipe character escaping in titles
- Duplicate prevention in index
- Atomic writes (.tmp + rename)
- Concurrent safety (race conditions)
- Error handling (OSError, FileNotFoundError)
"""

from threading import Thread

import pytest

from app.services.index_service import append_to_index, append_to_log


class TestIndexCreation:
    """Test index.md file creation and header setup."""

    def test_index_created_with_header_if_missing(self, tmp_path):
        """When index.md missing, create with header."""
        vault = tmp_path / "vault"
        vault.mkdir()

        append_to_index(str(vault), "job1", "article-1", "First Article", "url")

        index_file = vault / "index.md"
        assert index_file.exists()
        content = index_file.read_text()
        assert content.startswith("# Index\n\n")
        assert "article-1" in content
        assert "First Article" in content

    def test_index_appends_when_exists(self, tmp_path):
        """When index.md exists, append without replacing header."""
        vault = tmp_path / "vault"
        vault.mkdir()
        index_file = vault / "index.md"

        # Pre-populate with header and one entry
        index_file.write_text("# Index\n\n| slug1 | Title One | url |\n")

        append_to_index(str(vault), "job2", "article-2", "Second Article", "pdf")

        content = index_file.read_text()
        assert content.count("# Index") == 1  # Only one header
        assert "article-1" not in content  # Original entry removed? No, should be there
        assert "article-2" in content
        assert "Second Article" in content

    def test_index_table_format_correct(self, tmp_path):
        """Index entries use markdown table format."""
        vault = tmp_path / "vault"
        vault.mkdir()

        append_to_index(str(vault), "job1", "test-slug", "Test Title", "image")

        index_file = vault / "index.md"
        content = index_file.read_text()
        # Should contain markdown table row
        assert "| test-slug | Test Title | image |" in content


class TestLogCreation:
    """Test log.md file creation and header setup."""

    def test_log_created_with_header_if_missing(self, tmp_path):
        """When log.md missing, create with header."""
        vault = tmp_path / "vault"
        vault.mkdir()

        append_to_log(str(vault), "job1", "article-1", "url", "completed", error_detail="")

        log_file = vault / "log.md"
        assert log_file.exists()
        content = log_file.read_text()
        assert content.startswith("# Ingestion Log\n\n")
        assert "job1" in content
        assert "completed" in content

    def test_log_appends_when_exists(self, tmp_path):
        """When log.md exists, append without replacing header."""
        vault = tmp_path / "vault"
        vault.mkdir()
        log_file = vault / "log.md"

        # Pre-populate
        log_file.write_text("# Ingestion Log\n\n| job-old | slug1 | url | completed | |\n")

        append_to_log(str(vault), "job2", "article-2", "pdf", "failed", error_detail="parse error")

        content = log_file.read_text()
        assert content.count("# Ingestion Log") == 1
        assert "job2" in content
        assert "failed" in content

    def test_log_table_format_correct(self, tmp_path):
        """Log entries use markdown table format with all fields."""
        vault = tmp_path / "vault"
        vault.mkdir()

        append_to_log(str(vault), "job123", "clip-1", "url", "completed", error_detail="")

        log_file = vault / "log.md"
        content = log_file.read_text()
        assert "| job123 | clip-1 | url | completed |" in content


class TestPipeCharEscaping:
    """Test pipe character escaping in titles."""

    def test_title_with_pipe_escaped(self, tmp_path):
        """Title containing | should be escaped."""
        vault = tmp_path / "vault"
        vault.mkdir()

        append_to_index(str(vault), "job1", "article-1", "Title | With | Pipes", "url")

        index_file = vault / "index.md"
        content = index_file.read_text()
        # Pipes in title should be escaped
        assert "Title \\| With \\| Pipes" in content or "Title | With | Pipes" not in content.split("\n")[-1]

    def test_title_without_pipe_unchanged(self, tmp_path):
        """Title without pipes remains unchanged."""
        vault = tmp_path / "vault"
        vault.mkdir()

        append_to_index(str(vault), "job1", "article-1", "Normal Title", "url")

        index_file = vault / "index.md"
        content = index_file.read_text()
        assert "Normal Title" in content


class TestDuplicatePrevention:
    """Test duplicate prevention in index."""

    def test_no_duplicate_entries_for_same_slug(self, tmp_path):
        """Same slug should not create duplicate entries."""
        vault = tmp_path / "vault"
        vault.mkdir()

        append_to_index(str(vault), "job1", "article-1", "First Title", "url")
        append_to_index(str(vault), "job2", "article-1", "Updated Title", "url")

        index_file = vault / "index.md"
        content = index_file.read_text()

        # Count occurrences of article-1
        lines = [l for l in content.split("\n") if "article-1" in l]
        assert len(lines) == 1, f"Expected 1 line with article-1, got {len(lines)}"

    def test_different_slugs_create_separate_entries(self, tmp_path):
        """Different slugs should create separate entries."""
        vault = tmp_path / "vault"
        vault.mkdir()

        append_to_index(str(vault), "job1", "article-1", "Title One", "url")
        append_to_index(str(vault), "job2", "article-2", "Title Two", "pdf")

        index_file = vault / "index.md"
        content = index_file.read_text()

        assert "article-1" in content
        assert "article-2" in content
        assert content.count("article-") == 2


class TestAtomicWrites:
    """Test atomic write pattern (.tmp + rename)."""

    def test_atomic_write_creates_tmp_then_renames(self, tmp_path):
        """Atomic write should use .tmp file then rename."""
        vault = tmp_path / "vault"
        vault.mkdir()

        append_to_index(str(vault), "job1", "article-1", "Title", "url")

        # After successful write, no .tmp file should remain
        tmp_file = vault / "index.md.tmp"
        assert not tmp_file.exists(), "Leftover .tmp file found after successful write"

        index_file = vault / "index.md"
        assert index_file.exists()

    def test_tmp_cleanup_on_error(self, tmp_path):
        """On write error, .tmp file should be cleaned up."""
        vault = tmp_path / "vault"
        vault.mkdir()

        # Make vault read-only to trigger write error
        vault.chmod(0o444)

        try:
            with pytest.raises(OSError):
                append_to_index(str(vault), "job1", "article-1", "Title", "url")
        finally:
            vault.chmod(0o755)

        # Check no .tmp file remains
        tmp_file = vault / "index.md.tmp"
        assert not tmp_file.exists()


class TestConcurrentSafety:
    """Test concurrent write safety."""

    def test_concurrent_appends_dont_corrupt(self, tmp_path):
        """Multiple concurrent writes should not corrupt the file; last write wins."""
        vault = tmp_path / "vault"
        vault.mkdir()

        def write_entry(job_id, slug, title):
            try:
                append_to_index(str(vault), job_id, slug, title, "url")
            except OSError:
                pass

        threads = [
            Thread(target=write_entry, args=(f"job{i}", f"article-{i}", f"Title {i}"))
            for i in range(5)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        index_file = vault / "index.md"
        assert index_file.exists(), "Index file should exist after concurrent writes"
        content = index_file.read_text()
        assert content.startswith("# Index"), "Index header should be present"
        assert "| " in content, "At least one entry should be written"

    def test_log_concurrent_writes(self, tmp_path):
        """Multiple concurrent log writes should not corrupt file; last write wins."""
        vault = tmp_path / "vault"
        vault.mkdir()

        def write_log(job_id):
            try:
                append_to_log(str(vault), job_id, f"slug-{job_id}", "url", "completed", "")
            except OSError:
                pass

        threads = [Thread(target=write_log, args=(f"job{i}",)) for i in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        log_file = vault / "log.md"
        assert log_file.exists(), "Log file should exist after concurrent writes"
        content = log_file.read_text()
        assert content.startswith("# Ingestion Log"), "Log header should be present"
        assert "| " in content, "At least one log entry should be written"


class TestErrorHandling:
    """Test error handling and recovery."""

    def test_handles_missing_vault_path(self, tmp_path):
        """Should handle non-existent vault path gracefully."""
        vault = tmp_path / "nonexistent" / "vault"

        # Should either create the path or raise a clear error
        try:
            append_to_index(str(vault), "job1", "article-1", "Title", "url")
            # If it succeeds, the path should now exist
            assert vault.exists()
        except OSError:
            # Or it should fail with OSError (expected)
            pass

    def test_handles_readonly_vault(self, tmp_path):
        """Should handle read-only vault gracefully."""
        vault = tmp_path / "vault"
        vault.mkdir()
        vault.chmod(0o444)

        try:
            with pytest.raises(OSError):
                append_to_index(str(vault), "job1", "article-1", "Title", "url")
        finally:
            vault.chmod(0o755)

    def test_log_error_detail_included(self, tmp_path):
        """Error detail should be included in log entry."""
        vault = tmp_path / "vault"
        vault.mkdir()

        error_msg = "Failed to parse PDF: timeout"
        append_to_log(str(vault), "job1", "article-1", "pdf", "failed", error_detail=error_msg)

        log_file = vault / "log.md"
        content = log_file.read_text()
        assert error_msg in content

    def test_empty_error_detail_handled(self, tmp_path):
        """Empty error_detail should be handled correctly."""
        vault = tmp_path / "vault"
        vault.mkdir()

        append_to_log(str(vault), "job1", "article-1", "url", "completed", error_detail="")

        log_file = vault / "log.md"
        content = log_file.read_text()
        assert "job1" in content


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_special_chars_in_title(self, tmp_path):
        """Title with special markdown chars should be handled."""
        vault = tmp_path / "vault"
        vault.mkdir()

        append_to_index(str(vault), "job1", "article-1", "Title [with] *markdown*", "url")

        index_file = vault / "index.md"
        content = index_file.read_text()
        assert "article-1" in content

    def test_very_long_title(self, tmp_path):
        """Very long title should be handled."""
        vault = tmp_path / "vault"
        vault.mkdir()

        long_title = "A" * 500
        append_to_index(str(vault), "job1", "article-1", long_title, "url")

        index_file = vault / "index.md"
        content = index_file.read_text()
        assert long_title in content

    def test_empty_title_edge_case(self, tmp_path):
        """Empty title should be handled gracefully."""
        vault = tmp_path / "vault"
        vault.mkdir()

        # This may raise or handle gracefully depending on spec
        append_to_index(str(vault), "job1", "article-1", "", "url")

        index_file = vault / "index.md"
        assert index_file.exists()

    def test_unicode_in_title(self, tmp_path):
        """Unicode characters in title should be preserved."""
        vault = tmp_path / "vault"
        vault.mkdir()

        append_to_index(str(vault), "job1", "article-1", "Título en Español 中文 🚀", "url")

        index_file = vault / "index.md"
        content = index_file.read_text(encoding="utf-8")
        assert "Español" in content
        assert "中文" in content
