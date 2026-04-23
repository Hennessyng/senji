import logging
import os
from pathlib import Path

from app.errors import VaultError

logger = logging.getLogger("senji.pics.vault_writer")

_DEFAULT_VAULT_PATH = "/opt/vault"
_PLAN_SCHEMA_ORDER = (
    "title",
    "source",
    "date",
    "type",
    "tags",
    "language",
    "author",
    "description",
)


def _yaml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class VaultWriter:
    def __init__(self, vault_path: str | None = None) -> None:
        self._root = Path(vault_path or os.getenv("VAULT_PATH", _DEFAULT_VAULT_PATH))
        self._raw = self._root / "raw"
        self._wiki = self._root / "wiki"
        self._assets = self._raw / "assets"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        try:
            self._raw.mkdir(parents=True, exist_ok=True)
            self._wiki.mkdir(parents=True, exist_ok=True)
            self._assets.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error(
                "Failed to create vault dirs",
                extra={"root": str(self._root), "error": str(exc)},
                exc_info=True,
            )
            raise VaultError(
                f"Could not create vault directories under {self._root}",
                path=str(self._root),
            ) from exc
        logger.debug("Vault dirs ensured", extra={"root": str(self._root)})

    def save_raw(
        self,
        slug: str,
        content: str,
        frontmatter: dict,
        overwrite: bool = True,
    ) -> Path:
        return self._save(self._raw / f"{slug}.md", content, frontmatter, overwrite)

    def save_wiki(
        self,
        slug: str,
        content: str,
        frontmatter: dict,
        overwrite: bool = True,
    ) -> Path:
        return self._save(self._wiki / f"{slug}.md", content, frontmatter, overwrite)

    def _save(
        self,
        path: Path,
        content: str,
        frontmatter: dict,
        overwrite: bool,
    ) -> Path:
        if path.exists() and not overwrite:
            logger.info(
                "Duplicate skipped (overwrite=False)",
                extra={"path": str(path)},
            )
            return path
        fm_text = self._build_frontmatter(frontmatter)
        full_text = fm_text + "\n" + content
        self._atomic_write(path, full_text)
        logger.info(
            "Vault write complete",
            extra={"path": str(path), "bytes": len(full_text)},
        )
        return path

    def _atomic_write(self, path: Path, text: str) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
            os.rename(tmp, path)
        except OSError as exc:
            logger.error(
                "Atomic write failed",
                extra={"path": str(path), "error": str(exc)},
                exc_info=True,
            )
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            raise VaultError(f"Failed to write {path}", path=str(path)) from exc

    def _build_frontmatter(self, fm: dict) -> str:
        """TODO(user): Build YAML frontmatter block from dict. Contract in tests/test_vault_writer.py.
        
        Keys: use _PLAN_SCHEMA_ORDER. Omit None, "", [].
        Tags: YAML flow format [a, b].
        Strings: quote + _yaml_escape.
        Return: "---\\nkey: value\\n...\\n---"
        
        ~5-10 lines. Helpers: _yaml_escape, _PLAN_SCHEMA_ORDER.
        """
        raise NotImplementedError(
            "_build_frontmatter is a learning-mode contribution. See tests for contract."
        )
