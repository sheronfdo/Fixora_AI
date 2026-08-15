"""Runtime configuration, loaded from the environment (.env in dev)."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Service
    app_name: str = "Fixora AI Service"
    version: str = "1.0.0"
    environment: str = "development"

    # Supabase
    supabase_url: str = ""
    supabase_service_key: str = ""   # service-role key — NEVER exposed to clients
    supabase_anon_key: str = ""
    supabase_jwt_secret: str = ""    # for local HS256 verification of access tokens

    # OpenRouter (OpenAI-compatible LLM gateway) — used from Phase 5 onward
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_site_url: str = "https://fixora.app"     # sent as HTTP-Referer
    openrouter_app_name: str = "Fixora"                  # sent as X-Title

    # Rate limiting (per user, sliding window)
    rate_limit_requests: int = 30
    rate_limit_window_seconds: int = 60

    # CORS
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
