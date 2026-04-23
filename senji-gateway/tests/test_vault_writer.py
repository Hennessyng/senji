"""Tests for app.services.vault_writer (TDD, Task 3)."""

import os

import pytest

from app.errors import VaultError
from app.services.vault_writer import VaultWriter


@pytest.fixture
def writer(tmp_path) -> VaultWriter:
    return VaultWriter(str(tmp_path / "vault"))


def _fm() -> dict:
    return {
        "title": "Example Article",
        "source": "https://example.com/post",
        "date": "2026-04-23",
        "type": "web",
        "tags": ["clipping", "inbox"],
        "language": "en",
        "author": "Jane Doe",
        "description": "An example article for testing",
    }


def _fm_block(path) -> str:
    return path.read_text(encoding="utf-8").split("\n---\n", 1)[0]


def _frontmatter_keys_in_order(path) -> list[str]:
    return [
        line.split(":", 1)[0].strip()
        for line in _fm_block(path).splitlines()
        if ":" in line and not line.startswith("---")
    ]


def _is_subsequence(actual: list[str], reference: list[str]) -> bool:
    ref_iter = iter(reference)
    return all(key in ref_iter for key in actual)


def test_directories_auto_created(tmp_path) -> None:
    vault = tmp_path / "vault"
    VaultWriter(str(vault))
    assert (vault / "raw").is_dir()
    assert (vault / "wiki").is_dir()
    assert (vault / "raw" / "assets").is_dir()


def test_directory_creation_failure_raises_vault_error(tmp_path, monkeypatch) -> None:
    def boom(self, *args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr("pathlib.Path.mkdir", boom)
    with pytest.raises(VaultError):
        VaultWriter(str(tmp_path / "vault"))


def test_save_raw_creates_file_with_frontmatter(writer) -> None:
    path = writer.save_raw("test-article", "# Test\nBody content.", _fm())
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    head, _, body = text.partition("\n---\n")
    assert "title:" in head
    assert "# Test" in body


def test_save_raw_writes_under_raw_dir(writer) -> None:
    path = writer.save_raw("slug-x", "# Body", _fm())
    assert "raw" in path.parts
    assert "wiki" not in path.parts
    assert path.name == "slug-x.md"


def test_save_wiki_writes_to_wiki_dir(writer) -> None:
    path = writer.save_wiki("mytopic", "# Topic wiki", _fm())
    assert "wiki" in path.parts
    assert "raw" not in path.parts
    assert path.name == "mytopic.md"


def test_write_is_atomic(writer, monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    real_rename = os.rename

    def spy(src, dst):
        calls.append((str(src), str(dst)))
        return real_rename(src, dst)

    monkeypatch.setattr("app.services.vault_writer.os.rename", spy)
    writer.save_raw("atomic-test", "# Body", _fm())
    assert len(calls) >= 1, "os.rename was never called (write not atomic)"
    src, dst = calls[-1]
    assert src.endswith(".tmp"), f"expected .tmp src, got {src}"
    assert dst.endswith("atomic-test.md"), f"expected final .md dst, got {dst}"


def test_vault_error_on_rename_failure(writer, monkeypatch) -> None:
    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr("app.services.vault_writer.os.rename", boom)
    with pytest.raises(VaultError):
        writer.save_raw("fail", "body", _fm())


def test_duplicate_no_overwrite_returns_existing(writer) -> None:
    first_path = writer.save_raw("dup", "# First", _fm())
    first_bytes = first_path.read_bytes()
    second_path = writer.save_raw("dup", "# Second DIFFERENT", _fm(), overwrite=False)
    assert second_path == first_path
    assert first_path.read_bytes() == first_bytes, "file was modified despite overwrite=False"


def test_duplicate_overwrite_true_replaces_file(writer) -> None:
    writer.save_raw("dup2", "# First", _fm())
    writer.save_raw("dup2", "# Second", _fm(), overwrite=True)
    path = writer.save_raw("dup2", "# Third", _fm(), overwrite=True)
    assert "# Third" in path.read_text(encoding="utf-8")
    assert "# First" not in path.read_text(encoding="utf-8")


def test_frontmatter_includes_plan_schema_keys(writer) -> None:
    path = writer.save_raw("schema", "# x", _fm())
    block = _fm_block(path)
    for key in ("title", "source", "date", "type", "tags", "language", "author", "description"):
        assert f"{key}:" in block, f"frontmatter missing key: {key}"


def test_frontmatter_omits_none_and_empty_fields(writer) -> None:
    fm = {
        "title": "T",
        "source": "S",
        "date": "2026-04-23",
        "type": "web",
        "tags": [],
        "language": None,
        "author": "",
        "description": None,
    }
    path = writer.save_raw("omit", "#", fm)
    block = _fm_block(path)
    assert "title:" in block
    assert "source:" in block
    assert "date:" in block
    assert "type:" in block
    assert "tags:" not in block
    assert "language:" not in block
    assert "author:" not in block
    assert "description:" not in block


def test_frontmatter_tags_are_yaml_flow_sequence(writer) -> None:
    path = writer.save_raw("tags", "#", _fm())
    tags_line = next(line for line in _fm_block(path).splitlines() if line.startswith("tags:"))
    assert "[" in tags_line and "]" in tags_line
    assert "clipping" in tags_line
    assert "inbox" in tags_line


def test_frontmatter_field_order_matches_plan(writer) -> None:
    path = writer.save_raw("order", "#", _fm())
    plan_order = ["title", "source", "date", "type", "tags", "language", "author", "description"]
    assert _is_subsequence(_frontmatter_keys_in_order(path), plan_order)


def test_env_var_vault_path(tmp_path, monkeypatch) -> None:
    vault = tmp_path / "env-vault"
    monkeypatch.setenv("VAULT_PATH", str(vault))
    VaultWriter()
    assert (vault / "raw").is_dir()
    assert (vault / "wiki").is_dir()
