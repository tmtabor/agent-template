"""Example tool demonstrating the full production tool pattern.

Copy this file and modify for your specific tool. Key principles:
- Simple interfaces: avoid optional parameters where possible
- English errors: error messages should tell the LLM how to recover
- Log inputs and outputs: essential for debugging agentic loops
- Use ModelRetry for errors the LLM can fix by changing its input
- Use ToolFailed for expected, terminal failures the LLM can't fix but can
  work around (not found, unsupported operation) — no retry budget is spent
- Use regular exceptions for unexpected failures (bugs): log and re-raise
"""

from __future__ import annotations

from pydantic_ai import ModelRetry, RunContext, ToolFailed

from agent.logging import get_logger

logger = get_logger(__name__)

# Type alias for deps — replace with your actual deps type when copying
type AnyDeps = object


def _search_backend(query: str, max_results: int) -> list[str]:
    """Placeholder for the real search implementation (API client, DB query, ...).

    Replace with real code. It may raise LookupError when the thing searched
    for doesn't exist, or ConnectionError when the service is unreachable.
    """
    return [f"Result {i} for '{query}'" for i in range(1, max_results + 1)]


async def search_tool(ctx: RunContext[AnyDeps], query: str, max_results: int = 5) -> str:
    """Search for information matching the query.

    This docstring is sent to the LLM as the tool description.
    Be specific about what this tool does and when to use it.

    Args:
        query: Search query string. Must be non-empty.
        max_results: Maximum number of results to return (1-20).

    Returns:
        Search results as a formatted string, one result per line.
        Returns "No results found" if nothing matches.

    Raises:
        ModelRetry: When input is invalid or the search service is temporarily unavailable.
        ToolFailed: When the searched-for resource doesn't exist (a terminal failure).
    """
    # --- Input validation ---
    if not query or not query.strip():
        raise ModelRetry(
            "The query parameter cannot be empty. Please provide a specific search query string."
        )

    if not 1 <= max_results <= 20:
        raise ModelRetry(
            f"max_results must be between 1 and 20, got {max_results}. "
            "Please use a value in that range."
        )

    # --- Log the tool call ---
    logger.debug("Tool call: search", extra={"query": query, "max_results": max_results})

    try:
        results = _search_backend(query, max_results)

        if not results:
            return "No results found for this query. Try broadening your search terms."

        # --- Hold large payloads at tool layer ---
        # If results could be large, summarize or paginate here rather than
        # returning raw data that might overflow the context window.
        output = "\n".join(results[:max_results])

        # --- Log the result ---
        logger.debug("Tool result: search", extra={"result_count": len(results), "query": query})

        return output

    except LookupError as e:
        # Expected and terminal: retrying the same call won't help, but the LLM
        # can adapt (try another source, or tell the user). ToolFailed shows it
        # the failure without spending the tool's retry budget; USAGE_LIMITS
        # still bounds how often the run can keep failing.
        logger.warning("Tool failed: search target not found", extra={"error": str(e)})
        raise ToolFailed(
            f"Nothing was found for '{query}': {e}. "
            "Try a different source, or tell the user this information is unavailable."
        ) from e
    except ConnectionError as e:
        # Recoverable: service temporarily unavailable, LLM can retry
        raise ModelRetry(
            f"Search service is temporarily unavailable: {e}. Please try again in a moment."
        ) from e
    except Exception as e:
        # Unexpected: log and re-raise. Reserve ModelRetry for errors the LLM
        # can plausibly fix by changing its input and ToolFailed for failures
        # you anticipated above — never as a catch-all, which would hide bugs.
        logger.error("Tool failed: search", extra={"error": str(e), "query": query})
        raise
