from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ATLAS_", env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:atlas@localhost:5432/atlas"
    db_schema: str | None = None  # tests only: run in an isolated schema
    admin_token: str = Field(default="", repr=False)  # bootstrap token for /admin; empty disables it

    # Discovery reads (/v0/servers, agent cards, skill downloads) need a token unless this is set.
    public_read: bool = False

    # Policy
    licenses_allowed: list[str] = ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MPL-2.0", "Proprietary"]
    eval_min_score: float | None = None  # when set, approval needs an eval report at or above this score
    require_auth_on_agents: bool = True  # agent cards must declare securitySchemes
    max_skill_bytes: int = 10_000_000  # uncompressed size of a skill package
    max_skill_files: int = 500

    # Upstream registry for curated sync (imports land in review, never approved)
    upstream_registry_url: str = "https://registry.modelcontextprotocol.io"


settings = Settings()
