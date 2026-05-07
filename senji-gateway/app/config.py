import logging
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

_log = logging.getLogger(__name__)


def _default_yaml_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config.yaml"


_YAML_PATH = Path(os.getenv("SENJI_CONFIG_YAML", str(_default_yaml_path())))


class _GatewayYamlSource(PydanticBaseSettingsSource):
    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not _YAML_PATH.exists():
            return {}
        try:
            with _YAML_PATH.open("r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            _log.error("config.yaml parse error path=%s err=%s", _YAML_PATH, exc)
            raise
        if not isinstance(raw, dict):
            _log.warning("config.yaml root not a mapping path=%s", _YAML_PATH)
            return {}
        block = raw.get("gateway", {})
        return block if isinstance(block, dict) else {}

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        val = self._data.get(field_name)
        return val, field_name, val is not None

    def __call__(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for field_name, field in self.settings_cls.model_fields.items():
            val, key, found = self.get_field_value(field, field_name)
            if found:
                out[key] = val
        return out


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    senji_token: str = "dev-token"
    readability_url: str = "http://readability:3000"
    log_level: str = "INFO"
    sqlite_db_path: str = "/opt/vault/jobs.db"
    ollama_base_url: str = "http://localhost:11434"
    vault_path: str = "/opt/vault"
    ollama_model: str = "qwen3:8b"
    ollama_vision_model: str = "qwen2.5vl:7b"
    ollama_embed_model: str = "bge-m3"
    embedding_model: str = "BAAI/bge-m3"
    embedding_batch_size: int = 32
    max_file_size_mb: int = 50
    asset_timeout_seconds: int = 60
    asset_concurrency: int = 4
    asset_retry_count: int = 2

    fetcher_timeout_seconds: float = 30.0
    readability_timeout_seconds: float = 30.0
    job_fetch_timeout_seconds: float = 10.0
    ollama_health_timeout_seconds: float = 5.0
    ollama_generate_timeout_seconds: float = 120.0
    embedding_request_timeout_seconds: float = 120.0
    media_download_timeout_seconds: float = 15.0
    stale_job_timeout_minutes: int = 15
    wiki_content_max_chars: int = 8000

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            _GatewayYamlSource(settings_cls),
            file_secret_settings,
        )


settings = Settings()

VAULT_PATH = settings.vault_path
OLLAMA_BASE_URL = settings.ollama_base_url
OLLAMA_MODEL = settings.ollama_model
OLLAMA_VISION_MODEL = settings.ollama_vision_model
OLLAMA_EMBED_MODEL = settings.ollama_embed_model
