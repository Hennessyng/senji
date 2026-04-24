from pydantic_settings import BaseSettings


class Settings(BaseSettings):
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


settings = Settings()

VAULT_PATH = settings.vault_path
OLLAMA_BASE_URL = settings.ollama_base_url
OLLAMA_MODEL = settings.ollama_model
OLLAMA_VISION_MODEL = settings.ollama_vision_model
OLLAMA_EMBED_MODEL = settings.ollama_embed_model
