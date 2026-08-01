from dotenv import load_dotenv
from pydantic import Field, model_validator
from pydantic_ai.exceptions import UserError
from pydantic_ai.models import infer_model
from pydantic_settings import BaseSettings, SettingsConfigDict

# pydantic-settings' env_file support (below) only populates the Settings
# object, not os.environ — but pydantic-ai's provider classes (AnthropicProvider,
# OpenAIProvider, etc.) read their API key env vars directly via os.getenv(...),
# bypassing Settings entirely. Load .env into os.environ here too, so a key
# set only in .env is visible to those providers. override=False (the
# default) won't clobber real exported env vars.
load_dotenv()


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
        # Provider API keys (ANTHROPIC_API_KEY, GOOGLE_API_KEY, OLLAMA_BASE_URL,
        # …) live in .env unprefixed and undeclared here — the provider SDKs
        # read them directly via os.getenv(...). pydantic-settings' dotenv
        # source (unlike its env-var source) doesn't filter by env_prefix, so
        # without "ignore" any such key would trip extra="forbid" (the
        # BaseSettings default) before this class even finishes loading.
        extra="ignore",
    )

    # Model selection — model-agnostic, defaults to Claude Sonnet 5
    model: str = "anthropic:claude-sonnet-5"

    # Judge model for LLM-as-judge evals. Use a different model from the agent
    # to avoid self-assessment bias, but at least as capable — a weak judge
    # grading a strong agent introduces its own bias. Defaults to Opus 5,
    # a step up from the default agent model (Sonnet 5).
    judge_model: str = "anthropic:claude-opus-4-8"

    # Logfire — optional, falls back to console if not set. Unprefixed:
    # LOGFIRE_TOKEN is the standard name the Logfire SDK and CLI use.
    logfire_token: str | None = Field(default=None, validation_alias="LOGFIRE_TOKEN")

    # Logging
    log_level: str = "INFO"

    @model_validator(mode="after")
    def check_provider_key(self) -> "Settings":
        """Fail fast if the selected model's provider is misconfigured.

        Delegates to pydantic_ai's own provider construction instead of a
        hardcoded per-provider list — any provider pydantic_ai supports,
        including ones added in a future pydantic_ai release, is validated
        automatically with no changes needed here. pydantic_ai raises
        UserError naming the exact missing env var (ANTHROPIC_API_KEY,
        GOOGLE_API_KEY, OLLAMA_BASE_URL, …); we just fail fast with it.

        Only the agent model is validated here — the judge model is used
        only by evals, which require a real key at runtime anyway.
        """
        try:
            infer_model(self.model)
        except UserError as exc:
            raise ValueError(f"AGENT_MODEL={self.model!r} is misconfigured: {exc}") from exc
        return self


settings = Settings()
