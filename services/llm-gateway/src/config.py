"""Gateway configuration loaded from environment variables."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenAI
    openai_api_key: str = ""
    openai_api_base: str = "https://api.openai.com/v1"

    # Azure OpenAI
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = "2024-02-01"
    azure_openai_deployment: str = "gpt-4o"

    # Anthropic
    anthropic_api_key: str = ""

    # Groq
    groq_api_key: str = ""

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
    kafka_sync_mode: bool = True  # when True Kafka producer is disabled — no broker needed
    kafka_enabled: bool = False   # disabled by default; set KAFKA_ENABLED=true with a real broker

    # PII scrubbing
    pii_patterns_file: str = ""   # path to extra patterns JSON; built-ins always active

    # Gateway
    default_provider: str = "anthropic"       # openai | azure | anthropic | ollama
    fallback_provider: str = "openai"
    request_timeout_seconds: float = 120.0
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
