import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from pathlib import Path

# Add src to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.tools.web-search.web_search_tool import WebSearchTool  # Adjust import based on actual implementation


@pytest.mark.asyncio
async def test_web_search_tool_basic():
    """Test basic web search functionality"""

    # Mock the search engine response
    mock_search_result = {
        "results": [
            {
                "title": "Sample Search Result",
                "url": "https://example.com",
                "snippet": "This is a sample search result snippet"
            }
        ],
        "query": "test query"
    }

    with patch('src.tools.web-search.web_search_tool.perform_search') as mock_search:
        mock_search.return_value = mock_search_result

        tool = WebSearchTool()

        # Execute the tool
        result = await tool._arun("test query")

        # Verify the result
        assert "sample search result" in result.lower()
        mock_search.assert_called_once_with("test query")


@pytest.mark.asyncio
async def test_web_search_tool_empty_query():
    """Test web search with empty query"""

    tool = WebSearchTool()

    with pytest.raises(ValueError):
        await tool._arun("")


@pytest.mark.asyncio
async def test_web_search_tool_error_handling():
    """Test web search tool error handling"""

    with patch('src.tools.web-search.web_search_tool.perform_search') as mock_search:
        mock_search.side_effect = Exception("Network error")

        tool = WebSearchTool()

        # Should handle the error gracefully
        result = await tool._arun("error test query")

        # Expect error message in result
        assert "error" in result.lower() or "failed" in result.lower()


def test_web_search_tool_name_and_description():
    """Test web search tool name and description"""

    tool = WebSearchTool()

    # Verify tool has required attributes
    assert hasattr(tool, "name")
    assert hasattr(tool, "description")
    assert isinstance(tool.name, str)
    assert isinstance(tool.description, str)
    assert len(tool.name) > 0
    assert len(tool.description) > 0


@pytest.mark.asyncio
async def test_web_search_tool_multiple_results():
    """Test web search tool with multiple results"""

    mock_search_result = {
        "results": [
            {"title": "Result 1", "url": "https://example1.com", "snippet": "First result"},
            {"title": "Result 2", "url": "https://example2.com", "snippet": "Second result"},
            {"title": "Result 3", "url": "https://example3.com", "snippet": "Third result"}
        ],
        "query": "multi-result query"
    }

    with patch('src.tools.web-search.web_search_tool.perform_search') as mock_search:
        mock_search.return_value = mock_search_result

        tool = WebSearchTool()
        result = await tool._arun("multi-result query")

        # Verify all results are included in output
        assert "result 1" in result.lower()
        assert "result 2" in result.lower()
        assert "result 3" in result.lower()
        mock_search.assert_called_once()


@pytest.mark.asyncio
async def test_web_search_tool_long_query():
    """Test web search with a long query string"""

    long_query = "This is a very long query string that tests the web search tool's ability to handle extensive search terms and return relevant results"

    mock_search_result = {
        "results": [{"title": "Long Query Result", "url": "https://example.com", "snippet": "Result for long query"}],
        "query": long_query
    }

    with patch('src.tools.web-search.web_search_tool.perform_search') as mock_search:
        mock_search.return_value = mock_search_result

        tool = WebSearchTool()
        result = await tool._arun(long_query)

        assert "long query" in result.lower()
        mock_search.assert_called_once_with(long_query)