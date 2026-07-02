"""Example tool demonstrating the full production tool pattern.

Copy this file and modify for your specific tool. Key principles:
- Simple interfaces: avoid optional parameters where possible
- English errors: error messages should tell the LLM how to recover
- Log inputs and outputs: essential for debugging agentic loops
- Use ModelRetry for LLM-recoverable errors
- Use regular exceptions for unrecoverable failures
"""

from __future__ import annotations

from pydantic_ai import ModelRetry, RunContext

from agent.logging import get_logger

logger = get_logger(__name__)

# Type alias for deps — replace with your actual deps type when copying
type AnyDeps = object


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
        # Replace with real implementation
        results = [f"Result {i} for '{query}'" for i in range(1, max_results + 1)]

        if not results:
            return "No results found for this query. Try broadening your search terms."

        # --- Hold large payloads at tool layer ---
        # If results could be large, summarize or paginate here rather than
        # returning raw data that might overflow the context window.
        output = "\n".join(results[:max_results])

        # --- Log the result ---
        logger.debug("Tool result: search", extra={"result_count": len(results), "query": query})

        return output

    except ConnectionError as e:
        # Recoverable: service temporarily unavailable, LLM can retry
        raise ModelRetry(
            f"Search service is temporarily unavailable: {e}. Please try again in a moment."
        ) from e
    except Exception as e:
        # Unrecoverable: log and re-raise. Reserve ModelRetry for errors the
        # LLM can plausibly fix by changing its input — asking it to retry an
        # unknown failure just burns the agent's retry budget.
        logger.error("Tool failed: search", extra={"error": str(e), "query": query})
        raise
