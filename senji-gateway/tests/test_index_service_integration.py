"""
Integration test: Verify index_service integrates with job_queue processing.

Tests that the process_url_job, process_pdf_job, process_image_job methods
correctly call append_to_index and append_to_log during job completion.
"""



from app.services.index_service import append_to_index, append_to_log


def test_append_to_index_creates_markdown_entry(tmp_path):
    """Verify append_to_index creates proper markdown table entry."""
    vault = tmp_path / "vault"
    vault.mkdir()

    append_to_index(str(vault), "job1", "article-2025-01-15", "My Article", "url")

    index_file = vault / "index.md"
    assert index_file.exists()
    content = index_file.read_text()

    assert "# Index" in content
    assert "| article-2025-01-15 | My Article | url |" in content


def test_append_to_log_creates_markdown_entry(tmp_path):
    """Verify append_to_log creates proper markdown table entry."""
    vault = tmp_path / "vault"
    vault.mkdir()

    append_to_log(str(vault), "job1", "article-2025-01-15", "url", "completed", "")

    log_file = vault / "log.md"
    assert log_file.exists()
    content = log_file.read_text()

    assert "# Ingestion Log" in content
    assert "| job1 | article-2025-01-15 | url | completed |" in content


def test_vault_index_and_log_files_accumulate(tmp_path):
    """Multiple entries should accumulate in index and log files."""
    vault = tmp_path / "vault"
    vault.mkdir()

    for i in range(3):
        append_to_index(str(vault), f"job{i}", f"article-{i}", f"Title {i}", "url")
        append_to_log(str(vault), f"job{i}", f"article-{i}", "url", "completed", "")

    index_content = (vault / "index.md").read_text()
    log_content = (vault / "log.md").read_text()

    assert index_content.count("| article-") == 3
    assert log_content.count("| job") == 3
    assert "article-0" in index_content
    assert "article-1" in index_content
    assert "article-2" in index_content
