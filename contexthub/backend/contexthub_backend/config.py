from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database — sync URL used by Alembic; async variant derived below
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/contexthub_dev"

    # Supabase JWT secret (HS256); override in prod via SUPABASE_JWT_SECRET env var.
    supabase_jwt_secret: str = "test-secret-not-for-production-at-least-32-bytes"

    app_version: str = "0.1.0"

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if "+psycopg" in url:
            return url.replace("+psycopg", "+asyncpg")
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


settings = Settings()
