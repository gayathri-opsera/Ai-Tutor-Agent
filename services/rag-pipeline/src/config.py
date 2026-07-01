"""RAG Pipeline configuration."""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAG_", env_file=".env", extra="ignore")

    embedding_service_url: str = "http://embedding-service:8001"
    vector_namespace: str = "default"
    default_top_k: int = 5
    log_level: str = "INFO"

    # Allow override via plain EMBEDDING_SERVICE_URL env var too
    def model_post_init(self, __context):
        plain = os.getenv("EMBEDDING_SERVICE_URL")
        if plain and self.embedding_service_url == "http://embedding-service:8001":
            self.embedding_service_url = plain


settings = Settings()
