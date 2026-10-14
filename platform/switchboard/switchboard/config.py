from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SWITCHBOARD_", env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:switchboard@localhost:5432/switchboard"
    db_schema: str | None = None  # tests only: run in an isolated schema
    admin_token: str = Field(default="", repr=False)  # bearer token for /admin; empty disables the admin API

    anthropic_api_key: str = Field(default="", repr=False)  # the provider credential; apps never see it
    anthropic_base_url: str = "https://api.anthropic.com"
    default_anthropic_version: str = "2023-06-01"
    allowed_beta_headers: list[str] = []  # anthropic-beta values apps may pass through; empty = none

    # Fallback chains, tried in order when the requested model fails before any byte reaches the client.
    # The app must also allow the fallback model.
    fallbacks: dict[str, list[str]] = {
        "claude-opus-5-5": ["claude-sonnet-5-5"],
        "claude-sonnet-5-5": ["claude-haiku-5-5"],
    }

    max_body_bytes: int = 8_000_000
    connect_timeout_s: float = 5.0
    read_timeout_s: float = 600.0
    key_cache_ttl_s: float = 30.0  # revocation reaches other instances within this window
    breaker_threshold: int = 5
    breaker_reset_s: float = 30.0


settings = Settings()
