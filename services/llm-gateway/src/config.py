"""Gateway configuration loaded from environment variables."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenAI primary provider
    openai_api_key: str = ""
    openai_api_base: str = "https://api.openai.com/v1"

    # Azure OpenAI fallback provider
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = "2024-02-01"
    azure_openai_deployment: str = "gpt-4o"

    # Ollama (local dev)
    ollama_base_url: str = "http://localhost:11434"

    # Circuit breaker thresholds
    cb_failure_threshold: int = 5
    cb_error_rate_threshold: float = 0.5   # 50%
    cb_window_seconds: int = 30
    cb_recovery_timeout_seconds: int = 60

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_usage_topic: str = "llm-usage-events"
    kafka_enabled: bool = True

    # PII scrubbing
    pii_patterns_file: str = ""   # path to extra patterns JSON; built-ins always active

    # Gateway
    default_provider: str = "openai"          # openai | azure | ollama
    fallback_provider: str = "azure"
    request_timeout_seconds: float = 120.0
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
