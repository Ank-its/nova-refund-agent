"""Application settings, loaded once from the environment."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Per-provider default model when ``llm_model`` is not set explicitly.
_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-latest",
    "google": "gemini-2.5-flash",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+asyncpg://nova_user:nova_pass_2024@postgres_db:5432/nova"
    )

    # --- LLM provider selection ---------------------------------------------
    # Pick the active provider and (optionally) pin a model. Each provider reads
    # its own API key. Leave llm_model empty to use the provider's default.
    llm_provider: str = "openai"          # openai | anthropic | google
    llm_model: str = ""                   # explicit model override (optional)

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""

    testing: bool = False

    # Signs stateless auth tokens. Override in production via env so sessions
    # survive restarts/redeploys and aren't forgeable. The default is dev-only.
    secret_key: str = "nova-dev-secret-change-me"

    # --- Refund rule matrix (deterministic, never LLM-overridable) ---
    return_window_days: int = 30
    high_value_threshold: float = 500.0
    velocity_limit: int = 3            # max approved refunds / rolling window
    velocity_window_days: int = 30

    @property
    def provider(self) -> str:
        return (self.llm_provider or "openai").strip().lower()

    @property
    def active_api_key(self) -> str:
        """The API key for the currently selected provider."""
        return {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "google": self.google_api_key,
        }.get(self.provider, "")

    @property
    def active_model(self) -> str:
        """Explicit ``llm_model`` if set, else the provider's default."""
        return self.llm_model.strip() or _DEFAULT_MODELS.get(self.provider, "")

    @property
    def llm_enabled(self) -> bool:
        """True when the selected provider has a usable key configured."""
        key = self.active_api_key
        return bool(key) and key not in ("", "dummy")


@lru_cache
def get_settings() -> Settings:
    return Settings()
