from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSecrets(BaseModel):
    """What one agent holds: a Switchboard key and a Checkpoint token. Never a provider key or a tool credential."""

    switchboard_key: str = Field(repr=False)
    checkpoint_token: str = Field(repr=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HELPDESK_", env_file=".env", extra="ignore")

    database_url: str = "postgresql://helpdesk_app:helpdesk@localhost:5432/helpdesk"  # a role without BYPASSRLS
    db_schema: str | None = None  # tests only
    admin_token: str = Field(default="", repr=False)

    # The platform: the only two endpoints an agent knows
    switchboard_url: str = "http://localhost:8000"
    checkpoint_url: str = "http://localhost:8002"
    atlas_url: str = "http://localhost:8001"  # read by the evidence pack, never by agents
    agents: dict[str, AgentSecrets] = {}  # agent id -> its credentials, from a secret store
    console_tokens: dict[str, str] = Field(default={}, repr=False)  # tenant -> Checkpoint approver token
    switchboard_admin_token: str = Field(default="", repr=False)  # FinOps reports only
    checkpoint_admin_token: str = Field(default="", repr=False)  # evidence pack only
    atlas_token: str = Field(default="", repr=False)  # evidence pack only

    # Roster and models: every model choice lives in one file, so a suite can run on a second model
    agents_file: str = "config/agents.toml"
    models_file: str = "config/models.toml"
    skills_dir: str = "skills"

    # End users: the same JWT goes to Checkpoint as X-User-Token, so it names both audiences
    user_jwt_secret: str = Field(default="", repr=False)  # HS256 for development
    user_jwks_url: str = ""  # RS256 from your identity provider in production
    user_jwt_issuer: str = ""
    user_jwt_audience: str = "helpdesk"
    dev_tokens: bool = False  # POST /dev/token mints user tokens; never enable in production

    # Agent loop limits
    max_steps: int = 8  # model calls per agent turn
    max_handoffs: int = 3  # per ticket; a deeper chain goes to a person
    max_tokens: int = 1024

    # Operations and governance
    reopen_window_days: int = 7  # a ticket reopened within this window does not count as resolved
    retention_days: dict[str, int] = {"messages": 90, "events": 365, "escalations": 365}
    human_cost_per_escalation_usd: float = 6.0  # fully loaded cost assumptions for FinOps, labelled as such
    human_cost_per_approval_usd: float = 1.5
    allowed_origins: list[str] = []


settings = Settings()
