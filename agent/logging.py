import logging

import logfire

from agent.config import settings


def configure_logging() -> None:
    """Configure Logfire observability and stdlib logging routing.

    Call this once at application startup before creating any agents.

    If LOGFIRE_TOKEN is set, traces are sent to Logfire cloud.
    If not set, traces are printed to the console (development mode).
    """
    logfire_kwargs: dict = {}

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
    logfire.instrument_pydantic_ai()

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
