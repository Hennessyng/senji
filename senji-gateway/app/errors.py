"""Custom exceptions for senji-pics ingestion pipeline."""


class IngestError(Exception):
    """Base exception for ingestion failures (user-recoverable)."""

    def __init__(self, message: str, detail: str | None = None):
        self.message = message
        self.detail = detail
        super().__init__(message)


class VaultError(Exception):
    """Vault write/read failures (filesystem, permissions)."""

    def __init__(self, message: str, path: str | None = None):
        self.message = message
        self.path = path
        super().__init__(message)


class OllamaUnavailableError(Exception):
    """Ollama service down after retries."""

    def __init__(self, message: str = "Ollama unavailable"):
        self.message = message
        super().__init__(message)
