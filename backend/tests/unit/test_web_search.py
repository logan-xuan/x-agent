"""Unit tests for WebSearchTool.

Tests cover:
- Tool initialization and configuration
- Parameter validation
- DuckDuckGo API integration (mocked)
- Result formatting
- Error handling
- Edge cases
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import json

from src.tools.builtin.web_search import WebSearchTool
from src.tools.base import ToolParameterType, ToolResult


class TestWebSearchToolInitialization:
    """Tests for WebSearchTool initialization."""

    @pytest.fixture
    def web_search_tool(self) -> WebSearchTool:
        """Create WebSearchTool instance."""
        return WebSearchTool()

    def test_tool_name(self, web_search_tool: WebSearchTool) -> None:
        """Test tool name is correct."""
        assert web_search_tool.name == "web_search"

    def test_tool_description(self, web_search_tool: WebSearchTool) -> None:
        """Test tool description is present and reasonable."""
        assert web_search_tool.description is not None
        assert len(web_search_tool.description) > 50
        assert "search" in web_search_tool.description.lower()
        assert "duckduckgo" in web_search_tool.description.lower()

    def test_parameters_structure(self, web_search_tool: WebSearchTool) -> None:
        """Test parameters are correctly defined."""
        params = web_search_tool.parameters
        
        assert isinstance(params, list)
        assert len(params) == 2
        
        # Check query parameter
        query_param = params[0]
        assert query_param.name == "query"
        assert query_param.type == ToolParameterType.STRING
        assert query_param.required is True
        assert "query" in query_param.description.lower()
        
        # Check max_results parameter
        max_results_param = params[1]
        assert max_results_param.name == "max_results"
        assert max_results_param.type == ToolParameterType.INTEGER
        assert max_results_param.required is False
        assert max_results_param.default == 5

    def test_openai_tool_format(self, web_search_tool: WebSearchTool) -> None:
        """Test OpenAI tool format conversion."""
        openai_tool = web_search_tool.to_openai_tool()
        
        assert isinstance(openai_tool, dict)
        assert "type" in openai_tool
        assert openai_tool["type"] == "function"
        
        assert "function" in openai_tool
        function = openai_tool["function"]
        
        assert "name" in function
        assert function["name"] == "web_search"
        
        assert "description" in function
        assert "parameters" in function
        
        # Check parameters structure
        params = function["parameters"]
        assert "type" in params
        assert "properties" in params
        assert "required" in params


class TestWebSearchToolValidation:
    """Tests for parameter validation."""

    @pytest.fixture
    def web_search_tool(self) -> WebSearchTool:
        """Create WebSearchTool instance."""
        return WebSearchTool()

    def test_valid_params_minimal(self, web_search_tool: WebSearchTool) -> None:
        """Test validation with minimal valid params."""
        params = {"query": "test search"}
        is_valid, error = web_search_tool.validate_params(params)
        assert is_valid is True
        assert error is None

    def test_valid_params_complete(self, web_search_tool: WebSearchTool) -> None:
        """Test validation with complete valid params."""
        params = {"query": "test search", "max_results": 10}
        is_valid, error = web_search_tool.validate_params(params)
        assert is_valid is True
        assert error is None

    def test_invalid_missing_query(self, web_search_tool: WebSearchTool) -> None:
        """Test validation fails when query is missing."""
        params = {}
        is_valid, error = web_search_tool.validate_params(params)
        assert is_valid is False
        assert error is not None
        assert "query" in error.lower()

    def test_invalid_query_type(self, web_search_tool: WebSearchTool) -> None:
        """Test validation fails when query has wrong type."""
        params = {"query": 123}  # Should be string
        is_valid, error = web_search_tool.validate_params(params)
        assert is_valid is False
        assert error is not None

    def test_invalid_max_results_type(self, web_search_tool: WebSearchTool) -> None:
        """Test validation fails when max_results has wrong type."""
        params = {"query": "test", "max_results": "five"}  # Should be int
        is_valid, error = web_search_tool.validate_params(params)
        assert is_valid is False
        assert error is not None


class TestWebSearchToolExecution:
    """Tests for tool execution with mocked API."""

    @pytest.fixture
    def web_search_tool(self) -> WebSearchTool:
        """Create WebSearchTool instance."""
        return WebSearchTool()

    @pytest.mark.asyncio
    async def test_execute_success(self, web_search_tool: WebSearchTool) -> None:
        """Test successful execution with mocked results."""
        # Mock the _search_duckduckgo method
        mock_results = [
            {
                'title': 'Test Result 1',
                'snippet': 'This is the first test result',
                'url': 'https://example.com/1',
            },
            {
                'title': 'Test Result 2',
                'snippet': 'This is the second test result',
                'url': 'https://example.com/2',
            },
        ]
        
        with patch.object(
            web_search_tool, '_search_duckduckgo', new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = mock_results
            
            result = await web_search_tool.execute(
                query="test query",
                max_results=5
            )
            
            # Verify result structure
            assert isinstance(result, ToolResult)
            assert result.success is True
            assert result.error is None
            
            # Verify output format
            assert result.output is not None
            assert "Search results for: test query" in result.output
            assert "Test Result 1" in result.output
            assert "Test Result 2" in result.output
            assert "https://example.com/1" in result.output
            assert "https://example.com/2" in result.output
            
            # Verify metadata
            assert result.metadata is not None
            assert result.metadata.get("query") == "test query"
            assert result.metadata.get("results_count") == 2

    @pytest.mark.asyncio
    async def test_execute_no_results(self, web_search_tool: WebSearchTool) -> None:
        """Test execution when no results are found."""
        with patch.object(
            web_search_tool, '_search_duckduckgo', new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = []
            
            result = await web_search_tool.execute(
                query="empty query",
                max_results=5
            )
            
            assert result.success is True
            assert "No results found" in result.output
            assert "Try a different search query" in result.output

    @pytest.mark.asyncio
    async def test_execute_with_error(self, web_search_tool: WebSearchTool) -> None:
        """Test execution with API error."""
        with patch.object(
            web_search_tool, '_search_duckduckgo', new_callable=AsyncMock
        ) as mock_search:
            mock_search.side_effect = Exception("API connection failed")
            
            result = await web_search_tool.execute(
                query="error query",
                max_results=5
            )
            
            assert result.success is False
            assert result.error is not None
            assert "Web search failed" in result.error

    @pytest.mark.asyncio
    async def test_execute_default_max_results(self, web_search_tool: WebSearchTool) -> None:
        """Test execution uses default max_results."""
        with patch.object(
            web_search_tool, '_search_duckduckgo', new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = []
            
            await web_search_tool.execute(query="test")
            
            # Verify _search_duckduckgo was called with default max_results=5
            mock_search.assert_called_once_with("test", 5)


class TestDuckDuckGoSearch:
    """Tests for DuckDuckGo API interaction."""

    @pytest.fixture
    def web_search_tool(self) -> WebSearchTool:
        """Create WebSearchTool instance."""
        return WebSearchTool()

    @pytest.mark.asyncio
    async def test_search_duckduckgo_related_topics(
        self, web_search_tool: WebSearchTool
    ) -> None:
        """Test parsing RelatedTopics from API response."""
        mock_response_data = {
            "RelatedTopics": [
                {
                    "Text": "Python is a programming language",
                    "FirstURL": "https://example.com/python",
                },
                {
                    "Text": "Programming languages overview",
                    "FirstURL": "https://example.com/programming",
                },
            ]
        }
        
        with patch('src.tools.builtin.web_search.urllib.request') as mock_urllib:
            # Mock the URL request and response
            mock_request = MagicMock()
            mock_urllib.Request.return_value = mock_request
            
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps(mock_response_data).encode()
            mock_response.__enter__ = lambda s: mock_response
            mock_response.__exit__ = MagicMock()
            
            mock_urllib.urlopen.return_value = mock_response
            
            results = await web_search_tool._search_duckduckgo(
                query="python programming",
                max_results=5
            )
            
            assert len(results) == 2
            assert results[0]['snippet'] == "Python is a programming language"
            assert results[0]['url'] == "https://example.com/python"

    @pytest.mark.asyncio
    async def test_search_duckduckgo_abstract(
        self, web_search_tool: WebSearchTool
    ) -> None:
        """Test parsing Abstract from API response when no RelatedTopics."""
        mock_response_data = {
            "Abstract": "Python is a high-level programming language",
            "Heading": "Python (programming language)",
            "AbstractURL": "https://en.wikipedia.org/wiki/Python",
            "RelatedTopics": [],
        }
        
        with patch('src.tools.builtin.web_search.urllib.request') as mock_urllib:
            mock_request = MagicMock()
            mock_urllib.Request.return_value = mock_request
            
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps(mock_response_data).encode()
            mock_response.__enter__ = lambda s: mock_response
            mock_response.__exit__ = MagicMock()
            
            mock_urllib.urlopen.return_value = mock_response
            
            results = await web_search_tool._search_duckduckgo(
                query="python",
                max_results=5
            )
            
            assert len(results) == 1
            assert results[0]['title'] == "Python (programming language)"
            assert results[0]['snippet'] == "Python is a high-level programming language"
            assert results[0]['url'] == "https://en.wikipedia.org/wiki/Python"

    @pytest.mark.asyncio
    async def test_search_duckduckgo_fallback(
        self, web_search_tool: WebSearchTool
    ) -> None:
        """Test fallback when API returns no useful data."""
        mock_response_data = {
            "RelatedTopics": [],
            "Abstract": "",
        }
        
        with patch('src.tools.builtin.web_search.urllib.request') as mock_urllib:
            mock_request = MagicMock()
            mock_urllib.Request.return_value = mock_request
            
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps(mock_response_data).encode()
            mock_response.__enter__ = lambda s: mock_response
            mock_response.__exit__ = MagicMock()
            
            mock_urllib.urlopen.return_value = mock_response
            
            results = await web_search_tool._search_duckduckgo(
                query="obscure query xyz123",
                max_results=5
            )
            
            assert len(results) == 1
            assert results[0]['title'] == 'Limited Results'
            assert 'did not return instant answers' in results[0]['snippet']
            assert 'duckduckgo.com' in results[0]['url']

    @pytest.mark.asyncio
    async def test_search_duckduckgo_timeout(
        self, web_search_tool: WebSearchTool
    ) -> None:
        """Test handling of timeout errors."""
        with patch('src.tools.builtin.web_search.urllib.request') as mock_urllib:
            mock_urllib.urlopen.side_effect = Exception("timed out")
            
            results = await web_search_tool._search_duckduckgo(
                query="timeout test",
                max_results=5
            )
            
            assert len(results) == 1
            assert results[0]['title'] == 'Search Error'
            assert 'Could not complete search' in results[0]['snippet']


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    @pytest.fixture
    def web_search_tool(self) -> WebSearchTool:
        """Create WebSearchTool instance."""
        return WebSearchTool()

    @pytest.mark.asyncio
    async def test_special_characters_in_query(
        self, web_search_tool: WebSearchTool
    ) -> None:
        """Test handling of special characters in query."""
        with patch.object(
            web_search_tool, '_search_duckduckgo', new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = []
            
            # Should not raise exception
            result = await web_search_tool.execute(
                query="test & query <with> special \"chars\"",
                max_results=5
            )
            
            assert result.success is True
            mock_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_query_string(
        self, web_search_tool: WebSearchTool
    ) -> None:
        """Test handling of empty query string."""
        with patch.object(
            web_search_tool, '_search_duckduckgo', new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = []
            
            result = await web_search_tool.execute(
                query="",
                max_results=5
            )
            
            # Should handle gracefully
            assert result.success is True

    @pytest.mark.asyncio
    async def test_very_long_query(self, web_search_tool: WebSearchTool) -> None:
        """Test handling of very long query string."""
        long_query = "test " * 100  # 500 character query
        
        with patch.object(
            web_search_tool, '_search_duckduckgo', new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = []
            
            result = await web_search_tool.execute(
                query=long_query,
                max_results=5
            )
            
            # Should handle without crashing
            assert result.success is True

    @pytest.mark.asyncio
    async def test_zero_max_results(self, web_search_tool: WebSearchTool) -> None:
        """Test handling of zero max_results."""
        mock_results = [
            {'title': 'Result', 'snippet': 'Snippet', 'url': 'https://example.com'},
        ]
        
        with patch.object(
            web_search_tool, '_search_duckduckgo', new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = mock_results
            
            result = await web_search_tool.execute(
                query="test",
                max_results=0
            )
            
            assert result.success is True
            # Should return empty or limited results
            assert "Result" not in result.output

    @pytest.mark.asyncio
    async def test_large_max_results(self, web_search_tool: WebSearchTool) -> None:
        """Test handling of large max_results value."""
        mock_results = [{'title': f'Result {i}', 'snippet': 'Snippet', 'url': f'https://example.com/{i}'} 
                       for i in range(100)]
        
        with patch.object(
            web_search_tool, '_search_duckduckgo', new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = mock_results
            
            result = await web_search_tool.execute(
                query="test",
                max_results=1000
            )
            
            assert result.success is True
            # Should handle large numbers gracefully


class TestIntegration:
    """Integration tests simulating real usage scenarios."""

    @pytest.fixture
    def web_search_tool(self) -> WebSearchTool:
        """Create WebSearchTool instance."""
        return WebSearchTool()

    @pytest.mark.asyncio
    async def test_realistic_search_python(
        self, web_search_tool: WebSearchTool
    ) -> None:
        """Test realistic search for Python-related query."""
        mock_results = [
            {
                'title': 'Python (programming language) - Wikipedia',
                'snippet': 'Python is a high-level, general-purpose programming language...',
                'url': 'https://en.wikipedia.org/wiki/Python_(programming_language)',
            },
            {
                'title': 'Python.org - Official Documentation',
                'snippet': 'Welcome to Python.org. Download the latest version...',
                'url': 'https://www.python.org/',
            },
        ]
        
        with patch.object(
            web_search_tool, '_search_duckduckgo', new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = mock_results
            
            result = await web_search_tool.execute(
                query="Python programming language features",
                max_results=5
            )
            
            assert result.success is True
            assert result.output is not None
            assert len(result.output) > 100
            assert "Wikipedia" in result.output or "Python.org" in result.output

    @pytest.mark.asyncio
    async def test_result_formatting_consistency(
        self, web_search_tool: WebSearchTool
    ) -> None:
        """Test that result formatting is consistent."""
        mock_results = [
            {'title': 'Title 1', 'snippet': 'Snippet 1', 'url': 'https://url1.com'},
            {'title': 'Title 2', 'snippet': 'Snippet 2', 'url': 'https://url2.com'},
            {'title': 'Title 3', 'snippet': 'Snippet 3', 'url': 'https://url3.com'},
        ]
        
        with patch.object(
            web_search_tool, '_search_duckduckgo', new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = mock_results
            
            result1 = await web_search_tool.execute(query="test", max_results=3)
            result2 = await web_search_tool.execute(query="test", max_results=3)
            
            # Results should be formatted consistently
            assert result1.output == result2.output
