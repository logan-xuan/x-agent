"""Aliyun OpenSearch Web Search tool for X-Agent.

Provides comprehensive web search capability using Aliyun OpenSearch API.
Requires API key and workspace configuration.
"""

import json
import os
from typing import Any
import urllib.request
import ssl

from ..base import BaseTool, ToolResult, ToolParameter, ToolParameterType
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AliyunWebSearchTool(BaseTool):
    """Tool to search the web using Aliyun OpenSearch.
    
    Uses Aliyun OpenSearch Web Search API for comprehensive, high-quality results.
    This is the DEFAULT and PRIMARY web search tool for X-Agent.
    Requires API key and workspace configuration.
    
    Features:
    - Real-time web search with high-quality results
    - Query rewriting for better understanding
    - Support for conversation history
    - Token usage tracking
    - Optimized for Chinese and English queries
    
    CRITICAL: This tool REPLACES DuckDuckGo web_search as the primary search tool.
    The tool name is now "web_search" to maintain backward compatibility while
    providing superior Aliyun-powered results.
    """
    
    @property
    def name(self) -> str:
        return "web_search"
    
    @property
    def description(self) -> str:
        return (
            "DEFAULT WEB SEARCH TOOL - Powered by Aliyun OpenSearch. "
            "Use this tool for ANY query requiring CURRENT, REAL-TIME, or UP-TO-DATE information including: "
            "weather forecasts, news, stock prices, sports scores, recent events, trending topics, "
            "or any time-sensitive questions. Also use for general knowledge research in Chinese or English. "
            "If the user asks about 'today', 'current', 'latest', 'recent', or anything that changes over time, "
            "YOU MUST call this tool. Do NOT rely on your training data for time-sensitive information. "
            "Provides high-quality, authoritative results for both Chinese and English queries. "
            "This tool has replaced DuckDuckGo as the primary web search tool."
        )
    
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
            ToolParameter(
                name="content_type",
                type=ToolParameterType.STRING,
                description="Return content type: 'snippet' for summary or 'full' for complete content.",
                required=False,
                default="snippet",
            ),
        ]
    
    async def execute(
        self, 
        query: str, 
        max_results: int = 5,
        content_type: str = "snippet"
    ) -> ToolResult:
        """Execute the web search.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            content_type: Content type ('snippet' or 'full')
            
        Returns:
            ToolResult with search results
        """
        try:
            # Get configuration from x-agent.yaml
            from ...config.manager import get_config
            config = get_config()
            
            # Access aliyun_opensearch config directly (Pydantic model)
            aliyun_config = config.aliyun_opensearch
            api_key = aliyun_config.api_key
            host = aliyun_config.host
            workspace = aliyun_config.workspace
            enabled = aliyun_config.enabled
            
            if not enabled:
                logger.info("Aliyun OpenSearch is disabled in configuration")
                return ToolResult.error_result(
                    "Aliyun OpenSearch is disabled. Enable it in x-agent.yaml to use."
                )
            
            if not api_key or not host:
                logger.warning(
                    "Aliyun OpenSearch credentials not configured in x-agent.yaml. "
                    "Please configure aliyun_opensearch section."
                )
                return ToolResult.error_result(
                    "Aliyun OpenSearch not configured. Please add configuration to x-agent.yaml:\n"
                    "aliyun_opensearch:\n"
                    "  api_key: OS-your_api_key\n"
                    "  host: http://your-host-url\n"
                    "  workspace: default"
                )
            
            # Perform search
            results = await self._search_aliyun(
                query=query,
                max_results=max_results,
                content_type=content_type,
                api_key=api_key,
                host=host,
                workspace=workspace
            )
            
            if not results:
                return ToolResult.ok(
                    f"No results found for: {query}\n\nTry a different search query.",
                    query=query,
                )
            
            # Format results
            formatted = f"🔍 Aliyun Search results for: {query}\n\n"
            for i, result in enumerate(results[:max_results], 1):
                formatted += f"{i}. **{result.get('title', 'No title')}**\n"
                formatted += f"   {result.get('snippet', '')}\n"
                formatted += f"   🔗 {result.get('url', '')}\n\n"
            
            # Add usage info if available
            metadata = {"query": query, "results_count": len(results)}
            if self.last_usage_info:
                formatted += f"\n💡 Token Usage: {self.last_usage_info.get('total_tokens', 'N/A')} tokens\n"
                metadata["usage"] = self.last_usage_info
            
            logger.info(
                "Aliyun web search completed",
                extra={
                    "query": query,
                    "results_count": len(results),
                    "workspace": workspace,
                }
            )
            
            return ToolResult.ok(
                formatted,
                query=query,
                results_count=len(results),
                usage=self.last_usage_info,
            )
            
        except Exception as e:
            logger.error(
                "Aliyun web search failed",
                extra={"query": query, "error": str(e)},
                exc_info=True
            )
            return ToolResult.error_result(f"Aliyun web search failed: {str(e)}")
    
    def __init__(self):
        """Initialize the tool."""
        super().__init__()
        self.last_usage_info = None
    
    async def _search_aliyun(
        self,
        query: str,
        max_results: int,
        content_type: str,
        api_key: str,
        host: str,
        workspace: str
    ) -> list[dict]:
        """Search using Aliyun OpenSearch API.
        
        Args:
            query: Search query
            max_results: Maximum results to return
            content_type: Content type ('snippet' or 'full')
            api_key: API key for authentication
            host: Service host URL
            workspace: Workspace name
            
        Returns:
            List of search result dicts
        """
        results = []
        self.last_usage_info = None
        
        try:
            # Build URL
            service_id = "ops-web-search-001"
            url = f"{host}/v3/openapi/workspaces/{workspace}/web-search/{service_id}"
            
            # Prepare request body
            payload = {
                "query": query,
                "query_rewrite": True,
                "top_k": max_results,
                "content_type": content_type,
            }
            
            # Prepare headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            
            # Create request
            data = json.dumps(payload).encode('utf-8')
            request = urllib.request.Request(
                url,
                data=data,
                headers=headers,
                method='POST'
            )
            
            logger.debug(
                "Calling Aliyun OpenSearch API",
                extra={
                    "url": url,
                    "query": query,
                    "max_results": max_results,
                }
            )
            
            # Make request with SSL verification disabled for development
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            with urllib.request.urlopen(
                request,
                timeout=30,
                context=ssl_context
            ) as response:
                response_data = json.loads(response.read().decode())
            
            # Extract search results
            if "result" in response_data and "search_result" in response_data["result"]:
                search_results = response_data["result"]["search_result"]
                
                for item in search_results:
                    results.append({
                        'title': item.get('title', 'No title'),
                        'snippet': item.get('snippet', ''),
                        'url': item.get('link', ''),
                        'content': item.get('content', ''),
                        'position': item.get('position', 0),
                    })
                
                # Store usage info
                if "usage" in response_data:
                    usage = response_data["usage"]
                    total_tokens = (
                        usage.get('rewrite_model.total_tokens', 0) +
                        usage.get('filter_model.total_tokens', 0)
                    )
                    self.last_usage_info = {
                        'search_count': usage.get('search_count', 0),
                        'rewrite_tokens': usage.get('rewrite_model.total_tokens', 0),
                        'filter_tokens': usage.get('filter_model.total_tokens', 0),
                        'total_tokens': total_tokens,
                    }
                    
                    logger.debug(
                        "Token usage tracked",
                        extra=self.last_usage_info
                    )
            
            # If no results, provide helpful message
            if not results:
                results.append({
                    'title': 'No Results Found',
                    'snippet': f'Aliyun OpenSearch did not return results for "{query}". Try a different query or check your API configuration.',
                    'url': '',
                })
            
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if hasattr(e, 'read') else str(e)
            logger.error(
                f"HTTP Error {e.code}: {e.reason}",
                extra={
                    "error_body": error_body,
                    "query": query,
                },
                exc_info=True
            )
            results.append({
                'title': 'API Error',
                'snippet': f'HTTP {e.code}: {e.reason}. Check your API key and configuration.',
                'url': '',
            })
            
        except urllib.error.URLError as e:
            logger.error(
                f"URL Error: {e.reason}",
                extra={"query": query},
                exc_info=True
            )
            results.append({
                'title': 'Connection Error',
                'snippet': f'Failed to connect to Aliyun API: {e.reason}',
                'url': '',
            })
            
        except Exception as e:
            logger.error(
                f"Unexpected error: {str(e)}",
                extra={"query": query},
                exc_info=True
            )
            results.append({
                'title': 'Search Error',
                'snippet': f'Unexpected error: {str(e)}',
                'url': '',
            })
        
        return results
