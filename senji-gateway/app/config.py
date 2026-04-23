from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    senji_token: str = "dev-token"
    readability_url: str = "http://readability:3000"
    log_level: str = "INFO"
    sqlite_db_path: str = "/opt/vault/jobs.db"


settings = Settings()
