"""Embedding Service configuration."""
from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Active backend: "openai_gateway" | "sentence_transformers" | "mock"
    embedding_backend: str = "openai_gateway"

    # LLM Gateway URL (used by openai_gateway backend)
    llm_gateway_url: str = "http://localhost:8000"
    llm_gateway_timeout: float = 30.0

    # Default embedding model per backend
    openai_embedding_model: str = "text-embedding-ada-002"
    st_model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"   # multilingual model (50+ languages, 384-dim)

    # Request limits
    max_texts_per_batch: int = 100
    max_text_length_chars: int = 8192

    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
