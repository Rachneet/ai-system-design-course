from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CHECKPOINT_", env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:checkpoint@localhost:5432/checkpoint"
    db_schema: str | None = None  # tests only
    admin_token: str = Field(default="", repr=False)

    # Catalog: only servers approved in Atlas are reachable
    atlas_url: str = "http://localhost:8001"
    atlas_token: str = Field(default="", repr=False)
    catalog_ttl_s: float = 60.0
    upstream_credentials: dict[str, str] = Field(default={}, repr=False)  # server name -> Authorization value

    # Policy
    policy_file: str = "policies/default.cedar"

    # End-user identity, forwarded by the agent in X-User-Token (on-behalf-of)
    user_jwt_secret: str = Field(default="", repr=False)  # HS256 for development
    user_jwks_url: str = ""  # RS256 from your identity provider in production
    user_jwt_issuer: str = ""
    user_jwt_audience: str = "checkpoint"

    # Assertions Checkpoint signs for upstream servers: they verify against /.well-known/jwks.json
    assertion_private_key: str = Field(default="", repr=False)  # PEM; generated per process if empty (dev only)
    assertion_ttl_s: int = 60

    # Approvals: a pending request lapses after this long; an approval must be used within the second window
    approval_pending_ttl_s: int = 1800
    approval_use_ttl_s: int = 300

    calls_per_minute: int = 60  # per agent and tool
    allowed_origins: list[str] = []  # browser Origins allowed to call /mcp; empty = none (server-to-server only)


settings = Settings()
