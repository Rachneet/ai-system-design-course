from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RELAY_", env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:relay@localhost:5432/relay"
    model: str = "claude-opus-5-5"  # set RELAY_MODEL=claude-haiku-5-5 for cheap development
    memory_model: str = "claude-haiku-5-5"  # also used for quarantine and the user simulator
    judge_model: str = "claude-opus-5-5"  # pinned; changing it changes every judged score
    refusal_fallback: bool = True  # server-side fallback model when the main model declines
    max_steps: int = 8
    max_tokens: int = 4096
    tool_timeout_s: float = 5.0
    refund_limit: float = 200.0


settings = Settings()
