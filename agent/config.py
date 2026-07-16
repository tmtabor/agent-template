from pydantic import Field, model_validator
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
        # Agent-specific vars are prefixed (AGENT_MODEL, AGENT_LOG_LEVEL, …) so
        # a generic name like MODEL in the user's shell can't silently change
        # the provider. Fields with an explicit validation_alias are exempt.
        env_prefix="AGENT_",
    )

    # Provider API keys — required only for the provider of the selected model.
    # These keep their standard, unprefixed names: the provider SDKs read
    # these exact variables directly, so prefixing them would validate one
    # variable while the model client reads another.
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")

    # Model selection — model-agnostic, defaults to Claude Opus 4.8
    model: str = "anthropic:claude-opus-4-8"

    # Judge model for LLM-as-judge evals. Use a different model from the agent
    # to avoid self-assessment bias, but at least as capable — a weak judge
    # grading a strong agent introduces its own bias.
    judge_model: str = "anthropic:claude-sonnet-5"

    # Logfire — optional, falls back to console if not set. Unprefixed:
    # LOGFIRE_TOKEN is the standard name the Logfire SDK and CLI use.
    logfire_token: str | None = Field(default=None, validation_alias="LOGFIRE_TOKEN")

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
                "AGENT_MODEL is an Anthropic model but ANTHROPIC_API_KEY is not set. "
                "Add it to .env or the environment."
            )
        if provider == "openai" and not self.openai_api_key:
            raise ValueError(
                "AGENT_MODEL is an OpenAI model but OPENAI_API_KEY is not set. "
                "Add it to .env or the environment."
            )
        # "ollama" (and other local providers) run locally — no API key needed.
        return self


settings = Settings()
