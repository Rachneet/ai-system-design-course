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

    # Backends. "echo" and "hash" run without an API key or model downloads (container smoke tests).
    llm_backend: str = "anthropic"  # anthropic | echo
    embeddings: str = "local"  # local | hash

    # Authentication (Lab 4). jwt: RS256 tokens from your identity provider, verified against its JWKS.
    # dev: HS256 tokens signed with dev_jwt_secret, minted by scripts/dev_token.py. There is no unauthenticated mode.
    auth_mode: str = "jwt"  # jwt | dev
    jwks_url: str = ""
    jwt_issuer: str = ""
    jwt_audience: str = "relay-api"
    dev_jwt_secret: str = ""
    staff_role: str = "support"  # a token with this role in its "roles" claim may read internal documents

    # Abuse and cost limits (Lab 4)
    messages_per_minute: float = 20
    message_burst: int = 20
    daily_token_budget: int = 300_000
    memory_idle_s: int = 120  # extract memories once a session has been quiet this long


settings = Settings()
