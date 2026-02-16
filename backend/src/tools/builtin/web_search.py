"""Web search tool for X-Agent.

Provides web search capability using DuckDuckGo Instant Answer API.
No API key required.
"""

import json
import urllib.parse
import urllib.request
from typing import Any

from ..base import BaseTool, ToolResult, ToolParameter, ToolParameterType
from ...utils.logger import get_logger

logger = get_logger(__name__)


class WebSearchTool(BaseTool):
    """Tool to search the web.
    
    Uses DuckDuckGo Instant Answer API for web search.
    No API key required, but results may be limited.
    """
    
    @property
    def name(self) -> str:
        return "web_search"
    
    @property
    def description(self) -> str:
        return "Search the web for information. Returns search results from DuckDuckGo. Use this when you need to find current information or research a topic."
    
    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type=ToolParameterType.STRING,
                description="The search query. Be specific for better results.",
                required=True,
            ),
            ToolParameter(
                name="max_results",
                type=ToolParameterType.INTEGER,
                description="Maximum number of results to return. Default is 5.",
                required=False,
                default=5,
            ),
        ]
    
    async def execute(self, query: str, max_results: int = 5) -> ToolResult:
        """Execute the web search.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            ToolResult with search results
        """
        try:
            # Use DuckDuckGo Instant Answer API
            results = await self._search_duckduckgo(query, max_results)
            
            if not results:
                return ToolResult.ok(
                    f"No results found for: {query}\n\nTry a different search query.",
                    query=query,
                )
            
            # Format results
            formatted = f"Search results for: {query}\n\n"
            for i, result in enumerate(results[:max_results], 1):
                formatted += f"{i}. **{result.get('title', 'No title')}**\n"
                formatted += f"   {result.get('snippet', '')}\n"
                formatted += f"   URL: {result.get('url', '')}\n\n"
            
            logger.info(
                "Web search completed",
                extra={
                    "query": query,
                    "results_count": len(results),
                }
            )
            
            return ToolResult.ok(
                formatted,
                query=query,
                results_count=len(results),
            )
            
        except Exception as e:
            logger.error(
                "Web search failed",
                extra={"query": query, "error": str(e)}
            )
            return ToolResult.error_result(f"Web search failed: {str(e)}")
    
    async def _search_duckduckgo(self, query: str, max_results: int) -> list[dict]:
        """Search using DuckDuckGo Instant Answer API.
        
        Note: DuckDuckGo's instant answer API has limited results.
        For more comprehensive search, consider integrating with
        other search APIs (Google, Bing, etc.).
        
        Args:
            query: Search query
            max_results: Maximum results to return
            
        Returns:
            List of search result dicts
        """
        results = []
        
        try:
            # DuckDuckGo Instant Answer API
            url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1"
            
            request = urllib.request.Request(
                url,
                headers={'User-Agent': 'X-Agent/1.0'}
            )
            
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode())
            
            # Extract related topics
            if data.get('RelatedTopics'):
                for topic in data['RelatedTopics'][:max_results]:
                    if isinstance(topic, dict) and 'Text' in topic:
                        results.append({
                            'title': topic.get('FirstURL', '').split('/')[-1].replace('_', ' '),
                            'snippet': topic.get('Text', ''),
                            'url': topic.get('FirstURL', ''),
                        })
            
            # If no related topics, try abstract
            if not results and data.get('Abstract'):
                results.append({
                    'title': data.get('Heading', query),
                    'snippet': data.get('Abstract', ''),
                    'url': data.get('AbstractURL', ''),
                })
            
            # If still no results, provide helpful message
            if not results:
                results.append({
                    'title': 'Limited Results',
                    'snippet': f'DuckDuckGo did not return instant answers for "{query}". Try a more specific query or use a web browser for comprehensive search.',
                    'url': f'https://duckduckgo.com/?q={urllib.parse.quote(query)}',
                })
            
        except Exception as e:
            logger.warning(
                "DuckDuckGo API error",
                extra={"error": str(e)}
            )
            # Return a fallback result
            results.append({
                'title': 'Search Error',
                'snippet': f'Could not complete search. Error: {str(e)}',
                'url': '',
            })
        
        return results
