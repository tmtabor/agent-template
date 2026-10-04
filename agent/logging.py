import logging

import logfire

from agent.config import settings


def configure_logging(include_content: bool | None = None) -> None:
    """Configure Logfire observability and stdlib logging routing.

    Call this once at application startup before creating any agents.

    If LOGFIRE_TOKEN is set, traces are sent to Logfire cloud.
    If not set, traces are printed to the console (development mode).

    Args:
        include_content: Whether spans record prompts, outputs and tool
            arguments. None (default) follows settings.log_content. Evals pass
            True because span-based evaluators need tool arguments.
    """
    if include_content is None:
        include_content = settings.log_content

    logfire_kwargs: dict = {
        "service_name": settings.service_name,
        "environment": settings.environment,
    }

    if settings.logfire_token:
        logfire_kwargs["token"] = settings.logfire_token
    else:
        # Console fallback for local development — no token required
        logfire_kwargs["send_to_logfire"] = False
        logfire_kwargs["console"] = logfire.ConsoleOptions(
            min_log_level="debug",
            include_timestamps=True,
        )

    logfire.configure(**logfire_kwargs)

    # Instrument Pydantic AI — automatically traces all agent runs,
    # tool calls, model requests, and validation retries
    # include_content=False keeps prompts, outputs and tool arguments out of
    # spans (see AGENT_LOG_CONTENT) — timing, token usage and structure remain.
    logfire.instrument_pydantic_ai(include_content=include_content)

    # Route stdlib logging through Logfire so third-party library logs
    # (httpx, anthropic SDK, etc.) appear in traces alongside agent spans
    logging.basicConfig(handlers=[logfire.LogfireLoggingHandler()])

    # Set root log level from config
    logging.getLogger().setLevel(settings.log_level.upper())


def get_logger(name: str) -> logging.Logger:
    """Get a stdlib logger that routes through Logfire.

    Usage: logger = get_logger(__name__)
    """
    return logging.getLogger(name)
