import logging
import os
from typing import Any, Dict, List, Optional
import httpx

from agent.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"
DEFAULT_TIMEOUT = 10.0


class WebSearchTool(Tool):
    """Tool that performs web searches using the Tavily API and normalizes top search results."""

    name = "web_search"
    description = (
        "Searches the web for up-to-date information on a given query using the Tavily API."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query string to execute.",
            }
        },
        "required": ["query"],
    }

    def execute(self, args: dict) -> ToolResult:
        """Executes a web search via Tavily API with the given query argument.

        Returns a ToolResult containing a normalized list of top 5 results on success,
        or ToolResult with success=False and a distinct error message on failure.
        Never allows exceptions to escape.
        """
        try:
            if not isinstance(args, dict):
                return ToolResult(
                    success=False,
                    error_message="Invalid input arguments: expected a dictionary.",
                )

            query = args.get("query")
            if not query or not isinstance(query, str) or not query.strip():
                return ToolResult(
                    success=False,
                    error_message="Invalid query argument: 'query' string is required.",
                )

            api_key = os.getenv("SEARCH_API_KEY")
            if not api_key or not api_key.strip():
                return ToolResult(
                    success=False,
                    error_message="Tavily API key is missing in SEARCH_API_KEY environment variable.",
                )

            payload = {
                "api_key": api_key.strip(),
                "query": query.strip(),
                "max_results": 5,
            }

            try:
                response = httpx.post(
                    TAVILY_API_URL,
                    json=payload,
                    timeout=DEFAULT_TIMEOUT,
                )
            except httpx.TimeoutException:
                logger.warning(f"Tavily API request timed out for query '{query}'")
                return ToolResult(
                    success=False,
                    error_message="Tavily API request timed out after 10 seconds.",
                )
            except httpx.RequestError as exc:
                logger.error(f"Network error calling Tavily API: {exc}")
                return ToolResult(
                    success=False,
                    error_message=f"Tavily API network request error: {str(exc)}",
                )

            if response.status_code in (401, 403):
                return ToolResult(
                    success=False,
                    error_message="Tavily API authentication failed: invalid or unauthorized API key.",
                )

            if response.status_code == 429:
                return ToolResult(
                    success=False,
                    error_message="Tavily API rate-limit error: request quota exceeded.",
                )

            if response.status_code != 200:
                return ToolResult(
                    success=False,
                    error_message=f"Tavily API error: HTTP status code {response.status_code}.",
                )

            try:
                data = response.json()
            except Exception as json_err:
                return ToolResult(
                    success=False,
                    error_message=f"Failed to parse Tavily API response JSON: {str(json_err)}",
                )

            raw_results = data.get("results")
            if not raw_results or not isinstance(raw_results, list) or len(raw_results) == 0:
                return ToolResult(
                    success=False,
                    error_message="Zero search results found for the query.",
                )

            normalized_results = []
            for item in raw_results[:5]:
                snippet = item.get("snippet") or item.get("content") or ""
                normalized_results.append({
                    "title": item.get("title", ""),
                    "snippet": snippet,
                    "url": item.get("url", ""),
                })

            return ToolResult(
                success=True,
                data=normalized_results,
                error_message=None,
            )

        except Exception as e:
            logger.error(f"Unexpected exception in WebSearchTool.execute: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error_message=f"Unexpected error in WebSearchTool: {str(e)}",
            )
