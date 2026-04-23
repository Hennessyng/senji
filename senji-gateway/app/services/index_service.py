"""
Index and Log management service for vault ingestion tracking.

Provides atomic append operations for index.md and log.md files with:
- Automatic file creation with headers if missing
- Pipe character escaping in titles
- Duplicate prevention (index only)
- Atomic writes using .tmp + os.rename pattern
- Structured logging
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger("senji.pics.index_service")


def append_to_index(
    vault_path: str, job_id: str, slug: str, title: str, ingest_type: str
) -> None:
    """
    Append entry to vault's index.md file.
    
    Creates file with header if missing. Prevents duplicate entries by slug.
    Escapes pipe characters in title for markdown table safety.
    Uses atomic writes (.tmp + rename) for crash safety.
    
    Args:
        vault_path: Path to vault root directory
        job_id: Unique job identifier (for logging)
        slug: Article slug (checked for duplicates)
        title: Article title (pipe chars escaped)
        ingest_type: Ingest type (url, pdf, image)
    
    Raises:
        OSError: If write fails and retry exhausted
    """
    vault = Path(vault_path)
    index_file = vault / "index.md"
    
    escaped_title = title.replace("|", "\\|")
    new_entry = f"| {slug} | {escaped_title} | {ingest_type} |\n"
    
    full_text = _read_or_create_index(index_file)
    
    if _entry_exists(full_text, slug):
        logger.info(
            "Duplicate index entry skipped",
            extra={"job_id": job_id, "slug": slug},
        )
        return
    
    full_text += new_entry
    
    _atomic_write(index_file, full_text, job_id, "index")


def append_to_log(
    vault_path: str,
    job_id: str,
    slug: str,
    ingest_type: str,
    status: str,
    error_detail: str = "",
) -> None:
    """
    Append entry to vault's log.md file.
    
    Creates file with header if missing.
    Uses atomic writes (.tmp + rename) for crash safety.
    
    Args:
        vault_path: Path to vault root directory
        job_id: Unique job identifier
        slug: Article slug
        ingest_type: Ingest type (url, pdf, image)
        status: Job status (completed, failed, completed_raw_only)
        error_detail: Optional error message (empty string if none)
    
    Raises:
        OSError: If write fails and retry exhausted
    """
    vault = Path(vault_path)
    log_file = vault / "log.md"
    
    new_entry = f"| {job_id} | {slug} | {ingest_type} | {status} | {error_detail} |\n"
    
    full_text = _read_or_create_log(log_file)
    full_text += new_entry
    
    _atomic_write(log_file, full_text, job_id, "log")


def _read_or_create_index(file_path: Path) -> str:
    """Read index.md or return header if missing."""
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return "# Index\n\n"


def _read_or_create_log(file_path: Path) -> str:
    """Read log.md or return header if missing."""
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return "# Ingestion Log\n\n"


def _entry_exists(content: str, slug: str) -> bool:
    """Check if slug already exists in index content."""
    for line in content.split("\n"):
        if line.startswith("|") and f"| {slug} |" in line:
            return True
    return False


def _atomic_write(file_path: Path, content: str, job_id: str, file_type: str) -> None:
    """
    Atomically write content to file using .tmp + rename pattern.
    
    Ensures partial writes are never visible. Handles concurrent writes gracefully
    with retry on rename collision. On error, attempts cleanup of .tmp file and
    logs the failure.
    
    Args:
        file_path: Target file path
        content: Content to write
        job_id: Job ID for logging context
        file_type: "index" or "log" for log messages
    
    Raises:
        OSError: If write or rename fails after retry
    """
    import time
    
    tmp_file = file_path.with_suffix(file_path.suffix + ".tmp")
    max_retries = 3
    retry_delay = 0.01
    
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(content)
        
        for attempt in range(max_retries):
            try:
                os.rename(tmp_file, file_path)
                break
            except FileNotFoundError:
                if attempt < max_retries - 1 and tmp_file.exists():
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                raise
        
        logger.info(
            f"{file_type} write complete",
            extra={"job_id": job_id, "path": str(file_path), "bytes": len(content)},
        )
    except OSError as exc:
        logger.error(
            f"{file_type} write failed",
            extra={"job_id": job_id, "path": str(file_path), "error": str(exc)},
            exc_info=True,
        )
        try:
            if tmp_file.exists():
                tmp_file.unlink()
        except OSError:
            pass
        raise
