"""RAG Pipeline configuration."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAG_", env_file=".env", extra="ignore")

    embedding_service_url: str = "http://localhost:8002"
    vector_namespace: str = "default"
    default_top_k: int = 5
    log_level: str = "INFO"


settings = Settings()
