from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Validated at startup: if the selected model's provider requires an API
    key and it is missing, Settings() raises immediately with a clear error
    instead of failing cryptically at the first API call.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Provider API keys — required only for the provider of the selected model
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Model selection — model-agnostic, defaults to Claude Opus 4.8
    model: str = "anthropic:claude-opus-4-8"

    # Judge model for LLM-as-judge evals. Use a different model from the agent
    # to avoid self-assessment bias, but at least as capable — a weak judge
    # grading a strong agent introduces its own bias.
    judge_model: str = "anthropic:claude-sonnet-5"

    # Logfire — optional, falls back to console if not set
    logfire_token: str | None = None

    # Logging
    log_level: str = "INFO"

    @model_validator(mode="after")
    def check_provider_key(self) -> "Settings":
        """Fail fast if the selected model's provider key is missing.

        Only the agent model is validated here — the judge model is used
        only by evals, which require a real key at runtime anyway.
        """
        provider = self.model.split(":", 1)[0]
        if provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError(
                "MODEL is an Anthropic model but ANTHROPIC_API_KEY is not set. "
                "Add it to .env or the environment."
            )
        if provider == "openai" and not self.openai_api_key:
            raise ValueError(
                "MODEL is an OpenAI model but OPENAI_API_KEY is not set. "
                "Add it to .env or the environment."
            )
        # "ollama" (and other local providers) run locally — no API key needed.
        return self


settings = Settings()
