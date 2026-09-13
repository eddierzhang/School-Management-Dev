"""Runtime settings, read from HR_* environment variables or backend/.env.

`today` is the real date unless `HR_TODAY` pins it. The demo term is a fixed
fiction (Fall 2026, five weeks elapsed), so the seed, the tests and `dev.sh` pin
the clock to 2026-09-12 to keep "missing work", trends and attendance rates
stable no matter when they run. A real deployment leaves it unset.
"""
from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEMO_TODAY = date(2026, 9, 12)
DEV_SECRET = "development-only-secret-do-not-use-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HR_",
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"          # development | test | production
    database_url: str = "sqlite:///./halverson.db"
    cors_origins: str = "http://localhost:5174,http://127.0.0.1:5174"
    pinned_today: date | None = Field(default=None, validation_alias="HR_TODAY")
    term: str = "Fall 2026"
    school_name: str = "Halverson Ridge High School"

    # Local inference. Nothing leaves the machine.
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"
    ollama_timeout: float = 300.0
    ollama_temperature: float = 0.1
    # Sent on every request. Ollama's own default is 4,096 tokens, and input past
    # the window is cut to roughly half of it WITHOUT any error: a 50,000-character
    # document arrived as 2,050 tokens. 16k costs ~2.4 GB of KV cache on qwen3:4b.
    ollama_num_ctx: int = 16384
    agent_max_steps: int = 8
    agent_max_seconds: float = 420.0

    # Sign-in. `secret_key` signs the short-lived OIDC state cookie; production
    # refuses to start with the development value.
    secret_key: str = DEV_SECRET
    session_hours: float = 12.0
    cookie_secure: bool | None = None       # None: secure cookies in production only
    password_login: bool = True             # set false once everyone signs in through the school's IdP
    login_max_failures: int = 5
    login_lockout_minutes: int = 15
    # The school's identity provider (Google Workspace, Microsoft Entra, …). Enabled
    # when the issuer and client id are set. Only people who already have an
    # account here can sign in through it; it never creates accounts.
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""             # e.g. https://support.school.edu/api/auth/oidc/callback
    oidc_scopes: str = "openid email profile"
    oidc_button_label: str = "Sign in with your school account"

    # Thresholds the support office can tune without touching the engine.
    support_threshold: float = 72.0   # below this, a course grade needs a plan
    concern_floor: float = 65.0       # below this, tutoring rather than monitoring
    excelling_threshold: float = 86.0 # at or above this, enrichment is on the table

    @property
    def today(self) -> date:
        return self.pinned_today or date.today()

    @property
    def production(self) -> bool:
        return self.app_env == "production"

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def secure_cookies(self) -> bool:
        return self.production if self.cookie_secure is None else self.cookie_secure

    @property
    def oidc_enabled(self) -> bool:
        return bool(self.oidc_issuer and self.oidc_client_id)

    def production_problems(self) -> list[str]:
        """Settings that are fine on a laptop and unsafe in front of real records."""
        if not self.production:
            return []
        problems = []
        if self.secret_key == DEV_SECRET or len(self.secret_key) < 32:
            problems.append("HR_SECRET_KEY must be set to a random value of at least 32 characters.")
        if self.database_url.startswith("sqlite"):
            problems.append("HR_DATABASE_URL must point at Postgres, not SQLite.")
        if self.pinned_today is not None:
            problems.append("HR_TODAY pins the clock for the demo; leave it unset in production.")
        if not self.secure_cookies:
            problems.append("HR_COOKIE_SECURE must not be false in production (the site must be served over HTTPS).")
        if self.oidc_enabled and not (self.oidc_client_secret and self.oidc_redirect_uri):
            problems.append("OIDC needs HR_OIDC_CLIENT_SECRET and HR_OIDC_REDIRECT_URI as well.")
        if not self.password_login and not self.oidc_enabled:
            problems.append("With HR_PASSWORD_LOGIN=false, OIDC must be configured or nobody can sign in.")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
