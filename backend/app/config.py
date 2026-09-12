"""Runtime settings.

`today` exists because the seeded term is a fixed fiction: Fall 2026, five weeks
elapsed. Pinning the clock keeps "missing work", trends and attendance rates
stable no matter when the app is run, and keeps the numbers consistent with the
registrar console in the repo root.
"""
from datetime import date
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HR_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./halverson.db"
    cors_origins: str = "http://localhost:5174,http://127.0.0.1:5174"
    today: date = date(2026, 9, 12)
    term: str = "Fall 2026"
    school_name: str = "Halverson Ridge Middle School"

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

    # Thresholds the support office can tune without touching the engine.
    support_threshold: float = 72.0   # below this, a course grade needs a plan
    concern_floor: float = 65.0       # below this, tutoring rather than monitoring
    excelling_threshold: float = 86.0 # at or above this, enrichment is on the table

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
