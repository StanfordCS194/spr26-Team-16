from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Module 2/3 required settings.
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/contexthub_dev"
    supabase_jwt_secret: str = "test-secret-not-for-production-at-least-32-bytes"
    app_version: str = "0.1.0"

    # Modules 4-8 settings.
    app_env: str = "dev"
    ai_gateway_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AI_GATEWAY_API_KEY", "VERCEL_AI_GATEWAY_API_KEY"),
    )
    ai_gateway_base_url: str = "https://ai-gateway.vercel.sh/v1"
    ai_gateway_llm_model: str = "deepseek/deepseek-v4-flash"
    ai_gateway_embedding_model: str = "voyage/voyage-3.5-lite"
    ai_gateway_embedding_dimensions: int = 1024
    ai_gateway_json_mode: bool = False
    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "CH_ANTHROPIC_API_KEY"),
    )
    anthropic_model: str = "claude-haiku-4-5-20251001"
    voyage_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("VOYAGE_API_KEY", "CH_VOYAGE_API_KEY"),
    )
    voyage_model: str = "voyage-3-large"
    redis_url: str | None = Field(
        default="redis://localhost:6379",
        validation_alias=AliasChoices("REDIS_URL", "CH_REDIS_URL"),
    )
    supabase_url: str | None = None
    supabase_service_key: str | None = None
    transcript_bucket: str = "transcripts"
    rate_limit_per_minute: int = 30

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if "+psycopg" in url:
            return url.replace("+psycopg", "+asyncpg")
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


settings = Settings()
