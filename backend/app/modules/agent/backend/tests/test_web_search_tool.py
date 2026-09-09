import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import httpx
import pytest

# Ensure backend directory is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from agent.tools.base import ToolResult
from agent.tools.web_search_tool import WebSearchTool

# ==============================================================================
# MANUAL TEST NOTE:
# To manually test against the real Tavily API with a broken/missing API key:
# 1. Set SEARCH_API_KEY="invalid_key_12345" in environment or backend/.env
# 2. Execute Python command:
#    python -c "from agent.tools.web_search_tool import WebSearchTool; print(WebSearchTool().execute({'query': 'test'}))"
# 3. Confirm that it returns ToolResult(success=False, error_message='Tavily API authentication failed: invalid or unauthorized API key.')
#    without letting an exception escape.
# ==============================================================================


@pytest.fixture
def web_search_tool():
    return WebSearchTool()


@patch("agent.tools.web_search_tool.httpx.post")
def test_web_search_success(mock_post, web_search_tool, monkeypatch):
    """Test a successful Tavily API search returns a normalized list of top results."""
    monkeypatch.setenv("SEARCH_API_KEY", "mock-test-key")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "title": "Result 1",
                "url": "https://example.com/1",
                "content": "Snippet for result 1",
            },
            {
                "title": "Result 2",
                "url": "https://example.com/2",
                "snippet": "Snippet for result 2",
            },
            {
                "title": "Result 3",
                "url": "https://example.com/3",
                "content": "Snippet for result 3",
            },
            {
                "title": "Result 4",
                "url": "https://example.com/4",
                "content": "Snippet for result 4",
            },
            {
                "title": "Result 5",
                "url": "https://example.com/5",
                "content": "Snippet for result 5",
            },
            {
                "title": "Result 6",
                "url": "https://example.com/6",
                "content": "Snippet for result 6 (should be capped)",
            },
        ]
    }
    mock_post.return_value = mock_response

    result = web_search_tool.execute({"query": "python AI framework"})

    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.error_message is None
    assert isinstance(result.data, list)
    # Must cap results at top 5
    assert len(result.data) == 5

    first_item = result.data[0]
    assert first_item == {
        "title": "Result 1",
        "snippet": "Snippet for result 1",
        "url": "https://example.com/1",
    }


@patch("agent.tools.web_search_tool.httpx.post")
def test_web_search_zero_results(mock_post, web_search_tool, monkeypatch):
    """Test zero results returned by Tavily API produces a graceful, distinct ToolResult."""
    monkeypatch.setenv("SEARCH_API_KEY", "mock-test-key")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"results": []}
    mock_post.return_value = mock_response

    result = web_search_tool.execute({"query": "nonexistent_query_xyz_9999"})

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert result.data is None
    assert result.error_message == "Zero search results found for the query."


@patch("agent.tools.web_search_tool.httpx.post")
def test_web_search_timeout(mock_post, web_search_tool, monkeypatch):
    """Test API request timeout is caught and returns a graceful ToolResult."""
    monkeypatch.setenv("SEARCH_API_KEY", "mock-test-key")
    mock_post.side_effect = httpx.TimeoutException("Connection timed out")

    result = web_search_tool.execute({"query": "slow search query"})

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert result.data is None
    assert "timed out" in result.error_message.lower()


@patch("agent.tools.web_search_tool.httpx.post")
def test_web_search_auth_error(mock_post, web_search_tool, monkeypatch):
    """Test API HTTP 401 authentication error returns a graceful, distinct ToolResult."""
    monkeypatch.setenv("SEARCH_API_KEY", "bad-or-expired-key")

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {
        "detail": {"error": "Unauthorized: missing or invalid API key."}
    }
    mock_post.return_value = mock_response

    result = web_search_tool.execute({"query": "python"})

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert result.data is None
    assert "authentication failed" in result.error_message.lower()


@patch("agent.tools.web_search_tool.httpx.post")
def test_web_search_rate_limit_error(mock_post, web_search_tool, monkeypatch):
    """Test API HTTP 429 rate limit error returns a graceful, distinct ToolResult."""
    monkeypatch.setenv("SEARCH_API_KEY", "mock-key")

    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.json.return_value = {"detail": "Rate limit exceeded"}
    mock_post.return_value = mock_response

    result = web_search_tool.execute({"query": "python"})

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert result.data is None
    assert "rate-limit" in result.error_message.lower()


def test_web_search_missing_api_key(web_search_tool, monkeypatch):
    """Test missing SEARCH_API_KEY environment variable returns graceful ToolResult."""
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)

    result = web_search_tool.execute({"query": "python"})

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert result.data is None
    assert "missing" in result.error_message.lower()
