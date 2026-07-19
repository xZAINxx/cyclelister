"""Typed application settings (spec §15: config over code).

Layers repo-root .env then backend/.env then real environment variables.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
PROMPTS_DIR = BACKEND_DIR / "prompts"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"

    # Database
    database_url: str = (
        "postgresql+asyncpg://cyclelister:cyclelister@127.0.0.1:5533/cyclelister"
    )

    # Supabase auth — flip auth_required on for any non-local deployment.
    auth_required: bool = False
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""  # empty -> dev-mode auth bypass

    # Storage
    storage_backend: str = "local"  # local | supabase
    storage_dir: str = str(REPO_ROOT / "data" / "images")
    storage_bucket: str = "listing-images"

    # Anthropic (spec §8.4 model routing)
    anthropic_api_key: str = ""
    vision_model: str = "claude-sonnet-5"
    text_model: str = "claude-sonnet-5"
    classify_model: str = "claude-haiku-4-5"

    # eBay (spec §10)
    ebay_env: str = "sandbox"  # sandbox | production
    ebay_client_id: str = ""
    ebay_client_secret: str = ""
    ebay_ru_name: str = ""
    ebay_marketplace_id: str = "EBAY_US"
    # Marketplace Insights is access-restricted; flip only once eBay approves (spec §7.1).
    ebay_insights_enabled: bool = False
    ebay_token_key: str = ""  # Fernet key; tokens encrypted at rest (spec §15)

    # Jobs
    max_concurrent_jobs: int = 3
    order_poll_minutes: int = 15  # sale-detection cadence (spec §10)

    # CORS (comma-separated origins; dev Vite server by default)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def is_dev(self) -> bool:
        return self.app_env != "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
